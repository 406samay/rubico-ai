"""
One place that knows your personal settings.

Two files feed it:
  - config.yaml  -> non-secret settings (your name, city, timezone, which
                    data sources are switched on). Starts as a copy of
                    config.example.yaml - setup.py writes it for you.
  - .env         -> secrets (API keys, bot token). Never committed to git.

Every other tool asks this module instead of hardcoding anything, so the
same code works for anyone who clones the repo.

Environment overrides (mostly for demo mode, tests and cloud hosting):
  RUBICO_CONFIG    path to a different config file
  RUBICO_DATA_DIR  where the database and login tokens live
  RUBICO_DEMO=1    run on fake data, never touch real accounts
  RUBICO_CLOUD=1   running on a server (e.g. Railway) - see "Cloud mode" below
"""

import copy
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
# RUBICO_ENV_FILE lets tests use a throwaway secrets file instead of yours.
ENV_FILE = Path(os.environ.get("RUBICO_ENV_FILE", ROOT / ".env"))
load_dotenv(ENV_FILE)

# Every setting has a sensible default here, so a missing or half-filled
# config.yaml still works. config.example.yaml documents each one.
DEFAULTS = {
    "user": {"name": ""},
    "timezone": "Europe/London",
    "locale": "en-GB",
    "currency": "GBP",
    "location": {"name": "London", "latitude": 51.5072, "longitude": -0.1276},
    "briefing": {
        "time": "08:00",
        "max_words": 200,
        # If Rubico was off at briefing time, still send it when it starts
        # up - but only within this many minutes. A "morning" brief that
        # turns up at lunchtime is worse than none.
        "catch_up_minutes": 90,
    },
    "assistant": {
        "name": "Rubico",
        "model": "claude-sonnet-5",
        "voice": (
            "Friendly, warm and direct, like a helpful friend texting. Plain "
            "sentences, a light touch of emoji is fine. Never drop useful "
            "information just to be brief."
        ),
        "email_reply_style": (
            "Match the tone of the email being replied to. Short, clear and "
            "polite. Sign off with the user's first name if it is known."
        ),
        "review_window_minutes": 10,
    },
    "sources": {
        "gmail": {"enabled": False, "accounts": [], "max_emails": 10},
        "calendar": {"enabled": False, "accounts": []},
        "weather": {"enabled": True},
        "monzo": {"enabled": False, "window_days": 85},
        "spotify": {"enabled": False},
    },
    "features": {
        "web_search": True,
        "study_reminders": {
            "enabled": False,
            "schedule_days": [1, 3, 7, 14, 30],
            "reminder_time": "08:00",
            "add_to_calendar": True,
        },
    },
    "dashboard": {
        "enabled": True,
        # 127.0.0.1 = only reachable from this computer. Safest default:
        # the dashboard can show your bank balance.
        "host": "127.0.0.1",
        "port": 8600,
        "public_url": "",
    },
    "metrics": {"collect_every_minutes": 60},
    "storage": {"data_dir": "data"},
}

# What demo mode switches on. Fake account names only - nothing real.
DEMO_OVERRIDES = {
    "user": {"name": "Alex"},
    "location": {"name": "London", "latitude": 51.5072, "longitude": -0.1276},
    "sources": {
        "gmail": {"enabled": True, "accounts": ["personal", "work"]},
        "calendar": {"enabled": True, "accounts": ["personal"]},
        "weather": {"enabled": True},
        "monzo": {"enabled": True},
        "spotify": {"enabled": True},
    },
    "features": {"study_reminders": {"enabled": True, "add_to_calendar": False}},
    "storage": {"data_dir": "data/demo"},
}

_cache = None


def _deep_merge(base, override):
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------- cloud mode
# On a server (Railway) there's no terminal and the code folder is wiped on
# every update. So in cloud mode:
#   - everything you set up is saved on the persistent volume: config.yaml,
#     secrets.env (keys pasted into the browser setup page) and the database
#   - the web page listens on the port the host gives us ($PORT), on all
#     addresses, and is always password-protected (DASHBOARD_PASSWORD)
#   - links point at the public web address instead of 127.0.0.1

def is_cloud():
    flag = os.environ.get("RUBICO_CLOUD", "").strip().lower() in ("1", "true", "yes")
    return flag or bool(os.environ.get("RAILWAY_ENVIRONMENT_NAME") or os.environ.get("RAILWAY_ENVIRONMENT"))


def _cloud_dir():
    return Path(os.environ.get("RUBICO_DATA_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or ROOT / "data")


def has_persistent_storage():
    """On Railway, data only survives updates if a volume is attached."""
    return bool(os.environ.get("RUBICO_DATA_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH"))


def secrets_file():
    """Where keys entered in the browser setup page are saved."""
    return _cloud_dir() / "secrets.env" if is_cloud() else ENV_FILE


def public_url():
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    return f"https://{domain}/" if domain else ""


def save_secret(key, value):
    """Stores a key and makes it live immediately, no restart needed."""
    from dotenv import set_key

    path = secrets_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    set_key(str(path), key, value, quote_mode="never")
    os.environ[key] = value
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def config_path():
    if os.environ.get("RUBICO_CONFIG"):
        return Path(os.environ["RUBICO_CONFIG"])
    return _cloud_dir() / "config.yaml" if is_cloud() else ROOT / "config.yaml"


def save_user_config(updates):
    """Merges `updates` into config.yaml (only your changes are stored)."""
    data = _deep_merge(load_user_file(), updates)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Your Rubico settings. Every option is explained in config.example.yaml.\n"
        "# Edit freely, or re-run setup to change things step by step.\n\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return reload()


def is_demo():
    return os.environ.get("RUBICO_DEMO", "").strip().lower() in ("1", "true", "yes")


def load_user_file():
    """Just what's in config.yaml, without defaults (setup.py edits this)."""
    path = config_path()
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get():
    global _cache
    if _cache is None:
        if is_cloud():
            load_dotenv(secrets_file())  # real environment variables still win
        cfg = _deep_merge(DEFAULTS, load_user_file())
        if is_demo():
            cfg = _deep_merge(cfg, DEMO_OVERRIDES)
        if is_cloud():
            dash = cfg["dashboard"]
            dash.update(enabled=True, host="0.0.0.0", port=int(os.environ.get("PORT") or 8080))
            dash["public_url"] = dash.get("public_url") or public_url()
        _cache = cfg
    return _cache


def reload():
    global _cache
    _cache = None
    return get()


def source(name):
    return get()["sources"].get(name, {})


def source_enabled(name):
    return bool(source(name).get("enabled"))


def feature(name):
    return get()["features"].get(name, {})


def tz():
    try:
        return ZoneInfo(get()["timezone"])
    except Exception:
        return ZoneInfo("UTC")


def data_dir():
    override = os.environ.get("RUBICO_DATA_DIR")
    if is_cloud():
        path = _cloud_dir()
    else:
        path = Path(override) if override else ROOT / get()["storage"]["data_dir"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def token_path(filename):
    """Login tokens live in data/tokens/ - gitignored, never leaves this machine."""
    folder = data_dir() / "tokens"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / filename


def env(name, default=None):
    value = os.environ.get(name, "").strip()
    return value or default


def user_name():
    return (get()["user"].get("name") or "").strip()


def assistant_name():
    return get()["assistant"].get("name") or "Rubico"


def model():
    return get()["assistant"].get("model") or DEFAULTS["assistant"]["model"]


def dashboard_url():
    dash = get()["dashboard"]
    if dash.get("public_url"):
        return dash["public_url"]
    host = dash.get("host", "127.0.0.1")
    if host in ("0.0.0.0", "::"):
        host = "localhost"
    return f"http://{host}:{dash.get('port', 8600)}/"


def valid_time(value):
    """'08:00' -> (8, 0), or None if it isn't a real time. Also copes with
    YAML turning an unquoted 7:30 into the number 450 (minutes)."""
    if isinstance(value, int) and 0 <= value < 24 * 60:
        return divmod(value, 60)
    try:
        hh, mm = (int(x) for x in str(value).strip().split(":"))
    except ValueError:
        return None
    return (hh, mm) if 0 <= hh < 24 and 0 <= mm < 60 else None


def parse_time(value, default="08:00"):
    return valid_time(value) or valid_time(default) or (8, 0)


def dashboard_is_local():
    """True when only this computer can open the dashboard (the safe default)."""
    dash = get()["dashboard"]
    return not dash.get("public_url") and dash.get("host", "127.0.0.1") in ("127.0.0.1", "localhost", "::1")


def python_cmd():
    """How to run Python on this machine, for messages that tell you what to type."""
    return "python" if os.name == "nt" else "python3"
