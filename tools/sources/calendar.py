"""
Google Calendar: your events for the next 24 hours, from each account in
sources.calendar.accounts.
"""

import datetime

from googleapiclient.discovery import build

import config
from google_auth import client_config, get_credentials, token_file
from sources.base import DataSource


def get_todays_events(label, allow_browser=True):
    creds = get_credentials(label, allow_browser=allow_browser)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now = datetime.datetime.now(datetime.timezone.utc)
    events_result = service.events().list(
        calendarId="primary", timeMin=now.isoformat(),
        timeMax=(now + datetime.timedelta(days=1)).isoformat(),
        singleEvents=True, orderBy="startTime",
    ).execute()

    return [
        {
            "start": e["start"].get("dateTime", e["start"].get("date")),
            "summary": e.get("summary", "(no title)"),
        }
        for e in events_result.get("items", [])
    ]


def _demo_events():
    today = datetime.datetime.now(config.tz()).replace(second=0, microsecond=0)

    def at(hour, minute=0):
        return today.replace(hour=hour, minute=minute).isoformat()

    return [
        {"start": at(9, 30), "summary": "Team stand-up"},
        {"start": at(12, 30), "summary": "Lunch with Sam"},
        {"start": at(15, 0), "summary": "Sprint review"},
        {"start": at(18, 45), "summary": "Gym - leg day"},
    ]


class CalendarSource(DataSource):
    name = "calendar"
    title = "Google Calendar"
    description = "Today's events, so the brief knows what your day looks like."
    fix_hint = "python tools/reauth_google.py"

    @property
    def accounts(self):
        return self.settings.get("accounts") or []

    def problems(self):
        issues = []
        if not client_config():
            issues.append("Google OAuth client not set (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)")
        if not self.accounts:
            issues.append("no accounts listed under sources.calendar.accounts")
        for label in self.accounts:
            if not token_file(label).exists():
                issues.append(f"'{label}' hasn't logged in yet")
        return issues

    def fetch(self, allow_browser=True):
        out = {}
        for label in self.accounts:
            try:
                out[label] = get_todays_events(label, allow_browser)
            except Exception as e:
                out[label] = e
        return out

    def demo(self):
        return {label: _demo_events() for label in self.accounts}

    def broken_parts(self, data):
        return [f"Calendar {label}" for label, v in data.items() if isinstance(v, Exception)]

    def format(self, data):
        lines = []
        for label, events in data.items():
            lines.append(f"--- Calendar events for {label} (next 24h) ---")
            if isinstance(events, Exception):
                lines.append(f"(unavailable: {events})")
            elif not events:
                lines.append("(no events)")
            else:
                for ev in events:
                    lines.append(f"{ev['start']} - {ev['summary']}")
            lines.append("")
        return "\n".join(lines).rstrip()
