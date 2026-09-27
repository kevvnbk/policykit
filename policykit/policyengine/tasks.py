from __future__ import absolute_import, unicode_literals

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def evaluate_pending_proposals():
    """
    Iterates through all pending Proposals and re-evaluates them.
    """
    # import PK modules inside the task so we get code updates.
    from policyengine import engine
    from policyengine.models import Proposal, ExecutedActionTriggerAction, GovernableAction


    pending_proposals = Proposal.objects.filter(status=Proposal.PROPOSED)
    #logger.debug("Running evaluate_pending_proposals:" + str(len(pending_proposals)))

    for proposal in pending_proposals:
        try:
            community_name = proposal.action.community.community_name
        except Exception as e:
            logger.error(f"Error getting community name for proposal {proposal}, deleting proposal: {repr(e)} {e}")
            proposal.delete()
            continue
        logger.debug(f"{community_name} - Evaluating proposal '{proposal}'")
        try:
            engine.evaluate_proposal(proposal)
        except (engine.PolicyDoesNotExist, engine.PolicyIsNotActive, engine.PolicyDoesNotPassFilter) as e:
            logger.warn(f"{community_name} - ERROR - {type(e).__name__} deleting proposal: {proposal}")
            new_proposal = engine.delete_and_rerun(proposal)
            logger.debug(f"{community_name} - New proposal: {new_proposal}")
        except Exception as e:
            logger.error(f"{community_name} - Error running proposal {proposal}: {repr(e)} {e}")
            
            
        # If the engine just PASSED a GovernableAction, generate a new Trigger for the newly executed action.
        # This lets us use GovernableActions as triggers for trigger policies.
        if proposal.status == Proposal.PASSED and isinstance(proposal.action, GovernableAction):
            ExecutedActionTriggerAction.from_action(proposal.action).evaluate()

    clean_up_logs()
    # logger.debug("finished task")


def clean_up_logs():
    from django_db_logger.models import EvaluationLog
    from policykit.settings import DB_MAX_LOGS_TO_KEEP

    expired_logs = EvaluationLog.objects.filter(
        pk__in=EvaluationLog.objects.all().order_by("-create_datetime").values_list("pk")[DB_MAX_LOGS_TO_KEEP:]
    )

    if expired_logs.exists():
        # logger.debug(f"Deleting {expired_logs.count()} EvaluationLogs")
        expired_logs.delete()


@shared_task
def fire_due_scheduled_callbacks(now=None, platform=None):
    """
    Fire ctx.schedule() callbacks whose time has come.

    Runs on the same Celery beat that already re-evaluates PROPOSED proposals
    (see CELERY_BEAT_SCHEDULE) -- a second task on the existing scheduler, not
    a second scheduling system. It is deliberately NOT folded into
    evaluate_pending_proposals: that task's unit of work is "a Proposal still
    awaiting a decision", while a scheduled callback is not tied to any
    proposal or to any proposal status, and firing one must not depend on some
    unrelated proposal still being undecided.

    At-most-once, even with two overlapping poller runs: a row is claimed by a
    conditional UPDATE (... WHERE id = %s AND fired_at IS NULL), which only one
    caller can win. A callback that raises is still marked fired and records
    the error rather than being retried, so one bad callback can't wedge the
    queue behind it.

    `now` and `platform` are injectable for tests.
    """
    from django.utils import timezone

    from policyengine import script_runtime
    from policyengine.models import ScheduledCallback

    now = now or timezone.now()
    fired, failed = 0, 0

    due_ids = list(
        ScheduledCallback.objects.filter(fired_at__isnull=True, run_at__lte=now)
        .order_by("run_at")
        .values_list("pk", flat=True)
    )

    for pk in due_ids:
        claimed = ScheduledCallback.objects.filter(pk=pk, fired_at__isnull=True).update(
            fired_at=timezone.now()
        )
        if not claimed:
            # Another poller run got there first.
            continue

        row = ScheduledCallback.objects.get(pk=pk)
        try:
            script_runtime.run_scheduled_callback(row, platform=platform)
            fired += 1
        except Exception as e:
            failed += 1
            logger.error(f"Scheduled callback {row.pk} ({row.function_name}) failed: {repr(e)}")
            ScheduledCallback.objects.filter(pk=pk).update(error=f"{type(e).__name__}: {e}")

    if fired or failed:
        logger.debug(f"fire_due_scheduled_callbacks: {fired} fired, {failed} failed")
    return {"fired": fired, "failed": failed}
