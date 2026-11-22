import logging
from datetime import (
    date, datetime, time, timedelta, timezone
)
from pathlib import Path

from fastapi import APIRouter, HTTPException
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

router = APIRouter(
    prefix="/api/appointments",
    tags=["Appointments"]
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
TOKEN = ROOT / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events"
]

IST = timezone(
    timedelta(hours=5, minutes=30),
    name="Asia/Kolkata"
)

DURATION = timedelta(minutes=30)

WORK_START = time(10, 0)
WORK_END = time(18, 0)


def get_calendar_service():
    if not TOKEN.exists():
        raise HTTPException(
            status_code=503,
            detail="Google Calendar authorization missing"
        )

    try:
        credentials = Credentials.from_authorized_user_file(
            str(TOKEN), SCOPES
        )

        if not credentials.valid:
            if (
                credentials.expired
                and credentials.refresh_token
            ):
                credentials.refresh(Request())

                # Save refreshed credentials atomically
                temp = TOKEN.with_name("token.json.tmp")
                temp.write_text(
                    credentials.to_json(),
                    encoding="utf-8"
                )
                temp.replace(TOKEN)
            else:
                raise HTTPException(
                    status_code=503,
                    detail="Reconnect Google Calendar"
                )

        return build(
            "calendar",
            "v3",
            credentials=credentials,
            cache_discovery=False
        )

    except HTTPException:
        raise

    except (RefreshError, ValueError, OSError) as error:
        logger.warning(
            "Calendar authentication error: %s",
            type(error).__name__
        )
        raise HTTPException(
            status_code=503,
            detail="Reconnect using connect_google_calendar.py"
        ) from error


def parse_event_time(value):
    if "dateTime" in value:
        result = datetime.fromisoformat(
            value["dateTime"].replace("Z", "+00:00")
        )
        if result.tzinfo is None:
            raise ValueError("Event time has no timezone")
        return result.astimezone(IST)

    if "date" in value:
        return datetime.combine(
            date.fromisoformat(value["date"]),
            time.min,
            tzinfo=IST
        )

    raise ValueError("Invalid Google Calendar event time")


def get_busy_intervals(service, day):
    day_start = datetime.combine(
        day, time.min, IST
    )
    day_end = day_start + timedelta(days=1)

    busy = []
    page_token = None

    while True:
        response = service.events().list(
            calendarId="primary",
            timeMin=day_start.isoformat(),
            timeMax=day_end.isoformat(),
            timeZone="Asia/Kolkata",
            singleEvents=True,
            showDeleted=False,
            maxResults=2500,
            pageToken=page_token
        ).execute()

        for event in response.get("items", []):
            if event.get("status") == "cancelled":
                continue

            if event.get("transparency") == "transparent":
                continue

            start = parse_event_time(event["start"])
            end = parse_event_time(event["end"])

            if start < end:
                busy.append((start, end))

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return busy


def build_available_slots(day, busy, now=None):
    now = now or datetime.now(IST)

    if day.weekday() >= 5:
        return []

    if day < now.date():
        return []

    start = datetime.combine(day, WORK_START, IST)
    finish = datetime.combine(day, WORK_END, IST)

    slots = []
    current = start

    while current + DURATION <= finish:
        end = current + DURATION

        conflict = any(
            busy_start < end and busy_end > current
            for busy_start, busy_end in busy
        )

        if current > now and not conflict:
            slots.append({
                "start": current.isoformat(
                    timespec="minutes"
                ),
                "end": end.isoformat(
                    timespec="minutes"
                )
            })

        current += DURATION

    return slots


@router.get("/availability")
def check_availability(date: date):
    now = datetime.now(IST)

    response = {
        "success": True,
        "date": date.isoformat(),
        "timezone": "Asia/Kolkata",
        "duration_minutes": 30,
        "working_hours": {
            "start": "10:00",
            "end": "18:00"
        },
        "available_slots": [],
        "available_count": 0,
        "note": "Read-only availability; no booking made"
    }

    if date.weekday() >= 5:
        response["note"] = "No weekend appointments"
        return response

    if date < now.date():
        response["note"] = "Date is in the past"
        return response

    try:
        service = get_calendar_service()

        busy = get_busy_intervals(service, date)

        slots = build_available_slots(
            date, busy, now
        )

    except HTTPException:
        raise

    except (HttpError, ValueError, KeyError) as error:
        logger.warning(
            "Calendar availability failed: %s",
            type(error).__name__
        )

        raise HTTPException(
            status_code=502,
            detail="Could not retrieve calendar availability"
        ) from error

    response["available_slots"] = slots
    response["available_count"] = len(slots)

    return response
