# PolicyKit Integration Plan: Making PolicyKit Run Sandbox Scripts

## Executive Summary

**Goal:** Modify PolicyKit to execute our function-registration scripts while connecting to real Slack communities.

**Verdict:** ✅ **FEASIBLE** - Requires adding a new policy type to PolicyKit, not rewriting core engine.

**Effort Estimate:** 3-4 weeks of development + 2 weeks testing

**Key Insight:** Our event-driven model can coexist with PolicyKit's action-driven model through an adapter layer.

---

## Architecture Overview

### Current PolicyKit Flow

```
Slack Event (webhook)
  ↓
Metagov Plugin
  ↓
Create GovernableAction (e.g., SlackPostMessage)
  ↓
action.save() [triggers signal]
  ↓
evaluate_action() → find eligible policies
  ↓
For each Policy:
  - Create Proposal
  - Run filter() → if False, skip
  - Run initialize() → set variables
  - Run check() → return PASSED/FAILED/PROPOSED
  ↓
If FAILED → revert action
If PROPOSED → start vote (initiate_vote)
If PASSED → execute action
```

### Our Sandbox Flow

```
Event arrives
  ↓
EventBus.emit(event)
  ↓
Call registered handlers: handler(event, ctx)
  ↓
Handler logic:
  - Read community state
  - Check conditions
  - Create actions: ctx.emit_action(type, **data)
  - Execute: ctx.execute_action(action) OR
  - Govern: ctx.start_vote(proposal_id, action)
  ↓
Actions logged, votes tracked
```

### Proposed Integration Flow

```
Slack Event (webhook)
  ↓
Metagov Plugin
  ↓
Create GovernableAction
  ↓
action.save() [triggers signal]
  ↓
┌─────────────────────────────────────┐
│ NEW: ScriptPolicyEvaluator          │
│                                     │
│ 1. Convert action → event           │
│ 2. Create PolicyContext adapter     │
│ 3. Execute setup(ctx) if needed     │
│ 4. Emit event to handlers           │
│ 5. Handlers respond                 │
│ 6. Convert ctx actions → Proposals  │
│ 7. Return governance decision       │
└─────────────────────────────────────┘
  ↓
Standard PolicyKit governance
(votes, execution, reversion)
```

---

## Implementation Plan

### Phase 1: Create ScriptPolicy Model (Week 1)

Add a new policy type to PolicyKit that wraps our scripts.

**File:** `policykit/policyengine/models.py`

```python
class ScriptPolicy(Policy):
    """
    Policy defined by a function-registration script.
    
    Instead of 5-stage methods, this policy:
    1. Executes setup(ctx) to register event handlers
    2. Converts incoming actions to events
    3. Allows handlers to create governance responses
    """
    
    script_code = models.TextField(
        help_text="Python script with setup(ctx) entry point"
    )
    
    # Store registered handlers per instance
    _handlers = {}  # event_type -> [handler_funcs]
    _schedule = []  # [(interval, handler_func, recurring)]
    _initialized = False
    
    def filter(self):
        """Always evaluate - handlers decide internally."""
        return True
    
    def initialize(self):
        """Run setup(ctx) to register handlers."""
        if not self._initialized:
            ctx = self._create_policy_context()
            exec_code_block(self.script_code, {"ctx": ctx}, "setup")
            self._initialized = True
    
    def check(self):
        """
        Convert action to event, call handlers, collect responses.
        Handlers can:
        - ctx.execute_action() → return PASSED
        - ctx.start_vote() → return PROPOSED
        - raise Exception → return FAILED
        """
        from policyengine.script_adapter import ScriptEvaluator
        
        evaluator = ScriptEvaluator(self)
        result = evaluator.evaluate_action(self.action, self.proposal)
        
        return result.status  # PASSED/FAILED/PROPOSED
    
    def notify(self):
        """Emit 'proposal_created' event to handlers."""
        # Allow handlers to respond to governance events
        pass
    
    def success(self):
        """Emit 'action_passed' event."""
        pass
    
    def fail(self):
        """Emit 'action_failed' event."""
        pass
    
    def _create_policy_context(self):
        """Create PolicyContext adapter for this evaluation."""
        from policyengine.script_adapter import PolicyKitContextAdapter
        return PolicyKitContextAdapter(
            evaluation_context=self,
            community=self.community
        )
```

---

### Phase 2: PolicyContext Adapter (Week 1-2)

Create an adapter that makes PolicyKit's infrastructure look like our PolicyContext API.

**File:** `policykit/policyengine/script_adapter.py`

```python
class PolicyKitContextAdapter:
    """
    Adapter that provides sandbox PolicyContext API on top of PolicyKit.
    
    Maps:
    - ctx.emit_action() → create GovernableAction
    - ctx.execute_action() → mark for execution
    - ctx.start_vote() → create Proposal with vote
    - ctx.store → Policy variables or CommunityDataStore
    - ctx.get_user() → CommunityUser.objects.get()
    - ctx.get_channel() → Slack API call
    """
    
    def __init__(self, evaluation_context, community):
        self.community = community
        self._evaluation = evaluation_context  # The Policy instance
        self._event_handlers = {}
        self._pending_actions = []  # Actions created by handlers
        self._governance_decision = None
        
        # Access to PolicyKit models
        self.store = PolicyDataStoreAdapter(community)
        self.votes = PolicyVoteAdapter()
    
    @property
    def current_time(self):
        return timezone.now().timestamp()
    
    def on(self, event_type: str, handler):
        """Register an event handler."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    def schedule(self, interval: float, handler, recurring: bool = True):
        """
        Register a scheduled handler.
        Creates a Celery periodic task.
        """
        from django_celery_beat.models import PeriodicTask, IntervalSchedule
        
        # Create interval
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=int(interval),
            period=IntervalSchedule.SECONDS
        )
        
        # Create periodic task
        # Store handler in policy's script_metadata JSON field
        task_id = f"{self._evaluation.id}_schedule_{len(self._schedule)}"
        PeriodicTask.objects.create(
            interval=schedule,
            name=f"ScriptPolicy_{self._evaluation.id}_{task_id}",
            task='policyengine.tasks.execute_script_handler',
            args=json.dumps([self._evaluation.id, task_id]),
            one_off=not recurring
        )
        
        # Store handler reference
        self._schedule.append({
            'task_id': task_id,
            'handler_name': handler.__name__,
            'interval': interval,
            'recurring': recurring
        })
    
    def emit_action(self, action_type: str, **kwargs) -> GovernableAction:
        """
        Create a GovernableAction but don't execute yet.
        This mirrors sandbox behavior.
        """
        from integrations.slack.models import (
            SlackPostMessage, SlackRenameConversation, 
            SlackKickConversation, SlackPinMessage
        )
        
        # Map action type to GovernableAction class
        action_map = {
            'post_message': SlackPostMessage,
            'rename_conversation': SlackRenameConversation,
            'kick_conversation': SlackKickConversation,
            'pin_message': SlackPinMessage,
        }
        
        action_class = action_map.get(action_type)
        if not action_class:
            raise ValueError(f"Unknown action type: {action_type}")
        
        # Create action instance (don't save yet)
        action = action_class(
            community=self.community,
            initiator=kwargs.pop('actor_id', None),
            **kwargs
        )
        
        self._pending_actions.append(action)
        return action
    
    def execute_action(self, action: GovernableAction):
        """
        Mark action for immediate execution.
        Sets governance decision to PASSED.
        """
        self._governance_decision = 'PASSED'
        # Action will be executed by PolicyKit after check() returns
    
    def start_vote(self, proposal_id: str, action: GovernableAction):
        """
        Request a vote on this action.
        Sets governance decision to PROPOSED.
        """
        self._governance_decision = 'PROPOSED'
        self._pending_actions.append(action)
    
    def get_user(self, user_id: str):
        """Get CommunityUser by ID."""
        return CommunityUser.objects.get(
            community=self.community,
            username=user_id
        )
    
    def get_channel(self, channel_id: str):
        """
        Get channel info from Slack.
        Calls real Slack API via community's Metagov plugin.
        """
        slack_community = self.community.get_platform('slack')
        channels = slack_community.get_conversations()
        return next((ch for ch in channels if ch['id'] == channel_id), None)
    
    def get_channels(self):
        """Get all channels from Slack."""
        slack_community = self.community.get_platform('slack')
        return slack_community.get_conversations()
    
    def get_members(self):
        """Get all community members."""
        return CommunityUser.objects.filter(community=self.community)
    
    def post_message(self, channel_id: str, text: str, author_id: str = "__system__"):
        """
        Post a message to Slack.
        Creates SlackPostMessage action and executes immediately.
        """
        action = self.emit_action('post_message', 
                                   channel=channel_id, 
                                   text=text,
                                   actor_id=author_id)
        action.save(evaluate_action=False)  # Don't trigger policy evaluation
        action.execute()  # Execute immediately
    
    def read_document(self, url: str):
        """
        Read from external document.
        TODO: Integrate with PolicyKit's document storage.
        """
        # Could integrate with CommunityDoc or external data sources
        raise NotImplementedError("Document integration pending")
    
    def _emit_event_to_handlers(self, event_type: str, event_data: dict):
        """
        Emit event to registered handlers.
        Returns governance decision (PASSED/FAILED/PROPOSED).
        """
        if event_type not in self._event_handlers:
            return 'PASSED'  # No handlers = allow
        
        for handler in self._event_handlers[event_type]:
            try:
                handler(event={'type': event_type, 'data': event_data}, ctx=self)
            except Exception as e:
                logger.error(f"Handler {handler.__name__} failed: {e}")
                return 'FAILED'
        
        # Check if any handler set governance decision
        return self._governance_decision or 'PASSED'


class PolicyDataStoreAdapter:
    """Adapter for ctx.store using PolicyKit's data storage."""
    
    def __init__(self, community):
        self.community = community
    
    def get(self, key: str, default=None):
        from policyengine.models import DataStore
        try:
            obj = DataStore.objects.get(key=key, owner=self.community)
            return json.loads(obj.value)
        except DataStore.DoesNotExist:
            return default
    
    def set(self, key: str, value):
        from policyengine.models import DataStore
        DataStore.objects.update_or_create(
            key=key,
            owner=self.community,
            defaults={'value': json.dumps(value)}
        )
    
    def remove(self, key: str):
        from policyengine.models import DataStore
        DataStore.objects.filter(key=key, owner=self.community).delete()


class ScriptEvaluator:
    """
    Evaluates an action against a ScriptPolicy.
    Converts PolicyKit action → event → handlers → governance decision.
    """
    
    def __init__(self, script_policy):
        self.policy = script_policy
    
    def evaluate_action(self, action, proposal):
        """
        Convert action to event, call handlers, return decision.
        """
        # Create context
        ctx = PolicyKitContextAdapter(self.policy, self.policy.community)
        
        # Run setup(ctx) if not yet done
        if not self.policy._initialized:
            exec_code_block(self.policy.script_code, {"ctx": ctx}, "setup")
            self.policy._initialized = True
            self.policy._handlers = ctx._event_handlers
        else:
            # Restore handlers
            ctx._event_handlers = self.policy._handlers
        
        # Convert action to event
        event_type, event_data = self._action_to_event(action)
        
        # Emit to handlers
        decision = ctx._emit_event_to_handlers(event_type, event_data)
        
        # Store pending actions on proposal
        proposal.script_pending_actions = ctx._pending_actions
        
        return type('Result', (), {'status': decision})
    
    def _action_to_event(self, action):
        """Convert PolicyKit GovernableAction to sandbox event format."""
        from integrations.slack.models import SlackPostMessage
        
        if isinstance(action, SlackPostMessage):
            return 'message_posted', {
                'message_id': action.id,
                'channel_id': action.channel,
                'text': action.text,
                'author_id': action.initiator.username if action.initiator else None,
                'timestamp': action.datetime.timestamp()
            }
        
        # Add more action type mappings
        return 'unknown_action', {'action': action}
```

---

### Phase 3: Event Source Integration (Week 2)

Hook up real Slack events to our event system.

**File:** `integrations/slack/signals.py` (modify existing)

```python
# Add to existing signal handlers

@receiver(signal='event.message', sender='slack')
def handle_slack_message(sender, **kwargs):
    """
    Called when Slack message event arrives.
    Trigger ScriptPolicy evaluation.
    """
    from policyengine.models import ScriptPolicy
    
    event_data = kwargs['event_data']
    community = kwargs['community']
    
    # Create GovernableAction as usual
    action = SlackPostMessage(
        community=community,
        channel=event_data['channel'],
        text=event_data['text'],
        initiator=get_user(event_data['user']),
        community_origin=True
    )
    
    # Save triggers policy evaluation (including ScriptPolicies)
    action.save()  # Will call ScriptPolicy.check() if any exist
```

---

### Phase 4: Scheduled Handler Execution (Week 3)

Make `ctx.schedule()` work with real Celery tasks.

**File:** `policyengine/tasks.py` (add new task)

```python
from celery import shared_task

@shared_task
def execute_script_handler(policy_id, task_id):
    """
    Execute a scheduled handler from a ScriptPolicy.
    Called by Celery Beat on schedule.
    """
    from policyengine.models import ScriptPolicy
    from policyengine.script_adapter import PolicyKitContextAdapter
    
    policy = ScriptPolicy.objects.get(id=policy_id)
    
    # Create context
    ctx = PolicyKitContextAdapter(policy, policy.community)
    
    # Re-run setup to restore handlers
    exec_code_block(policy.script_code, {"ctx": ctx}, "setup")
    
    # Find the scheduled handler
    handler_info = next(
        h for h in ctx._schedule if h['task_id'] == task_id
    )
    
    # Get handler function by name
    # (handlers are in the local scope after exec_code_block)
    # This requires storing handlers differently - see below
    
    # Execute handler
    handler(event={'type': 'scheduled_check', 'data': {}}, ctx=ctx)
```

**Challenge:** Handlers are functions in the script's scope - can't easily serialize for Celery.

**Solution:** Store handler code separately or re-execute setup and call by name.

---

### Phase 5: Vote Integration (Week 3)

Connect `ctx.start_vote()` to PolicyKit's voting system.

```python
def start_vote(self, proposal_id: str, action: GovernableAction):
    """Start a vote via PolicyKit's voting system."""
    
    # Save action (don't evaluate)
    action.save(evaluate_action=False)
    
    # Create proposal
    proposal = Proposal.objects.create(
        policy=self._evaluation,
        action=action,
        status='proposed'
    )
    
    # Initiate vote via platform
    slack_community = self.community.get_platform('slack')
    slack_community.initiate_vote(
        proposal=proposal,
        users=None,  # Could be specified by handler
        post_type='channel',
        text=f"Vote on: {action.action_type}",
        channel=getattr(action, 'channel', None)
    )
    
    self._governance_decision = 'PROPOSED'
```

---

### Phase 6: Testing & Real Slack Integration (Week 4)

**Test Scenarios:**

1. **Simple message filter:**
```python
def setup(ctx):
    ctx.on("message_posted", check_spam)

def check_spam(event, ctx):
    if "spam" in event['data']['text'].lower():
        # Block the message
        raise Exception("Spam detected")
```

**Expected:** Message reverted when spam detected.

2. **Vote on channel creation:**
```python
def setup(ctx):
    ctx.on("channel_created", require_vote)

def require_vote(event, ctx):
    action = ctx.emit_action("create_channel", 
                             name=event['data']['name'])
    ctx.start_vote("channel_vote", action)
```

**Expected:** Vote initiated in Slack with emoji reactions.

3. **Scheduled inactive channel cleanup:**
```python
INACTIVE_DAYS = 30

def setup(ctx):
    ctx.schedule(86400, check_inactive_channels)  # Daily

def check_inactive_channels(event, ctx):
    channels = ctx.get_channels()
    for ch in channels:
        if is_inactive(ch, INACTIVE_DAYS):
            ctx.post_message(ch['id'], "⚠️ This channel will be archived")
```

**Expected:** Daily Celery task posts warnings to inactive channels.

---

## Real Slack Integration Architecture

### Component Overview

```
Real Slack Workspace
         ↓
    [Webhooks]
         ↓
   Metagov Plugin (receives events, makes API calls)
         ↓
   PolicyKit + ScriptPolicy
         ↓
   PolicyKitContextAdapter
         ↓
   Script Handlers (our generated code)
         ↓
   Governance Decisions (PASSED/FAILED/PROPOSED)
         ↓
   PolicyKit Execution (revert, execute, vote)
         ↓
   Metagov Plugin (makes Slack API calls)
         ↓
   Real Slack Workspace
```

### What Works With Current Architecture

✅ **Event handling:** Slack events → our handlers  
✅ **Action creation:** Handlers create PolicyKit actions  
✅ **Execution:** Actions execute via real Slack API  
✅ **Voting:** Can use PolicyKit's emoji-vote process  
✅ **Scheduling:** Celery handles periodic tasks  
✅ **State storage:** DataStore persists handler state  

### What Needs Adaptation

⚠️ **Document integration:** Need to add external document connectors to PolicyKit  
⚠️ **Handler serialization:** Scheduled handlers need special handling  
⚠️ **Multiple script policies:** Need coordination if multiple scripts handle same event  

---

## Migration Path for Existing Scripts

### Sandbox Script:
```python
def setup(ctx):
    ctx.on("message_posted", handle_message)

def handle_message(event, ctx):
    if "urgent" in event['data']['text']:
        ctx.post_message(
            event['data']['channel_id'],
            "Notifying moderators..."
        )
```

### Same Script in PolicyKit:
**No changes needed!** The adapter handles everything.

Just create a ScriptPolicy:
```python
policy = ScriptPolicy.objects.create(
    community=my_community,
    name="Urgent message notifier",
    script_code=script_text,
    is_active=True
)
```

---

## Advantages of This Approach

### ✅ Coexistence
- ScriptPolicies work alongside traditional 5-stage policies
- Don't have to migrate existing PolicyKit policies
- Gradual adoption path

### ✅ Real Platform Integration
- Full access to Metagov plugins
- Real Slack API calls
- Real vote processes
- Real scheduled tasks

### ✅ Backward Compatibility
- Sandbox scripts run in PolicyKit with zero changes
- Just need to create ScriptPolicy wrapper
- Can test in sandbox, deploy to PolicyKit

### ✅ LLM-Friendly
- Keep simple function-registration model
- LLMs generate same format
- No need to learn PolicyKit's 5-stage model

---

## Challenges & Solutions

### Challenge 1: Handler Persistence
**Problem:** Handlers are Python functions - can't easily serialize for Celery.

**Solution:** Store script code, re-execute `setup(ctx)` to restore handlers when needed.

### Challenge 2: Multiple Events per Action
**Problem:** One action might trigger multiple handlers.

**Solution:** Handlers return decisions; use most restrictive (FAILED > PROPOSED > PASSED).

### Challenge 3: Event Types Don't Match Action Types
**Problem:** PolicyKit has action classes; we have generic events.

**Solution:** Mapping layer in adapter (action → event, event → action).

### Challenge 4: Scheduled Handlers
**Problem:** `ctx.schedule()` needs Celery integration.

**Solution:** Create PeriodicTask on schedule(), task re-runs setup and calls handler.

### Challenge 5: External Documents
**Problem:** Sandbox has document integration; PolicyKit doesn't.

**Solution:** Add to PolicyKit or use CommunityDoc with external data adapters.

---

## Effort Breakdown

| Phase | Task | Effort | Dependencies |
|-------|------|--------|--------------|
| 1 | ScriptPolicy model | 3 days | None |
| 2 | PolicyKitContextAdapter | 5 days | Phase 1 |
| 3 | Event source integration | 2 days | Phase 2 |
| 4 | Scheduled handler execution | 3 days | Phase 2 |
| 5 | Vote integration | 3 days | Phase 2 |
| 6 | Testing with real Slack | 5 days | Phase 3-5 |
| 7 | Documentation | 2 days | All |
| 8 | Document integration (optional) | 5 days | Phase 2 |

**Total:** 23 days (4.6 weeks) → **3-4 weeks with parallelization**

---

## Risks & Mitigations

### Risk: Handler execution model mismatch
**Impact:** High  
**Mitigation:** Extensive testing of event flow; fallback to traditional policies if handler fails.

### Risk: Performance overhead
**Impact:** Medium  
**Mitigation:** Cache handler registrations; benchmark against traditional policies.

### Risk: Complex debugging
**Impact:** Medium  
**Mitigation:** Add logging at adapter boundaries; provide handler trace view in UI.

### Risk: Celery scheduling complexity
**Impact:** Medium  
**Mitigation:** Start with simple schedules; document limitations; consider django-q as alternative.

---

## Conclusion

### Can We Deploy Sandbox Scripts to Real PolicyKit?
✅ **YES** - Via ScriptPolicy adapter layer

### Can We Connect to Real Slack?
✅ **YES** - Via existing Metagov integration

### Do We Need to Change Our Architecture?
❌ **NO** - Our script format works as-is

### Effort Required?
⚠️ **MODERATE** - 3-4 weeks to build adapter + 2 weeks testing

### Recommended Path Forward

1. **Prototype ScriptPolicy** - Prove the adapter concept works (1 week)
2. **Test with real Slack workspace** - Verify event flow (1 week)
3. **Full implementation** - Complete all adapter features (2 weeks)
4. **Production hardening** - Error handling, logging, docs (2 weeks)

**Total: 6 weeks to production-ready deployment**

The key insight: **We don't need to change our architecture.** The adapter layer bridges both worlds cleanly.
