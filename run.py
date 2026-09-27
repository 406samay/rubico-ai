"""
Start Rubico. One command runs everything:

    python run.py

  - the Telegram chat (answers your messages, reminders, email actions)
  - the morning brief, sent every day at briefing.time in YOUR timezone
  - the dashboard web page (http://127.0.0.1:8600 by default)
  - an hourly data refresh for the dashboard charts

Leave it running (on a laptop that stays on, a Raspberry Pi, a home server).
Press Ctrl+C to stop. First time? Run `python setup.py` before this.
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
    up at lunchtime just because the computer was off in the morning.

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
                orchestrator.run_briefing(unattended=True)
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

    server = dashboard_server.make_server()
    log(f"Dashboard: {config.dashboard_url()}")
    threading.Thread(target=server.serve_forever, daemon=True, name="dashboard").start()


def main():
    missing = [k for k in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not config.env(k)]
    if missing:
        print("Missing from .env: " + ", ".join(missing))
        print("Run `python setup.py` first (or `python demo.py` to try it with fake data).")
        return 1

    cfg = config.get()
    on = [name for name, s in cfg["sources"].items() if s.get("enabled")]
    log(f"{config.assistant_name()} starting. Sources on: {', '.join(on) or 'none'}. "
        f"Brief at {cfg['briefing']['time']} ({cfg['timezone']}).")

    stop = threading.Event()
    if cfg["dashboard"].get("enabled"):
        dashboard_thread()
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
