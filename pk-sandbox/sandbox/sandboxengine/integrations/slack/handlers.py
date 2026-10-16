"""
Slack event handlers.

PolicyKit equivalent: integrations/slack/handlers.py
In PolicyKit, this:
- Receives platform_event_created signals from Metagov Slack plugin
- Maps Slack event types to GovernableAction subclasses:
    message -> SlackPostMessage
    member_joined_channel -> SlackJoinConversation
    channel_rename -> SlackRenameConversation
    pin_added -> SlackPinMessage
- Checks is_policykit_action() to avoid governing PK's own API calls
- Handles governance_process_updated for vote recording

Sandbox adaptation:
- Instead of Django signals, events arrive via EventBus.emit()
- Maps event types to the same action categories
- Vote recording handled by VoteTracker directly
"""

# --- Event type mapping ---
# TODO: Implement mapping from raw event types to sandbox action types:
#   "message_posted" -> handles text analysis, channel routing
#   "user_joined"    -> handles channel join events
#   "reaction_added" -> handles emoji reactions (used for voting)
#   "vote_cast"      -> records vote via VoteTracker
