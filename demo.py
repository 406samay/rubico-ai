"""
Try Rubico with ZERO accounts connected:

    python demo.py

Uses realistic-but-fake data (a pretend inbox, calendar, bank account and
music history). Two tabs open in your browser:
  1. 💬 a Telegram-style chat - this morning's brief is waiting, and you can
     text the bot just like you would in Telegram
  2. 📊 the dashboard, with 6 weeks of fake history

Nothing is sent anywhere and no real account is touched. If you have an
ANTHROPIC_API_KEY in .env, the brief is written live by Claude from the fake
data; without one you'll see a pre-written example.

Options:
  --chat         chat in this terminal instead of the browser
  --no-browser   don't open the dashboard automatically
  --port 8601    use a different port for the dashboard
  --offline      never call Claude, even if a key is set
"""

import argparse
import datetime
import os
import sys
import threading
import time
import webbrowser

os.environ["RUBICO_DEMO"] = "1"  # must be set before any tool is imported
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))

import config  # noqa: E402
from demo_data import PAST_BRIEFS, SAMPLE_BRIEF  # noqa: E402

def seed(days=45):
    import db
    import metrics_store
    import reminders
    import sources

    config.data_dir()  # make sure the demo folder exists
    # Fresh fake data every run. Only ever delete the demo's own database -
    # never a folder - so a mistake can't touch anyone's real data.
    if config.is_demo() and db.db_path().exists():
        db.db_path().unlink()

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
        brief = orchestrator.run_briefing(writer=writer)
    except Exception as e:
        print(f"Claude call failed ({e}) - showing the pre-written example instead.")
        brief = orchestrator.run_briefing(writer=lambda raw, due: SAMPLE_BRIEF)
    dashboard_server.demo_chat_history.append({"from": "bot", "text": brief, "time": config.get()["briefing"]["time"]})

    server = None
    for port in range(args.port, args.port + 20):  # skip ports already in use
        try:
            server = dashboard_server.make_server(host="127.0.0.1", port=port)
            break
        except OSError:
            continue
    if server is None:
        print(f"Couldn't find a free port near {args.port}. Try: python demo.py --port 9100")
        return 1
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"\n💬 Chat with the bot:  {url}chat")
    print(f"📊 Dashboard:          {url}")
    if not args.no_browser:
        webbrowser.open(url)
        if not args.chat:
            webbrowser.open(url + "chat")

    if args.chat:
        chat_loop()
    else:
        print("\nPress Ctrl+C to stop.")
        try:
            while True:  # a plain sleep loop so Ctrl+C works on Windows too
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    print("\nDemo finished. When you're ready for the real thing: python setup.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
