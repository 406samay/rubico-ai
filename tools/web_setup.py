"""
Setup in the browser: https://<your-rubico-address>/setup

The only setup Rubico has - a web page, so it can be done from a phone after
deploying to Railway (docs/deploy-railway.md).
Served by dashboard_server.py behind the dashboard password.

Each card is one step. Forms POST to /setup/<action>; logins with Google,
Monzo and Spotify bounce through their sites and come back to
/setup/<service>/callback.

Safety:
  - keys you paste are saved to secrets.env on your own storage volume and
    never shown on the page again
  - every form carries a secret token (CSRF) and must come from this page,
    so another website can't submit it on your behalf
"""

import html
import secrets
import time
from urllib.parse import parse_qs, urlencode

import config
import db
import google_auth
import places
import sources
import telegram_bot

esc = html.escape
PENDING_TTL = 15 * 60  # seconds a login may take before it's thrown away


# ---------------------------------------------------------------- helpers

def csrf_token():
    token = db.kv_get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(24)
        db.kv_set("csrf_token", token)
    return token


def _flash(ok=None, err=None, anchor=""):
    params = {}
    if ok:
        params["ok"] = ok
    if err:
        params["err"] = err
    return "/setup" + ("?" + urlencode(params) if params else "") + (f"#{anchor}" if anchor else "")


def _remember_login(kind, state, **data):
    pending = {k: v for k, v in (db.kv_get("oauth_pending") or {}).items()
               if time.time() - v.get("at", 0) < PENDING_TTL}
    pending[state] = {"kind": kind, "at": time.time(), **data}
    db.kv_set("oauth_pending", pending)


def _take_login(kind, state):
    pending = db.kv_get("oauth_pending") or {}
    item = pending.pop(state or "", None)
    db.kv_set("oauth_pending", pending)
    if not item or item["kind"] != kind or time.time() - item["at"] > PENDING_TTL:
        return None
    return item


def essentials_done():
    return all(config.env(k) for k in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"))


def _bot_username():
    name = db.kv_get("bot_username")
    if not name and config.env("TELEGRAM_BOT_TOKEN"):
        try:
            name = telegram_bot.bot_username()
            db.kv_set("bot_username", name)
        except Exception:
            name = None
    return name


# ---------------------------------------------------------------- actions

def act_anthropic(form, base):
    key = form.get("key", "").strip()
    if not key:
        return _flash(err="Paste your Anthropic API key first.", anchor="claude")
    try:
        import anthropic
        anthropic.Anthropic(api_key=key).models.retrieve(config.model())
    except anthropic.AuthenticationError:
        return _flash(err="Anthropic says that key isn't valid - check you copied all of it.", anchor="claude")
    except anthropic.NotFoundError:
        pass  # key works; the model name is a config choice
    except Exception as e:
        return _flash(err=f"Couldn't reach Anthropic: {e}", anchor="claude")
    config.save_secret("ANTHROPIC_API_KEY", key)
    return _flash(ok="Claude key saved and working ✅", anchor="telegram")


def act_telegram_token(form, base):
    token = form.get("token", "").strip()
    try:
        name = telegram_bot.bot_username(token)
    except Exception:
        return _flash(err="Telegram didn't accept that token - copy the whole thing from BotFather.",
                      anchor="telegram")
    config.save_secret("TELEGRAM_BOT_TOKEN", token)
    db.kv_set("bot_username", name)
    return _flash(ok=f"Connected to @{name}. Now send it a message and tap the link button.", anchor="telegram")


def act_telegram_link(form, base):
    """Looks for the message you just sent the bot, and links that chat."""
    token = config.env("TELEGRAM_BOT_TOKEN")
    chat = None
    try:
        telegram_bot.call("deleteWebhook", token=token, http_timeout=15)
        for _ in range(2):
            for update in telegram_bot.call("getUpdates", token=token, http_timeout=15, timeout=4):
                msg = update.get("message") or {}
                if msg.get("chat", {}).get("type") == "private":
                    chat = msg["chat"]
            if chat:
                break
    except Exception as e:
        return _flash(err=f"Couldn't check Telegram ({e}). If Rubico is already linked and running, "
                          "that's expected - it's busy listening.", anchor="telegram")
    if not chat:
        return _flash(err=f"No message yet. Open @{_bot_username()} in Telegram, press Start or send "
                          "\"hi\", then tap the button again.", anchor="telegram")
    config.save_secret("TELEGRAM_CHAT_ID", str(chat["id"]))
    try:
        telegram_bot.set_commands(token)
        telegram_bot.send_message(
            "✅ Rubico is connected! This is where your morning brief will arrive, and where you "
            "can text me any time. Send /help to see what I can do."
        )
    except Exception:
        pass
    return _flash(ok=f"Linked to {chat.get('first_name', 'you')} - check Telegram for a hello 👋", anchor="about")


def act_about(form, base):
    name = form.get("name", "").strip()[:60]
    city = form.get("city", "").strip()[:80]
    parsed = config.valid_time(form.get("time", "").strip())
    if not parsed:
        return _flash(err="Brief time should look like 07:30.", anchor="about")
    updates = {"user": {"name": name}, "briefing": {"time": f"{parsed[0]:02d}:{parsed[1]:02d}"}}
    if city:
        place = places.lookup(city)
        coords = form.get("coords", "").replace(" ", "")
        if place:
            updates["location"] = {k: place[k] for k in ("name", "latitude", "longitude")}
            if place["timezone"]:
                updates["timezone"] = place["timezone"]
            if place["currency"]:
                updates["currency"] = place["currency"]
        elif coords:
            try:
                lat, lon = (float(x) for x in coords.split(","))
            except ValueError:
                return _flash(err="Coordinates should look like 51.50, -0.12", anchor="about")
            updates["location"] = {"name": city, "latitude": lat, "longitude": lon}
        else:
            return _flash(err=f"Couldn't find \"{city}\". Try a bigger nearby city, or add coordinates.",
                          anchor="about")
    if form.get("timezone"):
        updates["timezone"] = form["timezone"].strip()
    config.save_user_config(updates)
    cfg = config.get()
    return _flash(ok=f"Saved: {cfg['location']['name']} · {cfg['timezone']} · {cfg['currency']} · "
                     f"brief at {cfg['briefing']['time']}", anchor="sources")


def act_sources(form, base):
    updates = {s.name: {"enabled": form.get(s.name) == "on"} for s in sources.all_sources()}
    config.save_user_config({
        "sources": updates,
        "features": {"study_reminders": {"enabled": form.get("study") == "on"}},
    })
    return _flash(ok="Data sources saved.", anchor="sources")


def act_personality(form, base):
    voice = form.get("voice", "").strip()[:1500]
    style = form.get("email_style", "").strip()[:1000]
    try:
        words = max(50, min(600, int(form.get("max_words") or 200)))
    except ValueError:
        return _flash(err="Brief length should be a number, e.g. 200.", anchor="personality")
    updates = {"briefing": {"max_words": words}, "assistant": {}}
    if voice:
        updates["assistant"]["voice"] = voice
    if style:
        updates["assistant"]["email_reply_style"] = style
    config.save_user_config(updates)
    return _flash(ok="Personality saved - your next message will sound like this.", anchor="personality")


def act_google_client(form, base):
    client_id, client_secret = form.get("client_id", "").strip(), form.get("client_secret", "").strip()
    if not client_id.endswith(".apps.googleusercontent.com") or not client_secret:
        return _flash(err="Paste both the Client ID (ends in .apps.googleusercontent.com) and the secret.",
                      anchor="google")
    config.save_secret("GOOGLE_CLIENT_ID", client_id)
    config.save_secret("GOOGLE_CLIENT_SECRET", client_secret)
    return _flash(ok="Google client saved. Now sign in below.", anchor="google")


def act_google_start(form, base):
    label = "".join(c for c in form.get("label", "").lower() if c.isalnum() or c in "-_")[:20] or "personal"
    want_gmail, want_cal = form.get("gmail") == "on", form.get("calendar") == "on"
    if not (want_gmail or want_cal):
        return _flash(err="Tick Gmail, Calendar or both.", anchor="google")
    cfg = config.get()["sources"]
    gmail, cal = list(cfg["gmail"].get("accounts") or []), list(cfg["calendar"].get("accounts") or [])
    if want_gmail and label not in gmail:
        gmail.append(label)
    if want_cal and label not in cal:
        cal.append(label)
    config.save_user_config({"sources": {
        "gmail": {"accounts": gmail, **({"enabled": True} if want_gmail else {})},
        "calendar": {"accounts": cal, **({"enabled": True} if want_cal else {})},
    }})
    redirect = f"{base}/setup/google/callback"
    try:
        url, state, verifier = google_auth.web_login_url(label, redirect)
    except Exception as e:
        return _flash(err=str(e), anchor="google")
    _remember_login("google", state, label=label, verifier=verifier)
    return url


def act_google_remove(form, base):
    label = form.get("label", "")
    cfg = config.get()["sources"]
    config.save_user_config({"sources": {
        "gmail": {"accounts": [a for a in cfg["gmail"].get("accounts") or [] if a != label]},
        "calendar": {"accounts": [a for a in cfg["calendar"].get("accounts") or [] if a != label]},
    }})
    try:
        google_auth.token_file(label).unlink()
    except OSError:
        pass
    emails = db.kv_get("google_emails") or {}
    emails.pop(label, None)
    db.kv_set("google_emails", emails)
    return _flash(ok=f"Removed '{label}'. (To fully revoke, visit myaccount.google.com/permissions.)",
                  anchor="google")


def act_monzo_client(form, base):
    cid, csec = form.get("client_id", "").strip(), form.get("client_secret", "").strip()
    if not (cid and csec):
        return _flash(err="Paste both the Monzo Client ID and secret.", anchor="monzo")
    config.save_secret("MONZO_CLIENT_ID", cid)
    config.save_secret("MONZO_CLIENT_SECRET", csec)
    return _flash(ok="Monzo client saved. Now tap Connect Monzo.", anchor="monzo")


def act_monzo_start(form, base):
    from sources import monzo_auth
    state = secrets.token_urlsafe(16)
    _remember_login("monzo", state)
    return monzo_auth.login_url(f"{base}/setup/monzo/callback", state)


def act_spotify_client(form, base):
    cid = form.get("client_id", "").strip()
    if not cid:
        return _flash(err="Paste the Spotify Client ID.", anchor="spotify")
    config.save_secret("SPOTIFY_CLIENT_ID", cid)
    return _flash(ok="Spotify client saved. Now tap Connect Spotify.", anchor="spotify")


def act_spotify_start(form, base):
    from sources import spotify_auth
    verifier, challenge = spotify_auth._pkce_pair()
    state = secrets.token_urlsafe(16)
    _remember_login("spotify", state, verifier=verifier)
    return spotify_auth.login_url(f"{base}/setup/spotify/callback", state, challenge)


ACTIONS = {
    "anthropic": act_anthropic, "telegram-token": act_telegram_token, "telegram-link": act_telegram_link,
    "about": act_about, "sources": act_sources, "personality": act_personality,
    "google-client": act_google_client, "google-start": act_google_start, "google-remove": act_google_remove,
    "monzo-client": act_monzo_client, "monzo-start": act_monzo_start,
    "spotify-client": act_spotify_client, "spotify-start": act_spotify_start,
}


def handle_post(action, body, base):
    """Returns the URL to redirect the browser to."""
    form = {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace")).items()}
    if not secrets.compare_digest(form.get("csrf", ""), csrf_token()):
        return _flash(err="That form was out of date - please try again.")
    fn = ACTIONS.get(action)
    if not fn:
        return _flash(err="Unknown setup step.")
    try:
        return fn(form, base)
    except Exception as e:
        return _flash(err=f"Something went wrong: {type(e).__name__}: {e}")


def handle_callback(kind, query, base, full_path):
    """Google / Monzo / Spotify send the browser back here after you log in."""
    params = {k: v[0] for k, v in parse_qs(query).items()}
    anchor = kind
    if params.get("error"):
        return _flash(err=f"{kind.title()} login was cancelled ({params['error']}).", anchor=anchor)
    pending = _take_login(kind, params.get("state"))
    if not pending:
        return _flash(err="That login link expired or was already used - please start again.", anchor=anchor)
    try:
        if kind == "google":
            email = google_auth.web_login_finish(
                pending["label"], f"{base}/setup/google/callback", params.get("state"),
                pending["verifier"], base + full_path,
            )
            emails = db.kv_get("google_emails") or {}
            emails[pending["label"]] = email or "connected"
            db.kv_set("google_emails", emails)
            return _flash(ok=f"'{pending['label']}' connected{' as ' + email if email else ''} ✅", anchor=anchor)
        if kind == "monzo":
            from sources import monzo_auth
            monzo_auth.exchange_code(params["code"], f"{base}/setup/monzo/callback")
            return _flash(ok="Monzo connected. Now open the Monzo app and tap Approve - nothing works "
                             "until you do.", anchor=anchor)
        if kind == "spotify":
            from sources import spotify_auth
            spotify_auth.exchange_code(params["code"], f"{base}/setup/spotify/callback", pending["verifier"])
            return _flash(ok="Spotify connected 🎧", anchor=anchor)
    except Exception as e:
        return _flash(err=f"{kind.title()} login failed: {type(e).__name__}: {e}", anchor=anchor)
    return _flash(err="Unknown login.")


# ---------------------------------------------------------------- page

CSS = """
:root { --bg:#F2F2F7; --card:#FFFFFF; --text:#1C1C1E; --muted:#6C6C70; --line:rgba(60,60,67,.14);
  --accent:#0A84FF; --good:#248A3D; --good-bg:rgba(52,199,89,.14); --warn:#B25000; --warn-bg:rgba(255,149,0,.16);
  --bad:#D70015; --bad-bg:rgba(255,59,48,.12); --field:#F2F2F7; color-scheme: light; }
@media (prefers-color-scheme: dark) { :root { --bg:#000; --card:#1C1C1E; --text:#F2F2F7; --muted:#98989F;
  --line:rgba(84,84,88,.5); --accent:#409CFF; --good:#30D158; --good-bg:rgba(48,209,88,.16); --warn:#FFB340;
  --warn-bg:rgba(255,159,10,.18); --bad:#FF6961; --bad-bg:rgba(255,69,58,.18); --field:#2C2C2E; color-scheme: dark; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text);
  font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
.wrap { max-width:640px; margin:0 auto; padding:24px 16px 60px; }
h1 { font-size:1.75rem; margin:0 0 4px; letter-spacing:-.02em; }
.lead { color:var(--muted); margin:0 0 18px; }
.card { background:var(--card); border-radius:16px; padding:18px; margin:14px 0; border:1px solid var(--line); }
.card h2 { font-size:1.1rem; margin:0; display:flex; align-items:center; gap:10px; }
.num { width:26px; height:26px; border-radius:50%; background:var(--accent); color:#fff; font-size:.85rem;
  display:inline-grid; place-items:center; flex:none; }
.badge { margin-left:auto; font-size:.78rem; font-weight:600; padding:3px 9px; border-radius:99px; white-space:nowrap; }
.b-ok { background:var(--good-bg); color:var(--good); } .b-todo { background:var(--warn-bg); color:var(--warn); }
.b-off { background:var(--field); color:var(--muted); }
p, ol { margin:10px 0; } ol { padding-left:20px; } li { margin:4px 0; }
.muted { color:var(--muted); font-size:.92rem; }
label { display:block; font-size:.9rem; font-weight:600; margin:12px 0 4px; }
input[type=text], input[type=password], input[type=time], input[type=number], textarea { width:100%; font:inherit; padding:11px 12px;
  border-radius:10px; border:1px solid var(--line); background:var(--field); color:var(--text); }
textarea { min-height:96px; resize:vertical; line-height:1.4; }
.check { display:flex; gap:10px; align-items:flex-start; font-weight:400; margin:10px 0; }
.check input { width:20px; height:20px; margin-top:2px; flex:none; }
button, .btn { display:inline-block; margin-top:14px; font:inherit; font-weight:600; border:0; border-radius:12px;
  padding:11px 18px; background:var(--accent); color:#fff; cursor:pointer; text-decoration:none; }
.btn-quiet { background:var(--field); color:var(--text); }
.row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
code, .copy { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:.85rem;
  background:var(--field); padding:2px 6px; border-radius:6px; word-break:break-all; }
.copy { display:block; padding:10px; margin:6px 0; user-select:all; }
.flash { border-radius:12px; padding:12px 14px; margin:12px 0; font-weight:500; }
.f-ok { background:var(--good-bg); color:var(--good); } .f-err { background:var(--bad-bg); color:var(--bad); }
.acct { display:flex; justify-content:space-between; align-items:center; gap:8px; padding:8px 0;
  border-top:1px solid var(--line); }
.acct form { margin:0; } .acct button { margin:0; padding:6px 12px; font-size:.85rem; }
a { color:var(--accent); }
"""


def _badge(state):
    return {"ok": '<span class="badge b-ok">✓ Done</span>',
            "todo": '<span class="badge b-todo">To do</span>',
            "off": '<span class="badge b-off">Off</span>'}[state]


def _form(action, inner, button, quiet=False):
    return (f'<form method="post" action="/setup/{action}">'
            f'<input type="hidden" name="csrf" value="{esc(csrf_token())}">{inner}'
            f'<button type="submit"{" class=btn-quiet" if quiet else ""}>{esc(button)}</button></form>')


def _card(anchor, number, title, state, body):
    return (f'<section class="card" id="{anchor}"><h2><span class="num">{number}</span>{esc(title)}'
            f'{_badge(state)}</h2>{body}</section>')


def _secret_input(name, label, placeholder=""):
    return (f'<label for="{name}">{esc(label)}</label>'
            f'<input type="password" id="{name}" name="{name}" placeholder="{esc(placeholder)}" '
            f'autocomplete="off" autocapitalize="off" spellcheck="false">')


def _text_input(name, label, value="", placeholder=""):
    return (f'<label for="{name}">{esc(label)}</label>'
            f'<input type="text" id="{name}" name="{name}" value="{esc(value)}" placeholder="{esc(placeholder)}">')


def render(base, query=""):
    params = {k: v[0] for k, v in parse_qs(query).items()}
    cfg = config.get()
    user_file = config.load_user_file()
    bot = _bot_username() if config.env("TELEGRAM_BOT_TOKEN") else None
    parts = []

    # ---- header
    parts.append(f'<h1>☀️ {esc(config.assistant_name())} setup</h1>')
    parts.append('<p class="lead">Your own AI morning brief on Telegram. Everything you enter here is '
                 'saved only on <b>your</b> Rubico - nobody else, including whoever wrote the code, can see it.</p>')
    if params.get("ok"):
        parts.append(f'<div class="flash f-ok">{esc(params["ok"])}</div>')
    if params.get("err"):
        parts.append(f'<div class="flash f-err">{esc(params["err"])}</div>')
    if config.is_cloud() and not config.has_persistent_storage():
        parts.append('<div class="flash f-err">⚠️ No storage volume is attached, so your settings and logins '
                     'will be wiped every time Rubico updates. In Railway: open your service → '
                     '<b>Add Volume</b> → mount path <code>/data</code>.</div>')
    if essentials_done():
        chat = f' · <a href="https://t.me/{esc(bot)}">💬 Open chat</a>' if bot else ""
        parts.append(f'<div class="flash f-ok">✅ Rubico is running. Your brief arrives at '
                     f'{esc(str(cfg["briefing"]["time"]))} ({esc(cfg["timezone"])}).'
                     f' <a href="/">📊 Dashboard</a>{chat}</div>')

    # ---- 1. Claude
    claude_ok = bool(config.env("ANTHROPIC_API_KEY"))
    parts.append(_card("claude", 1, "Claude API key", "ok" if claude_ok else "todo",
        ('<p class="muted">Claude writes your brief and answers your messages. Usually a few cents a day.</p>'
         + ('' if not claude_ok else '<p>Saved ✓ - paste a new one below only if you want to replace it.</p>')
         + '<ol><li>Open <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener">'
           'console.anthropic.com → API keys</a> (sign up if needed, add a little credit under Billing).</li>'
           '<li>Create a key called Rubico and copy it.</li></ol>'
         + _form("anthropic", _secret_input("key", "Anthropic API key", "sk-ant-…"), "Save key"))))

    # ---- 2. Telegram
    token_ok, linked = bool(config.env("TELEGRAM_BOT_TOKEN")), bool(config.env("TELEGRAM_CHAT_ID"))
    tg = ['<p class="muted">Where your brief arrives and where you text Rubico.</p>']
    if not token_ok:
        tg.append('<ol><li>In the Telegram app, search <b>@BotFather</b> (blue tick) and send <code>/newbot</code>.</li>'
                  '<li>Pick a name, then a username ending in "bot".</li>'
                  '<li>Copy the token it sends you (looks like <code>123456789:AAH…</code>).</li></ol>')
        tg.append(_form("telegram-token", _secret_input("token", "Bot token"), "Save bot"))
    else:
        tg.append(f'<p>Bot: <b>@{esc(bot or "?")}</b> ✓</p>')
        if linked:
            tg.append('<p>Linked to your chat ✓ - the bot only ever talks to you.</p>')
        else:
            tg.append(f'<ol><li>Open <a href="https://t.me/{esc(bot or "")}" target="_blank" rel="noopener">'
                      f'@{esc(bot or "")}</a> in the Telegram app and press <b>Start</b> (or send "hi").</li>'
                      '<li>Then tap the button below.</li></ol>')
            tg.append(_form("telegram-link", "", "I've sent it - link my chat"))
    parts.append(_card("telegram", 2, "Telegram bot", "ok" if token_ok and linked else "todo", "".join(tg)))

    # ---- 3. About you
    about_ok = bool(user_file.get("location"))
    parts.append(_card("about", 3, "About you", "ok" if about_ok else "todo",
        ('<p class="muted">Your city sets the weather, timezone and currency.</p>'
         + _form("about",
                 _text_input("name", "What should Rubico call you?", cfg["user"].get("name", ""), "First name (optional)")
                 + _text_input("city", "City", cfg["location"]["name"] if about_ok else "", "e.g. Manchester")
                 + _text_input("coords", "Coordinates (only if the city isn't found)", "", "e.g. 53.48, -2.24")
                 + f'<label for="time">Morning brief time</label><input type="time" id="time" name="time" '
                   f'value="{esc(str(cfg["briefing"]["time"]))}">'
                 + (f'<p class="muted">Now: {esc(cfg["location"]["name"])} · {esc(cfg["timezone"])} · '
                    f'{esc(cfg["currency"])}</p>' if about_ok else ""),
                 "Save"))))

    # ---- 4. Sources
    boxes = []
    for s in sources.all_sources():
        boxes.append(f'<label class="check"><input type="checkbox" name="{s.name}"{" checked" if s.enabled else ""}>'
                     f'<span><b>{esc(s.title)}</b><br><span class="muted">{esc(s.description)}</span></span></label>')
    study_on = config.feature("study_reminders").get("enabled")
    boxes.append(f'<label class="check"><input type="checkbox" name="study"{" checked" if study_on else ""}>'
                 '<span><b>Study reminders</b><br><span class="muted">Text "studied &lt;topic&gt;" for review '
                 'pings at 1, 3, 7, 14 and 30 days.</span></span></label>')
    parts.append(_card("sources", 4, "Data sources", "ok" if about_ok else "todo",
        '<p class="muted">Pick what goes in your brief. All optional - weather needs no login.</p>'
        + _form("sources", "".join(boxes), "Save sources")))

    # ---- 5. Personality
    assistant = cfg["assistant"]
    parts.append(_card("personality", 5, "Personality (optional)", "ok",
        '<p class="muted">How Rubico sounds. Write it however you like - it\'s passed straight to Claude.</p>'
        + _form("personality",
                '<label for="voice">Voice</label>'
                f'<textarea id="voice" name="voice">{esc(assistant["voice"].strip())}</textarea>'
                '<p class="muted">e.g. "Dry British humour, very concise, no emoji" or "Call me boss, '
                'all lowercase, lots of energy".</p>'
                '<label for="email_style">Email replies you ask it to write</label>'
                f'<textarea id="email_style" name="email_style">{esc(assistant["email_reply_style"].strip())}</textarea>'
                '<label for="max_words">Morning brief length (words)</label>'
                f'<input type="number" id="max_words" name="max_words" min="50" max="600" '
                f'value="{esc(str(cfg["briefing"]["max_words"]))}">',
                "Save personality")))

    step = 6
    # ---- Google
    if config.source_enabled("gmail") or config.source_enabled("calendar"):
        parts.append(_google_card(step, base))
        step += 1
    # ---- Monzo
    if config.source_enabled("monzo"):
        parts.append(_monzo_card(step, base))
        step += 1
    # ---- Spotify
    if config.source_enabled("spotify"):
        parts.append(_spotify_card(step, base))
        step += 1

    parts.append('<p class="muted" style="text-align:center;margin-top:24px">Change anything here any time. '
                 '<a href="/">📊 Dashboard</a></p>')
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{esc(config.assistant_name())} setup</title><style>{CSS}</style></head>"
            f'<body><main class="wrap">{"".join(parts)}</main></body></html>')


def _google_card(step, base):
    has_client = bool(google_auth.client_config())
    labels = google_auth.all_labels()
    emails = db.kv_get("google_emails") or {}
    connected = [l for l in labels if google_auth.token_file(l).exists()]
    body = ['<p class="muted">🔒 You make your own Google "OAuth client", so your login goes straight from '
            'Google to your Rubico - nobody in between. Rubico reads email for the brief, and only sends '
            'or deletes when you ask (with a 10-minute cancel window). Revoke any time at '
            '<a href="https://myaccount.google.com/permissions" target="_blank" rel="noopener">'
            'myaccount.google.com/permissions</a>.</p>']
    if not has_client:
        body.append(
            '<p><b>Part A - create your Google OAuth client (about 5 minutes, once)</b></p><ol>'
            '<li><a href="https://console.cloud.google.com/projectcreate" target="_blank" rel="noopener">Create a project</a> called Rubico.</li>'
            '<li>Enable the <a href="https://console.cloud.google.com/apis/library/gmail.googleapis.com" target="_blank" rel="noopener">Gmail API</a> '
            'and/or <a href="https://console.cloud.google.com/apis/library/calendar-json.googleapis.com" target="_blank" rel="noopener">Calendar API</a>.</li>'
            '<li><a href="https://console.cloud.google.com/auth/branding" target="_blank" rel="noopener">Consent screen</a>: '
            'app name Rubico, audience <b>External</b>.</li>'
            '<li><a href="https://console.cloud.google.com/auth/audience" target="_blank" rel="noopener">Audience</a>: '
            'click <b>Publish app</b> (or add yourself as a test user - but then Google logs you out every 7 days).</li>'
            '<li><a href="https://console.cloud.google.com/auth/clients" target="_blank" rel="noopener">Clients</a> → '
            'Create client → type <b>Web application</b> → under <b>Authorized redirect URIs</b> add exactly:'
            f'<span class="copy">{esc(base)}/setup/google/callback</span></li>'
            '<li>Create, then paste the Client ID and secret here.</li></ol>'
            + _form("google-client", _text_input("client_id", "Client ID", "", "….apps.googleusercontent.com")
                    + _secret_input("client_secret", "Client secret"), "Save Google client"))
    else:
        body.append('<p>Google client saved ✓. Its <b>Authorized redirect URIs</b> must include:'
                    f'<span class="copy">{esc(base)}/setup/google/callback</span></p>')
        for label in labels:
            state = f"✓ {esc(emails.get(label, 'connected'))}" if label in connected else "⚠️ not signed in"
            body.append(f'<div class="acct"><span><b>{esc(label)}</b> · <span class="muted">{state}</span></span>'
                        + _form("google-remove", f'<input type="hidden" name="label" value="{esc(label)}">',
                                "Remove", quiet=True) + '</div>')
        body.append('<p style="margin-top:14px"><b>Sign in with a Google account</b></p>'
                    + _form("google-start",
                            _text_input("label", "Nickname for this account", "" if labels else "personal",
                                        "e.g. personal, work")
                            + '<label class="check"><input type="checkbox" name="gmail" checked><span>Use for Gmail</span></label>'
                              '<label class="check"><input type="checkbox" name="calendar" checked><span>Use for Calendar</span></label>'
                              '<p class="muted">Google will say it "hasn\'t verified this app" - that\'s expected, it\'s '
                              '<b>your own</b> app. Tap Advanced → Go to Rubico → Continue.</p>',
                            "Sign in with Google"))
    state = "ok" if labels and len(connected) == len(labels) else "todo"
    return _card("google", step, "Google (Gmail & Calendar)", state, "".join(body))


def _monzo_card(step, base):
    from sources import monzo

    has_client = bool(config.env("MONZO_CLIENT_ID") and config.env("MONZO_CLIENT_SECRET"))
    connected = monzo.token_file().exists()
    body = ['<p class="muted">Balance and spending, for UK Monzo accounts.</p>']
    if not has_client:
        body.append('<ol><li>Sign in at <a href="https://developers.monzo.com/" target="_blank" rel="noopener">'
                    'developers.monzo.com</a> with your Monzo email (approve it in the app).</li>'
                    '<li>Clients → New OAuth Client · Confidentiality: <b>Confidential</b> · Redirect URL:'
                    f'<span class="copy">{esc(base)}/setup/monzo/callback</span></li></ol>'
                    + _form("monzo-client", _text_input("client_id", "Client ID")
                            + _secret_input("client_secret", "Client secret"), "Save Monzo client"))
    else:
        body.append(f'<p>{"Connected ✓" if connected else "Client saved ✓"} · redirect URL must be '
                    f'<span class="copy">{esc(base)}/setup/monzo/callback</span></p>'
                    + _form("monzo-start", "", "Reconnect Monzo" if connected else "Connect Monzo",
                            quiet=connected)
                    + '<p class="muted">After connecting, open the Monzo app and tap <b>Approve</b>.</p>')
    return _card("monzo", step, "Monzo", "ok" if connected else "todo", "".join(body))


def _spotify_card(step, base):
    from sources import spotify

    has_client = bool(config.env("SPOTIFY_CLIENT_ID"))
    connected = spotify.token_file().exists()
    body = ['<p class="muted">What you\'ve been listening to.</p>']
    if not has_client:
        body.append('<ol><li>Open the <a href="https://developer.spotify.com/dashboard" target="_blank" '
                    'rel="noopener">Spotify developer dashboard</a> → Create app.</li>'
                    '<li>Redirect URI:'
                    f'<span class="copy">{esc(base)}/setup/spotify/callback</span> · tick <b>Web API</b> → Save.</li>'
                    '<li>Settings → copy the Client ID (no secret needed).</li></ol>'
                    + _form("spotify-client", _text_input("client_id", "Client ID"), "Save Spotify client"))
    else:
        body.append(f'<p>{"Connected ✓" if connected else "Client saved ✓"} · redirect URI must be '
                    f'<span class="copy">{esc(base)}/setup/spotify/callback</span></p>'
                    + _form("spotify-start", "", "Reconnect Spotify" if connected else "Connect Spotify",
                            quiet=connected))
    return _card("spotify", step, "Spotify", "ok" if connected else "todo", "".join(body))
