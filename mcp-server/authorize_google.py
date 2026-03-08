"""One-time OAuth2 authorization. Run once, saves token to .google-token.json."""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
import json

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/presentations',
    'https://www.googleapis.com/auth/tasks',
]

CLIENT_FILE = Path(__file__).parent.parent / '.google-oauth-client.json'
TOKEN_FILE = Path(__file__).parent.parent / '.google-token.json'

flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
creds = flow.run_local_server(port=0)

TOKEN_FILE.write_text(creds.to_json())
print(f"\nToken saved to {TOKEN_FILE}")
print("Authorization complete. You can close this terminal tab.")
