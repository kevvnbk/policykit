# Google OAuth Setup Guide

## Quick Setup (5 minutes)

### Step 1: Create OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)

2. **Create a new project** (or select existing):
   - Click project dropdown at top
   - Click "New Project"
   - Name: "PKWrapper Sandbox" (or any name)
   - Click "Create"

3. **Enable Google Sheets API**:
   - In left menu, go to "APIs & Services" > "Library"
   - Search for "Google Sheets API"
   - Click it, then click "Enable"

4. **Create OAuth 2.0 Credentials**:
   - Go to "APIs & Services" > "Credentials"
   - Click "+ CREATE CREDENTIALS" at top
   - Select "OAuth client ID"
   - If prompted, configure OAuth consent screen:
     - User Type: "External" (click Create)
     - App name: "PKWrapper Sandbox"
     - User support email: your email
     - Developer contact: your email
     - Click "Save and Continue" through all screens
   - Back at "Create OAuth client ID":
     - Application type: **Desktop app**
     - Name: "Sandbox Sheet Fetcher"
     - Click "Create"

5. **Download credentials**:
   - You'll see a popup with Client ID and Client Secret
   - Click "DOWNLOAD JSON"
   - Save as `credentials.json`

6. **Move credentials.json**:
   - Place the downloaded file in: `sandbox/credentials.json`
   - (Same directory as this README)

### Step 2: Run the Script

```bash
cd sandbox
python scripts/fetch_google_sheet.py "YOUR_SHEET_URL"
```

### Step 3: Sign In

- Script will open a browser
- Sign in with your Google account
- Click "Allow" to grant access
- Browser will show "The authentication flow has completed"
- Return to terminal to see results

### Step 4: Token Saved

- A `.google_sheets_token.pickle` file is created
- Future runs won't require re-authentication
- Token expires after ~7 days (will auto-refresh if refresh token available)

---

## Troubleshooting

### "Access blocked: This app's request is invalid"

**Cause**: OAuth consent screen not configured

**Fix**:
1. Go to "APIs & Services" > "OAuth consent screen"
2. Add your email as a test user under "Test users"
3. Or publish the app (not necessary for testing)

### "Permission denied" or 403 error

**Cause**: Sheet isn't shared with the account you signed in with

**Fix**:
1. Open the sheet in browser
2. Click "Share"
3. Add the email you signed in with
4. Or make it "Anyone with the link can view"

### "credentials.json not found"

**Fix**: Make sure `credentials.json` is in the `sandbox/` directory (same level as `sandboxengine/`)

### Token expired

**Fix**: Delete `.google_sheets_token.pickle` and run script again to re-authenticate

---

## Security Notes

- `credentials.json` contains your OAuth client ID (public) and secret (semi-public)
- `.google_sheets_token.pickle` contains your actual access token (private)
- Both are in `.gitignore` and won't be committed
- Never share `.google_sheets_token.pickle` with anyone

---

## Alternative: Public Sheets Only

If you only need public/link-shared sheets and don't want OAuth:

```bash
python scripts/fetch_public_sheet.py "SHEET_URL"
```

This works without credentials but only for publicly accessible sheets.
