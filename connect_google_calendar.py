from pathlib import Path
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent
CREDENTIALS = ROOT / "credentials.json"
TOKEN = ROOT / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events"
]


def connect_calendar():
    if not CREDENTIALS.exists():
        raise FileNotFoundError(
            "credentials.json not found in project folder"
        )

    creds = None

    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(
            str(TOKEN), SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("Opening Google authentication...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN.write_text(
            creds.to_json(),
            encoding="utf-8"
        )

    service = build(
        "calendar",
        "v3",
        credentials=creds,
        cache_discovery=False
    )

    print("Connecting to Google Calendar...")

    result = service.events().list(
        calendarId="primary",
        timeMin=datetime.now(timezone.utc).isoformat(),
        maxResults=3,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = result.get("items", [])

    print("\nSUCCESS: Google Calendar connected!")
    print("Upcoming events found:", len(events))
    print("Calendar authentication is working.")
    print("No appointments were created.")


if __name__ == "__main__":
    connect_calendar()
