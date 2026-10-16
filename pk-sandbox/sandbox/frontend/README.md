# PolicyKit Sandbox - Frontend

React-based web interface for the PolicyKit sandbox pipeline.

## Features

- **Policy Input**: Natural language governance policy editor
- **Document Input**: Paste external document data (Google Sheets, etc.) as JSON
- **Pipeline Visualization**: Real-time progress tracking through 6 stages
- **Stage Inspector**: View outputs, errors, and LLM interactions
- **Revision Tracking**: Detailed view of script revision attempts
- **Action Log**: See all community actions executed during tests

## Quick Start

```bash
# Install dependencies
npm install

# Start dev server
npm run dev

# Open browser
open http://localhost:5174
```

The frontend proxies API requests to the backend on `localhost:8001`.

## Usage

### 1. Enter Policy Text

Describe your governance policy in natural language:

```
When a user posts more than 5 messages in 60 seconds, 
mute them for 5 minutes.
```

### 2. Add External Documents (Optional)

Paste document data as JSON in the second textarea:

```json
[
  {
    "source_type": "google_sheets",
    "source_url": "https://docs.google.com/spreadsheets/d/...",
    "structure": {
      "columns": ["timestamp", "user", "proposal"]
    },
    "sample_data": [
      {"timestamp": "2024-01-15", "user": "alice", "proposal": "Create channel"}
    ],
    "metadata": {}
  }
]
```

See `examples/sample_document.json` for a complete example.

### 3. Run Pipeline

Click "Run in Sandbox" to start the pipeline. Watch progress through:
1. **Headers** - Generate function signatures
2. **Script** - Implement community script
3. **Tests** - Generate test scenarios
4. **Execute** - Run tests
5. **Revise** - Fix failing tests (up to 3 attempts)
6. **Report** - Final summary

### 4. Inspect Results

- Click any stage to view its output in the right panel
- Check the Action Log at the bottom to see all community actions
- Review revision attempts if tests needed fixes

## Document Input Format

The document input accepts an array of document objects. Each document must have:

- `source_type` (string) - e.g., "google_sheets", "notion", "airtable"
- `source_url` (string) - Document URL
- `structure` (object) - Document structure metadata
  - `columns` (array) - Column names
  - `spreadsheet_title` (string, optional) - Sheet title
  - `sheet_names` (array, optional) - Sheet names
- `sample_data` (array) - Sample rows from the document
- `metadata` (object) - Additional metadata

**Single Document:**
You can paste a single object without array brackets - it will be automatically wrapped.

**Validation:**
Invalid JSON will show an error message below the input field.

## Project Structure

```
frontend/
├── src/
│   ├── App.jsx           # Main application component
│   ├── App.css           # Application styles
│   ├── main.jsx          # React entry point
│   └── index.css         # Global styles
├── public/               # Static assets
├── vite.config.js        # Vite configuration
└── package.json          # Dependencies
```

## Components

### App
Main container coordinating all panels and state management.

### LeftPanel
- Policy text input
- Document JSON input
- Run button
- Example policies
- History sidebar

### CenterPanel
- Pipeline stage visualization
- Stage status indicators
- Result summary

### RightPanel
- Stage inspector
- Output viewer
- Error display
- Revision attempt details

### Footer
- Action log
- Collapsible detail view

## Development

```bash
# Install dependencies
npm install

# Start dev server with hot reload
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Lint code
npm run lint
```

## Configuration

### Backend URL

Edit `vite.config.js` to change the backend proxy:

```js
server: {
  proxy: {
    '/sandbox': 'http://localhost:8001',
    '/health': 'http://localhost:8001',
  }
}
```

### Port

Change the frontend port in `vite.config.js`:

```js
server: {
  port: 5174,
  strictPort: true,
}
```

## API Integration

The frontend communicates with the backend via:

**POST /sandbox/run**
- Creates a new pipeline run
- Body: `{ policy_text: string, documents: DocumentData[] }`
- Returns: `{ id: string, status: string }`

**GET /sandbox/run/:id/status**
- Polls for pipeline progress
- Returns full run state with all stage outputs

**GET /health**
- Health check endpoint

## Technologies

- **React 18** - UI framework
- **Vite** - Build tool and dev server
- **CSS Variables** - Dark theme styling
- **Fetch API** - Backend communication

## Troubleshooting

**"Connection refused" errors:**
- Ensure backend is running on port 8001
- Check `vite.config.js` proxy configuration

**Documents not being included:**
- Verify JSON is valid (use JSONLint)
- Check browser console for parsing errors
- Ensure documents is an array or single object

**Pipeline stuck in "running":**
- Check backend logs for errors
- Verify AWS credentials are configured
- Pipeline auto-retries LLM calls on failures

## Related Documentation

- Backend API: `../sandboxengine/README.md`
- Document integration: `../docs/FRONTEND_DOCUMENTS_UPDATE.md`
- Example usage: `../examples/README.md`
