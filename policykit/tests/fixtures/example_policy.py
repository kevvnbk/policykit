# Real script from the generation pipeline, used as an integration fixture.
#
# ONE change from what was generated, per the runtime's ctx.schedule contract:
# the original wrapped the delayed call in a closure --
#
#     def make_evaluator(pid):
#         def evaluate_later(event, ctx):
#             evaluate_proposal_vote(pid, ctx)
#         return evaluate_later
#
#     ctx.schedule(48 * 3600, make_evaluator(proposal_id))
#
# -- which cannot be persisted, since only a function NAME survives until the
# call is due. Rewritten to pass the top-level function directly with the
# captured id as a plain argument. Everything else is as generated, including
# the redundant `import datetime` (datetime is already provided to scripts).
def setup(ctx):
    for ch in ctx.get_channels():
        if ch.name == "social":
            ctx.store.set("social_channel_id", ch.id)
        if ch.name == "announcements":
            ctx.store.set("announcements_channel_id", ch.id)
    ctx.on("message_posted", handle_proposal_message)


def handle_proposal_message(event, ctx):
    social_channel_id = ctx.store.get("social_channel_id")
    if event.data.get("channel_id") != social_channel_id:
        return
    text = event.data.get("text", "")
    if not is_valid_proposal_message(text, ctx):
        return
    user_id = event.actor_id
    if not has_member_role(user_id, ctx):
        return
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    channel_name = None
    description = None
    for line in lines:
        lower = line.lower()
        if lower.startswith("channel name:"):
            channel_name = line[len("channel name:"):].strip()
        elif lower.startswith("description:"):
            description = line[len("description:"):].strip()
    if not channel_name or not description:
        return
    import datetime
    now = datetime.datetime.utcnow()
    proposal_id = "proposal_" + str(int(now.timestamp() * 1000))
    message_ts = event.data.get("timestamp", str(now.timestamp()))
    deadline = now + datetime.timedelta(hours=48)
    proposal_data = {
        "id": proposal_id,
        "proposer": user_id,
        "proposed_channel_name": channel_name,
        "proposed_channel_description": description,
        "vote_result": None,
        "thumbs_up_count": 0,
        "thumbs_down_count": 0,
        "total_votes": 0,
        "status": "open",
        "message_timestamp": message_ts,
        "voting_deadline": deadline.isoformat(),
        "channel_id": social_channel_id,
    }
    save_proposal(proposal_data, ctx)
    voting_prompt = (
        f"New Channel Proposal by <@{user_id}>\n"
        f"Proposed Channel: #{channel_name}\n"
        f"Description: {description}\n\n"
        f"Vote with :+1: to approve or :-1: to reject.\n"
        f"Voting closes in 48 hours. Minimum 10 votes required for quorum.\n"
        f"Proposal ID: {proposal_id}"
    )
    ctx.post_message(social_channel_id, voting_prompt)
    import datetime as dt2
    voting_msg_ts = str(dt2.datetime.utcnow().timestamp())
    proposal_data["voting_message_timestamp"] = voting_msg_ts
    save_proposal(proposal_data, ctx)

    ctx.schedule(48 * 3600, evaluate_proposal_vote, proposal_id)


def evaluate_proposal_vote(proposal_id, ctx):
    proposals = ctx.store.get("proposals") or {}
    proposal = proposals.get(proposal_id)
    if not proposal or proposal.get("status") != "open":
        return
    counts = get_proposal_vote_counts(proposal_id, ctx)
    thumbs_up = counts["thumbs_up"]
    thumbs_down = counts["thumbs_down"]
    total = counts["total"]
    vote_data = {
        "thumbs_up_count": thumbs_up,
        "thumbs_down_count": thumbs_down,
        "total_votes": total,
    }
    if total < 10:
        vote_data["vote_result"] = "inconclusive"
        update_proposal_status(proposal_id, "inconclusive", vote_data, ctx)
        handle_proposal_inconclusive(proposal_id, ctx)
    elif thumbs_up / total > 0.5:
        vote_data["vote_result"] = "passed"
        update_proposal_status(proposal_id, "approved", vote_data, ctx)
        handle_proposal_passed(proposal_id, ctx)
    else:
        vote_data["vote_result"] = "failed"
        update_proposal_status(proposal_id, "rejected", vote_data, ctx)
        handle_proposal_failed(proposal_id, ctx)


def handle_proposal_passed(proposal_id, ctx):
    proposals = ctx.store.get("proposals") or {}
    proposal = proposals.get(proposal_id)
    if not proposal:
        return
    channel_name = proposal["proposed_channel_name"]
    description = proposal["proposed_channel_description"]
    proposer = proposal["proposer"]
    thumbs_up = proposal.get("thumbs_up_count", 0)
    thumbs_down = proposal.get("thumbs_down_count", 0)
    total = proposal.get("total_votes", 0)
    pct = round(thumbs_up / total * 100, 1) if total > 0 else 0
    ann_channel_id = ctx.store.get("announcements_channel_id")
    ann_text = (
        f"New Channel Approved!\n"
        f"Admins: Please manually create the channel #{channel_name}.\n"
        f"Description: {description}\n"
        f"Proposed by: <@{proposer}>\n"
        f"Vote Result: {thumbs_up} up / {thumbs_down} down ({pct}% approval, {total} total votes)\n"
        f"@admins - action required: create channel #{channel_name}"
    )
    ctx.post_message(ann_channel_id, ann_text)
    pending = ctx.store.get("pending_channel_creations") or {}
    pending[proposal_id] = {"channel_name": channel_name, "description": description, "proposer": proposer}
    ctx.store.set("pending_channel_creations", pending)


def handle_proposal_failed(proposal_id, ctx):
    proposals = ctx.store.get("proposals") or {}
    proposal = proposals.get(proposal_id)
    if not proposal:
        return
    proposer = proposal["proposer"]
    channel_name = proposal["proposed_channel_name"]
    thumbs_up = proposal.get("thumbs_up_count", 0)
    thumbs_down = proposal.get("thumbs_down_count", 0)
    total = proposal.get("total_votes", 0)
    pct = round(thumbs_up / total * 100, 1) if total > 0 else 0
    dm_text = (
        f"Your proposal for #{channel_name} did not pass.\n"
        f"Final Vote: {thumbs_up} up / {thumbs_down} down\n"
        f"Total Votes: {total} | Approval: {pct}%\n"
        f"More than 50% approval was required to pass."
    )
    ctx.post_message(proposer, dm_text)


def handle_proposal_inconclusive(proposal_id, ctx):
    proposals = ctx.store.get("proposals") or {}
    proposal = proposals.get(proposal_id)
    if not proposal:
        return
    proposer = proposal["proposer"]
    channel_name = proposal["proposed_channel_name"]
    thumbs_up = proposal.get("thumbs_up_count", 0)
    thumbs_down = proposal.get("thumbs_down_count", 0)
    total = proposal.get("total_votes", 0)
    dm_text = (
        f"Your proposal for #{channel_name} was closed as inconclusive.\n"
        f"The minimum of 10 votes was not reached within the 48-hour voting window.\n"
        f"Votes Cast: {total} (up {thumbs_up} / down {thumbs_down})\n"
        f"At least 10 total votes are required for a result to count."
    )
    ctx.post_message(proposer, dm_text)


def is_valid_proposal_message(text, ctx):
    lower = text.lower()
    has_name = "channel name:" in lower
    has_desc = "description:" in lower
    return has_name and has_desc


def get_proposal_vote_counts(proposal_id, ctx):
    proposals = ctx.store.get("proposals") or {}
    proposal = proposals.get(proposal_id)
    if not proposal:
        return {"thumbs_up": 0, "thumbs_down": 0, "total": 0}
    social_channel_id = proposal.get("channel_id") or ctx.store.get("social_channel_id")
    voting_msg_ts = proposal.get("voting_message_timestamp")
    proposal_msg_ts = proposal.get("message_timestamp")
    thumbs_up = 0
    thumbs_down = 0
    for ts in [voting_msg_ts, proposal_msg_ts]:
        if not ts:
            continue
        try:
            reactions = ctx.get_message_reactions(social_channel_id, ts)
            if reactions:
                for r in reactions:
                    name = r.get("name", "")
                    count = r.get("count", 0)
                    if name in ("+1", "thumbsup", "thumbs_up"):
                        thumbs_up = count
                    elif name in ("-1", "thumbsdown", "thumbs_down"):
                        thumbs_down = count
                break
        except Exception:
            continue
    total = thumbs_up + thumbs_down
    return {"thumbs_up": thumbs_up, "thumbs_down": thumbs_down, "total": total}


def has_member_role(user_id, ctx):
    try:
        user = ctx.get_user(user_id)
        if not user:
            return False
        roles = user.roles if hasattr(user, "roles") else user.get("roles", [])
        return "member" in roles
    except Exception:
        return False


def save_proposal(proposal_data, ctx):
    proposals = ctx.store.get("proposals") or {}
    proposal_id = proposal_data["id"]
    proposals[proposal_id] = proposal_data
    ctx.store.set("proposals", proposals)
    ts_index = ctx.store.get("proposal_by_timestamp") or {}
    ts = proposal_data.get("message_timestamp")
    if ts:
        ts_index[ts] = proposal_id
    ctx.store.set("proposal_by_timestamp", ts_index)


def get_proposal_by_message_timestamp(timestamp, ctx):
    ts_index = ctx.store.get("proposal_by_timestamp") or {}
    proposal_id = ts_index.get(timestamp)
    if not proposal_id:
        return None
    proposals = ctx.store.get("proposals") or {}
    return proposals.get(proposal_id)


def update_proposal_status(proposal_id, status, vote_data, ctx):
    proposals = ctx.store.get("proposals") or {}
    proposal = proposals.get(proposal_id)
    if not proposal:
        return
    proposal["status"] = status
    for key, value in vote_data.items():
        proposal[key] = value
    proposals[proposal_id] = proposal
    ctx.store.set("proposals", proposals)
