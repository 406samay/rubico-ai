"""
Try Rubico with ZERO accounts connected:

    python demo.py

Uses realistic-but-fake data (a pretend inbox, calendar, bank account and
music history) to show you:
  1. what a morning brief looks like (printed right here in the terminal)
  2. the dashboard, with 6 weeks of fake history, in your browser

Nothing is sent anywhere and no real account is touched. If you have an
ANTHROPIC_API_KEY in .env, the brief is written live by Claude from the fake
data; without one you'll see a pre-written example.

Options:
  --chat         also chat with the bot right here in the terminal
  --no-browser   don't open the dashboard automatically
  --port 8601    use a different port for the dashboard
  --offline      never call Claude, even if a key is set
"""

import argparse
import datetime
import os
import shutil
import sys
import threading
import webbrowser

os.environ["RUBICO_DEMO"] = "1"  # must be set before any tool is imported
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))

import config  # noqa: E402

SAMPLE_BRIEF = (
    "Morning Alex ☀️ Showers on and off today in London, 18° high, so grab a jacket "
    "before the gym tonight.\n\n"
    "Two emails actually need you. Priya wants your regional figures for the Q3 report "
    "by Wednesday EOD, and Jordan is asking if you're still on for dinner Saturday at "
    "7:30 - worth a quick yes. Your dentist wants you to confirm Thursday's 10:15 "
    "check-up, and your IT password expires in 3 days. There's also a new sign-in "
    "alert from your bank - fine if that was you on Windows, otherwise check it. The "
    "MegaStore sale is just noise.\n\n"
    "Calendar: stand-up at 9:30, lunch with Sam at 12:30, and the sprint review has "
    "moved to 3pm. Your parcel lands between 1 and 3, so you'll be out for part of it.\n\n"
    "Money: £1,284 in the account, £12.60 out yesterday, and Jordan sent you £250 🍝\n\n"
    "Focus for today: get Priya her numbers before the sprint review so Wednesday isn't a scramble."
)

PAST_BRIEFS = [
    "Quiet Sunday 😌 Dry and 17°. Nothing urgent in either inbox - just a delivery "
    "update and newsletters. You spent £23 at Tesco yesterday. Focus: prep the week, "
    "that Q3 deadline is Wednesday.",
    "Busy one today. Three meetings back to back from 10, and Priya's chasing the Q3 "
    "numbers. Rain from 2pm. Focus: block 30 minutes before lunch for the figures.",
    "Morning! Light day on the calendar. Your gym membership renews Friday (£34). "
    "You listened to 2 hours of Khruangbin yesterday 🎧 Focus: clear the inbox backlog.",
    "Heads up: the train strike is on tomorrow per the TfL email. Clear skies, 20°. "
    "Focus: sort your commute plan tonight.",
    "Nothing needs a reply today 🎉 Warmest day of the week at 21°. £42 on groceries "
    "yesterday. Focus: that side project you keep putting off.",
]


def seed(days=45):
    import db
    import metrics_store
    import reminders
    import sources

    folder = config.data_dir()
    shutil.rmtree(folder, ignore_errors=True)  # fresh fake data every run
    folder.mkdir(parents=True, exist_ok=True)

    dates = list(metrics_store.date_range(days - 1))
    store = {"meta": {"currency": config.get()["currency"]}, "days": {}}
    for src in sources.enabled_sources():
        for date_str, sections in src.demo_history(dates).items():
            store["days"].setdefault(date_str, {}).update(sections)
    store["meta"]["spotify_since"] = dates[0]
    store["meta"]["top_artists_4w"] = [
        {"name": n, "genres": g} for n, g in [
            ("Fred again..", ["house"]), ("Little Simz", ["uk hip hop"]),
            ("Khruangbin", ["psychedelic soul"]), ("Arctic Monkeys", ["indie rock"]),
            ("Nia Archives", ["jungle"]),
        ]
    ]
    metrics_store.save(store)

    tz = config.tz()
    with db.connect() as conn:
        for i, text in enumerate(PAST_BRIEFS, start=1):
            when = datetime.datetime.now(tz).replace(hour=8, minute=0, second=0) - datetime.timedelta(days=i)
            conn.execute(
                "INSERT INTO briefings (created_at, date, text, broken, demo) VALUES (?, ?, ?, '[]', 1)",
                (when.isoformat(), when.date().isoformat(), text),
            )

    today = reminders.today()
    reminders.add("Submit the parking permit form", today, original="remind me to submit the parking permit form tomorrow")
    reminders.add("Call the dentist to confirm Thursday", None, original="note to self call the dentist")
    reminders.add("Order flowers for Mum's birthday", today + datetime.timedelta(days=3))
    reminders.add("Renew passport - expires in 2 months", today + datetime.timedelta(days=9))


def chat_loop():
    import chat_listener

    print("\n💬 Demo chat - type like you would on Telegram. Try:")
    print("   remind me tomorrow to submit the form   |   /reminders   |   /cancel 3")
    print("   what's on my calendar today?   |   delete the promo emails   |   /help")
    print("   (type 'quit' to exit)\n")
    while True:
        try:
            text = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if text.lower() in ("quit", "exit"):
            return
        if text:
            try:
                chat_listener.handle_message(text)
                chat_listener.process_due_sends()
            except Exception as e:
                print(f"(error: {type(e).__name__}: {e})")


def main():
    parser = argparse.ArgumentParser(description="Run Rubico on fake data.")
    parser.add_argument("--chat", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8600)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    import dashboard_server
    import llm
    import orchestrator

    print("🧪 Rubico demo mode - fake data only, nothing is sent or touched.\n")
    seed()

    config.get()["dashboard"]["port"] = args.port  # so the brief links the right page
    use_claude = llm.has_key() and not args.offline
    print("Writing today's brief " + ("with Claude (from the fake data)..." if use_claude
                                     else "(pre-written example - add ANTHROPIC_API_KEY to .env for a live one)..."))
    writer = None if use_claude else (lambda raw, due: SAMPLE_BRIEF)
    try:
        orchestrator.run_briefing(writer=writer)
    except Exception as e:
        print(f"Claude call failed ({e}) - showing the pre-written example instead.")
        orchestrator.run_briefing(writer=lambda raw, due: SAMPLE_BRIEF)

    server = dashboard_server.make_server(host="127.0.0.1", port=args.port)
    url = f"http://127.0.0.1:{args.port}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"📊 Dashboard running at {url}")
    if not args.no_browser:
        webbrowser.open(url)

    if args.chat:
        chat_loop()
    else:
        print("Press Ctrl+C to stop. (Run `python demo.py --chat` to try chatting too.)")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    print("\nDemo finished. When you're ready for the real thing: python setup.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
