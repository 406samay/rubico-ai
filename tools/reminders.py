"""
Notes and reminders you text the bot.

Send something like "remind me tomorrow to submit the form" and it gets
stored with the date it should come back:
  - a specific day ("tomorrow", "in 3 days", "on friday", "oct 5")
  - or no date at all -> it comes back in the very next morning brief

Every morning brief pulls in whatever is due that day (or overdue, or
"next brief"), then marks those delivered so they don't repeat.

Chat commands:
  /reminders      list what's still waiting
  /cancel 4       cancel reminder #4

Claude reads the wording and picks the date. If Claude isn't available
(no API key, network down, demo mode), simple_parse() handles the common
phrasings on its own so a reminder is never lost.
"""

import datetime
import re

import config
import db
import llm

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def today():
    return datetime.datetime.now(config.tz()).date()


# ---------------------------------------------------------------- storage

def add(text, due_date=None, original=None):
    """due_date: a datetime.date, or None for 'next briefing'."""
    now = datetime.datetime.now(config.tz()).isoformat()
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (text, due_date, status, created_at, original) "
            "VALUES (?, ?, 'active', ?, ?)",
            (text, due_date.isoformat() if due_date else None, now, original),
        )
        return cur.lastrowid


def get(reminder_id):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
    return dict(row) if row else None


def list_active():
    """Soonest first; 'next briefing' ones (no date) at the top."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE status = 'active' "
            "ORDER BY due_date IS NOT NULL, due_date, id"
        ).fetchall()
    return [dict(r) for r in rows]


def cancel(reminder_id):
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE reminders SET status = 'cancelled' WHERE id = ? AND status = 'active'",
            (reminder_id,),
        )
        return cur.rowcount > 0


def due_for_briefing(on_date=None):
    """Everything the brief on `on_date` should include: no-date notes, plus
    anything due that day or earlier (so a missed brief doesn't lose one)."""
    on_date = on_date or today()
    return [
        r for r in list_active()
        if r["due_date"] is None or r["due_date"] <= on_date.isoformat()
    ]


def mark_delivered(ids):
    if not ids:
        return
    now = datetime.datetime.now(config.tz()).isoformat()
    with db.connect() as conn:
        conn.executemany(
            "UPDATE reminders SET status = 'delivered', delivered_at = ? WHERE id = ?",
            [(now, i) for i in ids],
        )


# ---------------------------------------------------------------- wording

def describe_due(reminder, on_date=None):
    on_date = on_date or today()
    if not reminder["due_date"]:
        return "next brief"
    due = datetime.date.fromisoformat(reminder["due_date"])
    delta = (due - on_date).days
    if delta < 0:
        return f"overdue since {due.strftime('%a %d %b')}"
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    return due.strftime("%a %d %b")


def format_list(items=None):
    items = list_active() if items is None else items
    if not items:
        return "No active reminders. Text me something like \"remind me tomorrow to call the bank\" to add one."
    lines = ["Your reminders:"]
    for r in items:
        lines.append(f"#{r['id']}  {r['text']}  ({describe_due(r)})")
    lines.append("\nCancel one with /cancel <number>, e.g. /cancel " + str(items[0]["id"]))
    return "\n".join(lines)


def confirmation(reminder_id):
    r = get(reminder_id)
    when = describe_due(r)
    when_text = "in your next morning brief" if when == "next brief" else f"in the morning brief {when}"
    if when not in ("next brief", "today", "tomorrow"):
        when_text = f"in the morning brief on {when}"
    return f"Saved as reminder #{r['id']} 📌 I'll bring it up {when_text}:\n\"{r['text']}\""


# ---------------------------------------------------------------- parsing

def _coerce_date(value, base):
    """Accepts what Claude returns: an ISO date, or null / 'next_briefing'."""
    if value in (None, "", "null", "next_briefing", "next brief"):
        return None
    try:
        due = datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return simple_parse(str(value), base)[1]
    return max(due, base)  # a date in the past just means "as soon as possible"


def parse_with_claude(message, base=None):
    """Returns (reminder_text, due_date_or_None). Raises if Claude fails."""
    base = base or today()
    system = (
        "You turn a note someone texted into a reminder. Reply with ONLY a JSON "
        'object: {"text": "<what to remind them about, short, in their own '
        'words, without the timing phrase>", "due": "<YYYY-MM-DD or null>"}\n'
        f"Today is {base.strftime('%A')} {base.isoformat()}. Work out the date "
        "from phrases like 'tomorrow', 'in 3 days', 'next friday', 'on the 5th', "
        "'end of the month'. If no time is mentioned, use null - it will then "
        "show up in their next morning brief. 'Tonight' or 'later today' means "
        "today's date."
    )
    data = llm.parse_json_object(llm.ask(system, message, max_tokens=300))
    if not data or not data.get("text"):
        raise ValueError("Claude didn't return a usable reminder")
    return data["text"].strip(), _coerce_date(data.get("due"), base)


_PREFIX = re.compile(
    r"^\s*(please\s+)?(remind\s+me|reminder|note\s+to\s+self|note|remember)\b[\s:,-]*(to\s+)?",
    re.I,
)


def simple_parse(message, base=None):
    """No-AI fallback for the common phrasings. Returns (text, date_or_None)."""
    base = base or today()
    text = message.strip()
    low = text.lower()
    due = None

    patterns = [
        (r"\bday after tomorrow\b", lambda m: base + datetime.timedelta(days=2)),
        (r"\btomorrow\b", lambda m: base + datetime.timedelta(days=1)),
        (r"\b(today|tonight|later today)\b", lambda m: base),
        (r"\bin (\d+) days?\b", lambda m: base + datetime.timedelta(days=int(m.group(1)))),
        (r"\bin (\d+) weeks?\b", lambda m: base + datetime.timedelta(weeks=int(m.group(1)))),
        (r"\bin a week\b|\bnext week\b", lambda m: base + datetime.timedelta(days=7)),
        (r"\b(\d{4}-\d{2}-\d{2})\b", lambda m: datetime.date.fromisoformat(m.group(1))),
        (r"\b(?:on |next |this )?(" + "|".join(WEEKDAYS) + r")\b", _next_weekday(base)),
        (r"\b(?:on )?(\d{1,2})(?:st|nd|rd|th)? (" + "|".join(MONTHS) + r")[a-z]*\b",
         _day_month(base, day_first=True)),
        (r"\b(?:on )?(" + "|".join(MONTHS) + r")[a-z]* (\d{1,2})(?:st|nd|rd|th)?\b",
         _day_month(base, day_first=False)),
    ]
    for pattern, resolve in patterns:
        m = re.search(pattern, low)
        if m:
            try:
                due = resolve(m)
            except ValueError:
                continue
            text = (text[:m.start()] + text[m.end():]).strip()
            break

    text = _PREFIX.sub("", text).strip(" ,.-:")
    text = re.sub(r"\s{2,}", " ", text)
    if due is not None:
        due = max(due, base)
    return (text or message.strip()), due


def _next_weekday(base):
    def resolve(m):
        target = WEEKDAYS.index(m.group(1))
        ahead = (target - base.weekday()) % 7 or 7
        return base + datetime.timedelta(days=ahead)
    return resolve


def _day_month(base, day_first):
    def resolve(m):
        day, month = (m.group(1), m.group(2)) if day_first else (m.group(2), m.group(1))
        month_num = MONTHS.index(month[:3]) + 1
        due = datetime.date(base.year, month_num, int(day))
        if due < base:
            due = datetime.date(base.year + 1, month_num, int(day))
        return due
    return resolve


def parse(message, base=None):
    """Claude first (understands anything), plain rules as the safety net."""
    if llm.has_key() and not config.is_demo():
        try:
            return parse_with_claude(message, base)
        except Exception as exc:
            print(f"Claude couldn't parse reminder, using simple parser: {exc}")
    return simple_parse(message, base)
