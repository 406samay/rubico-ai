"""
Creates events on a connected Google Calendar (e.g. spaced-repetition study
review reminders). Reading today's events lives in sources/calendar.py -
this module is for actually writing events.
"""

import datetime

from googleapiclient.discovery import build

import config
from google_auth import get_credentials


def create_event(account_label, summary, start_dt, duration_minutes=15, description=""):
    if config.is_demo():
        return f"demo-event-{int(start_dt.timestamp())}"

    creds = get_credentials(account_label, allow_browser=False)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)
    tz_name = config.get()["timezone"]
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": tz_name},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": tz_name},
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    return created["id"]
