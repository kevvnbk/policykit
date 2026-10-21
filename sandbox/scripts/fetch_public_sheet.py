#!/usr/bin/env python3
"""
Fetch public/shared Google Sheets data without OAuth.

Usage:
    python scripts/fetch_public_sheet.py <spreadsheet_url>

For public or link-shared spreadsheets only.
"""

import sys
import json
import re
import requests
from typing import Dict, List, Any


def extract_spreadsheet_id(url: str) -> str:
    """Extract spreadsheet ID from Google Sheets URL."""
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    if not match:
        raise ValueError(f"Cannot extract spreadsheet ID from URL: {url}")
    return match.group(1)


def extract_gid(url: str) -> str:
    """Extract gid (sheet ID) from URL if present."""
    match = re.search(r'[#&]gid=(\d+)', url)
    if match:
        return match.group(1)
    return "0"  # Default to first sheet


def fetch_sheet_as_csv(spreadsheet_id: str, gid: str = "0", format: str = "csv") -> List[List[str]]:
    """
    Fetch a public Google Sheet as CSV or TSV.

    This works for:
    - Fully public sheets
    - Link-shared sheets (anyone with link can view)

    Parameters:
        spreadsheet_id: The sheet ID
        gid: Sheet/tab ID (default "0" for first sheet)
        format: "csv" or "tsv" (default "csv")
    """
    # Google Sheets export URL
    export_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format={format}&gid={gid}"

    print(f"Fetching from: {export_url}")
    print(f"Format: {format.upper()}")

    try:
        response = requests.get(export_url, timeout=30)
        response.raise_for_status()

        # Parse CSV/TSV
        import csv
        import io

        data = response.text

        # Use appropriate delimiter
        delimiter = '\t' if format == 'tsv' else ','
        reader = csv.reader(io.StringIO(data), delimiter=delimiter)
        rows = list(reader)

        return rows

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            print("\n❌ ERROR: Sheet is not publicly accessible or link-sharing is disabled.")
            print("\nTo fix:")
            print("1. Open the sheet")
            print("2. Click 'Share' button")
            print("3. Change to 'Anyone with the link can view'")
            print("\nOR use the OAuth version: fetch_google_sheet.py")
            sys.exit(1)
        else:
            raise


def parse_csv_to_structured(rows: List[List[str]]) -> Dict[str, Any]:
    """Convert CSV rows to structured format."""
    if not rows:
        return {
            'sheet_name': 'Sheet1',
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
        'sheet_name': 'Sheet1',  # We don't know the actual name without API
        'headers': headers,
        'rows': structured_rows,
        'row_count': len(structured_rows),
    }


def generate_document_schema(
    spreadsheet_id: str,
    gid: str,
    sheet_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate DocumentSchema format for sandbox."""

    # Sample data: first 5 rows
    sample_data = sheet_data['rows'][:5]

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"

    return {
        'source_type': 'google_sheets',
        'source_url': url,
        'structure': {
            'spreadsheet_title': 'Untitled',  # Can't get without API
            'sheet_names': ['Sheet1'],  # Can't get without API
            'columns': sheet_data['headers'],
            'primary_sheet': 'Sheet1',
            'gid': gid,
        },
        'sample_data': sample_data,
        'metadata': {
            'spreadsheet_id': spreadsheet_id,
            'total_sheets': 1,  # Unknown without API
            'row_count': sheet_data['row_count'],
            'col_count': len(sheet_data['headers']),
            'writable': False,
            'fetch_method': 'public_csv',
        }
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python fetch_public_sheet.py <spreadsheet_url> [format]")
        print("\nExample:")
        print("  python fetch_public_sheet.py https://docs.google.com/spreadsheets/d/1ABC.../edit")
        print("  python fetch_public_sheet.py https://docs.google.com/spreadsheets/d/1ABC.../edit tsv")
        print("\nFormats: csv (default), tsv")
        print("\nNote: This works for public or link-shared sheets only.")
        print("For private sheets, use fetch_google_sheet.py with OAuth.")
        sys.exit(1)

    url = sys.argv[1]
    format = sys.argv[2] if len(sys.argv) > 2 else "csv"

    if format not in ["csv", "tsv"]:
        print(f"ERROR: Invalid format '{format}'. Use 'csv' or 'tsv'.")
        sys.exit(1)

    print(f"Fetching public Google Sheet: {url}\n")

    # Extract spreadsheet ID and gid
    try:
        spreadsheet_id = extract_spreadsheet_id(url)
        gid = extract_gid(url)
        print(f"Spreadsheet ID: {spreadsheet_id}")
        print(f"GID (sheet ID): {gid}\n")
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Fetch data as CSV/TSV
    print("Fetching spreadsheet data...")
    try:
        rows = fetch_sheet_as_csv(spreadsheet_id, gid, format)
        print(f"✓ Fetched {len(rows)} rows\n")
    except Exception as e:
        print(f"\n❌ ERROR: Failed to fetch sheet: {e}")
        sys.exit(1)

    # Parse to structured format
    sheet_data = parse_csv_to_structured(rows)

    # Generate schema for sandbox
    document_schema = generate_document_schema(spreadsheet_id, gid, sheet_data)

    # Output results
    print("=" * 60)
    print("DOCUMENT SCHEMA (for sandbox API)")
    print("=" * 60)
    print(json.dumps(document_schema, indent=2))

    print("\n" + "=" * 60)
    print("SAMPLE DATA")
    print("=" * 60)
    print(f"\nHeaders: {sheet_data['headers']}")
    print(f"Total rows: {sheet_data['row_count']}")

    if sheet_data['rows']:
        print(f"\nFirst 3 rows:")
        for i, row in enumerate(sheet_data['rows'][:3]):
            print(f"  Row {i+1}: {row}")

    # Save to file
    output_file = f"google_sheet_{spreadsheet_id}.json"
    output_data = {
        'full_data': {
            'metadata': {
                'title': 'Untitled',
                'sheets': [{
                    'name': 'Sheet1',
                    'id': gid,
                    'row_count': sheet_data['row_count'],
                    'col_count': len(sheet_data['headers'])
                }],
                'url': f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
            },
            'sheets': [sheet_data]
        },
        'document_schema': document_schema,
    }

    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n✅ Data saved to: {output_file}")
    print(f"\nTo use in API testing:")
    print(f"  POST /api/generate_policy")
    print(f"  Body: {{")
    print(f"    \"nl_policy\": \"...\",")
    print(f"    \"documents\": [<content from {output_file}>['document_schema']]")
    print(f"  }}")


if __name__ == '__main__':
    main()
