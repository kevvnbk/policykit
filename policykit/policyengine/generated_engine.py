"""
Evaluation engine for GeneratedPolicy
event-driven scripts (setup(ctx), ctx.on handlers, ctx.store, ctx.schedule). 
"""

import logging

from policyengine import script_runtime

logger = logging.getLogger(__name__)
db_logger = logging.getLogger("db")


class _ProposalLogAdapter(logging.LoggerAdapter):
    """
    Minimal stand-in for engine.EvaluationLogAdapter so a generated policy's
    log messages show up on the dashboard's Logs page like a legacy policy's
    do.
    """
    def process(self, msg, kwargs):
        kwargs["extra"] = self.extra
        return (msg, kwargs)


def run_generated_policies(action, generated_policies):
    """
    Run every eligible GeneratedPolicy against `action`, independently of
    each other and of action.kind.
    """
    from policyengine.models import Proposal

    proposals = []
    for policy in generated_policies.order_by('pk'):
        proposal = Proposal(policy=policy, action=action, status=Proposal.PROPOSED)
        if not action.pk:
            action.save()
        proposal.save()
        try:
            evaluate_generated_proposal(proposal)
        except Exception as e:
            # One policy's failure must not stop the others from running.
            # Logged with the policy id (not just the proposal) so this is
            # findable even if the proposal itself gets deleted below.
            logger.error(
                f"GeneratedPolicy {policy.pk} ('{policy.name}') raised {type(e).__name__} "
                f"evaluating {action}: {e}"
            )
            proposal.delete()
        else:
            proposals.append(proposal)
    return proposals


def evaluate_generated_proposal(proposal):
    """
    Evaluate one GeneratedPolicy proposal: convert the triggering action
    into an event and run whichever handler(s) the script registered for
    that event type at install time (GeneratedPolicy.handler_registry).

    Called both by run_generated_policies() (first evaluation) and by
    policyengine.engine.evaluate_proposal() (periodic re-evaluation of a
    PROPOSED proposal, from policyengine.tasks.evaluate_pending_proposals)
    """
    policy = proposal.policy
    action = proposal.action

    log_context = {"community": action.community.community, "proposal": proposal}
    log = _ProposalLogAdapter(db_logger, log_context)

    if not policy.initialized:
        # Dispatch reads the registry that setup() populates at install, so an
        # uninitialized policy matches nothing. Say so loudly: silently doing
        # nothing looks exactly like a policy that correctly had no opinion.
        log.warning(
            f"Policy '{policy.name}' has never been installed (setup(ctx) has not run), "
            f"so it has no handlers and will ignore this action. Run "
            f"`manage.py install_script_policies` to install it."
        )
        return True

    event = script_runtime.action_to_event(action)
    handlers = script_runtime.dispatch_event(
        policy, event, proposal=proposal, evaluation_context=_EvalContextShim(log)
    )
    if not handlers:
        log.debug(f"Policy '{policy.name}' has no handler for event '{event.type}', ignoring")
    return True


class _EvalContextShim:
    """
    script_runtime.PolicyRuntimeContext.log() only ever reads `.logger` off
    whatever it's handed as evaluation_context (see ctx.log() in
    script_runtime.py). This is the smallest thing that satisfies that,
    without constructing engine.EvaluationContext -- which pulls in Metagov,
    CommunityPlatform shimming, and policy.variables, none of which a
    generated script has any use for.
    """
    def __init__(self, logger_adapter):
        self.logger = logger_adapter
