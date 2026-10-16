# Sandbox Scripts

Utility scripts for development and testing.

## fetch_google_sheet.py

Fetches Google Sheets data for testing external document integration.

### Setup

1. **Install dependencies**:
   ```bash
   pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
   ```

2. **Get Google OAuth credentials**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a project (or select existing)
   - Enable Google Sheets API
   - Create OAuth 2.0 credentials (Desktop app type)
   - Download as `credentials.json`
   - Place in sandbox root directory

### Usage

```bash
python scripts/fetch_google_sheet.py "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit"
```

### Output

The script will:
1. Prompt for Google sign-in (first time only)
2. Fetch spreadsheet metadata and data
3. Display formatted output
4. Save to `google_sheet_YOUR_SHEET_ID.json`

### Output Format

```json
{
  "full_data": {
    "metadata": {...},
    "sheets": [...]
  },
  "document_schema": {
    "source_type": "google_sheets",
    "source_url": "...",
    "structure": {...},
    "sample_data": [...],
    "metadata": {...}
  }
}
```

### Using in API Tests

The `document_schema` object can be passed directly to the sandbox API:

```python
import requests
import json

with open('google_sheet_abc123.json') as f:
    data = json.load(f)

response = requests.post('http://localhost:8001/api/generate_policy', json={
    "nl_policy": "When a user posts in #proposals, log to the tracking sheet",
    "documents": [data['document_schema']]
})
```
