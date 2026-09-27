"""
Rubico setup - run this once and it walks you through everything:

    python setup.py

It checks what's missing, explains where to get each key, tests that each
one actually works, and logs in to your accounts in your browser.
Safe to run again any time - it keeps what's already working.

    python setup.py --check          just report what's set up, change nothing
    python setup.py --only google    redo one part (anthropic, telegram, basics,
                                     sources, google, monzo, spotify)
"""

import argparse
import getpass
import os
import sys
import time
import webbrowser
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("Rubico needs Python 3.10 or newer. You have " + sys.version.split()[0])

try:
    import anthropic  # noqa: F401
    import google_auth_oauthlib  # noqa: F401
    import googleapiclient  # noqa: F401
    import requests
    import yaml
    from dotenv import set_key
except ImportError as e:
    sys.exit(
        f"A required package is missing ({e.name}).\n"
        "Install everything first:\n\n    pip install -r requirements.txt\n"
    )

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import config  # noqa: E402

ENV_FILE = ROOT / ".env"
PY = config.python_cmd()

# ---------------------------------------------------------------- helpers

BOLD, DIM, GREEN, YELLOW, RED, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    BOLD = DIM = GREEN = YELLOW = RED = RESET = ""  # old Windows consoles show codes literally


def title(text):
    print(f"\n{BOLD}{'━' * 64}\n  {text}\n{'━' * 64}{RESET}")


def ok(text):
    print(f"  {GREEN}✔{RESET} {text}")


def warn(text):
    print(f"  {YELLOW}!{RESET} {text}")


def bad(text):
    print(f"  {RED}✘{RESET} {text}")


def ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    answer = input(f"  {prompt}{suffix}: ").strip()
    return answer or default


def yes(prompt, default=True):
    hint = "Y/n" if default else "y/N"
    answer = input(f"  {prompt} ({hint}): ").strip().lower()
    return default if not answer else answer.startswith("y")


def secret(prompt):
    print(f"  {DIM}(for safety nothing shows while you paste - just paste and press Enter){RESET}")
    return getpass.getpass(f"  {prompt}: ").strip()


def open_link(url):
    print(f"    {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass


def save_env(key, value):
    if not ENV_FILE.exists():
        ENV_FILE.touch()
    set_key(str(ENV_FILE), key, value, quote_mode="never")
    os.environ[key] = value
    try:
        os.chmod(ENV_FILE, 0o600)  # only your user account can read your keys
    except OSError:
        pass


def save_config(updates):
    """Merges updates into config.yaml. Only your changes are written there;
    everything else keeps its default (see config.example.yaml)."""
    data = config._deep_merge(config.load_user_file(), updates)
    header = (
        "# Your Rubico settings. Every option is explained in config.example.yaml.\n"
        "# Edit freely, or re-run `python setup.py` to change things step by step.\n\n"
    )
    with open(config.config_path(), "w", encoding="utf-8") as f:
        f.write(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    config.reload()


def pause():
    input(f"  {DIM}Press Enter when you're ready...{RESET}")


# ---------------------------------------------------------------- steps

def intro():
    title("Welcome to Rubico 👋")
    print("""
  This will take about 10-15 minutes. You'll need:
    • an Anthropic API key (Claude writes your brief)       - required
    • a Telegram bot (how Rubico talks to you)               - required
    • your Google account, bank, Spotify...                  - all optional

  🔒 Your privacy, in plain English:
    • Rubico is fully open source and runs ONLY on your computer.
      There is no Rubico server. Nobody - including whoever wrote
      this code - can see your data, keys or logins.
    • Keys are saved in the .env file, logins in data/tokens/.
      Both stay on this machine and are never uploaded to GitHub.
    • The only places your data goes: Anthropic (so Claude can write
      your brief), Telegram (to deliver it to you), and the services
      you choose to connect.
""")


def step_anthropic():
    title("Step 1 · Anthropic API key (lets Claude write your brief)")
    if config.env("ANTHROPIC_API_KEY") and check_anthropic(quiet=True):
        ok("Anthropic key already set and working.")
        if not yes("Replace it?", default=False):
            return
    print("""
  1. Open the Anthropic Console (sign up if you haven't):""")
    open_link("https://console.anthropic.com/settings/keys")
    print("""  2. Add a little credit under Billing (a daily brief usually costs a few
     cents a day; chat messages cost about the same each).
  3. Click "Create Key", name it Rubico, and copy it (starts with sk-ant-).
""")
    while True:
        key = secret("Paste your Anthropic API key")
        if not key:
            warn("Skipped. Rubico can't write briefs without it - run setup again later.")
            return
        save_env("ANTHROPIC_API_KEY", key)
        if check_anthropic():
            return
        if not yes("Try a different key?"):
            return


def check_anthropic(quiet=False):
    try:
        anthropic.Anthropic(api_key=config.env("ANTHROPIC_API_KEY")).models.retrieve(config.model())
        if not quiet:
            ok(f"Key works (model {config.model()} is available).")
        return True
    except anthropic.AuthenticationError:
        if not quiet:
            bad("Anthropic says that key isn't valid. Check you copied all of it.")
    except anthropic.NotFoundError:
        if not quiet:
            bad(f"Key works, but model '{config.model()}' isn't available to it. "
                "Change assistant.model in config.yaml.")
        return True
    except Exception as e:
        if not quiet:
            bad(f"Couldn't reach Anthropic: {e}")
    return False


def tg(method, token, **params):
    resp = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=params, timeout=40)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "unknown Telegram error"))
    return data["result"]


def step_telegram():
    title("Step 2 · Telegram bot (how Rubico messages you)")
    token = config.env("TELEGRAM_BOT_TOKEN")
    bot = None
    if token:
        try:
            bot = tg("getMe", token)
            ok(f"Bot already set up: @{bot['username']}")
        except Exception:
            warn("The saved bot token doesn't work any more - let's replace it.")
            token = None

    if not token:
        print("""
  1. Open Telegram and search for @BotFather (it has a blue tick).
  2. Send it:  /newbot
  3. Pick a display name (e.g. Rubico) and a username ending in "bot"
     (e.g. alex_rubico_bot).
  4. BotFather replies with a token that looks like 123456789:AAH...
""")
        while True:
            token = secret("Paste your bot token")
            if not token:
                warn("Skipped - Rubico can't message you without a bot.")
                return
            try:
                bot = tg("getMe", token)
                save_env("TELEGRAM_BOT_TOKEN", token)
                ok(f"Connected to your bot @{bot['username']}")
                break
            except Exception as e:
                bad(f"Telegram didn't accept that token ({e}).")

    if config.env("TELEGRAM_CHAT_ID") and not yes("Re-link which Telegram chat the bot talks to?", default=False):
        send_test_message(token)
        return

    print(f"""
  Now link the bot to YOU (it will only ever talk to this one chat):
  Open this link on your phone or computer and press START (or send "hi"):""")
    open_link(f"https://t.me/{bot['username']}")
    try:
        tg("deleteWebhook", token)
    except Exception:
        pass
    print("  Waiting for your message (up to 3 minutes)...")
    deadline = time.time() + 180
    offset = None
    chat = None
    while time.time() < deadline and not chat:
        params = {"timeout": 20}
        if offset:
            params["offset"] = offset
        for update in tg("getUpdates", token, **params):
            offset = update["update_id"] + 1
            msg = update.get("message") or {}
            if msg.get("chat", {}).get("type") == "private":
                chat = msg["chat"]
    if not chat:
        bad("Didn't see a message. Run `python setup.py --only telegram` to try again.")
        return
    save_env("TELEGRAM_CHAT_ID", str(chat["id"]))
    ok(f"Linked to {chat.get('first_name', 'you')} (chat {chat['id']}). Messages from anyone else are ignored.")
    send_test_message(token)


def send_test_message(token):
    try:
        tg("sendMessage", token, chat_id=config.env("TELEGRAM_CHAT_ID"),
           text="✅ Rubico is connected! This is where your morning brief will arrive.")
        ok("Sent you a test message on Telegram.")
        if not yes("Did it arrive?"):
            warn("Check you pressed Start on the right bot, then run: python setup.py --only telegram")
    except Exception as e:
        bad(f"Couldn't send a test message: {e}")


def step_basics():
    title("Step 3 · About you")
    cfg = config.get()
    name = ask("What should Rubico call you? (first name, or leave blank)", cfg["user"]["name"])
    city = ask("Which city are you in? (for weather + timezone)", cfg["location"]["name"])
    location, timezone = cfg["location"], cfg["timezone"]
    if city != cfg["location"]["name"] or not config.load_user_file().get("location"):
        try:
            found = requests.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1}, timeout=15,
            ).json().get("results") or []
        except Exception:
            found = []
        if found:
            place = found[0]
            label = ", ".join(x for x in (place["name"], place.get("admin1"), place.get("country")) if x)
            ok(f"Found {label} (timezone {place.get('timezone')})")
            location = {"name": place["name"], "latitude": place["latitude"], "longitude": place["longitude"]}
            timezone = place.get("timezone") or timezone
        else:
            warn(f"Couldn't look up \"{city}\" automatically.")
            print("  Find your coordinates at https://www.latlong.net (e.g. 53.48, -2.24)")
            coords = ask("Latitude, longitude (blank = keep previous)")
            try:
                lat, lon = (float(x) for x in coords.replace(" ", "").split(","))
                location = {"name": city, "latitude": lat, "longitude": lon}
            except ValueError:
                warn(f"Keeping {cfg['location']['name']} for weather.")
    timezone = ask("Timezone (e.g. Europe/London, America/New_York)", timezone)
    while True:
        parsed = config.valid_time(ask("What time should the morning brief arrive? (24h, HH:MM)",
                                       str(cfg["briefing"]["time"])))
        if parsed:
            brief_time = f"{parsed[0]:02d}:{parsed[1]:02d}"
            break
        warn("Please use HH:MM, e.g. 07:30")
    currency = ask("Your currency code (GBP, USD, EUR...)", cfg["currency"]).upper()
    save_config({
        "user": {"name": name}, "location": location, "timezone": timezone,
        "briefing": {"time": brief_time}, "currency": currency,
    })
    ok("Saved to config.yaml")


def step_sources():
    import sources

    title("Step 4 · Choose your data sources")
    print("  Switch on only what you want. You can change this any time in config.yaml.\n")
    updates = {}
    for src in sources.all_sources():
        print(f"  {BOLD}{src.title}{RESET} - {src.description}")
        updates[src.name] = {"enabled": yes(f"Use {src.title}?", default=src.enabled)}
        print()
    features = {}
    features["study_reminders"] = {"enabled": yes(
        "Also turn on study reminders? (text \"studied <topic>\" -> review pings at 1, 3, 7, 14, 30 days)",
        default=config.feature("study_reminders").get("enabled", False))}
    save_config({"sources": updates, "features": features})
    ok("Saved. Next we'll connect the ones you picked.")


GOOGLE_SAFETY = """
  🔒 How connecting Google stays safe - please read:
    • You'll make your OWN free Google Cloud "OAuth client". It's like a key
      you cut yourself: your login goes straight from Google to this computer.
      No company in the middle - not Rubico, not the author, nobody.
    • Your login is saved in data/tokens/ on this computer only.
    • Rubico asks Google for exactly what it needs:
        Gmail    - read emails (for the brief), send replies you approve,
                   move emails you approve to Trash (recoverable for 30 days)
        Calendar - read today's events, add study review events
    • Nothing is sent or deleted without you seeing it first: every email
      action waits {window} minutes on Telegram so you can reply CANCEL.
    • Email subjects and previews are sent to Anthropic's API so Claude can
      summarise them. (Anthropic doesn't train on API data by default.)
    • Change your mind? Remove access any time at
      https://myaccount.google.com/permissions  or delete data/tokens/.
"""


def step_google():
    import google_auth
    import pending_actions

    wants = [n for n in ("gmail", "calendar") if config.source_enabled(n)]
    if not wants:
        return
    title("Step 5 · Connect Google (" + " + ".join(w.title() for w in wants) + ")")
    print(GOOGLE_SAFETY.format(window=pending_actions.window_minutes()))

    if google_auth.client_config():
        ok("Your Google OAuth client is already set up.")
    else:
        print(f"""  {BOLD}Part A - create your Google OAuth client (about 5 minutes, one time){RESET}

  1. Create a project: name it "Rubico", then click Create.""")
        open_link("https://console.cloud.google.com/projectcreate")
        pause()
        print("\n  2. Turn on the APIs you'll use - on each page click ENABLE:")
        if "gmail" in wants:
            open_link("https://console.cloud.google.com/apis/library/gmail.googleapis.com")
        if "calendar" in wants:
            open_link("https://console.cloud.google.com/apis/library/calendar-json.googleapis.com")
        pause()
        print("""
  3. Set up the consent screen ("Get started" if asked):
       App name: Rubico · Support email: your email · Audience: External
       Contact email: your email · tick the agreement · Create""")
        open_link("https://console.cloud.google.com/auth/branding")
        pause()
        print("""
  4. Audience page -> under "Test users" click "Add users" and add every
     Gmail address you'll connect. (Optional but recommended: click
     "Publish app" here instead. In "Testing" mode Google logs you out
     every 7 days; published, it keeps working. It stays private - it's
     your own client, and nobody can use it without your password.)""")
        open_link("https://console.cloud.google.com/auth/audience")
        pause()
        print("""
  5. Clients page -> "Create client" -> Application type: Desktop app
     -> Name: Rubico -> Create. Copy the Client ID and Client secret.""")
        open_link("https://console.cloud.google.com/auth/clients")
        client_id = ask("Paste the Client ID (ends in .apps.googleusercontent.com)")
        client_secret = secret("Paste the Client secret")
        if not (client_id and client_secret):
            warn("Skipped. Run `python setup.py --only google` when you're ready.")
            return
        save_env("GOOGLE_CLIENT_ID", client_id)
        save_env("GOOGLE_CLIENT_SECRET", client_secret)
        ok("Saved to .env")

    print(f"""
  {BOLD}Part B - log in to your Google account(s){RESET}
  Give each account a short nickname (e.g. personal, work). You'll see
  the nickname in your brief. Your browser will open for each one.""")
    if not (os.name == "nt" or sys.platform == "darwin" or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        warn("This looks like a computer without a screen (e.g. a server over SSH).")
        warn("Google login needs a browser on the SAME machine. Easiest: run setup on your")
        warn("laptop, then copy the data/tokens/ folder to the server.")

    gmail = list(config.source("gmail").get("accounts") or [])
    calendar = list(config.source("calendar").get("accounts") or [])
    existing = google_auth.all_labels()
    if existing:
        ok("Already added: " + ", ".join(existing))
    while True:
        if existing and not yes("Add another Google account?", default=False):
            break
        label = ask("Nickname for this Google account", "personal" if not existing else "").lower()
        label = "".join(c for c in label if c.isalnum() or c in "-_")
        if not label:
            break
        if "gmail" in wants and yes(f"Use '{label}' for Gmail?") and label not in gmail:
            gmail.append(label)
        if "calendar" in wants and yes(f"Use '{label}' for Calendar?") and label not in calendar:
            calendar.append(label)
        save_config({"sources": {"gmail": {"accounts": gmail}, "calendar": {"accounts": calendar}}})
        existing = google_auth.all_labels()

    for label in google_auth.all_labels():
        try:
            google_auth.get_credentials(label, allow_browser=True)
            ok(f"'{label}' connected as {google_auth.account_email(label)}")
        except Exception as e:
            bad(f"'{label}' didn't connect: {e}")
            if "access_denied" in str(e) or "403" in str(e):
                warn("Usually means that address isn't a Test user yet (step 4 above).")


def step_monzo():
    if not config.source_enabled("monzo"):
        return
    title("Connect Monzo (UK bank)")
    if not (config.env("MONZO_CLIENT_ID") and config.env("MONZO_CLIENT_SECRET")):
        print("""
  1. Sign in to the Monzo developer portal with your Monzo email
     (you'll approve it in the Monzo app):""")
        open_link("https://developers.monzo.com/")
        print("""  2. Clients -> New OAuth Client:
       Name: Rubico · Redirect URL: http://localhost:8085/monzo/callback
       Confidentiality: Confidential -> Submit
  3. Open the client and copy its Client ID and Client secret.
""")
        cid = ask("Paste the Monzo Client ID")
        csec = secret("Paste the Monzo Client secret")
        if not (cid and csec):
            warn("Skipped Monzo.")
            return
        save_env("MONZO_CLIENT_ID", cid)
        save_env("MONZO_CLIENT_SECRET", csec)
    import sources.monzo_auth as monzo_auth
    try:
        if monzo_auth.main() == 0:
            print("  Once you've tapped Approve in the Monzo app:")
            pause()
    except SystemExit:
        bad("Monzo login didn't finish - run `python setup.py --only monzo` to retry.")


def step_spotify():
    if not config.source_enabled("spotify"):
        return
    title("Connect Spotify")
    if not config.env("SPOTIFY_CLIENT_ID"):
        print("""
  1. Open the Spotify developer dashboard and click "Create app":""")
        open_link("https://developer.spotify.com/dashboard")
        print("""  2. Name: Rubico · Description: anything
     Redirect URI: http://127.0.0.1:8888/callback  (click Add)
     Tick "Web API" -> Save
  3. Open Settings and copy the Client ID. (No secret needed - Rubico uses
     the PKCE login method, so there's no secret to leak.)
""")
        cid = ask("Paste the Spotify Client ID")
        if not cid:
            warn("Skipped Spotify.")
            return
        save_env("SPOTIFY_CLIENT_ID", cid)
    import sources.spotify_auth as spotify_auth
    try:
        spotify_auth.main()
    except SystemExit:
        bad("Spotify login didn't finish - run `python setup.py --only spotify` to retry.")


# ---------------------------------------------------------------- check

def check(verbose=True):
    import sources

    all_good = True
    title("Status check")
    if config.env("ANTHROPIC_API_KEY") and check_anthropic(quiet=True):
        ok("Anthropic API key works")
    else:
        bad("Anthropic API key missing or not working")
        all_good = False

    token = config.env("TELEGRAM_BOT_TOKEN")
    try:
        bot = tg("getMe", token) if token else None
        if bot and config.env("TELEGRAM_CHAT_ID"):
            ok(f"Telegram bot @{bot['username']} linked to your chat")
        else:
            bad("Telegram " + ("chat not linked yet" if bot else "bot token missing"))
            all_good = False
    except Exception as e:
        bad(f"Telegram bot token not working ({e})")
        all_good = False

    for src in sources.all_sources():
        if not src.enabled:
            print(f"  {DIM}-  {src.title}: off{RESET}")
            continue
        problems = src.problems()
        if problems:
            warn(f"{src.title}: " + "; ".join(problems))
            all_good = False
        else:
            ok(f"{src.title}: ready")

    cfg = config.get()
    print(f"\n  Morning brief: {cfg['briefing']['time']} ({cfg['timezone']}) · "
          f"Weather for {cfg['location']['name']} · Dashboard: {config.dashboard_url()}")
    return all_good


# ---------------------------------------------------------------- main

STEPS = {
    "anthropic": step_anthropic, "telegram": step_telegram, "basics": step_basics,
    "sources": step_sources, "google": step_google, "monzo": step_monzo, "spotify": step_spotify,
}


def main():
    parser = argparse.ArgumentParser(description="Set up Rubico.")
    parser.add_argument("--check", action="store_true", help="only report status")
    parser.add_argument("--only", choices=list(STEPS), help="run just one step")
    args = parser.parse_args()

    if args.check:
        return 0 if check() else 1

    try:
        if args.only:
            STEPS[args.only]()
        else:
            intro()
            for step in STEPS.values():
                step()
    except KeyboardInterrupt:
        print("\n\n  Setup paused. Everything so far is saved - run `python setup.py` to continue.")
        return 1

    good = check()
    title("All done 🎉" if good else "Nearly there")
    if good:
        print(f"""
  Start Rubico (leave it running):     {PY} run.py
  Send a brief right now to test:      {PY} tools/orchestrator.py
  Dashboard (while run.py is running): {config.dashboard_url()}

  Text your bot /help to see what it can do.
""")
    else:
        print(f"\n  Fix the items above (re-run `{PY} setup.py`), then start with `{PY} run.py`.\n")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
