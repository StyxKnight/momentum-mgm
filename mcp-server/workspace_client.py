"""Google Workspace client — Sheets, Docs, Calendar, Drive."""
import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

TOKEN_FILE = Path(__file__).parent.parent / '.google-token.json'

def _creds():
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json())
    return creds


def get_sheets_service():
    return build('sheets', 'v4', credentials=_creds())

def get_docs_service():
    return build('docs', 'v1', credentials=_creds())

def get_calendar_service():
    return build('calendar', 'v3', credentials=_creds())

def get_drive_service():
    return build('drive', 'v3', credentials=_creds())


def create_or_get_sheet(title: str) -> tuple:
    """Create a Sheet owned by service account. Returns (sheet_id, url)."""
    drive = get_drive_service()
    results = drive.files().list(
        q=f"name='{title}' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
        fields="files(id, name)"
    ).execute()
    files = results.get('files', [])
    if files:
        sid = files[0]['id']
    else:
        drive = get_drive_service()
        body = {'name': title, 'mimeType': 'application/vnd.google-apps.spreadsheet'}
        resp = drive.files().create(body=body, fields='id').execute()
        sid = resp['id']
        _share_with_admin(sid)
    url = f"https://docs.google.com/spreadsheets/d/{sid}/edit"
    return sid, url


def write_to_sheet(sheet_id: str, tab_name: str, rows: list) -> None:
    """Delete and recreate tab, then write rows. Ensures clean formatting."""
    sheets = get_sheets_service()
    meta = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}

    requests = []
    if tab_name in existing:
        requests.append({'deleteSheet': {'sheetId': existing[tab_name]}})
    requests.append({'addSheet': {'properties': {'title': tab_name}}})
    sheets.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={'requests': requests}).execute()

    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption='RAW',
        body={'values': rows}
    ).execute()


def create_doc(title: str, sections: list) -> tuple:
    """Create a formatted Google Doc.
    sections = list of (text, style) where style is 'h1','h2','body','bullet' or None.
    Returns (doc_id, url)."""
    docs = get_docs_service()
    doc = docs.documents().create(body={'title': title}).execute()
    doc_id = doc['documentId']

    full_text = ""
    positions = []
    idx = 1

    for text, style in sections:
        line = (text or "") + "\n"
        start = idx
        end = idx + len(line)
        positions.append((start, end - 1, style))
        full_text += line
        idx = end

    style_map = {'h1': 'HEADING_1', 'h2': 'HEADING_2', 'h3': 'HEADING_3', 'body': 'NORMAL_TEXT', 'bullet': 'NORMAL_TEXT'}
    requests = [{"insertText": {"location": {"index": 1}, "text": full_text}}]

    for start, end, style in positions:
        if start >= end:
            continue
        requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": {"namedStyleType": style_map.get(style or 'body', 'NORMAL_TEXT')},
                "fields": "namedStyleType"
            }
        })
        if style == 'bullet':
            requests.append({
                "createParagraphBullets": {
                    "range": {"startIndex": start, "endIndex": end},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
                }
            })

    docs.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()
    _share_with_admin(doc_id)
    return doc_id, f"https://docs.google.com/document/d/{doc_id}/edit"


def _share_with_admin(file_id: str) -> None:
    admin_email = os.getenv('GOOGLE_ADMIN_EMAIL')
    if not admin_email:
        return
    drive = get_drive_service()
    drive.permissions().create(
        fileId=file_id,
        body={'type': 'user', 'role': 'writer', 'emailAddress': admin_email},
        fields='id'
    ).execute()


def create_calendar_event(cal_id: str, event: dict) -> str:
    """Create a calendar event, skip if duplicate. Returns event id or 'skipped'."""
    cal = get_calendar_service()
    existing = cal.events().list(
        calendarId=cal_id,
        timeMin=event['start']['dateTime'],
        timeMax=event['end']['dateTime'],
        q=event['summary']
    ).execute()
    if existing.get('items'):
        return 'skipped'
    result = cal.events().insert(calendarId=cal_id, body=event).execute()
    return result['id']


def create_calendar(name: str) -> tuple:
    """Create a calendar owned by service account. Returns (cal_id, url)."""
    cal = get_calendar_service()
    body = {'summary': name, 'timeZone': 'America/Chicago'}
    result = cal.calendars().insert(body=body).execute()
    cal_id = result['id']
    cal.acl().insert(
        calendarId=cal_id,
        body={'role': 'writer', 'scope': {'type': 'user', 'value': os.getenv('GOOGLE_ADMIN_EMAIL')}}
    ).execute()
    url = f"https://calendar.google.com/calendar/r?cid={cal_id}"
    return cal_id, url
