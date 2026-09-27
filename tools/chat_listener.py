"""
Two-way chat: watches Telegram for messages you text the bot.

Most messages just get answered using your recent data. Some trigger
something specific:

  remind me tomorrow to X     -> saves a reminder (see reminders.py)
  /reminders                  -> lists active reminders
  /cancel 3                   -> cancels reminder #3
  search <question>           -> live web search, answered by Claude
  studied <topic>             -> spaced-repetition reviews (optional feature)
  /brief                      -> sends the morning brief right now
  /help                       -> what the bot can do

And three email actions, all with a review window first so nothing
happens silently:
  - Asking it to reply to a specific email: it drafts the reply and sends
    it to you on Telegram with a countdown before it actually sends.
  - Asking it to clean up promotional emails: it counts exactly how many
    Gmail's own Promotions filter has flagged, shows you the list, and
    trashes them (recoverable in Gmail for 30 days) after the countdown.
  - Asking it to delete emails matching a description (e.g. "delete the
    recent login attempts from my bank"): it turns that into a Gmail
    search, shows you exactly what matched, and trashes them after the
    countdown.
In all cases, reply CANCEL during the countdown to stop it.

Run: python tools/chat_listener.py   (run.py starts it for you)
"""

import datetime
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import calendar_actions
import config
import db
import llm
import pending_actions
import reminders
import study_reminders
import telegram_bot
from data_sources import build_raw_data, calendar_accounts, gmail_accounts
from gmail_actions import (
    get_reply_context,
    list_promotional_emails,
    search_messages,
    send_reply,
    trash_messages,
)

CANCEL_WORDS = {"cancel", "stop", "no", "abort"}
SEARCH_PREFIX = "search "
STUDIED_PREFIX = "studied"
REMINDER_START = re.compile(r"^\s*(please\s+)?(remind me|reminder|note to self|note:|remember to)\b", re.I)
CANCEL_REMINDER = re.compile(r"^\s*/?cancel(\s+reminder)?\s+#?(\d+)\s*$", re.I)
LIST_REMINDERS = {"/reminders", "reminders", "list reminders", "my reminders", "/list"}


def send_telegram(text):
    telegram_bot.send_message(text)


def help_text():
    lines = [
        f"Hi! I'm {config.assistant_name()} 👋 Here's what I can do:",
        "",
        "• Ask me anything about your day - emails, calendar, spending, weather",
        "• \"remind me tomorrow to submit the form\" - saves a reminder for that morning's brief",
        "• /reminders - see your reminders,  /cancel 3 - cancel reminder #3",
    ]
    if gmail_accounts():
        lines += [
            "• \"reply to Jordan saying I'm in\" - I draft it, you get "
            f"{pending_actions.window_minutes()} min to say cancel",
            "• \"delete the promo emails\" or \"delete the login alerts from my bank\"",
        ]
    if config.feature("web_search"):
        lines.append("• search <question> - live web search")
    if study_reminders.enabled():
        lines.append("• studied <topic> - spaced-repetition review reminders")
    lines += ["• /brief - send the morning brief now", "", "Reply CANCEL to stop anything that's counting down."]
    return "\n".join(lines)


def _action_instructions():
    """Only describe the actions this user has actually switched on."""
    blocks = []
    today = reminders.today()
    blocks.append(
        "Saving a note or reminder for later (e.g. \"remind me tomorrow to renew my "
        "passport\", \"note to self: call the dentist\", \"on friday remind me about the "
        "invoice\"):\n"
        '{"action": "add_reminder", "text": "<the reminder, short, their own wording, '
        'without the timing phrase>", "due": "<YYYY-MM-DD, or null if no time was given>"}\n'
        f"Today is {today.strftime('%A')} {today.isoformat()} - work out dates from "
        "phrases like 'tomorrow' or 'next friday'. Only use this when they clearly want "
        "something saved for later.\n\n"
        "Listing reminders (e.g. \"what reminders do I have\"):\n"
        '{"action": "list_reminders"}\n\n'
        "Cancelling a reminder (e.g. \"cancel the passport reminder\") - pick its number "
        "from the reminders listed in the data:\n"
        '{"action": "cancel_reminder", "id": <number>}'
    )
    accounts = gmail_accounts()
    if accounts:
        blocks.append(
            "Drafting and sending a reply to one specific email:\n"
            '{"action": "draft_reply", "account": "<account label>", "message_id": '
            '"<the ID shown for that email>", "to": "<sender email address>", '
            '"body": "<the reply text>"}\n'
            "Only do this when there's a clear specific email and clear intent to reply. "
            f"Style for the reply body: {config.get()['assistant']['email_reply_style'].strip()}"
        )
        blocks.append(
            "Cleaning up promotional/marketing emails (e.g. \"delete the promo junk\"):\n"
            '{"action": "bulk_trash_promotions", "accounts": ["<account label>", ...]}\n'
            "List every account if they don't name one. Never invent message IDs or decide "
            "per-email what's promotional yourself - Gmail's own Promotions label handles that."
        )
        blocks.append(
            "Deleting emails matching a description that ISN'T just \"promotions\" (e.g. "
            "\"delete the recent login alerts from my bank\"):\n"
            '{"action": "delete_emails_matching", "accounts": ["<account label>", ...], '
            '"query": "<Gmail search query>", "description": "<short label, e.g. \'bank '
            'login alerts\'>"}\n'
            f"Connected accounts: {', '.join(accounts)}. List every account if they don't "
            "name one. Build 'query' with real Gmail search operators (from:, subject:, "
            "older_than:, newer_than:, etc) so it matches what they described. Don't add a "
            "date restriction unless they imply one."
        )
    if study_reminders.enabled():
        blocks.append(
            "Telling you they studied, learned or read up on something (past tense, e.g. "
            "\"i studied sales forecasting today\"):\n"
            '{"action": "log_study_topic", "topic": "<short topic name>"}\n'
            "NOT for questions about a topic (\"how does X work\", \"quiz me on X\")."
        )
    return "\n\n".join(f"{i}. {b}" for i, b in enumerate(blocks, 1))


def ask_claude(question, raw_data):
    active = reminders.list_active()
    reminder_lines = "\n".join(f"#{r['id']}: {r['text']} ({reminders.describe_due(r)})" for r in active)
    system = (
        "You help the user with their email, calendar, and other connected data below "
        "- each email is shown with an ID and which account it's in.\n\n"
        "Some requests get a JSON response instead of plain text - ONLY the JSON "
        "object, nothing else:\n\n" + _action_instructions() + "\n\n"
        "For anything else, answer normally in plain text - be direct and concise, and "
        "say so plainly if the data doesn't have enough to answer. "
        + llm.voice_instructions()
        + "\n\n--- Active reminders ---\n" + (reminder_lines or "(none)")
        + "\n\n" + raw_data
    )
    return llm.ask(system, question)


def web_search_answer(query):
    system = (
        "Answer the user's question using web search. Be direct and concise, suitable "
        "for a text message - a couple of short paragraphs at most. " + llm.voice_instructions()
    )
    answer = llm.ask(
        system, query,
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}],
    )
    return answer or "Couldn't find an answer to that."


VALID_ACTIONS = {
    "draft_reply", "bulk_trash_promotions", "delete_emails_matching",
    "log_study_topic", "add_reminder", "list_reminders", "cancel_reminder",
}


def try_parse_action(answer):
    if not answer.strip().startswith("{") and not answer.strip().startswith("```"):
        return None
    data = llm.parse_json_object(answer)
    return data if data and data.get("action") in VALID_ACTIONS else None


# ---------------------------------------------------------------- handlers

def handle_draft_action(action):
    context = get_reply_context(action["account"], action["message_id"])
    pending_actions.create_pending_send(
        account_label=action["account"],
        to=action["to"],
        subject=context["subject"],
        thread_id=context["thread_id"],
        in_reply_to_header=context["message_id_header"],
        body=action["body"],
    )
    send_telegram(
        f"Draft reply to {action['to']} 📝 re: {context['subject']}\n\n{action['body']}\n\n"
        f"Sending automatically in {pending_actions.window_minutes()} minutes. Reply CANCEL to stop it."
    )


def _queue_trash(account, previews, what):
    pending_actions.create_pending_trash(
        account_label=account,
        message_ids=[p["id"] for p in previews],
        preview_lines=[f"{p['from']}: {p['subject']}" for p in previews],
    )
    listing = "\n".join(f"- {p['from']}: {p['subject']}" for p in previews[:15])
    more = f"\n...and {len(previews) - 15} more" if len(previews) > 15 else ""
    send_telegram(
        f"Found {len(previews)} {what} in {account} 🗑️\n{listing}{more}\n\n"
        f"Moving them to Trash in {pending_actions.window_minutes()} minutes (recoverable "
        "from Gmail Trash for 30 days). Reply CANCEL to stop it."
    )


def handle_bulk_trash_action(action):
    for account in action["accounts"]:
        previews = list_promotional_emails(account)
        if not previews:
            send_telegram(f"No promotional emails in {account} right now 👍")
            continue
        _queue_trash(account, previews, "promotional emails")


def handle_delete_matching_action(action):
    query = action["query"]
    description = action.get("description", query)
    for account in action["accounts"]:
        previews = search_messages(account, query)
        if not previews:
            send_telegram(f"Couldn't find anything matching \"{description}\" in {account} "
                          f"(searched: {query})")
            continue
        _queue_trash(account, previews, f"emails matching \"{description}\" (searched: {query})")


def _describe(action):
    if action["type"] == "gmail_reply":
        return f"the reply to {action['to']}"
    if action["type"] == "gmail_bulk_trash":
        return f"trashing {len(action['message_ids'])} emails in {action['account']}"
    return "that"


def handle_add_reminder(text, due_value, original):
    due = reminders._coerce_date(due_value, reminders.today())
    reminder_id = reminders.add(text, due, original=original)
    send_telegram(reminders.confirmation(reminder_id))


def handle_quick_reminder(message):
    text, due = reminders.parse(message)
    reminder_id = reminders.add(text, due, original=message)
    send_telegram(reminders.confirmation(reminder_id))


def handle_cancel_reminder(reminder_id):
    r = reminders.get(reminder_id)
    if r and reminders.cancel(reminder_id):
        send_telegram(f"Cancelled reminder #{reminder_id}: \"{r['text']}\" ✅")
    else:
        send_telegram(f"There's no active reminder #{reminder_id}.\n\n" + reminders.format_list())


def handle_studied_log(topic):
    entry = study_reminders.create_topic(topic)

    calendar_added = 0
    cal_accounts = calendar_accounts()
    if cal_accounts and config.feature("study_reminders").get("add_to_calendar"):
        for stage in entry["stages"]:
            due_dt = study_reminders.parse_datetime(stage["due_at"])
            try:
                event_id = calendar_actions.create_event(
                    account_label=cal_accounts[0],
                    summary=f"Review: {topic}",
                    start_dt=due_dt,
                    duration_minutes=15,
                    description=f"Spaced-repetition review reminder, logged via {config.assistant_name()}.",
                )
                study_reminders.set_calendar_event_id(entry["id"], stage["day"], event_id)
                calendar_added += 1
            except Exception as e:
                print(f"Calendar event failed for day {stage['day']} of \"{topic}\": {e}")

    dates = ", ".join(
        f"day {stage['day']}: {study_reminders.parse_datetime(stage['due_at']).strftime('%a %b %d')}"
        for stage in entry["stages"]
    )
    total = len(entry["stages"])
    calendar_note = (
        f" Added all {total} to your calendar too 📅" if calendar_added == total
        else f" ({calendar_added}/{total} made it onto your calendar.)" if calendar_added
        else ""
    )
    send_telegram(
        f"Logged \"{topic}\" 📚 I'll ping you to review it on {dates} - spaced "
        f"repetition so it actually sticks 🧠{calendar_note}"
    )


def process_due_study_reminders():
    if not study_reminders.enabled():
        return
    for topic, stage in study_reminders.get_due_reminders():
        studied_date = study_reminders.parse_datetime(topic["studied_at"]).strftime("%b %d")
        day_word = "day" if stage["day"] == 1 else "days"
        send_telegram(
            f"📚 Review time - it's been {stage['day']} {day_word} since you studied "
            f"\"{topic['topic']}\" (logged {studied_date}). Give it a quick recall before it fades 🧠"
        )
        study_reminders.mark_sent(topic["id"], stage["day"])


def handle_cancel():
    pending = pending_actions.get_latest_pending()
    if not pending:
        send_telegram("Nothing pending to cancel. (To cancel a reminder, use /cancel <number>.)")
        return
    pending_actions.mark_status(pending["id"], "cancelled")
    send_telegram(f"Cancelled {_describe(pending)} 👍")


def process_due_sends():
    for action in pending_actions.get_due_pending():
        try:
            if action["type"] == "gmail_reply":
                send_reply(
                    account_label=action["account"], to=action["to"], subject=action["subject"],
                    thread_id=action["thread_id"], in_reply_to_header=action["in_reply_to_header"],
                    body=action["body"],
                )
                pending_actions.mark_status(action["id"], "sent")
                send_telegram(f"Sent that reply to {action['to']} ✅")
            elif action["type"] == "gmail_bulk_trash":
                trash_messages(action["account"], action["message_ids"])
                pending_actions.mark_status(action["id"], "sent")
                send_telegram(f"Moved {len(action['message_ids'])} emails in {action['account']} to Trash 🗑️")
        except Exception as e:
            pending_actions.mark_status(action["id"], "failed")
            send_telegram(f"Couldn't complete {_describe(action)} - {e} ⚠️")


def handle_message(text):
    """Everything one incoming message can do. Shared by Telegram and demo chat."""
    stripped = text.strip()
    lower = stripped.lower()

    if lower in ("/start", "/help", "help"):
        return send_telegram(help_text())
    if lower in CANCEL_WORDS:
        return handle_cancel()
    if lower in LIST_REMINDERS:
        return send_telegram(reminders.format_list())
    m = CANCEL_REMINDER.match(stripped)
    if m:
        return handle_cancel_reminder(int(m.group(2)))
    if lower == "/brief":
        import orchestrator
        return orchestrator.run_briefing(unattended=True)
    if lower.startswith(SEARCH_PREFIX) and config.feature("web_search"):
        return send_telegram(web_search_answer(stripped[len(SEARCH_PREFIX):].strip()))
    if lower.startswith(STUDIED_PREFIX) and study_reminders.enabled():
        topic = stripped[len(STUDIED_PREFIX):].lstrip(":").strip()
        if not topic:
            return send_telegram("What did you study? Text it like \"studied mitochondria\" 📚")
        return handle_studied_log(topic)
    if REMINDER_START.match(stripped):
        # Obvious reminders skip fetching all your data - faster and cheaper.
        return handle_quick_reminder(stripped)

    if not llm.has_key():
        return send_telegram("I need an ANTHROPIC_API_KEY in .env to answer that. "
                             "Reminders (/reminders, /cancel) still work without it.")

    raw_data, _broken = build_raw_data()
    answer = ask_claude(stripped, raw_data)
    action = try_parse_action(answer)
    kind = action["action"] if action else None

    if kind == "draft_reply":
        handle_draft_action(action)
    elif kind == "bulk_trash_promotions":
        handle_bulk_trash_action(action)
    elif kind == "delete_emails_matching":
        handle_delete_matching_action(action)
    elif kind == "log_study_topic" and study_reminders.enabled():
        handle_studied_log(action["topic"])
    elif kind == "add_reminder":
        handle_add_reminder(action.get("text") or stripped, action.get("due"), stripped)
    elif kind == "list_reminders":
        send_telegram(reminders.format_list())
    elif kind == "cancel_reminder":
        handle_cancel_reminder(int(action.get("id", 0)))
    else:
        send_telegram(answer)


def poll_once(offset):
    """One round: run due jobs, fetch new messages, handle them. Returns new offset."""
    process_due_sends()
    process_due_study_reminders()

    updates = telegram_bot.get_updates(offset + 1 if offset is not None else None)
    allowed_chat = str(config.env("TELEGRAM_CHAT_ID"))
    for update in updates:
        offset = update["update_id"]
        db.kv_set("telegram_offset", offset)

        message = update.get("message")
        if not message or "text" not in message:
            continue
        # The bot is yours alone: anyone else who finds it gets ignored.
        if str(message["chat"]["id"]) != allowed_chat:
            print(f"Ignored message from unknown chat {message['chat']['id']}")
            continue

        print(f"Message: {message['text']}")
        try:
            handle_message(message["text"])
        except Exception as e:
            print(f"Error handling message: {type(e).__name__}: {e}")
            send_telegram(f"Something went wrong handling that ⚠️ ({type(e).__name__}: {e})")
    return offset


def main(stop_event=None):
    print(f"[{datetime.datetime.now():%H:%M:%S}] Listening for Telegram messages. Ctrl+C to stop.")
    offset = db.kv_get("telegram_offset")
    backoff = 5
    while not (stop_event and stop_event.is_set()):
        try:
            offset = poll_once(offset)
            backoff = 5
        except KeyboardInterrupt:
            raise
        except Exception as e:
            # Wi-Fi drops, Telegram hiccups: wait and try again rather than crash.
            print(f"Chat loop error ({type(e).__name__}: {e}) - retrying in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)


if __name__ == "__main__":
    main()
