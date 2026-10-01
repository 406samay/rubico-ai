"""
Starts Rubico. On Railway this is what the Dockerfile runs, and on your own
computer you run it with `python run.py --local` (or double click start.bat,
start.command or start.sh). Either way it does it all:

  - the web page: /setup (first-time setup) and the dashboard
  - the Telegram chat (answers your messages, reminders, email actions)
  - the morning brief, sent every day at briefing.time in YOUR timezone
  - an hourly data refresh for the dashboard charts

Until setup is finished only the web page runs; the bot starts by itself
the moment the Claude key and Telegram chat are filled in on /setup.

--local runs it on your own computer: the page only opens on this computer,
your settings sit next to the code, and the brief only goes out while the
computer is on. A small server is better for a daily brief, see the README.
"""

import datetime
import os
import signal
import sys
import threading
import time
import traceback
import webbrowser

# Must happen before config is imported, because config reads it.
if "--local" in sys.argv:
    sys.argv.remove("--local")
    os.environ["RUBICO_CLOUD"] = "0"

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))

import config  # noqa: E402
import db  # noqa: E402


def log(msg):
    print(f"[{datetime.datetime.now(config.tz()):%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def briefing_due(now):
    """True once today's briefing time has passed and today's brief hasn't
    gone out - but only within the catch-up window, so a brief never turns
    up at lunchtime just because Rubico was restarting in the morning.

    Uses your timezone from config.yaml, so clock changes (summer/winter
    time) are handled automatically - no cron DST tricks needed.
    """
    cfg = config.get()["briefing"]
    hh, mm = config.parse_time(cfg["time"])
    scheduled = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < scheduled:
        return False
    if db.kv_get("last_briefing_date") == now.date().isoformat():
        return False
    late_by = (now - scheduled).total_seconds() / 60
    if late_by > cfg.get("catch_up_minutes", 90):
        return False
    return True


def scheduler_loop(stop):
    import collect_metrics
    import orchestrator

    every = max(5, int(config.get()["metrics"].get("collect_every_minutes", 60)))
    next_collect = time.monotonic() + 30  # first refresh shortly after start-up
    while not stop.is_set():
        now = datetime.datetime.now(config.tz())
        try:
            if briefing_due(now):
                log("Sending the morning brief...")
                orchestrator.run_briefing()
        except Exception:
            traceback.print_exc()
            # Mark it done anyway: retrying every 30s would spam you.
            db.kv_set("last_briefing_date", now.date().isoformat())

        if time.monotonic() >= next_collect:
            try:
                collect_metrics.collect(log=lambda m: log(f"metrics: {m}"))
            except Exception:
                traceback.print_exc()
            next_collect = time.monotonic() + every * 60
        stop.wait(30)


def dashboard_thread():
    import dashboard_server

    try:
        server = dashboard_server.make_server()
    except OSError as e:
        log(f"Dashboard couldn't start ({e}). Is another copy of Rubico or the demo running? "
            "Change dashboard.port in config.yaml to use a different port.")
        return
    log(f"Dashboard: {config.dashboard_url()}")
    threading.Thread(target=server.serve_forever, daemon=True, name="dashboard").start()


def announce_bot():
    """Adds the / command menu in Telegram and remembers the bot's username
    so the dashboard's "Open chat" button can link straight to it."""
    import telegram_bot
    try:
        telegram_bot.set_commands()
        username = telegram_bot.bot_username()
        db.kv_set("bot_username", username)
        log(f"Telegram: text your bot at https://t.me/{username}")
    except Exception as e:
        log(f"Telegram: couldn't reach the bot yet ({e}) - will keep trying")


ESSENTIALS = ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")


def missing_essentials():
    return [k for k in ESSENTIALS if not config.env(k)]


def open_in_browser(url):
    """Opens the setup page for you on your own computer. Set RUBICO_NO_BROWSER=1
    to turn that off (the tests and the GitHub checks do)."""
    if config.env("RUBICO_NO_BROWSER"):
        return
    try:
        webbrowser.open(url)
    except Exception:
        pass  # the address is printed above, so you can open it yourself


GUIDE_URL = "https://github.com/406samay/rubico-ai/blob/main/docs/deploy-railway.md"

WHERE_QUESTION = """
  Where do you want Rubico to run?

    1) On Railway (recommended). A small private server, about $5 a month.
       Your brief arrives every morning even when your computer is off, and
       you set it up from your phone in about 15 minutes.

    2) On this computer. It's free and good for trying Rubico out, but the
       brief only goes out while this computer is on and awake.
"""

RAILWAY_STEPS = f"""
  Great choice. Here is the short version, and the full guide with pictures is here.
      {GUIDE_URL}

    1. Fork the Rubico repo on GitHub (the Fork button at the top of its page).
    2. On railway.com choose New Project, then Deploy from GitHub repo, and pick your fork.
    3. Add two variables, DASHBOARD_PASSWORD (a password you choose) and PORT set to 8080.
    4. Add a volume at /data, then generate a domain.
    5. Open your new address with /setup on the end and follow the cards.

  The guide should open in your browser. Run this again any time to use your computer instead.
"""


def ask_where_it_runs():
    """The first time Rubico starts on a computer, ask whether the person would
    rather use Railway. The answer is remembered, so it only asks once.
    Returns True to carry on running here, False when they chose Railway."""
    if not config.is_local() or config.get().get("where") or not missing_essentials():
        return True
    if not sys.stdin or not sys.stdin.isatty():
        return True  # nobody to ask (the GitHub checks run like this)
    print(WHERE_QUESTION)
    while True:
        try:
            answer = input("  Type 1 or 2 and press Enter: ").strip()
        except EOFError:
            return True
        if answer == "1":
            print(RAILWAY_STEPS)
            open_in_browser(GUIDE_URL)
            return False
        if answer == "2":
            config.save_user_config({"where": "laptop"})
            print("\n  Okay, setting Rubico up on this computer.\n")
            return True
        print("  Please type 1 or 2.")


def wait_for_web_setup():
    """Cloud mode: no terminal, so setup happens in the browser. Keep the web
    page up and start the bot as soon as the essentials are filled in."""
    if config.is_local():
        url = config.local_setup_url()
        log(f"Waiting for setup - opening {url}")
        open_in_browser(url)
    else:
        url = (config.dashboard_url().rstrip("/") + "/setup") if config.public_url() else "your Rubico web address + /setup"
        log(f"Waiting for setup - open {url} (log in with your DASHBOARD_PASSWORD)")
    while missing_essentials():
        time.sleep(3)
    config.reload()
    log("Setup complete - starting the bot.")


def stop_on_sigterm():
    """A server (Railway, Docker) stops Rubico with SIGTERM, so treat it like Ctrl+C
    and shut down cleanly instead of being killed after a timeout."""
    def on_sigterm(*_):
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGTERM, on_sigterm)
    except (ValueError, OSError):
        pass  # not the main thread, or a system without SIGTERM


def main():
    try:
        return serve()
    except KeyboardInterrupt:
        log("Stopping. Bye!")
        return 0


def serve():
    stop_on_sigterm()
    if config.is_local():
        log(f"Running on this computer. Data folder: {config.data_dir()}")
    else:
        log(f"Data folder: {config.data_dir()}"
            + ("" if config.has_persistent_storage() else "  ⚠️ NO VOLUME - data will be lost on update!"))
    if not ask_where_it_runs():
        return 0
    dashboard_thread()  # the setup page lives here, so it always starts first
    if missing_essentials():
        wait_for_web_setup()

    cfg = config.get()
    on = [name for name, s in cfg["sources"].items() if s.get("enabled")]
    log(f"{config.assistant_name()} starting. Sources on: {', '.join(on) or 'none'}. "
        f"Brief at {cfg['briefing']['time']} ({cfg['timezone']}).")

    announce_bot()
    stop = threading.Event()
    threading.Thread(target=scheduler_loop, args=(stop,), daemon=True, name="scheduler").start()

    import chat_listener
    try:
        chat_listener.main(stop)
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
