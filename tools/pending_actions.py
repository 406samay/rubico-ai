"""
Tracks actions (Gmail replies, bulk trashing) that are queued to happen
automatically after a review window, unless cancelled first. This is what
makes these actions safe: nothing happens the moment it's requested.

The window length is assistant.review_window_minutes in config.yaml.
"""

import datetime
import json

import config
import db


def window_minutes():
    return int(config.get()["assistant"].get("review_window_minutes", 10))


# Kept as a name other tools read in messages ("sending in N minutes").
CANCEL_WINDOW_MINUTES = window_minutes()


def _row_to_action(row):
    action = json.loads(row["payload"])
    action.update({
        "id": row["id"], "type": row["type"], "created_at": row["created_at"],
        "send_at": row["send_at"], "status": row["status"],
    })
    return action


def _create(type_, fields):
    now = datetime.datetime.now(datetime.timezone.utc)
    send_at = now + datetime.timedelta(minutes=window_minutes())
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO pending_actions (type, created_at, send_at, status, payload) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (type_, now.isoformat(), send_at.isoformat(), json.dumps(fields)),
        )
        action_id = cur.lastrowid
    return {"id": action_id, "type": type_, "status": "pending", **fields}


def create_pending_send(account_label, to, subject, thread_id, in_reply_to_header, body):
    return _create("gmail_reply", {
        "account": account_label,
        "to": to,
        "subject": subject,
        "thread_id": thread_id,
        "in_reply_to_header": in_reply_to_header,
        "body": body,
    })


def create_pending_trash(account_label, message_ids, preview_lines):
    return _create("gmail_bulk_trash", {
        "account": account_label,
        "message_ids": message_ids,
        "preview_lines": preview_lines,
    })


def get_due_pending():
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM pending_actions WHERE status = 'pending' AND send_at <= ? ORDER BY id",
            (now,),
        ).fetchall()
    return [_row_to_action(r) for r in rows]


def get_latest_pending():
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM pending_actions WHERE status = 'pending' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return _row_to_action(row) if row else None


def mark_status(action_id, status):
    with db.connect() as conn:
        conn.execute("UPDATE pending_actions SET status = ? WHERE id = ?", (status, action_id))
