"""
Slack-specific models.

PolicyKit equivalent: integrations/slack/models.py
Contains:
- SlackCommunity (extends CommunityPlatform)
    - team_id, platform="slack"
    - Methods: initiate_vote(), initiate_advanced_vote(), post_message(),
      get_conversations(), get_users_in_channel(), rename_conversation(),
      kick_conversation(), join_conversation()
- SlackUser (extends CommunityUser)
- GovernableActions:
    - SlackPostMessage (text, channel, timestamp)
    - SlackRenameConversation (name, channel, previous_name)
    - SlackJoinConversation (channel, users)
    - SlackPinMessage (channel, timestamp)
    - SlackScheduleMessage (text, channel, post_at)
    - SlackKickConversation (user, channel)

Each GovernableAction defines:
    - ACTION: Slack API method name
    - AUTH: token type (app/user/admin_bot/admin_user)
    - EXECUTE_PARAMETERS: fields sent to API
    - FILTER_PARAMETERS: no-code filter UI metadata
    - _revert(): undo logic

Sandbox adaptation:
- SlackCommunity methods become simulated (emit actions instead of API calls)
- GovernableActions become Event types that flow through the sandbox
- No actual Slack API calls; all actions are recorded in ActionLog
"""

# --- SlackCommunity ---
# TODO: Implement simulated SlackCommunity with same method signatures:
#   initiate_vote(proposal, users, post_type, text, channel, options)
#   post_message(text, channel)
#   get_conversations() -> list of channels
#   get_users_in_channel(channel_id) -> list of users


# --- SlackUser ---
# TODO: Implement (likely just an alias to CommunityUser with no extra fields)


# --- Governable Actions (as Event types) ---
# TODO: Define event type constants matching PolicyKit's action classes:
#   "slack_post_message"       -> SlackPostMessage
#   "slack_rename_conversation" -> SlackRenameConversation
#   "slack_join_conversation"  -> SlackJoinConversation
#   "slack_pin_message"        -> SlackPinMessage
#   "slack_schedule_message"   -> SlackScheduleMessage
#   "slack_kick_conversation"  -> SlackKickConversation
