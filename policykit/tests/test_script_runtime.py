import datetime
import os
import threading
import types

from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

import tests.utils as TestUtils
from policyengine import script_runtime
from policyengine.models import CommunityRole, GeneratedPolicy, PolicyStoreEntry, ScheduledCallback
from policyengine.script_runtime import PlatformAdapter, PolicyScriptError
from policyengine.tasks import fire_due_scheduled_callbacks

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "example_policy.py")


def read_fixture():
    with open(FIXTURE_PATH) as f:
        return f.read()


class FakePlatformAdapter(PlatformAdapter):
    """
    Stand-in for SlackPlatformAdapter. Only the four world-facing methods are
    faked -- store/on/schedule come from PolicyRuntimeContext unchanged, which
    is the point of keeping the adapter separate.
    """

    def __init__(self, channels=None, users=None, reactions=None):
        self.channels = channels or [("C_SOCIAL", "social"), ("C_ANN", "announcements")]
        self.users = users or {}
        self.reactions = reactions if reactions is not None else []
        self.posted = []

    def get_channels(self):
        return [types.SimpleNamespace(id=cid, name=name) for cid, name in self.channels]

    def get_user(self, user_id):
        return self.users.get(user_id)

    def get_message_reactions(self, channel_id, timestamp):
        # The fixture fabricates its own voting-message timestamp rather than
        # using post_message's return, so answer for whatever ts it asks about.
        return list(self.reactions)

    def post_message(self, target_id, text):
        ts = f"ts-{len(self.posted) + 1}"
        self.posted.append({"target": target_id, "text": text, "ts": ts})
        return ts

    def posts_to(self, target_id):
        return [p for p in self.posted if p["target"] == target_id]


class ScriptRuntimeTestCase(TestCase):
    def setUp(self):
        self.slack_community, self.user = TestUtils.create_slack_community_and_user(username="U_PROPOSER")
        self.community = self.slack_community.community
        self.policy = GeneratedPolicy.objects.create(
            kind="platform",
            name="channel proposal vote",
            community=self.community,
            script_code=read_fixture(),
        )
        self.platform = FakePlatformAdapter(
            users={"U_PROPOSER": types.SimpleNamespace(id="U_PROPOSER", roles=["member"])}
        )

    def proposal_event(self, text=None, channel_id="C_SOCIAL", actor_id="U_PROPOSER"):
        return types.SimpleNamespace(
            type="message_posted",
            actor_id=actor_id,
            timestamp="1700000000.0001",
            data={
                "channel_id": channel_id,
                "text": text or "channel name: design\ndescription: a place for design chat",
                "timestamp": "1700000000.0001",
            },
        )

    def install(self):
        return script_runtime.install_script_policy(self.policy, platform=self.platform)

    def store(self):
        return script_runtime.PolicyStore(self.policy)


class InstallTests(ScriptRuntimeTestCase):
    def test_setup_runs_once_and_registers_handlers(self):
        registry = self.install()
        self.assertEqual(registry, {"message_posted": ["handle_proposal_message"]})

        self.policy.refresh_from_db()
        self.assertTrue(self.policy.initialized)
        self.assertEqual(self.policy.handler_registry, {"message_posted": ["handle_proposal_message"]})
        # setup() did real work: it looked channel ids up and cached them.
        self.assertEqual(self.store().get("social_channel_id"), "C_SOCIAL")
        self.assertEqual(self.store().get("announcements_channel_id"), "C_ANN")

    def test_installing_twice_is_a_no_op(self):
        self.install()
        calls_before = len(self.platform.posted)

        # A second install must not re-register (which would double-fire every
        # handler) and must not raise.
        registry = self.install()

        self.assertEqual(registry, {"message_posted": ["handle_proposal_message"]})
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.handler_registry["message_posted"], ["handle_proposal_message"])
        self.assertEqual(len(self.platform.posted), calls_before)

    def test_import_of_already_provided_module_is_allowed(self):
        # The fixture does `import datetime` inside a handler even though
        # datetime is pre-injected. That must not be a SyntaxError.
        self.install()
        script_runtime.dispatch_event(self.policy, self.proposal_event(), platform=self.platform)
        self.assertEqual(len(self.platform.posts_to("C_SOCIAL")), 1)

    def test_import_of_disallowed_module_is_still_rejected(self):
        policy = GeneratedPolicy.objects.create(
            kind="platform", name="bad import", community=self.community,
            script_code="def setup(ctx):\n    import os\n    ctx.on('message_posted', setup)\n",
        )
        with self.assertRaises(SyntaxError):
            script_runtime.install_script_policy(policy, platform=self.platform)


class ProposalFlowTests(ScriptRuntimeTestCase):
    def install_and_propose(self):
        self.install()
        script_runtime.dispatch_event(self.policy, self.proposal_event(), platform=self.platform)
        return ScheduledCallback.objects.get(policy=self.policy)

    def test_proposal_message_posts_vote_announcement_and_schedules_tally(self):
        row = self.install_and_propose()

        posts = self.platform.posts_to("C_SOCIAL")
        self.assertEqual(len(posts), 1)
        self.assertIn("New Channel Proposal", posts[0]["text"])
        self.assertIn("#design", posts[0]["text"])

        # Scheduled as data: a top-level name plus JSON args. Nothing here
        # could have come from a closure.
        self.assertEqual(row.function_name, "evaluate_proposal_vote")
        self.assertEqual(len(row.args), 1)
        self.assertTrue(row.args[0].startswith("proposal_"))
        self.assertIsNone(row.fired_at)
        delay = row.run_at - timezone.now()
        self.assertGreater(delay.total_seconds(), 47 * 3600)
        self.assertLess(delay.total_seconds(), 49 * 3600)

    def test_non_member_proposal_is_ignored(self):
        self.install()
        event = self.proposal_event(actor_id="U_STRANGER")
        script_runtime.dispatch_event(self.policy, event, platform=self.platform)
        self.assertEqual(self.platform.posts_to("C_SOCIAL"), [])
        self.assertEqual(ScheduledCallback.objects.count(), 0)

    def test_message_in_other_channel_is_ignored(self):
        self.install()
        script_runtime.dispatch_event(self.policy, self.proposal_event(channel_id="C_OTHER"), platform=self.platform)
        self.assertEqual(self.platform.posted, [])
        self.assertEqual(ScheduledCallback.objects.count(), 0)

    def test_passed_branch_fires_after_48h(self):
        row = self.install_and_propose()
        self.platform.reactions = [{"name": "+1", "count": 12}, {"name": "-1", "count": 2}]

        result = fire_due_scheduled_callbacks(
            now=row.run_at + datetime.timedelta(minutes=1), platform=self.platform
        )
        self.assertEqual(result, {"fired": 1, "failed": 0})

        announcements = self.platform.posts_to("C_ANN")
        self.assertEqual(len(announcements), 1)
        self.assertIn("New Channel Approved!", announcements[0]["text"])
        self.assertIn("#design", announcements[0]["text"])
        self.assertIn("12 up / 2 down", announcements[0]["text"])

        pending = self.store().get("pending_channel_creations")
        self.assertEqual(len(pending), 1)
        self.assertEqual(list(pending.values())[0]["channel_name"], "design")

        row.refresh_from_db()
        self.assertIsNotNone(row.fired_at)
        self.assertEqual(row.error, "")

    def test_inconclusive_branch_dms_proposer(self):
        row = self.install_and_propose()
        self.platform.reactions = [{"name": "+1", "count": 3}, {"name": "-1", "count": 1}]

        fire_due_scheduled_callbacks(now=row.run_at + datetime.timedelta(minutes=1), platform=self.platform)

        dms = self.platform.posts_to("U_PROPOSER")
        self.assertEqual(len(dms), 1)
        self.assertIn("inconclusive", dms[0]["text"])
        self.assertEqual(self.platform.posts_to("C_ANN"), [])

    def test_failed_branch_dms_proposer(self):
        row = self.install_and_propose()
        self.platform.reactions = [{"name": "+1", "count": 3}, {"name": "-1", "count": 9}]

        fire_due_scheduled_callbacks(now=row.run_at + datetime.timedelta(minutes=1), platform=self.platform)

        dms = self.platform.posts_to("U_PROPOSER")
        self.assertEqual(len(dms), 1)
        self.assertIn("did not pass", dms[0]["text"])
        self.assertEqual(self.platform.posts_to("C_ANN"), [])

    def test_callback_does_not_fire_before_it_is_due(self):
        self.install_and_propose()
        result = fire_due_scheduled_callbacks(now=timezone.now(), platform=self.platform)
        self.assertEqual(result, {"fired": 0, "failed": 0})
        self.assertEqual(self.platform.posts_to("C_ANN"), [])

    def test_callback_fires_at_most_once_across_overlapping_polls(self):
        row = self.install_and_propose()
        self.platform.reactions = [{"name": "+1", "count": 12}, {"name": "-1", "count": 2}]
        due = row.run_at + datetime.timedelta(minutes=1)

        first = fire_due_scheduled_callbacks(now=due, platform=self.platform)
        second = fire_due_scheduled_callbacks(now=due, platform=self.platform)

        self.assertEqual(first["fired"], 1)
        self.assertEqual(second["fired"], 0)
        self.assertEqual(len(self.platform.posts_to("C_ANN")), 1)

    def test_failing_callback_is_marked_fired_and_records_the_error(self):
        row = self.install_and_propose()
        self.policy.script_code = "def setup(ctx):\n    pass\n"
        self.policy.save()

        result = fire_due_scheduled_callbacks(
            now=row.run_at + datetime.timedelta(minutes=1), platform=self.platform
        )

        self.assertEqual(result, {"fired": 0, "failed": 1})
        row.refresh_from_db()
        self.assertIsNotNone(row.fired_at)
        self.assertIn("evaluate_proposal_vote", row.error)


class ScheduleContractTests(ScriptRuntimeTestCase):
    def schedule_with(self, body):
        policy = GeneratedPolicy.objects.create(
            kind="platform", name="schedule contract", community=self.community, script_code=body
        )
        ctx = script_runtime.PolicyRuntimeContext(policy, platform=self.platform)
        script_runtime.execute_generated_script(body, "setup", ctx)

    def test_closure_is_rejected_with_a_pointed_message(self):
        # Matches the generator's real closure pattern: the inner function
        # actually captures the id, which is exactly what cannot be persisted.
        body = (
            "def tally(pid, ctx):\n"
            "    pass\n"
            "def setup(ctx):\n"
            "    def make_evaluator(pid):\n"
            "        def evaluate_later(ctx):\n"
            "            tally(pid, ctx)\n"
            "        return evaluate_later\n"
            "    ctx.schedule(60, make_evaluator('p1'))\n"
        )
        with self.assertRaises(PolicyScriptError) as cm:
            self.schedule_with(body)
        message = str(cm.exception)
        self.assertIn("closure", message)
        self.assertIn("pid", message)

    def test_nested_function_is_rejected_even_without_captures(self):
        body = (
            "def setup(ctx):\n"
            "    def inner(ctx):\n"
            "        pass\n"
            "    ctx.schedule(60, inner)\n"
        )
        with self.assertRaises(PolicyScriptError) as cm:
            self.schedule_with(body)
        self.assertIn("inside another function", str(cm.exception))

    def test_lambda_is_rejected(self):
        body = "def setup(ctx):\n    ctx.schedule(60, lambda ctx: None)\n"
        with self.assertRaises(PolicyScriptError) as cm:
            self.schedule_with(body)
        self.assertIn("lambda", str(cm.exception))

    def test_non_serializable_argument_is_rejected(self):
        body = (
            "def tally(thing, ctx):\n"
            "    pass\n"
            "def setup(ctx):\n"
            "    ctx.schedule(60, tally, {1, 2, 3})\n"
        )
        with self.assertRaises(PolicyScriptError) as cm:
            self.schedule_with(body)
        self.assertIn("JSON-serialisable", str(cm.exception))

    def test_top_level_function_is_accepted(self):
        body = (
            "def tally(proposal_id, ctx):\n"
            "    pass\n"
            "def setup(ctx):\n"
            "    ctx.schedule(60, tally, 'p1')\n"
        )
        self.schedule_with(body)
        row = ScheduledCallback.objects.latest("pk")
        self.assertEqual(row.function_name, "tally")
        self.assertEqual(row.args, ["p1"])


class EventShapeTests(ScriptRuntimeTestCase):
    def test_action_to_event_exposes_attribute_style_fields(self):
        from integrations.slack.models import SlackPostMessage

        action = SlackPostMessage(
            community=self.slack_community, text="channel name: x", channel="C_SOCIAL", initiator=self.user
        )
        action.timestamp = "1700000000.0001"
        event = script_runtime.action_to_event(action)

        # Scripts use event.data.get(...) / event.actor_id, not dict access.
        self.assertEqual(event.type, "message_posted")
        self.assertEqual(event.actor_id, "U_PROPOSER")
        self.assertEqual(event.data.get("channel_id"), "C_SOCIAL")
        self.assertEqual(event.data.get("text"), "channel name: x")
        self.assertEqual(event.data.get("message_id"), "1700000000.0001")


class PolicyStoreConcurrencyTests(TransactionTestCase):
    """
    Concurrency is the reason ctx.store is one row per key rather than one JSON
    blob per policy: a blob store read-modify-writes the whole thing, so two
    writers racing on different keys lose one of the two writes.
    """

    def setUp(self):
        self.slack_community, self.user = TestUtils.create_slack_community_and_user(username="U1")
        self.policy = GeneratedPolicy.objects.create(
            kind="platform", name="store test", community=self.slack_community.community, script_code=""
        )

    def run_concurrently(self, targets):
        errors = []

        def wrapper(fn):
            def inner():
                try:
                    fn()
                except Exception as e:  # surface thread failures in the test
                    errors.append(e)
                finally:
                    connection.close()
            return inner

        threads = [threading.Thread(target=wrapper(t)) for t in targets]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])

    def test_concurrent_writes_to_different_keys_do_not_lose_updates(self):
        keys = [f"key_{i}" for i in range(8)]

        def writer(key):
            return lambda: script_runtime.PolicyStore(self.policy).set(key, {"v": key})

        self.run_concurrently([writer(k) for k in keys])

        store = script_runtime.PolicyStore(self.policy)
        for key in keys:
            self.assertEqual(store.get(key), {"v": key}, f"lost the write to {key}")
        self.assertEqual(PolicyStoreEntry.objects.filter(policy=self.policy).count(), len(keys))

    def test_concurrent_writes_to_the_same_key_settle_on_one_value(self):
        store = script_runtime.PolicyStore(self.policy)
        store.set("untouched", "keep me")

        def writer(value):
            return lambda: script_runtime.PolicyStore(self.policy).set("contended", value)

        self.run_concurrently([writer(i) for i in range(8)])

        self.assertIn(store.get("contended"), list(range(8)))
        # A neighbouring key must survive a contended write to a different key.
        self.assertEqual(store.get("untouched"), "keep me")
        self.assertEqual(PolicyStoreEntry.objects.filter(policy=self.policy, key="contended").count(), 1)

    def test_store_supports_both_method_and_dict_styles(self):
        store = script_runtime.PolicyStore(self.policy)
        store.set("a", 1)
        store["b"] = 2
        self.assertEqual(store.get("a"), 1)
        self.assertEqual(store["b"], 2)
        self.assertEqual(store.setdefault("c", 3), 3)
        self.assertEqual(store.setdefault("c", 99), 3)
        self.assertIn("a", store)
        store.remove("a")
        self.assertIsNone(store.get("a"))
        self.assertEqual(store.get("missing", "fallback"), "fallback")

    def test_store_is_scoped_per_policy_not_per_proposal(self):
        other = GeneratedPolicy.objects.create(
            kind="platform", name="other", community=self.slack_community.community, script_code=""
        )
        script_runtime.PolicyStore(self.policy).set("k", "mine")
        script_runtime.PolicyStore(other).set("k", "theirs")
        self.assertEqual(script_runtime.PolicyStore(self.policy).get("k"), "mine")
        self.assertEqual(script_runtime.PolicyStore(other).get("k"), "theirs")
