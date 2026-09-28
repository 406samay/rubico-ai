"""
Starts Rubico. On Railway this is what the Dockerfile runs; it does it all:

  - the web page: /setup (first-time setup) and the dashboard
  - the Telegram chat (answers your messages, reminders, email actions)
  - the morning brief, sent every day at briefing.time in YOUR timezone
  - an hourly data refresh for the dashboard charts

Until setup is finished only the web page runs; the bot starts by itself
the moment the Claude key and Telegram chat are filled in on /setup.
"""

import datetime
import os
import sys
import threading
import time
import traceback

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


def wait_for_web_setup():
    """Cloud mode: no terminal, so setup happens in the browser. Keep the web
    page up and start the bot as soon as the essentials are filled in."""
    url = (config.dashboard_url().rstrip("/") + "/setup") if config.public_url() else "your Rubico web address + /setup"
    log(f"Waiting for setup - open {url} (log in with your DASHBOARD_PASSWORD)")
    while missing_essentials():
        time.sleep(3)
    config.reload()
    log("Setup complete - starting the bot.")


def main():
    log(f"Data folder: {config.data_dir()}"
        + ("" if config.has_persistent_storage() else "  ⚠️ NO VOLUME - data will be lost on update!"))
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
    except KeyboardInterrupt:
        log("Stopping. Bye!")
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
