"""
Shared helper for talking to your Telegram bot.

The bot only ever talks to ONE chat: TELEGRAM_CHAT_ID (yours, linked on /setup).
Messages from anyone else are ignored by chat_listener.py.

In demo mode nothing is sent - messages are printed to the terminal instead.
"""

import requests

import config

# TELEGRAM_API_URL is only for tests (pointing at a fake Telegram server).
API = config.env("TELEGRAM_API_URL", "https://api.telegram.org") + "/bot{token}/{method}"
MAX_LEN = 4000  # Telegram's hard limit is 4096 characters per message


def _token():
    token = config.env("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing - add it on the /setup page.")
    return token


def call(method, token=None, http_timeout=35, **params):
    """params go to Telegram as-is (Telegram has its own `timeout` parameter
    for long polling, so the network timeout here is called http_timeout)."""
    token = token or _token()
    try:
        resp = requests.post(API.format(token=token, method=method), json=params, timeout=http_timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        # Telegram's address contains the bot token - never let it reach logs
        # or error messages.
        raise RuntimeError(f"Telegram {method} failed: {str(e).replace(token, '<bot-token>')}") from None
    return resp.json()["result"]


def _chunks(text):
    """Split long messages on line breaks so nothing gets cut off."""
    while len(text) > MAX_LEN:
        cut = text.rfind("\n", 0, MAX_LEN)
        cut = cut if cut > 0 else MAX_LEN
        yield text[:cut]
        text = text[cut:].lstrip("\n")
    if text:
        yield text


def send_message(text):
    if config.is_demo():
        print(f"\n[{config.assistant_name()} -> Telegram]\n{text}\n")
        return
    chat_id = config.env("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID is missing - link your chat on the /setup page.")
    for part in _chunks(text):
        call("sendMessage", http_timeout=20, chat_id=chat_id, text=part)


def get_updates(offset=None, timeout=30):
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    return call("getUpdates", http_timeout=timeout + 5, **params)


# Shows up when you tap the menu button in Telegram, so nobody has to
# remember the commands.
COMMANDS = [
    ("help", "What I can do"),
    ("reminders", "List your reminders"),
    ("cancel", "Cancel a reminder, e.g. /cancel 3"),
    ("brief", "Send the morning brief now"),
]


def set_commands(token=None):
    call("setMyCommands", token=token, http_timeout=20,
         commands=[{"command": c, "description": d} for c, d in COMMANDS])


def bot_username(token=None):
    return call("getMe", token=token, http_timeout=20)["username"]
