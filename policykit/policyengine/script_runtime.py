"""
Event-driven policy runtime: runs generated `setup(ctx)` scripts alongside
PolicyKit's existing five-block policies, without touching them.

Shape of a script (see tests/fixtures/example_policy.py):

    def setup(ctx):                     # runs ONCE, at install
        ctx.on("message_posted", handle_message)

    def handle_message(event, ctx):     # runs on each matching real event
        ...
        ctx.schedule(48 * 3600, tally, proposal_id)   # runs later, durably

    def tally(proposal_id, ctx):        # ctx is passed LAST
        ...

Three things make this work in a Django process that does not stay resident
between events:

* Handler registration is DATA. ctx.on() records a function NAME into
  GeneratedPolicy.handler_registry at install time; dispatch re-executes the
  script and looks the name up again. Nothing holds a live function object.
* ctx.store is a per-POLICY table (PolicyStoreEntry), not per-Proposal --
  a script's state has to outlive the single action that triggered it.
* ctx.schedule() writes a ScheduledCallback row; a periodic task fires it.
  That is why only plain top-level functions are accepted: a closure cannot
  be written down as a name and reconstructed later.
"""
import datetime
import inspect
import json
import logging
import types

from django.utils import timezone

from RestrictedPython import compile_restricted
from RestrictedPython.Eval import default_guarded_getitem, default_guarded_getiter
from RestrictedPython.Guards import safer_getattr, guarded_unpack_sequence, guarded_iter_unpack_sequence

from policyengine.safe_exec_code import (
    policykit_builtins,
    STATIC_GLOBAL_VARIABLES,
    OwnRestrictingNodeTransformer,
    _guarded_import,
    _hook_writable,
)

logger = logging.getLogger(__name__)


class ScriptRestrictingNodeTransformer(OwnRestrictingNodeTransformer):
    """
    Same restrictions as the five-block sandbox, with one narrowing removed:
    `import X` is allowed when X is ALREADY provided to policy code as a
    pre-injected name (datetime, json, random, ...).

    Generated scripts emit `import datetime` despite the code generator telling
    them not to, and the base transformer rejects the statement at compile time
    -- a hard SyntaxError on a script that is otherwise fine and that could
    already use `datetime` without importing it. Allowing only names already in
    policykit_builtins grants no capability that wasn't reachable anyway.

    Subclassed rather than changing OwnRestrictingNodeTransformer so the
    existing five-block policy path keeps exactly its current behaviour.
    """

    def visit_Import(self, node):
        names = [alias.name for alias in node.names]
        disallowed = [n for n in names if n.split(".")[0] not in policykit_builtins]
        if disallowed:
            raise SyntaxError(
                f"Import statements are not allowed (cannot import {', '.join(disallowed)}).",
                ("<policy_script>", node.lineno, node.col_offset, ""),
            )
        return self.node_contents_visit(node)

    def visit_ImportFrom(self, node):
        module = (node.module or "").split(".")[0]
        if module not in policykit_builtins:
            raise SyntaxError(
                f"Import statements are not allowed (cannot import from {node.module}).",
                ("<policy_script>", node.lineno, node.col_offset, ""),
            )
        return self.node_contents_visit(node)


class PolicyScriptError(Exception):
    """A policy script violated the runtime contract (bad ctx.schedule target,
    unserialisable argument, missing entry point...). Raised with a message
    aimed at whoever has to fix the script."""


# --------------------------------------------------------------------------
# Sandboxed execution
# --------------------------------------------------------------------------

def execute_generated_script(script_code, func_name, *args, **kwargs):
    """
    Compile a whole multi-function script in PolicyKit's RestrictedPython
    sandbox and call one of its top-level functions.

    Deliberately not safe_exec_code.execute_user_code: that runs with separate
    globals/locals dicts, which is right for a single wrapped five-block stage
    but breaks a multi-function script -- a function's __globals__ is bound to
    the `globals` dict at def time while sibling defs land only in `locals`, so
    setup(ctx) cannot see a handler defined next to it. One dict for both
    restores normal module-level name resolution between a script's own
    functions; every other guard (compile_restricted, the restricted builtins,
    the import and write guards) is reused from safe_exec_code unchanged.

    Compile and import errors propagate as-is -- they name the real problem,
    and wrapping them loses the line number.
    """
    namespace = build_script_namespace()
    byte_code = compile_restricted(
        script_code, filename="<policy_script>", mode="exec", policy=ScriptRestrictingNodeTransformer
    )
    exec(byte_code, namespace)

    func = namespace.get(func_name)
    if not callable(func):
        # List only what the SCRIPT defined, not the names the sandbox injects.
        injected = set(build_script_namespace())
        defined = sorted(
            n for n, v in namespace.items()
            if callable(v) and not n.startswith("_") and n not in injected
        )
        raise PolicyScriptError(
            f"policy script has no top-level function '{func_name}' "
            f"(defines: {', '.join(defined) or 'nothing'})"
        )
    return func(*args, **kwargs)


def build_script_namespace():
    """The restricted globals a policy script runs in."""
    def _apply(f, *a, **kw):
        return f(*a, **kw)

    return {
        "__builtins__": {
            **policykit_builtins,
            "__import__": _guarded_import,
        },
        "_getitem_": default_guarded_getitem,
        "_getiter_": default_guarded_getiter,
        "_unpack_sequence_": guarded_unpack_sequence,
        "_iter_unpack_sequence_": guarded_iter_unpack_sequence,
        "_getattr_": safer_getattr,
        "_inplacevar_": lambda op, val, expr: val + expr,
        "_write_": _hook_writable,
        "_apply_": _apply,
        "hasattr": lambda obj, attr: hasattr(obj, attr),
        **STATIC_GLOBAL_VARIABLES,
    }


def _require_top_level_function(func, where):
    """
    Return the name to persist for `func`, or raise PolicyScriptError.

    Closures are rejected rather than introspected: the whole point is that
    only a NAME survives to fire time, so anything whose behaviour depends on
    captured state cannot be reconstructed. Failing loudly here beats firing a
    subtly wrong callback two days later.
    """
    if isinstance(func, str):
        return func

    if inspect.ismethod(func):
        raise PolicyScriptError(
            f"{where} needs a plain top-level function, but got the bound method "
            f"'{getattr(func, '__qualname__', func)}'. Define a module-level function "
            f"in the policy script and pass any state as plain arguments instead."
        )
    if not inspect.isfunction(func):
        raise PolicyScriptError(
            f"{where} needs a plain top-level function, but got {type(func).__name__} "
            f"({func!r}). Define it with `def` at the top level of the policy script."
        )

    name = func.__name__
    if name == "<lambda>":
        raise PolicyScriptError(
            f"{where} needs a named top-level function, but got a lambda. Only a function "
            f"NAME can be stored and resolved again later, and a lambda has none. Define it "
            f"with `def` at the top level of the policy script."
        )
    if func.__closure__:
        captured = ", ".join(func.__code__.co_freevars) or "outer variables"
        raise PolicyScriptError(
            f"{where} got '{name}', which is a closure (it captures {captured}). Only a "
            f"function NAME is stored, so captured values would be lost by the time it runs. "
            f"Define '{name}' at the top level and pass the captured values as arguments: "
            f"{where}(delay, {name}, {captured})."
        )
    qualname = getattr(func, "__qualname__", name)
    if qualname != name:
        raise PolicyScriptError(
            f"{where} got '{qualname}', which is defined inside another function. Only a "
            f"top-level function can be resolved again by name later -- move '{name}' to the "
            f"top level of the policy script."
        )
    return name


# --------------------------------------------------------------------------
# Platform adapter: everything that touches the outside world
# --------------------------------------------------------------------------

class PlatformAdapter:
    """
    The only part of the runtime that talks to a real platform. Kept separate
    from store/on/schedule so a sandbox or test can swap in a fake adapter and
    reuse PolicyRuntimeContext as-is, with no duplicated persistence logic.
    """

    def get_channels(self):
        raise NotImplementedError

    def get_user(self, user_id):
        raise NotImplementedError

    def get_message_reactions(self, channel_id, timestamp):
        raise NotImplementedError

    def post_message(self, target_id, text):
        raise NotImplementedError


class SlackPlatformAdapter(PlatformAdapter):
    """Real adapter, backed by this community's SlackCommunity."""

    def __init__(self, community):
        self.community = community

    @property
    def slack(self):
        from integrations.slack.models import SlackCommunity

        slack = SlackCommunity.objects.filter(community=self.community).first()
        if slack is None:
            raise PolicyScriptError(f"No SlackCommunity configured for community {self.community.pk}")
        return slack

    def get_channels(self):
        return [
            types.SimpleNamespace(id=c.get("id"), name=c.get("name"), raw=c)
            for c in self.slack.get_conversations()
        ]

    def get_user(self, user_id):
        from policyengine.models import CommunityUser

        user = CommunityUser.objects.filter(community__community=self.community, username=user_id).first()
        if user is None:
            return None
        # Scripts check `r.lower() in {...}` against .roles, so hand back role
        # NAMES, not the CommunityRole objects get_roles() returns.
        return types.SimpleNamespace(
            id=user.username,
            roles=[r.role_name for r in user.get_roles()],
            raw=user,
        )

    def get_message_reactions(self, channel_id, timestamp):
        from policyengine.models import LogAPICall

        response = LogAPICall.make_api_call(
            self.slack,
            values={"method_name": "reactions.get", "channel": channel_id, "timestamp": str(timestamp)},
            call="reactions.get",
        ) or {}
        message = response.get("message") or {}
        return [{"name": r.get("name"), "count": r.get("count", 0)} for r in message.get("reactions", [])]

    def post_message(self, target_id, text):
        from policyengine.models import LogAPICall

        # chat.postMessage takes a user id in `channel` and delivers a DM, so one
        # call covers both "post to a channel" and "DM a user".
        #
        # Routed through LogAPICall (not metagov_plugin directly) so the call is
        # recorded: is_policykit_action() matches incoming Slack events against
        # recent LogAPICalls by text, which is what stops a message this policy
        # just posted from coming back as an event and re-triggering it.
        response = LogAPICall.make_api_call(
            self.slack,
            values={"method_name": "chat.postMessage", "channel": target_id, "text": text},
            call="chat.postMessage",
        ) or {}
        return response.get("ts")


# --------------------------------------------------------------------------
# Durable per-policy key/value store
# --------------------------------------------------------------------------

class PolicyStore:
    """
    ctx.store. One row per (policy, key), so a write touches exactly one row.

    Supports both shapes real generated scripts use against the same object:
    method style (.get/.set, seen in the channel-proposal script) and dict
    style (store["k"], .setdefault, seen in others).
    """

    def __init__(self, policy):
        self.policy = policy

    def get(self, key, default=None):
        from policyengine.models import PolicyStoreEntry

        row = PolicyStoreEntry.objects.filter(policy=self.policy, key=key).first()
        if row is None or row.value is None:
            return default
        return row.value

    def set(self, key, value):
        from django.db import IntegrityError
        from policyengine.models import PolicyStoreEntry

        # Single-row UPDATE, falling back to INSERT -- never read-whole-blob,
        # mutate, write-whole-blob, which would lose a concurrent write to a
        # different key.
        updated = PolicyStoreEntry.objects.filter(policy=self.policy, key=key).update(
            value=value, updated_at=timezone.now()
        )
        if not updated:
            try:
                PolicyStoreEntry.objects.create(policy=self.policy, key=key, value=value)
            except IntegrityError:
                # Another writer inserted the same key between the UPDATE and
                # the INSERT; their row is now the one to update.
                PolicyStoreEntry.objects.filter(policy=self.policy, key=key).update(
                    value=value, updated_at=timezone.now()
                )
        return value

    def remove(self, key):
        from policyengine.models import PolicyStoreEntry

        PolicyStoreEntry.objects.filter(policy=self.policy, key=key).delete()

    def setdefault(self, key, default):
        current = self.get(key)
        if current is None:
            self.set(key, default)
            return default
        return current

    def keys(self):
        from policyengine.models import PolicyStoreEntry

        return list(PolicyStoreEntry.objects.filter(policy=self.policy).values_list("key", flat=True))

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)

    def __contains__(self, key):
        return self.get(key) is not None


# --------------------------------------------------------------------------
# The ctx object
# --------------------------------------------------------------------------

class PolicyRuntimeContext:
    """
    The only interface a generated script has to the world.

    World-facing calls delegate to a PlatformAdapter; store/on/schedule are
    persistence and live here, so swapping the adapter is enough to run the
    same scripts against a fake platform.
    """

    def __init__(self, policy, platform=None, proposal=None, evaluation_context=None, now=None):
        self.policy = policy
        self.platform = platform if platform is not None else SlackPlatformAdapter(policy.community)
        self.store = PolicyStore(policy)
        self.proposal = proposal
        self.action = proposal.action if proposal is not None else None
        self.eval_context = evaluation_context
        self._now = now

        self.registered_handlers = {}
        """{event_type: [function name]} built during a setup() run; persisted
        onto the policy by install_script_policy()."""

        self.scheduled_rows = []
        self._decided = False

    def now(self):
        return self._now() if callable(self._now) else (self._now or timezone.now())

    # -- world (delegated) --------------------------------------------------

    def get_channels(self):
        return self.platform.get_channels()

    def get_channel(self, channel_id):
        for channel in self.get_channels():
            if channel.id == channel_id:
                return channel
        return None

    def get_user(self, user_id):
        return self.platform.get_user(user_id)

    def get_message_reactions(self, channel_id, timestamp):
        return self.platform.get_message_reactions(channel_id, timestamp)

    def post_message(self, target_id, text):
        return self.platform.post_message(target_id, text)

    def get_members(self):
        from policyengine.models import CommunityUser

        return CommunityUser.objects.filter(community__community=self.policy.community)

    # -- registration -------------------------------------------------------

    def on(self, event_type, handler):
        """Register a handler for an event type. Only the NAME is kept -- see
        module docstring -- so the same top-level-function rule as schedule()
        applies."""
        name = _require_top_level_function(handler, "ctx.on")
        handlers = self.registered_handlers.setdefault(event_type, [])
        if name not in handlers:
            handlers.append(name)
        return name

    def schedule(self, delay_seconds, func, *args):
        """Call func(*args, ctx) after delay_seconds, durably. Writes a row;
        holds nothing in memory."""
        from policyengine.models import ScheduledCallback

        name = _require_top_level_function(func, "ctx.schedule")
        try:
            json.dumps(list(args))
        except (TypeError, ValueError) as exc:
            raise PolicyScriptError(
                f"ctx.schedule arguments for '{name}' must be JSON-serialisable, since they are "
                f"stored until the call runs: {exc}"
            )
        try:
            delay = float(delay_seconds)
        except (TypeError, ValueError):
            raise PolicyScriptError(
                f"ctx.schedule delay for '{name}' must be a number of seconds, got {delay_seconds!r}."
            )

        row = ScheduledCallback.objects.create(
            policy=self.policy,
            run_at=self.now() + datetime.timedelta(seconds=delay),
            function_name=name,
            args=list(args),
        )
        self.scheduled_rows.append(row)
        return row

    # -- logging ------------------------------------------------------------

    def log(self, message, level="info"):
        """Write to this evaluation's EvaluationLog, so it shows on the
        dashboard's Logs page. Falls back to the module logger when there is no
        evaluation in progress (install, or a scheduled callback)."""
        target = getattr(self.eval_context, "logger", None) or logger
        getattr(target, level, target.info)(message)

    # -- bookkeeping on the triggering action -------------------------------

    def approve(self):
        """Approve the action that triggered this evaluation. No-op when there
        is no triggering action (install / scheduled callback)."""
        if self._decided or self.proposal is None:
            return
        self._decided = True
        self.log(f"Policy '{self.policy.name}' approved {self.action}")
        self.proposal._pass_evaluation()
        if self.action._is_executable:
            self.action.execute()

    def reject(self):
        """Reject the triggering action: mark the proposal failed and revert it
        if it is reversible (for a Slack message, that deletes it)."""
        if self._decided or self.proposal is None:
            return
        self._decided = True
        self.log(f"Policy '{self.policy.name}' rejected {self.action}")
        self.proposal._fail_evaluation()
        if self.action._is_reversible:
            self.action._revert()


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------

# ActionType codename <-> the event name generated scripts use. Not an invented
# convention: "member_joined_channel" appears verbatim in real generated
# scripts and matches how integrations/slack/utils.py already maps that Slack
# event to SlackJoinConversation; "message_posted" matches the sandbox's docs.
ACTION_TYPE_TO_EVENT_TYPE = {
    "slackpostmessage": "message_posted",
    "slackjoinconversation": "member_joined_channel",
}
EVENT_TYPE_TO_ACTION_TYPE = {v: k for k, v in ACTION_TYPE_TO_EVENT_TYPE.items()}


def action_to_event(action):
    """
    Wrap a real PolicyKit action as the event object scripts expect. Attribute
    access (event.data, event.actor_id), not a dict -- that is what real
    generated scripts use.
    """
    action_type = getattr(action, "action_type", type(action).__name__.lower())
    timestamp = getattr(action, "timestamp", None)
    data = {"action_type": action_type}
    for attr, key in (("text", "text"), ("channel", "channel_id")):
        if hasattr(action, attr):
            data[key] = getattr(action, attr)
    if timestamp:
        # Scripts use these interchangeably to point at "the message this was";
        # for Slack both are the message ts.
        data["timestamp"] = timestamp
        data["message_id"] = timestamp

    initiator = getattr(action, "initiator", None)
    return types.SimpleNamespace(
        type=ACTION_TYPE_TO_EVENT_TYPE.get(action_type, f"{action_type}_created"),
        data=data,
        actor_id=getattr(initiator, "username", None),
        timestamp=timestamp,
        action=action,
    )


def event_type_to_action_type_codename(event_type):
    """Reverse of ACTION_TYPE_TO_EVENT_TYPE, for deriving which ActionTypes a
    script's registered events correspond to. None for an unknown event type --
    the caller reports it rather than this guessing."""
    return EVENT_TYPE_TO_ACTION_TYPE.get(event_type)


# --------------------------------------------------------------------------
# Install and dispatch
# --------------------------------------------------------------------------

def install_script_policy(policy, platform=None, force=False):
    """
    Run the script's setup(ctx) exactly once and persist what it registered.

    Calling this again is a no-op (not an error, and not a second registration
    that would double-fire handlers). `force` re-runs it, for a script edit.
    """
    if policy.initialized and not force:
        return policy.handler_registry or {}

    ctx = PolicyRuntimeContext(policy, platform=platform)
    execute_generated_script(policy.script_code, "setup", ctx)

    policy.handler_registry = ctx.registered_handlers
    policy.initialized = True
    policy.save()
    return policy.handler_registry


def dispatch_event(policy, event, platform=None, proposal=None, evaluation_context=None):
    """
    Run every handler registered for this event type. Returns the names run, so
    callers can tell "no handler for this event" from "handled".
    """
    handlers = (policy.handler_registry or {}).get(event.type, [])
    if not handlers:
        return []

    ctx = PolicyRuntimeContext(
        policy, platform=platform, proposal=proposal, evaluation_context=evaluation_context
    )
    for name in handlers:
        execute_generated_script(policy.script_code, name, event, ctx)
    return handlers


def run_scheduled_callback(row, platform=None):
    """Fire one ScheduledCallback: func(*args, ctx), with ctx last."""
    from policyengine.models import GeneratedPolicy

    policy = GeneratedPolicy.objects.filter(pk=row.policy_id).first()
    if policy is None:
        raise PolicyScriptError(f"scheduled callback {row.pk} refers to a policy that no longer exists")

    # A missing function_name here means the script was edited between
    # scheduling and firing; execute_generated_script names it in the error.
    ctx = PolicyRuntimeContext(policy, platform=platform)
    args = list(row.args or [])
    return execute_generated_script(policy.script_code, row.function_name, *args, ctx)
