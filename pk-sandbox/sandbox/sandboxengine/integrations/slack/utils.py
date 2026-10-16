"""
Slack utilities.

PolicyKit equivalent: integrations/slack/utils.py
In PolicyKit, contains:
- SlackUtils class with helpers for:
    - slack_event_to_platform_action(): maps raw Slack event payloads
      to GovernableAction instances
    - Event type constants and payload parsing

Sandbox adaptation:
- Provides helpers for constructing well-formed Slack-style events
- Provides test fixture builders for Slack community setup
"""

# TODO: Implement SlackUtils with:
#   build_message_event(user_id, channel_id, text, ...) -> Event dict
#   build_join_event(user_id, channel_id) -> Event dict
#   build_reaction_event(user_id, message_id, emoji) -> Event dict
#   build_slack_community_fixture(users, channels) -> setup dict
