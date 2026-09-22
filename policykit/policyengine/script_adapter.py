"""
Adapter exposing a sandbox-style `ctx` API (see pk-sandbox's PolicyContext)
on top of real PolicyKit objects, for GeneratedPolicy scripts.

Unlike PolicyKit's traditional 5-stage Policy evaluation, a GeneratedPolicy's
script owns its own bookkeeping directly: ctx methods call action.execute()/
.revert() and mark the Proposal passed/failed themselves, rather than
returning a status for the engine to act on. See engine.py's
evaluate_generated_policy(), which is the only caller of this module.

The ctx API surface (on/schedule/store/get_user/...) intentionally mirrors
pk-sandbox's PolicyContext (sandboxengine/policyengine/engine.py) so scripts
written for the sandbox need no changes to run here. That mapping is a
moving target -- see NOTES.md for the sync-with-Brian caveat.
"""
import logging

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


def execute_generated_script(script_code: str, func_name: str, **kwargs):
    """
    Compile and run a full multi-function script (setup(ctx) plus any
    handlers it defines) in the same RestrictedPython sandbox as PolicyKit's
    existing policy code, then call one top-level function from it by name.

    This is deliberately NOT policyengine.safe_exec_code.execute_user_code:
    that helper runs with separate `globals`/`locals` dicts, which is fine
    for a single wrapped function (the existing filter/check/notify/etc
    stages) but breaks a multi-function script -- a function's __globals__
    is fixed to the `globals` dict at def-time, while sibling top-level defs
    in a two-dict exec() only land in `locals`, so e.g. setup(ctx) can't see
    a sibling `check_spam` by name (confirmed via NameError during testing).
    Using ONE dict for both restores normal module-level name resolution
    between a script's own functions, while reusing every other security
    primitive (compile_restricted, the same restricted builtins, the same
    import/write guards) unchanged from safe_exec_code.py.
    """
    def _apply(f, *a, **kw):
        return f(*a, **kw)

    restricted_namespace = {
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

    call_kwargs_name = "pk_call_kwargs"
    restricted_namespace[call_kwargs_name] = kwargs

    full_code = f"{script_code}\npk_result = {func_name}(**{call_kwargs_name})"

    byte_code = compile_restricted(full_code, filename="<generated_policy_script>", mode="exec", policy=OwnRestrictingNodeTransformer)
    exec(byte_code, restricted_namespace)
    return restricted_namespace.get("pk_result")

# proposal.data keys used to persist what a script's setup(ctx) registered,
# since the registered handler *functions* can't survive between separate
# evaluate_generated_policy() calls -- only their names are persisted, and
# setup(ctx) is re-run each call to rebuild the actual callables.
HANDLERS_KEY = "_generated_policy_handlers"  # event_type -> handler function name
SCHEDULE_KEY = "_generated_policy_schedule"  # [{interval, handler, recurring}]


class PolicyKitContext:
    """
    ctx object passed to a GeneratedPolicy script's setup(ctx) and its
    registered handlers.
    """

    def __init__(self, proposal, evaluation_context):
        self.proposal = proposal
        self.action = proposal.action
        self.policy = proposal.policy
        self.eval_context = evaluation_context
        """The real EvaluationContext for this proposal -- gives access to
        e.g. ctx.eval_context.slack, ctx.eval_context.metagov if a script
        needs the underlying platform client directly."""

        self.store = proposal.data
        """Proposal-scoped persistent key/value store (DataStore.get/set/remove)."""

        self._event_handlers = {}
        self._schedule = []
        self._decided = False

    # -- registration, called from setup(ctx) --------------------------------

    def on(self, event_type, handler):
        """Register a handler for an event type. Only the function's name is
        kept (see module docstring) -- handler is looked up again by name
        from this same script on the invocation that actually dispatches it."""
        self._event_handlers[event_type] = getattr(handler, "__name__", handler)

    def schedule(self, interval, handler, recurring=True):
        """Register a scheduled handler. NOT YET WIRED to a real periodic
        task -- see NOTES.md. Recorded here so setup() can run without
        raising, but nothing currently triggers scheduled handlers."""
        self._schedule.append({
            "interval": interval,
            "handler": getattr(handler, "__name__", handler),
            "recurring": recurring,
        })

    # -- logging, visible on the PolicyKit dashboard's Logs page --------------

    def log(self, message, level="info"):
        """
        Log a message to this evaluation's EvaluationLog, same as legacy
        Policy code can via the injected `logger` -- shows up on the
        dashboard's Logs page (policyengine/api_views.py's logs() /
        LogsSerializer, backed by django_db_logger.EvaluationLog).
        """
        getattr(self.eval_context.logger, level, self.eval_context.logger.info)(message)

    # -- bookkeeping, called from a handler -----------------------------------

    def approve(self):
        """Approve the triggering action: mark this proposal passed and
        execute the action. Owned by the script, not the engine."""
        if self._decided:
            return
        self._decided = True
        self.log(f"GeneratedPolicy '{self.policy.name}' approved {self.action}")
        self.proposal._pass_evaluation()
        if self.action._is_executable:
            self.action.execute()

    def reject(self):
        """Reject the triggering action: mark this proposal failed and
        revert the action if it's reversible."""
        if self._decided:
            return
        self._decided = True
        self.log(f"GeneratedPolicy '{self.policy.name}' rejected {self.action}")
        self.proposal._fail_evaluation()
        if self.action._is_reversible:
            self.action._revert()

    # -- platform access -------------------------------------------------------

    def post_message(self, channel_id, text, **kwargs):
        slack = getattr(self.eval_context, "slack", None)
        if slack is None:
            raise NotImplementedError("No 'slack' CommunityPlatform available in this EvaluationContext")
        slack.post_message(text=text, channel=channel_id, **kwargs)

    def get_members(self):
        from policyengine.models import CommunityUser
        return CommunityUser.objects.filter(community__community=self.action.community.community)


def action_to_event(action):
    """
    Convert a real PolicyKit action into the sandbox event shape scripts
    expect: {"type": ..., "data": {...}}.

    TODO: this only covers SlackPostMessage so far -- extend per action type
    as needed. See Brian's _action_to_event in POLICYKIT_INTEGRATION_PLAN.md
    for the fuller mapping to crib from (with the same TODO: verify against
    real field names, that doc wasn't checked against actual model fields).
    """
    action_type = getattr(action, "action_type", type(action).__name__.lower())
    data = {"action_type": action_type}
    if hasattr(action, "text"):
        data["text"] = action.text
    if hasattr(action, "channel"):
        data["channel_id"] = action.channel
    return {"type": f"{action_type}_created", "data": data}
