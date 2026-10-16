# Google Sheets Implementation Plan

## Architecture Overview

```
User writes policy with Sheet URL
        ↓
Frontend captures URL
        ↓
Frontend: User signs into Google OAuth
        ↓
Frontend fetches Sheet data via Google Sheets API
        ↓
Frontend sends to Sandbox API: {nl_policy, document_data}
        ↓
Sandbox: Inject document data into LLM prompts
        ↓
Sandbox: Generate script with ctx.read_document(url)
        ↓
Sandbox: Generate tests with mocked document data
        ↓
Sandbox: Execute tests against in-memory DataSource
```

**Key Constraint**: Sandbox has **no Google credentials**. All document data comes pre-fetched from the frontend.

---

## Part 1: Data Extraction Utility Script

### Purpose

A standalone script for **developers** to:
1. Fetch Google Sheets data for testing
2. Generate example payloads for API testing
3. Understand the data format frontend will provide

### Script: `scripts/fetch_google_sheet.py`

```python
#!/usr/bin/env python3
"""
Fetch Google Sheets data for testing external document integration.

Usage:
    python scripts/fetch_google_sheet.py <spreadsheet_url>
    
The script will:
1. Open a browser for Google OAuth
2. Fetch the spreadsheet data
3. Output JSON that can be used in API testing
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import os.path
import re

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
TOKEN_PATH = '.google_sheets_token.pickle'


def extract_spreadsheet_id(url: str) -> str:
    """Extract spreadsheet ID from Google Sheets URL."""
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    if not match:
        raise ValueError(f"Cannot extract spreadsheet ID from URL: {url}")
    return match.group(1)


def get_credentials() -> Credentials:
    """Get Google OAuth credentials, prompting user if needed."""
    creds = None
    
    # Check for existing token
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, prompt user to sign in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Need to have credentials.json from Google Cloud Console
            if not os.path.exists('credentials.json'):
                print("ERROR: credentials.json not found!")
                print("\nTo get credentials.json:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Create a project (or select existing)")
                print("3. Enable Google Sheets API")
                print("4. Create OAuth 2.0 credentials (Desktop app)")
                print("5. Download as credentials.json")
                print("6. Place in the same directory as this script")
                sys.exit(1)
            
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next run
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)
    
    return creds


def fetch_sheet_metadata(service, spreadsheet_id: str) -> Dict[str, Any]:
    """Fetch spreadsheet metadata (title, sheet names, etc.)."""
    spreadsheet = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id
    ).execute()
    
    return {
        'title': spreadsheet.get('properties', {}).get('title', 'Untitled'),
        'sheets': [
            {
                'name': sheet['properties']['title'],
                'id': sheet['properties']['sheetId'],
                'row_count': sheet['properties']['gridProperties'].get('rowCount', 0),
                'col_count': sheet['properties']['gridProperties'].get('columnCount', 0),
            }
            for sheet in spreadsheet.get('sheets', [])
        ],
        'url': f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
    }


def fetch_sheet_data(
    service, 
    spreadsheet_id: str, 
    sheet_name: str = None,
    max_rows: int = 100
) -> Dict[str, Any]:
    """
    Fetch data from a specific sheet.
    
    Returns structured data with headers and rows.
    """
    # If no sheet name, use first sheet
    if sheet_name is None:
        metadata = fetch_sheet_metadata(service, spreadsheet_id)
        sheet_name = metadata['sheets'][0]['name']
    
    # Fetch data
    range_name = f"{sheet_name}!A1:ZZ{max_rows}"
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name
    ).execute()
    
    rows = result.get('values', [])
    
    if not rows:
        return {
            'sheet_name': sheet_name,
            'headers': [],
            'rows': [],
            'row_count': 0,
        }
    
    # First row is headers
    headers = rows[0]
    data_rows = rows[1:]
    
    # Convert to list of dicts
    structured_rows = []
    for row in data_rows:
        # Pad row if it has fewer columns than headers
        padded_row = row + [''] * (len(headers) - len(row))
        row_dict = dict(zip(headers, padded_row))
        structured_rows.append(row_dict)
    
    return {
        'sheet_name': sheet_name,
        'headers': headers,
        'rows': structured_rows,
        'row_count': len(structured_rows),
    }


def fetch_all_sheets(
    service,
    spreadsheet_id: str,
    max_rows_per_sheet: int = 100
) -> Dict[str, Any]:
    """Fetch data from all sheets in the spreadsheet."""
    metadata = fetch_sheet_metadata(service, spreadsheet_id)
    
    sheets_data = []
    for sheet_info in metadata['sheets']:
        sheet_name = sheet_info['name']
        print(f"  Fetching sheet: {sheet_name}")
        
        sheet_data = fetch_sheet_data(
            service, 
            spreadsheet_id, 
            sheet_name,
            max_rows_per_sheet
        )
        sheets_data.append(sheet_data)
    
    return {
        'metadata': metadata,
        'sheets': sheets_data,
    }


def generate_document_schema(spreadsheet_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate DocumentSchema format for sandbox.
    
    This is what the frontend should send to the sandbox API.
    """
    metadata = spreadsheet_data['metadata']
    sheets = spreadsheet_data['sheets']
    
    # Use first sheet as primary data source
    primary_sheet = sheets[0] if sheets else {
        'headers': [], 'rows': [], 'sheet_name': 'Sheet1'
    }
    
    # Sample data: first 5 rows
    sample_data = primary_sheet['rows'][:5]
    
    return {
        'source_type': 'google_sheets',
        'source_url': metadata['url'],
        'structure': {
            'spreadsheet_title': metadata['title'],
            'sheet_names': [s['name'] for s in metadata['sheets']],
            'columns': primary_sheet['headers'],
            'primary_sheet': primary_sheet['sheet_name'],
        },
        'sample_data': sample_data,
        'metadata': {
            'spreadsheet_id': extract_spreadsheet_id(metadata['url']),
            'total_sheets': len(metadata['sheets']),
            'row_count': primary_sheet['row_count'],
            'col_count': len(primary_sheet['headers']),
            'writable': False,  # Sandbox always treats as read-only
        }
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python fetch_google_sheet.py <spreadsheet_url>")
        print("\nExample:")
        print("  python fetch_google_sheet.py https://docs.google.com/spreadsheets/d/1ABC.../edit")
        sys.exit(1)
    
    url = sys.argv[1]
    
    print(f"Fetching Google Sheet: {url}\n")
    
    # Extract spreadsheet ID
    try:
        spreadsheet_id = extract_spreadsheet_id(url)
        print(f"Spreadsheet ID: {spreadsheet_id}")
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    
    # Get credentials
    print("\nAuthenticating with Google...")
    creds = get_credentials()
    
    # Build service
    service = build('sheets', 'v4', credentials=creds)
    
    # Fetch data
    print("\nFetching spreadsheet data...")
    spreadsheet_data = fetch_all_sheets(service, spreadsheet_id, max_rows_per_sheet=100)
    
    # Generate schema for sandbox
    document_schema = generate_document_schema(spreadsheet_data)
    
    # Output results
    print("\n" + "="*60)
    print("SPREADSHEET METADATA")
    print("="*60)
    print(json.dumps(spreadsheet_data['metadata'], indent=2))
    
    print("\n" + "="*60)
    print("DOCUMENT SCHEMA (for sandbox API)")
    print("="*60)
    print(json.dumps(document_schema, indent=2))
    
    print("\n" + "="*60)
    print("SAMPLE DATA")
    print("="*60)
    for sheet in spreadsheet_data['sheets']:
        print(f"\nSheet: {sheet['sheet_name']}")
        print(f"Headers: {sheet['headers']}")
        print(f"Rows: {sheet['row_count']}")
        if sheet['rows']:
            print(f"First row: {sheet['rows'][0]}")
    
    # Save to file
    output_file = f"google_sheet_{spreadsheet_id}.json"
    with open(output_file, 'w') as f:
        json.dumps({
            'full_data': spreadsheet_data,
            'document_schema': document_schema,
        }, f, indent=2)
    
    print(f"\n✅ Data saved to: {output_file}")
    print(f"\nTo use in API testing:")
    print(f"  POST /api/generate_policy")
    print(f"  Body: {{")
    print(f"    \"nl_policy\": \"...\",")
    print(f"    \"documents\": [{{...document_schema...}}]")
    print(f"  }}")


if __name__ == '__main__':
    main()
```

### Installation

```bash
# In sandbox directory
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

# Create scripts directory
mkdir -p scripts
# Place fetch_google_sheet.py in scripts/

# Get credentials.json from Google Cloud Console
# Place in sandbox root directory
```

### Usage

```bash
# Fetch a Google Sheet
python scripts/fetch_google_sheet.py "https://docs.google.com/spreadsheets/d/1ABC.../edit"

# Output: google_sheet_1ABC.json
```

---

## Part 2: API Payload Format

### Request Format

When the frontend sends a policy with external documents:

```json
{
  "nl_policy": "When a user posts in #proposals, log it to the tracking sheet",
  "documents": [
    {
      "source_type": "google_sheets",
      "source_url": "https://docs.google.com/spreadsheets/d/abc123/edit",
      "structure": {
        "spreadsheet_title": "Community Proposals Tracker",
        "sheet_names": ["Proposals", "Archive"],
        "columns": ["author", "text", "timestamp", "status", "votes"],
        "primary_sheet": "Proposals"
      },
      "sample_data": [
        {"author": "alice", "text": "Add a code of conduct", "timestamp": "2024-01-01", "status": "pending", "votes": "3"},
        {"author": "bob", "text": "Change meeting time", "timestamp": "2024-01-02", "status": "approved", "votes": "8"}
      ],
      "metadata": {
        "spreadsheet_id": "abc123",
        "total_sheets": 2,
        "row_count": 15,
        "col_count": 5,
        "writable": false
      }
    }
  ],
  "options": {
    "generate_document_tests": true
  }
}
```

### Response Format

```json
{
  "pipeline_id": "pipe-12345",
  "status": "success",
  "script": "def setup(ctx): ...",
  "scenarios": [
    {
      "name": "basic_flow",
      "type": "standard",
      "...": "..."
    },
    {
      "name": "document_read_test",
      "type": "document",
      "...": "..."
    },
    {
      "name": "document_write_test", 
      "type": "document",
      "...": "..."
    }
  ],
  "document_usage": {
    "https://docs.google.com/spreadsheets/d/abc123/edit": {
      "reads": 2,
      "writes": 1,
      "queries": 1
    }
  }
}
```

---

## Part 3: Sandbox API Changes

### Modify `api_views.py`

```python
# sandboxengine/sandboxengine/api_views.py

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class DocumentData(BaseModel):
    """External document data provided by frontend."""
    source_type: str = Field(..., description="Type of document source")
    source_url: str = Field(..., description="URL of the document")
    structure: Dict[str, Any] = Field(..., description="Document structure")
    sample_data: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class GeneratePolicyRequest(BaseModel):
    nl_policy: str = Field(..., description="Natural language policy")
    documents: List[DocumentData] = Field(
        default_factory=list,
        description="External documents referenced in the policy"
    )
    options: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Generation options"
    )

@app.post("/api/generate_policy")
async def generate_policy(request: GeneratePolicyRequest):
    """
    Generate a policy script from natural language.
    
    If documents are provided, they are:
    1. Injected into LLM prompts for context
    2. Used to generate document-aware test scenarios
    3. Mocked in test execution with in-memory data sources
    """
    # Convert DocumentData to internal DocumentSchema format
    document_schemas = {}
    for doc in request.documents:
        document_schemas[doc.source_url] = DocumentSchema(
            source_type=doc.source_type,
            source_url=doc.source_url,
            structure=doc.structure,
            sample_data=doc.sample_data,
            metadata=doc.metadata
        )
    
    # Run pipeline with document context
    orchestrator = PipelineOrchestrator(llm_client, document_schemas)
    result = await orchestrator.generate_policy(
        request.nl_policy,
        generate_document_tests=request.options.get("generate_document_tests", True)
    )
    
    return result
```

---

## Part 4: Generation Prompt Changes

### Enhanced Header Generation

```python
# sandboxengine/policyengine/llm.py

def build_header_generation_prompt(
    nl_policy: str, 
    document_schemas: Dict[str, DocumentSchema]
) -> str:
    """Build prompt for generating function headers."""
    
    prompt = f"""Generate function headers for this policy:

{nl_policy}

"""
    
    if document_schemas:
        prompt += "\n## External Documents Referenced\n\n"
        prompt += "This policy references the following external documents:\n\n"
        
        for url, schema in document_schemas.items():
            prompt += f"### {schema.source_type}: {schema.structure.get('spreadsheet_title', 'Untitled')}\n"
            prompt += f"**URL**: {url}\n"
            prompt += f"**Columns**: {', '.join(schema.structure.get('columns', []))}\n"
            
            if schema.sample_data:
                prompt += f"\n**Sample Data** (first {len(schema.sample_data)} rows):\n"
                prompt += "```json\n"
                prompt += json.dumps(schema.sample_data, indent=2)
                prompt += "\n```\n"
            
            prompt += "\n**Sheet Names**: " + ", ".join(schema.structure.get('sheet_names', [])) + "\n"
            prompt += "\n"
        
        prompt += """
### How to Access Documents in Generated Code

Use these PolicyContext methods:

```python
# Read all data (returns List[Dict])
data = ctx.read_document("URL")

# Query with filters
filtered = ctx.query_document("URL", {
    "status": "pending",
    "votes": ">5"
})

# Write data (append to sheet)
ctx.write_document("URL", [
    {"author": "alice", "text": "...", "timestamp": ctx.current_time, "status": "pending"}
], mode="append")

# Specify sheet name for multi-sheet spreadsheets
data = ctx.read_document("URL", query={"sheet": "Archive"})
```

**Important**: 
- Column names in your code must match the columns shown above
- Sample data shows the format/types expected
- Write operations should match the schema structure
"""
    
    return prompt


def build_script_generation_prompt(
    nl_policy: str,
    headers: str,
    document_schemas: Dict[str, DocumentSchema]
) -> str:
    """Build prompt for generating the full script."""
    
    prompt = f"""Generate a complete policy script.

## Natural Language Policy
{nl_policy}

## Function Headers (implement these)
```python
{headers}
```

"""
    
    if document_schemas:
        prompt += "\n## External Documents\n\n"
        
        # Create URL constants
        prompt += "Define URL constants at the top of your script:\n```python\n"
        for i, url in enumerate(document_schemas.keys()):
            schema = document_schemas[url]
            title = schema.structure.get('spreadsheet_title', f'Document{i}')
            const_name = title.upper().replace(' ', '_').replace('-', '_') + '_URL'
            prompt += f'{const_name} = "{url}"\n'
        prompt += "```\n\n"
        
        # Show available columns for each document
        for url, schema in document_schemas.items():
            prompt += f"**Document**: {schema.structure.get('spreadsheet_title', 'Untitled')}\n"
            prompt += f"**Columns**: `{', '.join(['\"' + c + '\"' for c in schema.structure.get('columns', [])])}`\n"
            prompt += "\n"
    
    prompt += """
## Implementation Requirements

1. Implement all functions from the headers
2. Use ctx.read_document(), ctx.write_document(), ctx.query_document() for external data
3. Match column names exactly as shown above
4. Handle edge cases (empty results, missing columns, etc.)
5. Use URL constants defined above

Generate the complete script now.
"""
    
    return prompt
```

---

## Part 5: Document-Specific Test Generation

### Strategy

Generate **additional** tests specifically for document operations, **separate from** the standard 3-5 behavioral tests.

```python
# sandboxengine/policyengine/tasks.py

class PipelineOrchestrator:
    async def generate_policy(
        self, 
        nl_policy: str,
        generate_document_tests: bool = True
    ) -> Dict:
        
        # Step 0: Process document schemas (already provided by frontend)
        # (no fetching needed, already in self.document_schemas)
        
        # Step 1: Generate headers with document context
        headers = await self._generate_headers(nl_policy, self.document_schemas)
        
        # Step 2: Generate script
        script = await self._generate_script(nl_policy, headers, self.document_schemas)
        
        # Step 3: Generate standard behavioral tests (3-5 tests)
        standard_tests = await self._generate_standard_tests(headers, self.document_schemas)
        
        # Step 3b: Generate document-specific tests (if documents present)
        document_tests = []
        if generate_document_tests and self.document_schemas:
            document_tests = await self._generate_document_tests(
                headers, 
                self.document_schemas
            )
        
        all_tests = standard_tests + document_tests
        
        # Step 4-6: Execute, revise, report (same as before)
        results = await self._execute_tests(script, all_tests)
        # ...
    
    async def _generate_document_tests(
        self,
        headers: str,
        document_schemas: Dict[str, DocumentSchema]
    ) -> List[Scenario]:
        """
        Generate tests specifically for document operations.
        
        These tests verify:
        - Reading from documents works correctly
        - Writing to documents produces expected output
        - Querying/filtering works as intended
        - Edge cases (empty results, malformed data)
        """
        
        prompt = f"""Generate test scenarios for external document operations.

## Function Headers
```python
{headers}
```

## External Documents
"""
        
        for url, schema in document_schemas.items():
            prompt += f"\n### {schema.structure.get('spreadsheet_title', 'Document')}\n"
            prompt += f"**URL**: {url}\n"
            prompt += f"**Columns**: {schema.structure.get('columns', [])}\n"
            prompt += f"**Sample Data**:\n```json\n{json.dumps(schema.sample_data, indent=2)}\n```\n"
        
        prompt += """
## Test Requirements

Generate 2-3 test scenarios that specifically test document operations:

1. **Read Test**: Verify the policy reads document data correctly
   - Setup: Populate document with known data
   - Event: Trigger that causes policy to read document
   - Assert: Policy uses document data correctly

2. **Write Test**: Verify the policy writes to document correctly
   - Setup: Start with empty or known document state
   - Event: Trigger that causes policy to write
   - Assert: Document contains expected written data

3. **Query Test** (optional): Verify filtering/querying works
   - Setup: Document with mixed data
   - Event: Trigger that should query subset
   - Assert: Only matching data is used

## Test Format

Each test scenario should include a `documents` section in `community_setup`:

```json
{
  "name": "test_document_read",
  "description": "Verify policy reads document data correctly",
  "community_setup": {
    "users": [...],
    "channels": [...],
    "documents": {
      "URL": {
        "schema": {...},
        "initial_data": [
          {"col1": "val1", "col2": "val2"},
          ...
        ]
      }
    }
  },
  "events": [...],
  "assertions": [
    {
      "type": "document_contains",
      "expected": {
        "url": "URL",
        "conditions": {"col1": "expected_value"}
      },
      "description": "Document should contain written data"
    }
  ]
}
```

Generate the test scenarios now.
"""
        
        # Call LLM to generate document tests
        document_tests_json = await self.llm.generate_scenarios(prompt)
        
        # Parse and return
        scenarios = [Scenario(**test) for test in document_tests_json]
        
        # Mark as document tests (for reporting)
        for scenario in scenarios:
            scenario.test_type = "document"  # vs. "standard"
        
        return scenarios
```

### Test Execution Flow

```python
# sandboxengine/policyengine/engine.py

class SandboxRunner:
    def run(self, script: str, scenario: Scenario) -> ScenarioResult:
        # Build community
        community = self._build_community(scenario.community_setup)
        event_bus = EventBus()
        
        # NEW: Build document registry from scenario
        document_registry = self._build_document_registry(
            scenario.community_setup.get("documents", {})
        )
        
        # Create context with document access
        ctx = PolicyContext(community, event_bus, document_registry)
        
        # Execute setup, replay events, check assertions
        # ...
        
        # Include document state in results
        result.document_state = {
            url: {
                "data": source.data,
                "writes": source.write_log
            }
            for url, source in document_registry._sources.items()
        }
        
        return result
    
    def _build_document_registry(
        self, 
        documents_config: Dict[str, Any]
    ) -> DataSourceRegistry:
        """
        Build in-memory document registry from test scenario.
        
        Format:
        {
          "URL": {
            "schema": {...},
            "initial_data": [...]
          }
        }
        """
        registry = DataSourceRegistry()
        
        for url, config in documents_config.items():
            schema = DocumentSchema(**config["schema"])
            initial_data = config.get("initial_data", [])
            
            # Create in-memory mock
            source = InMemoryDataSource(schema, initial_data.copy())
            registry.register_source(url, source)
        
        return registry
```

---

## Part 6: Example Test Case

### Natural Language Policy

```
When a user posts a message in #proposals, log it to the Community Proposals 
spreadsheet at https://docs.google.com/spreadsheets/d/abc123/edit.

Each row should have: author, proposal_text, timestamp, status (set to "pending"), votes (set to 0).
```

### Document Schema (from frontend)

```json
{
  "source_type": "google_sheets",
  "source_url": "https://docs.google.com/spreadsheets/d/abc123/edit",
  "structure": {
    "spreadsheet_title": "Community Proposals",
    "sheet_names": ["Proposals", "Archive"],
    "columns": ["author", "proposal_text", "timestamp", "status", "votes"],
    "primary_sheet": "Proposals"
  },
  "sample_data": [
    {"author": "alice", "proposal_text": "Add CoC", "timestamp": "2024-01-01", "status": "approved", "votes": "8"},
    {"author": "bob", "proposal_text": "New logo", "timestamp": "2024-01-02", "status": "pending", "votes": "3"}
  ],
  "metadata": {
    "spreadsheet_id": "abc123",
    "total_sheets": 2,
    "row_count": 12,
    "col_count": 5
  }
}
```

### Generated Standard Test (behavioral)

```python
{
  "name": "log_proposal_on_message",
  "description": "Verify proposal is logged when message posted",
  "community_setup": {
    "users": [{"id": "alice", "name": "Alice"}],
    "channels": [{"id": "proposals", "name": "proposals"}],
    "documents": {
      "https://docs.google.com/spreadsheets/d/abc123/edit": {
        "schema": {
          "source_type": "google_sheets",
          "source_url": "https://docs.google.com/spreadsheets/d/abc123/edit",
          "structure": {"columns": ["author", "proposal_text", "timestamp", "status", "votes"]},
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
      "data": {"channel": "proposals", "author": "alice", "text": "Let's add a code of conduct"},
      "at": 100.0
    }
  ],
  "assertions": [
    {
      "type": "document_contains",
      "expected": {
        "url": "https://docs.google.com/spreadsheets/d/abc123/edit",
        "conditions": {
          "author": "alice",
          "proposal_text": "Let's add a code of conduct",
          "status": "pending"
        }
      },
      "description": "Proposal should be logged to spreadsheet"
    }
  ]
}
```

### Generated Document Test (additional)

```python
{
  "name": "document_write_formats_correctly",
  "description": "Verify written data matches schema format",
  "test_type": "document",
  "community_setup": {
    "users": [{"id": "bob", "name": "Bob"}],
    "channels": [{"id": "proposals", "name": "proposals"}],
    "documents": {
      "https://docs.google.com/spreadsheets/d/abc123/edit": {
        "schema": {...},
        "initial_data": []
      }
    }
  },
  "events": [
    {
      "type": "message",
      "data": {"channel": "proposals", "author": "bob", "text": "Test proposal"},
      "at": 50.0
    }
  ],
  "assertions": [
    {
      "type": "document_written",
      "expected": {"url": "https://docs.google.com/spreadsheets/d/abc123/edit"},
      "description": "Document should have received a write"
    },
    {
      "type": "document_row_matches_schema",
      "expected": {
        "url": "https://docs.google.com/spreadsheets/d/abc123/edit",
        "required_columns": ["author", "proposal_text", "timestamp", "status", "votes"]
      },
      "description": "Written row should have all required columns"
    },
    {
      "type": "document_contains",
      "expected": {
        "url": "https://docs.google.com/spreadsheets/d/abc123/edit",
        "conditions": {"votes": "0"}
      },
      "description": "votes should be initialized to 0"
    }
  ]
}
```

---

## Part 7: New Assertion Types

### Document Assertions

```python
# sandboxengine/policyengine/engine.py

class SandboxRunner:
    def _evaluate_assertion(
        self,
        assertion: Assertion,
        community: Community,
        bus: EventBus,
        data_registry: DataSourceRegistry
    ) -> dict:
        
        # ... existing assertion types ...
        
        # NEW: Document assertions
        if assertion.type == "document_written":
            url = assertion.expected["url"]
            source = data_registry.get_source(url)
            passed = len(source.write_log) > 0
            return {
                "assertion": assertion.description or "Document was written to",
                "passed": passed,
                "detail": f"{len(source.write_log)} write(s) performed"
            }
        
        if assertion.type == "document_contains":
            url = assertion.expected["url"]
            conditions = assertion.expected["conditions"]
            source = data_registry.get_source(url)
            matching = source.query(conditions)
            passed = len(matching) > 0
            return {
                "assertion": assertion.description or "Document contains matching data",
                "passed": passed,
                "detail": f"found {len(matching)} matching row(s)"
            }
        
        if assertion.type == "document_row_matches_schema":
            url = assertion.expected["url"]
            required_columns = assertion.expected["required_columns"]
            source = data_registry.get_source(url)
            
            # Check if any written data has all required columns
            all_match = True
            for write_entry in source.write_log:
                for row in write_entry["data"]:
                    missing_cols = [col for col in required_columns if col not in row]
                    if missing_cols:
                        all_match = False
                        break
            
            return {
                "assertion": assertion.description or "Written data matches schema",
                "passed": all_match,
                "detail": "All rows have required columns" if all_match else f"Missing columns in some rows"
            }
        
        if assertion.type == "document_row_count":
            url = assertion.expected["url"]
            expected_count = assertion.expected["count"]
            source = data_registry.get_source(url)
            actual_count = len(source.data)
            passed = actual_count == expected_count
            return {
                "assertion": assertion.description or "Document has expected row count",
                "passed": passed,
                "detail": f"expected {expected_count}, got {actual_count}"
            }
        
        # ... rest of existing assertions ...
```

---

## Part 8: Frontend Integration Guide

### For Frontend Developers

When a user enters a Google Sheets URL in their policy:

1. **Detect URL**: Extract `https://docs.google.com/spreadsheets/d/...`
2. **OAuth**: Prompt user to sign in with Google (if not already)
3. **Fetch Data**: Use Google Sheets API to fetch spreadsheet
4. **Format**: Convert to `DocumentData` format (see Part 2)
5. **Send**: POST to `/api/generate_policy` with `documents` array

### Example Frontend Code (Pseudocode)

```typescript
// Frontend: React/Next.js example

async function handlePolicySubmit(nlPolicy: string) {
  // 1. Extract Google Sheets URLs from policy text
  const sheetUrls = extractGoogleSheetsUrls(nlPolicy);
  
  // 2. For each URL, fetch data
  const documents = [];
  for (const url of sheetUrls) {
    // Check if user is authenticated
    if (!isGoogleAuthenticated()) {
      await promptGoogleSignIn();
    }
    
    // Fetch sheet data
    const sheetData = await fetchGoogleSheetData(url);
    
    // Convert to DocumentData format
    const documentData = {
      source_type: "google_sheets",
      source_url: url,
      structure: {
        spreadsheet_title: sheetData.title,
        sheet_names: sheetData.sheets.map(s => s.name),
        columns: sheetData.sheets[0].headers,
        primary_sheet: sheetData.sheets[0].name
      },
      sample_data: sheetData.sheets[0].rows.slice(0, 5),
      metadata: {
        spreadsheet_id: extractSpreadsheetId(url),
        total_sheets: sheetData.sheets.length,
        row_count: sheetData.sheets[0].row_count,
        col_count: sheetData.sheets[0].headers.length
      }
    };
    
    documents.push(documentData);
  }
  
  // 3. Send to sandbox API
  const response = await fetch('/api/generate_policy', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      nl_policy: nlPolicy,
      documents: documents,
      options: {
        generate_document_tests: true
      }
    })
  });
  
  const result = await response.json();
  
  // 4. Display results to user
  displayPolicyResults(result);
}
```

---

## Part 9: Testing the Integration

### Manual Testing Steps

1. **Create a test Google Sheet**:
   - Go to sheets.google.com
   - Create a new sheet with columns: `author`, `proposal`, `status`, `votes`
   - Add 2-3 sample rows
   - Copy the URL

2. **Run fetch script**:
   ```bash
   python scripts/fetch_google_sheet.py "YOUR_SHEET_URL"
   ```
   
3. **Use output in API testing**:
   ```bash
   curl -X POST http://localhost:8001/api/generate_policy \
     -H "Content-Type: application/json" \
     -d @google_sheet_abc123.json
   ```

4. **Verify generated code**:
   - Check that script uses `ctx.read_document()` with correct URL
   - Check that tests include `documents` in `community_setup`
   - Check that assertions use document-specific types

### Automated Tests

```python
# tests/test_document_integration.py

def test_generate_policy_with_google_sheet():
    """Test policy generation with Google Sheets document data."""
    
    # Simulate frontend-provided document data
    document_data = {
        "source_type": "google_sheets",
        "source_url": "https://docs.google.com/spreadsheets/d/test123/edit",
        "structure": {
            "columns": ["name", "email", "role"],
            "primary_sheet": "Members"
        },
        "sample_data": [
            {"name": "Alice", "email": "alice@example.com", "role": "admin"},
            {"name": "Bob", "email": "bob@example.com", "role": "member"}
        ],
        "metadata": {"row_count": 2, "col_count": 3}
    }
    
    # Call pipeline
    orchestrator = PipelineOrchestrator(
        llm_client=MockLLMClient(),
        document_schemas={
            document_data["source_url"]: DocumentSchema(**document_data)
        }
    )
    
    result = orchestrator.generate_policy(
        "When a new user joins, add them to the member roster sheet",
        generate_document_tests=True
    )
    
    # Assertions
    assert "ctx.write_document" in result["script"]
    assert result["script"].count(document_data["source_url"]) > 0
    
    # Check document tests were generated
    document_tests = [s for s in result["scenarios"] if s.test_type == "document"]
    assert len(document_tests) >= 2  # Should have read and write tests
    
    # Check test includes document setup
    assert "documents" in result["scenarios"][0].community_setup
```

---

## Implementation Checklist

- [ ] **Script**: Create `scripts/fetch_google_sheet.py`
- [ ] **Dependencies**: Install Google API Python libraries
- [ ] **API Models**: Add `DocumentData` to Pydantic models
- [ ] **API Endpoint**: Modify `/api/generate_policy` to accept documents
- [ ] **Prompt Engineering**: Update header/script generation prompts
- [ ] **Test Generation**: Implement `_generate_document_tests()`
- [ ] **Document Registry**: Update `SandboxRunner._build_document_registry()`
- [ ] **Assertions**: Add document-specific assertion types
- [ ] **Documentation**: Update API docs with document format
- [ ] **Frontend Guide**: Document integration steps for frontend team
- [ ] **Examples**: Create sample sheets and test payloads
- [ ] **Tests**: Write integration tests for document flow

---

## Summary

This implementation:

1. ✅ **No credentials in sandbox** — Frontend fetches all document data
2. ✅ **Utility script** — Developers can extract sheet data for testing
3. ✅ **API integration** — Clean payload format for frontend → sandbox
4. ✅ **Enhanced prompts** — LLM sees document structure during generation
5. ✅ **Additional tests** — Document tests supplement (don't replace) standard tests
6. ✅ **Flexible** — Easy to extend to other document types (Notion, Airtable)

The key insight: **External documents are treated as fixtures** in the sandbox — pre-fetched by the frontend, mocked during testing, and real in production.
