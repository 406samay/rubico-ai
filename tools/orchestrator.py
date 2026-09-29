"""
The morning brief.

Pulls today's data from every switched-on source, hands it to Claude to
write a short judgment-call summary, adds any reminders that are due,
sends it to you on Telegram, and saves a copy for the dashboard.

run.py sends it automatically every morning at briefing.time. To get one
right now, text your bot /brief.
"""

import argparse
import datetime
import json
import os
import sys
import traceback

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import db
import llm
import reminders
from data_sources import build_raw_data
import telegram_bot


def write_brief(raw_data, due_reminders=()):
    cfg = config.get()
    now = datetime.datetime.now(config.tz())
    reminder_note = ""
    if due_reminders:
        reminder_note = (
            " The user also has reminders due today (listed below the data). They "
            "will be printed as a list underneath your brief, so don't repeat them "
            "one by one - but do factor them in when picking today's focus."
        )
    system = (
        "You write a short, useful morning brief for one person based on their raw "
        "data (email, calendar, weather, money, music - whatever is included). Call "
        "out anything that looks urgent or needs a reply. Skip newsletters and "
        "promotional noise unless something genuinely stands out. End with one "
        "specific thing worth focusing on today. "
        f"Keep it under {cfg['briefing']['max_words']} words.{reminder_note} "
        f"Today is {now.strftime('%A %d %B %Y')}.\n\n" + llm.voice_instructions()
    )
    content = raw_data
    if due_reminders:
        content += "\n\n--- Reminders due today ---\n" + "\n".join(f"- {r['text']}" for r in due_reminders)
    return llm.ask(system, content)


def reminders_block(due):
    if not due:
        return ""
    lines = ["📌 Reminders for today:"]
    for r in due:
        when = reminders.describe_due(r)
        suffix = f" ({when})" if when.startswith("overdue") else ""
        lines.append(f"• {r['text']}{suffix}")
    return "\n".join(lines)


def save_briefing(text, broken, demo=False):
    now = datetime.datetime.now(config.tz())
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO briefings (created_at, date, text, broken, demo) VALUES (?, ?, ?, ?, ?)",
            (now.isoformat(), now.date().isoformat(), text,
             json.dumps([b for b, _ in broken]), int(demo)),
        )


def run_briefing(writer=None, send=True):
    """Build, send and store today's brief. Returns the message text.

    `writer` lets demo mode swap in a canned brief when there's no API key.
    """
    stamp = datetime.datetime.now(config.tz()).strftime("%Y-%m-%d %H:%M")
    print(f"=== morning brief {stamp} ===")

    try:
        raw_data, broken = build_raw_data()
    except Exception:
        traceback.print_exc()
        raw_data, broken = "(no data could be loaded)", [("every data source", f"open {config.dashboard_url().rstrip('/')}/setup")]

    due = reminders.due_for_briefing()
    if writer is None and config.is_demo() and not llm.has_key():
        from demo_data import SAMPLE_BRIEF
        writer = lambda raw, due: SAMPLE_BRIEF  # noqa: E731

    try:
        brief = (writer or write_brief)(raw_data, due)
    except Exception as e:
        # Still deliver the reminders - they're the one thing that must not
        # silently disappear because an API call failed.
        traceback.print_exc()
        brief = "⚠️ Couldn't write your brief this morning. " + llm.friendly_error(e)

    parts = [brief]
    if due:
        parts.append(reminders_block(due))
    if config.get()["dashboard"].get("enabled"):
        parts.append(f"📊 Dashboard: {config.dashboard_url()}")
    if broken:
        # Surface dead sources in the message itself, with the exact fix.
        # An expired login used to fail invisibly; now it shows up every
        # morning until it's reconnected.
        fixes = []
        for name, hint in broken:
            fix = (f" -> {hint}" if hint.startswith("open ") else f" -> run: {hint}") if hint else ""
            fixes.append(f"• {name.split(' (')[0]}{fix}")
            print(f"BROKEN SOURCE: {name}")
        parts.append("⚠️ Couldn't reach:\n" + "\n".join(fixes))
    message = "\n\n".join(parts)

    if not (send and config.is_demo()):  # demo "sending" already prints it
        print(message)
    if send:
        telegram_bot.send_message(message)
        print("Sent.")
    reminders.mark_delivered([r["id"] for r in due])
    save_briefing(message, broken, demo=config.is_demo())
    db.kv_set("last_briefing_date", datetime.datetime.now(config.tz()).date().isoformat())
    return message


def main():
    parser = argparse.ArgumentParser(description="Send the morning brief to Telegram now.")
    parser.add_argument("--no-send", action="store_true", help="Print it, don't send it.")
    args = parser.parse_args()
    try:
        run_briefing(send=not args.no_send)
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
