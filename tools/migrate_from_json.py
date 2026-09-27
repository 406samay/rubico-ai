"""
One-time upgrade for people who ran the older version of this project,
which kept its data in loose JSON/txt files. Copies everything into the
new database (data/rubico.db) and moves logins into data/tokens/.

    python tools/migrate_from_json.py            # looks in the project folder
    python tools/migrate_from_json.py --from ~/DailyBrief

Your old files are left untouched, so it's safe to run - delete them
yourself once you're happy. Google logins can't be carried over (the new
version uses one login per account instead of one per service), so
finish with:  python setup.py --only google
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import db
import metrics_store


def _load(path):
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def migrate(src):
    done = []

    notes = _load(src / "notes.json")
    if notes:
        with db.connect() as conn:
            for n in notes:
                if not n.get("delivered"):
                    conn.execute(
                        "INSERT INTO reminders (text, due_date, status, created_at) VALUES (?, NULL, 'active', datetime('now'))",
                        (n["text"],),
                    )
        done.append(f"{sum(not n.get('delivered') for n in notes)} undelivered notes -> reminders")

    metrics = _load(src / "metrics_history.json")
    if metrics:
        store = metrics_store.load()
        for date_str, day in metrics.get("days", {}).items():
            store["days"].setdefault(date_str, {}).update(
                {k: v for k, v in day.items() if k != "nutrition"}  # MyFitnessPal was removed
            )
        store["meta"].update(metrics.get("meta", {}))
        metrics_store.save(store)
        done.append(f"{len(metrics.get('days', {}))} days of dashboard history")

    topics = _load(src / "study_reminders.json")
    if topics:
        with db.connect() as conn:
            for t in topics:
                cur = conn.execute("INSERT INTO study_topics (topic, studied_at) VALUES (?, ?)",
                                   (t["topic"], t["studied_at"]))
                conn.executemany(
                    "INSERT INTO study_stages (topic_id, day, due_at, sent, calendar_event_id) VALUES (?, ?, ?, ?, ?)",
                    [(cur.lastrowid, s["day"], s["due_at"], int(s["sent"]), s.get("calendar_event_id"))
                     for s in t["stages"]],
                )
        done.append(f"{len(topics)} study topics")

    offset_file = src / "chat_offset.txt"
    if offset_file.exists():
        db.kv_set("telegram_offset", int(offset_file.read_text().strip()))
        done.append("Telegram message position")

    for old, new in (("monzo_token.json", "monzo.json"), ("spotify_token.json", "spotify.json")):
        if (src / old).exists() and not config.token_path(new).exists():
            shutil.copy(src / old, config.token_path(new))
            done.append(f"{old} -> data/tokens/{new}")

    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="src", default=str(config.ROOT))
    args = parser.parse_args()
    src = Path(os.path.expanduser(args.src))

    done = migrate(src)
    if not done:
        print(f"Nothing to migrate in {src}.")
        return 0
    print("Migrated:\n  " + "\n  ".join(done))
    print("\nNext: python setup.py --only google   (to log your Google accounts in again)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
