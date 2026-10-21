"""
Core data models for the sandbox policy engine.

PolicyKit equivalent: policyengine/models.py
Contains: Community, CommunityUser, CommunityRole, Channel, Message,
          GovernableAction, Proposal, DataStore, VoteTracker.

Key differences from PolicyKit:
- No Django ORM; uses dataclasses
- No database persistence; all in-memory per scenario run
- Simulated time instead of real datetime
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    PASSED = "passed"
    FAILED = "failed"


class VoteType(str, Enum):
    BOOLEAN = "boolean"
    NUMBER = "number"


@dataclass
class CommunityRole:
    role_name: str
    description: str = ""
    is_base_role: bool = False


@dataclass
class CommunityUser:
    id: str
    readable_name: str
    roles: list[str] = field(default_factory=list)

    def has_role(self, role_name: str) -> bool:
        return role_name in self.roles

    def get_roles(self) -> list[str]:
        return list(self.roles)


@dataclass
class Channel:
    id: str
    name: str
    is_private: bool = False
    members: list[str] = field(default_factory=list)


@dataclass
class Message:
    id: str
    channel_id: str
    author_id: str
    text: str
    timestamp: float = 0.0
    deleted: bool = False
    reactions: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class GovernableAction:
    id: str
    action_type: str
    actor_id: str
    data: dict[str, Any] = field(default_factory=dict)
    status: ActionStatus = ActionStatus.PROPOSED
    timestamp: float = 0.0


@dataclass
class Proposal:
    id: str
    action: GovernableAction
    status: ActionStatus = ActionStatus.PROPOSED
    votes: list[Vote] = field(default_factory=list)

    def get_yes_votes(self) -> int:
        return sum(1 for v in self.votes if v.value is True)

    def get_no_votes(self) -> int:
        return sum(1 for v in self.votes if v.value is False)

    def get_vote_count(self) -> int:
        return len(self.votes)


@dataclass
class Vote:
    voter_id: str
    proposal_id: str
    value: Any = None
    vote_type: VoteType = VoteType.BOOLEAN


class DataStore:
    """Key-value store adapted from PolicyKit DataStore (models.py:407-464)."""

    def __init__(self):
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def remove(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            return True
        return False

    def has(self, key: str) -> bool:
        return key in self._data

    def keys(self) -> list[str]:
        return list(self._data.keys())


class VoteTracker:
    """Unified vote tallying adapted from PolicyKit Proposal vote methods."""

    def __init__(self):
        self._proposals: dict[str, Proposal] = {}

    def create_proposal(self, proposal_id: str, action: GovernableAction) -> Proposal:
        proposal = Proposal(id=proposal_id, action=action)
        self._proposals[proposal_id] = proposal
        return proposal

    def cast_vote(self, proposal_id: str, voter_id: str, value: Any, vote_type: VoteType = VoteType.BOOLEAN) -> Vote | None:
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return None  # Proposal doesn't exist - fail gracefully
        for existing in proposal.votes:
            if existing.voter_id == voter_id:
                existing.value = value
                return existing
        vote = Vote(voter_id=voter_id, proposal_id=proposal_id, value=value, vote_type=vote_type)
        proposal.votes.append(vote)
        return vote

    def get_proposal(self, proposal_id: str) -> Proposal | None:
        return self._proposals.get(proposal_id)

    def resolve(self, proposal_id: str, status: ActionStatus) -> None:
        proposal = self._proposals[proposal_id]
        proposal.status = status
        proposal.action.status = status


@dataclass
class Community:
    """In-memory community for sandbox scenarios."""

    id: str = "sandbox-community"
    users: dict[str, CommunityUser] = field(default_factory=dict)
    channels: dict[str, Channel] = field(default_factory=dict)
    roles: dict[str, CommunityRole] = field(default_factory=dict)
    messages: dict[str, Message] = field(default_factory=dict)
    actions: list[GovernableAction] = field(default_factory=list)
    store: DataStore = field(default_factory=DataStore)
    votes: VoteTracker = field(default_factory=VoteTracker)

    def add_user(self, user_id: str, name: str, roles: list[str] | None = None) -> CommunityUser:
        user = CommunityUser(id=user_id, readable_name=name, roles=roles or [])
        self.users[user_id] = user
        return user

    def add_channel(self, channel_id: str, name: str, members: list[str] | None = None) -> Channel:
        channel = Channel(id=channel_id, name=name, members=members or [])
        self.channels[channel_id] = channel
        return channel

    def add_role(self, role_name: str, description: str = "", is_base_role: bool = False) -> CommunityRole:
        role = CommunityRole(role_name=role_name, description=description, is_base_role=is_base_role)
        self.roles[role_name] = role
        return role

    def get_members(self) -> list[CommunityUser]:
        return list(self.users.values())

    def get_user(self, user_id: str) -> CommunityUser | None:
        return self.users.get(user_id)

    def get_channel(self, channel_id: str) -> Channel | None:
        return self.channels.get(channel_id)

    def get_channels(self) -> list[Channel]:
        return list(self.channels.values())

    def post_message(self, msg_id: str, channel_id: str, author_id: str, text: str, timestamp: float = 0.0) -> Message:
        msg = Message(id=msg_id, channel_id=channel_id, author_id=author_id, text=text, timestamp=timestamp)
        self.messages[msg_id] = msg
        return msg
