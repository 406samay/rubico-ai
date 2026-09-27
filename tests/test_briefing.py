import datetime
import json

import config
import data_sources
import db
import orchestrator
import reminders
import run


def test_demo_raw_data_covers_every_source():
    text, broken = data_sources.build_raw_data()
    assert broken == []
    for heading in ("Emails from personal", "Calendar events", "Weather in", "Monzo", "Spotify"):
        assert heading in text


def test_briefing_lists_due_reminders_then_marks_them_delivered(sent):
    reminders.add("Submit the form", reminders.today())
    later = reminders.add("Later thing", reminders.today() + datetime.timedelta(days=3))

    msg = orchestrator.run_briefing(writer=lambda raw, due: "Brief body")
    assert msg.startswith("Brief body")
    assert "📌 Reminders for today" in msg and "Submit the form" in msg
    assert "Later thing" not in msg
    assert [r["id"] for r in reminders.list_active()] == [later]

    with db.connect() as conn:
        row = conn.execute("SELECT text, broken FROM briefings").fetchone()
    assert row["text"] == msg and json.loads(row["broken"]) == []


def test_reminders_still_delivered_when_claude_fails(sent):
    reminders.add("Important", None)

    def boom(raw, due):
        raise RuntimeError("API down")

    msg = orchestrator.run_briefing(writer=boom)
    assert "Couldn't write your brief" in msg and "Important" in msg


def test_scheduler_catch_up_window():
    tz = config.tz()
    config.get()["briefing"].update({"time": "08:00", "catch_up_minutes": 90})
    day = datetime.datetime(2026, 9, 28, tzinfo=tz)
    assert not run.briefing_due(day.replace(hour=7, minute=59))
    assert run.briefing_due(day.replace(hour=8, minute=0))
    assert run.briefing_due(day.replace(hour=9, minute=29))
    assert not run.briefing_due(day.replace(hour=12))  # too late - skip, don't spam at lunch
    db.kv_set("last_briefing_date", "2026-09-28")
    assert not run.briefing_due(day.replace(hour=8, minute=5))  # already sent today
