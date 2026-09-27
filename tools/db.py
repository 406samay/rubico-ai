"""
The local database: one SQLite file at data/rubico.db.

SQLite is just a file on disk - no server to install. It replaces the
separate JSON files the project used to keep (notes.json,
pending_actions.json, metrics_history.json, ...). A crash halfway through
a save can't leave it half-written the way a JSON file can.

Tables:
  kv               small settings the app remembers (Telegram offset, etc.)
  briefings        every morning brief that was sent, for the dashboard
  reminders        notes you text the bot, and when to bring them back
  pending_actions  email sends/deletes waiting out their cancel window
  metrics_days     one row per day of dashboard numbers (JSON blob)
  study_topics     spaced-repetition study log (optional feature)
  study_stages     the review dates for each study topic
"""

import json
import sqlite3
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS briefings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    date       TEXT NOT NULL,
    text       TEXT NOT NULL,
    broken     TEXT,
    demo       INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reminders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    text          TEXT NOT NULL,
    due_date      TEXT,
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TEXT NOT NULL,
    delivered_at  TEXT,
    original      TEXT
);
CREATE TABLE IF NOT EXISTS pending_actions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    send_at    TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    payload    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metrics_days (
    date TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_topics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    topic      TEXT NOT NULL,
    studied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_stages (
    topic_id          INTEGER NOT NULL,
    day               INTEGER NOT NULL,
    due_at            TEXT NOT NULL,
    sent              INTEGER NOT NULL DEFAULT 0,
    calendar_event_id TEXT,
    PRIMARY KEY (topic_id, day)
);
"""


def db_path():
    return config.data_dir() / "rubico.db"


@contextmanager
def connect():
    """Open, run, commit, close. A fresh connection per use keeps it safe
    to call from the chat, scheduler and dashboard threads at once."""
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def kv_get(key, default=None):
    with connect() as conn:
        row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return json.loads(row["value"])


def kv_set(key, value):
    with connect() as conn:
        conn.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
