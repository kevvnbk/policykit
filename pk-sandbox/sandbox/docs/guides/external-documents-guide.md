# External Document Integration Plan

## Overview

Enable the sandbox to generate community scripts that can read and write external documents (Google Sheets, Notion, Airtable, etc.). This must work across three distinct contexts:

1. **Generation-time**: LLM reads documents to understand structure and generate appropriate code
2. **Testing-time**: Sandbox simulates documents to validate script behavior
3. **Runtime**: Real backend connects to actual external services to execute policies

**Key Constraint**: The backend executing scripts is separate from the sandbox generating them, requiring a portable abstraction layer.

---

## Architecture Components

### 1. Data Source Abstraction Layer

A unified interface that works identically in sandbox and production:

```python
# sandboxengine/policyengine/datasources.py

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

@dataclass
class DocumentSchema:
    """Describes the structure of a document for LLM understanding."""
    source_type: str  # "google_sheets", "notion", "airtable"
    source_url: str
    structure: Dict[str, Any]  # columns, headers, sheet names, etc.
    sample_data: List[Dict[str, Any]]  # first few rows for context
    metadata: Dict[str, Any]  # access patterns, update frequency, etc.

class DataSource(ABC):
    """Abstract interface for external documents."""
    
    @abstractmethod
    def read(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Read data from source. Query filters results."""
        pass
    
    @abstractmethod
    def write(self, data: List[Dict[str, Any]], mode: str = "append") -> None:
        """Write data. Modes: 'append', 'update', 'replace'."""
        pass
    
    @abstractmethod
    def get_schema(self) -> DocumentSchema:
        """Return schema for LLM understanding."""
        pass
    
    @abstractmethod
    def query(self, conditions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Query with conditions (filters, sorting, limits)."""
        pass

class DataSourceRegistry:
    """Maps source URLs to DataSource implementations."""
    
    def __init__(self):
        self._sources: Dict[str, DataSource] = {}
        self._factories: Dict[str, callable] = {}
    
    def register_factory(self, source_type: str, factory: callable) -> None:
        """Register a factory function for a source type."""
        self._factories[source_type] = factory
    
    def register_source(self, source_id: str, source: DataSource) -> None:
        """Register a specific source instance."""
        self._sources[source_id] = source
    
    def get_source(self, source_url: str) -> DataSource:
        """Get or create a source for the given URL."""
        if source_url in self._sources:
            return self._sources[source_url]
        
        source_type = self._infer_source_type(source_url)
        if source_type not in self._factories:
            raise ValueError(f"No factory registered for source type: {source_type}")
        
        source = self._factories[source_type](source_url)
        self._sources[source_url] = source
        return source
    
    def _infer_source_type(self, url: str) -> str:
        if "docs.google.com/spreadsheets" in url:
            return "google_sheets"
        elif "notion.so" in url:
            return "notion"
        elif "airtable.com" in url:
            return "airtable"
        raise ValueError(f"Cannot infer source type from URL: {url}")
```

### 2. PolicyContext Extension

Add document access to the script API surface:

```python
# sandboxengine/policyengine/engine.py (additions)

class PolicyContext:
    def __init__(self, community: Community, event_bus: EventBus, data_registry: DataSourceRegistry):
        self.community = community
        self.store = community.store
        self.votes = community.votes
        self.data = data_registry  # NEW: document access
        self._bus = event_bus
        self._action_counter = 0
    
    # NEW: Convenience methods for document access
    def read_document(self, source_url: str, query: Optional[Dict] = None) -> List[Dict]:
        """Read from an external document."""
        source = self.data.get_source(source_url)
        return source.read(query)
    
    def write_document(self, source_url: str, data: List[Dict], mode: str = "append") -> None:
        """Write to an external document."""
        source = self.data.get_source(source_url)
        source.write(data, mode)
    
    def query_document(self, source_url: str, conditions: Dict) -> List[Dict]:
        """Query document with conditions."""
        source = self.data.get_source(source_url)
        return source.query(conditions)
```

### 3. Sandbox Implementations (Testing)

Mock document sources for testing:

```python
# sandboxengine/policyengine/datasources_sandbox.py

class InMemoryDataSource(DataSource):
    """In-memory document for sandbox testing."""
    
    def __init__(self, schema: DocumentSchema, initial_data: List[Dict] = None):
        self.schema = schema
        self.data = initial_data or []
        self.write_log = []  # Track all writes for assertions
    
    def read(self, query: Optional[Dict] = None) -> List[Dict]:
        if query is None:
            return self.data.copy()
        
        # Simple filtering
        results = self.data
        if "limit" in query:
            results = results[:query["limit"]]
        if "filter" in query:
            results = [row for row in results if self._matches_filter(row, query["filter"])]
        return results
    
    def write(self, data: List[Dict], mode: str = "append") -> None:
        self.write_log.append({"data": data, "mode": mode})
        
        if mode == "append":
            self.data.extend(data)
        elif mode == "replace":
            self.data = data
        elif mode == "update":
            # Update by matching first column (ID)
            for new_row in data:
                key = list(new_row.values())[0]
                for i, existing_row in enumerate(self.data):
                    if list(existing_row.values())[0] == key:
                        self.data[i] = new_row
                        break
    
    def get_schema(self) -> DocumentSchema:
        return self.schema
    
    def query(self, conditions: Dict) -> List[Dict]:
        return [row for row in self.data if self._matches_filter(row, conditions)]
    
    def _matches_filter(self, row: Dict, filter_dict: Dict) -> bool:
        for key, value in filter_dict.items():
            if key not in row or row[key] != value:
                return False
        return True
```

### 4. Real Backend Implementations

Actual external service connectors:

```python
# policykit/policyengine/datasources_external.py (in real backend, not sandbox)

from google.oauth2 import service_account
from googleapiclient.discovery import build

class GoogleSheetsDataSource(DataSource):
    """Real Google Sheets integration."""
    
    def __init__(self, spreadsheet_url: str, credentials_path: str):
        self.url = spreadsheet_url
        self.spreadsheet_id = self._extract_id(spreadsheet_url)
        
        creds = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        self.service = build('sheets', 'v4', credentials=creds)
        self._cached_schema = None
    
    def read(self, query: Optional[Dict] = None) -> List[Dict]:
        sheet_name = query.get("sheet", "Sheet1") if query else "Sheet1"
        range_name = f"{sheet_name}!A:Z"
        
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=range_name
        ).execute()
        
        rows = result.get('values', [])
        if not rows:
            return []
        
        headers = rows[0]
        data = [dict(zip(headers, row)) for row in rows[1:]]
        
        # Apply query filters
        if query and "filter" in query:
            data = [row for row in data if self._matches_filter(row, query["filter"])]
        if query and "limit" in query:
            data = data[:query["limit"]]
        
        return data
    
    def write(self, data: List[Dict], mode: str = "append") -> None:
        sheet_name = "Sheet1"  # Could be configurable
        
        if mode == "append":
            headers = list(data[0].keys())
            rows = [[row.get(h, "") for h in headers] for row in data]
            
            body = {'values': rows}
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A:Z",
                valueInputOption='RAW',
                body=body
            ).execute()
        
        elif mode == "replace":
            # Clear and write
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A:Z"
            ).execute()
            
            headers = list(data[0].keys())
            rows = [headers] + [[row.get(h, "") for h in headers] for row in data]
            
            body = {'values': rows}
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption='RAW',
                body=body
            ).execute()
    
    def get_schema(self) -> DocumentSchema:
        if self._cached_schema:
            return self._cached_schema
        
        # Read first few rows to infer schema
        sample = self.read({"limit": 5})
        headers = list(sample[0].keys()) if sample else []
        
        self._cached_schema = DocumentSchema(
            source_type="google_sheets",
            source_url=self.url,
            structure={
                "columns": headers,
                "sheet_names": self._get_sheet_names(),
            },
            sample_data=sample,
            metadata={
                "spreadsheet_id": self.spreadsheet_id,
                "writable": True,
            }
        )
        return self._cached_schema
    
    def query(self, conditions: Dict) -> List[Dict]:
        # Use read() with filter
        return self.read({"filter": conditions})
    
    def _extract_id(self, url: str) -> str:
        # Extract spreadsheet ID from URL
        import re
        match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
        if match:
            return match.group(1)
        raise ValueError(f"Cannot extract spreadsheet ID from URL: {url}")
    
    def _get_sheet_names(self) -> List[str]:
        metadata = self.service.spreadsheets().get(
            spreadsheetId=self.spreadsheet_id
        ).execute()
        return [sheet['properties']['title'] for sheet in metadata.get('sheets', [])]
    
    def _matches_filter(self, row: Dict, filter_dict: Dict) -> bool:
        for key, value in filter_dict.items():
            if key not in row or row[key] != value:
                return False
        return True
```

---

## Pipeline Integration

### Phase 1: Document Discovery (Generation-time)

When user provides NL policy with document URLs, extract and analyze them:

```python
# sandboxengine/policyengine/tasks.py (additions)

class PipelineOrchestrator:
    def __init__(self, llm_client, document_fetcher):
        self.llm = llm_client
        self.doc_fetcher = document_fetcher
        self.document_schemas = {}
    
    async def generate_policy(self, nl_policy: str) -> Dict:
        # Step 0: Extract and analyze document URLs
        doc_urls = self._extract_document_urls(nl_policy)
        
        for url in doc_urls:
            schema = await self._fetch_document_schema(url)
            self.document_schemas[url] = schema
        
        # Step 1: Generate function headers (now with document context)
        headers = await self._generate_headers(nl_policy, self.document_schemas)
        
        # Steps 2-6: Continue as normal...
        # ...
    
    def _extract_document_urls(self, text: str) -> List[str]:
        """Extract Google Sheets, Notion, etc. URLs from text."""
        import re
        patterns = [
            r'https://docs\.google\.com/spreadsheets/d/[a-zA-Z0-9-_]+',
            r'https://www\.notion\.so/[a-zA-Z0-9-]+',
            r'https://airtable\.com/[a-zA-Z0-9-_/]+',
        ]
        
        urls = []
        for pattern in patterns:
            urls.extend(re.findall(pattern, text))
        return urls
    
    async def _fetch_document_schema(self, url: str) -> DocumentSchema:
        """Fetch document schema for LLM understanding."""
        # Create a sandbox data source to read the document
        source_type = self._infer_source_type(url)
        
        if source_type == "google_sheets":
            # Use read-only Google Sheets API
            source = GoogleSheetsDataSource(url, credentials_path="./credentials.json")
            return source.get_schema()
        
        # Add other source types...
        raise ValueError(f"Unsupported source type: {source_type}")
```

### Phase 2: LLM Prompt Enhancement

Inject document schemas into LLM prompts:

```python
# sandboxengine/policyengine/llm.py (additions)

def build_generation_prompt(nl_policy: str, document_schemas: Dict[str, DocumentSchema]) -> str:
    """Build prompt with document context."""
    
    prompt = f"""Generate a policy script for this natural language policy:

{nl_policy}

"""
    
    if document_schemas:
        prompt += "\n## External Documents\n\n"
        prompt += "The policy references these external documents:\n\n"
        
        for url, schema in document_schemas.items():
            prompt += f"**{schema.source_type}**: {url}\n"
            prompt += f"- Columns: {', '.join(schema.structure.get('columns', []))}\n"
            prompt += f"- Sample data:\n"
            for i, row in enumerate(schema.sample_data[:3]):
                prompt += f"  Row {i+1}: {row}\n"
            prompt += "\n"
        
        prompt += """
### How to access documents in your script:

```python
def setup(ctx):
    # Read all data
    data = ctx.read_document("URL")
    
    # Query with conditions
    filtered = ctx.query_document("URL", {"status": "pending"})
    
    # Write data (append, replace, or update)
    ctx.write_document("URL", [{"name": "Alice", "votes": 5}], mode="append")
```

Generate a script that properly uses these document APIs.
"""
    
    return prompt
```

### Phase 3: Test Generation with Mocked Documents

Generate tests that use in-memory documents:

```python
# sandboxengine/policyengine/tasks.py (test generation)

async def _generate_tests(self, headers: str, document_schemas: Dict) -> List[Scenario]:
    """Generate tests with mocked documents."""
    
    # Build prompt for test generation
    prompt = f"""Generate test scenarios for this policy.

Function headers:
{headers}

"""
    
    if document_schemas:
        prompt += "\n## Document Mocking\n\n"
        prompt += "Tests should use in-memory mocked documents. Setup format:\n\n"
        prompt += """
```python
{
    "documents": {
        "URL": {
            "schema": {...},
            "initial_data": [
                {"column1": "value1", "column2": "value2"},
                ...
            ]
        }
    }
}
```

Your test assertions can verify document writes:
- `document_written`: Check if data was written to document
- `document_contains`: Check if document contains specific data
"""
    
    # LLM generates scenarios...
    scenarios = await self.llm.generate_scenarios(prompt)
    return scenarios
```

### Phase 4: Sandbox Execution with Mocked Documents

Enhance `SandboxRunner` to handle document scenarios:

```python
# sandboxengine/policyengine/engine.py (additions)

class SandboxRunner:
    def run(self, script: str, scenario: Scenario) -> ScenarioResult:
        community = self._build_community(scenario.community_setup)
        event_bus = EventBus()
        
        # NEW: Setup document registry with mocked documents
        data_registry = self._build_document_registry(scenario.community_setup.get("documents", {}))
        
        ctx = PolicyContext(community, event_bus, data_registry)
        
        # ... rest of execution
    
    def _build_document_registry(self, document_config: Dict) -> DataSourceRegistry:
        """Create registry with in-memory mocked documents."""
        registry = DataSourceRegistry()
        
        for url, config in document_config.items():
            schema = DocumentSchema(**config["schema"])
            initial_data = config.get("initial_data", [])
            
            source = InMemoryDataSource(schema, initial_data)
            registry.register_source(url, source)
        
        return registry
    
    def _check_assertions(self, assertions: List[Assertion], community: Community, 
                         bus: EventBus, data_registry: DataSourceRegistry) -> List[Dict]:
        """Add document assertions."""
        results = []
        
        for assertion in assertions:
            if assertion.type == "document_written":
                url = assertion.expected["url"]
                source = data_registry.get_source(url)
                passed = len(source.write_log) > 0
                results.append({
                    "assertion": assertion.description,
                    "passed": passed,
                    "detail": f"{len(source.write_log)} writes"
                })
            
            elif assertion.type == "document_contains":
                url = assertion.expected["url"]
                conditions = assertion.expected["conditions"]
                source = data_registry.get_source(url)
                matching = source.query(conditions)
                passed = len(matching) > 0
                results.append({
                    "assertion": assertion.description,
                    "passed": passed,
                    "detail": f"found {len(matching)} matching rows"
                })
            
            else:
                # ... existing assertion types
                pass
        
        return results
```

---

## Backend Integration (Separate from Sandbox)

The real PolicyKit backend needs minimal changes:

```python
# policykit/policyengine/engine.py (in real backend)

class PolicyKitContext:
    """Real PolicyKit context with live document access."""
    
    def __init__(self, community, data_registry: DataSourceRegistry):
        self.community = community
        self.store = community.store
        self.data = data_registry  # Real sources, not mocked
        # ... other initialization
    
    # Same API as PolicyContext, but connects to real services
    def read_document(self, source_url: str, query: Optional[Dict] = None):
        return self.data.get_source(source_url).read(query)

# Configuration in policykit/settings.py
DATA_SOURCE_FACTORIES = {
    "google_sheets": lambda url: GoogleSheetsDataSource(
        url, 
        credentials_path=os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    ),
    # Register other source types...
}

# Initialize registry on startup
def get_data_registry():
    registry = DataSourceRegistry()
    for source_type, factory in DATA_SOURCE_FACTORIES.items():
        registry.register_factory(source_type, factory)
    return registry
```

---

## Security and Access Control

### 1. URL Allowlisting

Only allow documents from approved domains:

```python
# sandboxengine/sandboxengine/settings.py

ALLOWED_DOCUMENT_DOMAINS = [
    "docs.google.com",
    "notion.so",
    "airtable.com",
]

def validate_document_url(url: str) -> bool:
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    return any(allowed in domain for allowed in ALLOWED_DOCUMENT_DOMAINS)
```

### 2. Credential Management

Store credentials securely:

```python
# In real backend (not sandbox):
# - Use environment variables or secret managers
# - Never expose credentials in generated scripts
# - Use service accounts with minimal permissions

# Example: Google Sheets credentials
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON")
```

### 3. Rate Limiting

Prevent abuse of external APIs:

```python
# sandboxengine/policyengine/datasources.py

class RateLimitedDataSource(DataSource):
    """Wraps a data source with rate limiting."""
    
    def __init__(self, inner: DataSource, max_requests_per_minute: int = 60):
        self.inner = inner
        self.max_rpm = max_requests_per_minute
        self.request_times = []
    
    def read(self, query):
        self._check_rate_limit()
        return self.inner.read(query)
    
    def write(self, data, mode):
        self._check_rate_limit()
        return self.inner.write(data, mode)
    
    def _check_rate_limit(self):
        import time
        now = time.time()
        # Remove requests older than 1 minute
        self.request_times = [t for t in self.request_times if now - t < 60]
        
        if len(self.request_times) >= self.max_rpm:
            raise Exception(f"Rate limit exceeded: {self.max_rpm} requests/minute")
        
        self.request_times.append(now)
```

---

## Example: Generated Script with Document Access

### Natural Language Policy

```
When a user posts a message in #proposals, add their proposal to the 
"Community Proposals" spreadsheet at https://docs.google.com/spreadsheets/d/abc123.
The spreadsheet tracks: author, proposal_text, timestamp, status.
Set status to "pending" initially.

Every day at 9am, check the spreadsheet for proposals with status="pending" 
for more than 7 days. Post a reminder in #governance to vote on them.
```

### Generated Script

```python
PROPOSAL_SHEET = "https://docs.google.com/spreadsheets/d/abc123"

def setup(ctx):
    ctx.on("message", handle_proposal)
    ctx.schedule(86400, check_old_proposals, recurring=True)  # Daily

def handle_proposal(event, ctx):
    if event.data.get("channel") != "proposals":
        return
    
    author = event.data.get("author")
    text = event.data.get("text")
    
    # Write to spreadsheet
    ctx.write_document(PROPOSAL_SHEET, [{
        "author": author,
        "proposal_text": text,
        "timestamp": ctx.current_time,
        "status": "pending"
    }], mode="append")
    
    # Confirm to user
    ctx.post_message(
        "proposals",
        f"@{author} Your proposal has been recorded! Track it in the spreadsheet.",
        author_id="__system__"
    )

def check_old_proposals(ctx):
    import time
    cutoff_time = ctx.current_time - (7 * 86400)  # 7 days ago
    
    # Query pending proposals
    proposals = ctx.query_document(PROPOSAL_SHEET, {"status": "pending"})
    
    old_proposals = [
        p for p in proposals 
        if float(p.get("timestamp", 0)) < cutoff_time
    ]
    
    if old_proposals:
        authors = [p["author"] for p in old_proposals]
        ctx.post_message(
            "governance",
            f"⏰ Reminder: {len(old_proposals)} proposals need votes: {', '.join(authors)}",
            author_id="__system__"
        )
```

### Generated Test Scenario

```python
{
    "name": "proposal_tracking",
    "description": "Test proposal spreadsheet integration",
    "community_setup": {
        "users": [{"id": "alice", "name": "Alice"}],
        "channels": [{"id": "proposals", "name": "proposals"}],
        "documents": {
            "https://docs.google.com/spreadsheets/d/abc123": {
                "schema": {
                    "source_type": "google_sheets",
                    "source_url": "https://docs.google.com/spreadsheets/d/abc123",
                    "structure": {
                        "columns": ["author", "proposal_text", "timestamp", "status"]
                    },
                    "sample_data": [],
                    "metadata": {}
                },
                "initial_data": []
            }
        }
    },
    "events": [
        {
            "type": "message",
            "data": {
                "channel": "proposals",
                "author": "alice",
                "text": "Let's add a code of conduct"
            },
            "at": 100.0
        },
        {
            "type": "__tick__",
            "at": 100.0 + (8 * 86400)  # 8 days later
        }
    ],
    "assertions": [
        {
            "type": "document_contains",
            "expected": {
                "url": "https://docs.google.com/spreadsheets/d/abc123",
                "conditions": {"author": "alice", "status": "pending"}
            },
            "description": "Proposal added to spreadsheet"
        },
        {
            "type": "message_posted",
            "expected": {
                "channel_id": "governance",
                "contains": "proposals need votes"
            },
            "description": "Reminder posted after 7 days"
        }
    ]
}
```

---

## Implementation Order

| Step | Component | Files to Create/Modify |
|------|-----------|----------------------|
| 1 | Abstract data source layer | `policyengine/datasources.py` |
| 2 | In-memory mock implementation | `policyengine/datasources_sandbox.py` |
| 3 | PolicyContext extension | `policyengine/engine.py` |
| 4 | Document URL extraction | `policyengine/tasks.py` |
| 5 | Generation-time fetcher | `policyengine/tasks.py` + add Google Sheets read-only |
| 6 | LLM prompt enhancement | `policyengine/llm.py` |
| 7 | Test generation with docs | `policyengine/tasks.py` |
| 8 | Sandbox runner updates | `policyengine/engine.py` |
| 9 | Document assertions | `policyengine/engine.py` |
| 10 | Real backend: Google Sheets | `policykit/policyengine/datasources_external.py` (in main PK repo) |
| 11 | Real backend: integration | `policykit/policyengine/engine.py` (in main PK repo) |
| 12 | API reference docs | `docs/api_reference.md` update |
| 13 | Policy authoring guide | `docs/policy-authoring-guide.md` update |

---

## Testing Strategy

### Unit Tests

```python
# tests/test_datasources.py

def test_in_memory_source():
    schema = DocumentSchema(
        source_type="test",
        source_url="test://example",
        structure={"columns": ["name", "age"]},
        sample_data=[],
        metadata={}
    )
    
    source = InMemoryDataSource(schema, [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25}
    ])
    
    # Test read
    data = source.read()
    assert len(data) == 2
    
    # Test query
    filtered = source.query({"name": "Alice"})
    assert len(filtered) == 1
    assert filtered[0]["age"] == 30
    
    # Test write (append)
    source.write([{"name": "Charlie", "age": 35}], mode="append")
    assert len(source.data) == 3
    
    # Verify write log
    assert len(source.write_log) == 1
```

### Integration Tests

```python
# tests/test_document_pipeline.py

async def test_document_policy_generation():
    """Test full pipeline with document URL."""
    
    nl_policy = """
    When a message is posted in #tracking, log it to this spreadsheet:
    https://docs.google.com/spreadsheets/d/test123
    """
    
    orchestrator = PipelineOrchestrator(llm, doc_fetcher)
    result = await orchestrator.generate_policy(nl_policy)
    
    # Verify document schema was fetched
    assert "test123" in [s.source_url for s in orchestrator.document_schemas.values()]
    
    # Verify generated script uses document API
    assert "ctx.write_document" in result["script"]
    
    # Verify tests include document setup
    assert "documents" in result["scenarios"][0].community_setup
```

### End-to-End Tests

```python
# tests/test_e2e_documents.py

def test_spreadsheet_policy_execution():
    """Test policy execution with mocked spreadsheet."""
    
    script = """
def setup(ctx):
    ctx.on("message", log_message)

def log_message(event, ctx):
    ctx.write_document("test://sheet", [{
        "text": event.data.get("text"),
        "author": event.data.get("author")
    }], mode="append")
"""
    
    scenario = Scenario(
        name="test",
        community_setup={
            "users": [{"id": "alice"}],
            "channels": [{"id": "general"}],
            "documents": {
                "test://sheet": {
                    "schema": {...},
                    "initial_data": []
                }
            }
        },
        events=[
            ScenarioEvent(type="message", data={"text": "hello", "author": "alice"}, at=1.0)
        ],
        assertions=[
            Assertion(type="document_contains", expected={
                "url": "test://sheet",
                "conditions": {"text": "hello"}
            })
        ]
    )
    
    runner = SandboxRunner()
    result = runner.run(script, scenario)
    
    assert result.passed
```

---

## Future Enhancements

### 1. Schema Evolution Tracking

Detect when document schemas change and notify policy authors:

```python
class SchemaChangeDetector:
    def detect_changes(self, old_schema: DocumentSchema, new_schema: DocumentSchema):
        changes = []
        
        old_cols = set(old_schema.structure.get("columns", []))
        new_cols = set(new_schema.structure.get("columns", []))
        
        added = new_cols - old_cols
        removed = old_cols - new_cols
        
        if added:
            changes.append(f"Columns added: {added}")
        if removed:
            changes.append(f"Columns removed: {removed}")
        
        return changes
```

### 2. Document Access Analytics

Track which policies use which documents:

```python
class DocumentUsageTracker:
    def log_access(self, policy_id: str, source_url: str, operation: str):
        # Log to analytics database
        pass
    
    def get_usage_report(self, source_url: str):
        # Return which policies depend on this document
        pass
```

### 3. Multi-Document Joins

Support queries across multiple documents:

```python
def setup(ctx):
    users = ctx.read_document(USERS_SHEET)
    proposals = ctx.read_document(PROPOSALS_SHEET)
    
    # Join data
    enriched = []
    for proposal in proposals:
        author_info = next(u for u in users if u["id"] == proposal["author_id"])
        enriched.append({**proposal, "author_name": author_info["name"]})
```

### 4. Document Webhooks

React to document changes:

```python
# External webhook endpoint
@app.post("/webhooks/sheets/{sheet_id}")
async def handle_sheet_change(sheet_id: str, change: Dict):
    # Trigger policy re-evaluation
    event_bus.emit(Event(type="document_changed", data={
        "source_url": f"sheets/{sheet_id}",
        "changes": change
    }))
```

### 5. Caching Layer

Cache document reads to reduce API calls:

```python
class CachedDataSource(DataSource):
    def __init__(self, inner: DataSource, ttl_seconds: int = 300):
        self.inner = inner
        self.cache = {}
        self.ttl = ttl_seconds
    
    def read(self, query):
        cache_key = hash(str(query))
        
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.ttl:
                return data
        
        data = self.inner.read(query)
        self.cache[cache_key] = (data, time.time())
        return data
```

---

## Documentation Updates

### API Reference Addition

```markdown
## Document Access

### ctx.read_document(source_url, query=None)

Read data from an external document.

**Parameters:**
- `source_url` (str): URL of the document
- `query` (dict, optional): Query filters
  - `limit`: Maximum rows to return
  - `filter`: Dictionary of column conditions
  - `sheet`: Sheet name (for spreadsheets)

**Returns:** List[Dict[str, Any]]

**Example:**
```python
# Read all data
data = ctx.read_document("https://docs.google.com/spreadsheets/d/abc123")

# Read with filters
pending = ctx.read_document(
    "https://docs.google.com/spreadsheets/d/abc123",
    query={"filter": {"status": "pending"}, "limit": 10}
)
```

### ctx.write_document(source_url, data, mode="append")

Write data to an external document.

**Parameters:**
- `source_url` (str): URL of the document
- `data` (List[Dict]): Rows to write
- `mode` (str): Write mode
  - `"append"`: Add rows to end
  - `"replace"`: Replace all data
  - `"update"`: Update matching rows

**Example:**
```python
ctx.write_document(
    "https://docs.google.com/spreadsheets/d/abc123",
    [{"name": "Alice", "votes": 5}],
    mode="append"
)
```
```

---

## Summary

This plan enables:

1. ✅ **Generation-time context**: LLM reads document structure to generate appropriate code
2. ✅ **Testing isolation**: Sandbox uses in-memory mocks to validate behavior
3. ✅ **Runtime integration**: Real backend connects to actual external services
4. ✅ **Portable abstraction**: Same script runs in sandbox and production
5. ✅ **Security**: URL validation, credential management, rate limiting
6. ✅ **Extensibility**: Easy to add new document types (Notion, Airtable, etc.)

The abstraction layer keeps the sandbox standalone while ensuring generated scripts work identically in the real PolicyKit backend.
