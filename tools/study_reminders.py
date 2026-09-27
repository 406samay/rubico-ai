"""
Optional feature (features.study_reminders in config.yaml).

Tracks topics you've studied and schedules spaced-repetition review
reminders based on the forgetting curve: most of what you learn fades in
the first 24 hours, so reminders fire at 1, 3, 7, 14, and 30 days after
you log a topic - each gap roughly doubling, like real spaced repetition.

Times are computed in YOUR timezone (config.yaml) regardless of the
server's own clock, so "8am" always means 8am for you, not 8am UTC.
"""

import datetime

import config
import db


def _settings():
    return config.feature("study_reminders")


def enabled():
    return bool(_settings().get("enabled"))


def schedule_days():
    return list(_settings().get("schedule_days") or [1, 3, 7, 14, 30])


def _reminder_time():
    return config.parse_time(_settings().get("reminder_time"))


def _morning_of(dt):
    hour, minute = _reminder_time()
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)


def parse_datetime(dt_str):
    dt = datetime.datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=config.tz())
    return dt


def _load_topic(conn, topic_id):
    topic = dict(conn.execute("SELECT * FROM study_topics WHERE id = ?", (topic_id,)).fetchone())
    stages = conn.execute(
        "SELECT * FROM study_stages WHERE topic_id = ? ORDER BY day", (topic_id,)
    ).fetchall()
    topic["stages"] = [
        {"day": s["day"], "due_at": s["due_at"], "sent": bool(s["sent"]),
         "calendar_event_id": s["calendar_event_id"]}
        for s in stages
    ]
    return topic


def create_topic(topic_name):
    now = datetime.datetime.now(config.tz())
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO study_topics (topic, studied_at) VALUES (?, ?)",
            (topic_name, now.isoformat()),
        )
        topic_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO study_stages (topic_id, day, due_at) VALUES (?, ?, ?)",
            [
                (topic_id, day, _morning_of(now + datetime.timedelta(days=day)).isoformat())
                for day in schedule_days()
            ],
        )
        return _load_topic(conn, topic_id)


def get_due_reminders():
    """Pairs of (topic, stage) whose due_at has passed and hasn't been sent yet."""
    now = datetime.datetime.now(config.tz())
    due = []
    with db.connect() as conn:
        rows = conn.execute("SELECT DISTINCT topic_id FROM study_stages WHERE sent = 0").fetchall()
        topics = [_load_topic(conn, r["topic_id"]) for r in rows]
    for topic in topics:
        for stage in topic["stages"]:
            if not stage["sent"] and parse_datetime(stage["due_at"]) <= now:
                due.append((topic, stage))
    return due


def mark_sent(topic_id, day):
    with db.connect() as conn:
        conn.execute(
            "UPDATE study_stages SET sent = 1 WHERE topic_id = ? AND day = ?", (topic_id, day)
        )


def set_calendar_event_id(topic_id, day, event_id):
    with db.connect() as conn:
        conn.execute(
            "UPDATE study_stages SET calendar_event_id = ? WHERE topic_id = ? AND day = ?",
            (event_id, topic_id, day),
        )
