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
import re
import os.path
import pickle

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    print("ERROR: Google API libraries not installed!")
    print("\nInstall with:")
    print("  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    sys.exit(1)

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
        json.dump({
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
