"""Exercises the REAL (non-demo) Claude and Telegram code against tiny fake
servers on this machine, so request/response handling is tested without
real keys or network access."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import pytest

import config


class FakeServer:
    """Records every request; `respond(path, body)` decides the reply."""

    def __init__(self, respond):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}"
                try:
                    body = json.loads(raw)
                except ValueError:  # form-encoded, e.g. OAuth token requests
                    body = {k: v[0] for k, v in parse_qs(raw.decode()).items()}
                outer.requests.append((self.path, body))
                payload = json.dumps(respond(self.path, body)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setenv("RUBICO_DEMO", "0")
    config.reload()


def test_claude_request_and_reply(real_mode, monkeypatch):
    import llm

    def respond(path, body):
        return {"id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
                "content": [{"type": "text", "text": "Hello from fake Claude"}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 3, "output_tokens": 4}}

    fake = FakeServer(respond)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", fake.url)
    try:
        assert llm.ask("be nice", "hi") == "Hello from fake Claude"
        path, body = fake.requests[-1]
        assert path == "/v1/messages"
        assert body["model"] == config.model() and body["system"] == "be nice"
        assert body["messages"] == [{"role": "user", "content": "hi"}]
    finally:
        fake.close()


def test_telegram_only_answers_the_owner(real_mode, monkeypatch):
    import chat_listener
    import db
    import telegram_bot

    updates = [
        {"update_id": 10, "message": {"chat": {"id": 111}, "text": "/reminders"}},
        {"update_id": 11, "message": {"chat": {"id": 999}, "text": "/reminders"}},  # a stranger
    ]

    def respond(path, body):
        if path.endswith("/getUpdates"):
            return {"ok": True, "result": updates if not body.get("offset") else []}
        return {"ok": True, "result": {"message_id": 1}}

    fake = FakeServer(respond)
    monkeypatch.setattr(telegram_bot, "API", fake.url + "/bot{token}/{method}")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    try:
        offset = chat_listener.poll_once(None)
        sends = [b for p, b in fake.requests if p.endswith("/sendMessage")]
        assert len(sends) == 1 and sends[0]["chat_id"] == "111"
        assert "No active reminders" in sends[0]["text"]
        assert offset == 11 and db.kv_get("telegram_offset") == 11
    finally:
        fake.close()


def test_long_telegram_messages_are_split(real_mode, monkeypatch):
    import telegram_bot

    fake = FakeServer(lambda p, b: {"ok": True, "result": {}})
    monkeypatch.setattr(telegram_bot, "API", fake.url + "/bot{token}/{method}")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    try:
        telegram_bot.send_message("\n".join(["line"] * 2000))  # ~10k characters
        parts = [b["text"] for p, b in fake.requests]
        assert len(parts) >= 3 and all(len(t) <= 4096 for t in parts)
    finally:
        fake.close()


def test_dead_google_login_never_hangs(real_mode, monkeypatch):
    """A Gmail account with no/expired login must be reported, not open a
    browser and wait forever (which would freeze the bot)."""
    import data_sources

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "x.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "y")
    cfg = config.get()
    cfg["sources"]["gmail"].update(enabled=True, accounts=["personal"])
    cfg["sources"]["weather"]["enabled"] = False
    text, broken = data_sources.build_raw_data()
    assert "unavailable" in text
    assert broken == [("Gmail personal", f"open {config.dashboard_url().rstrip('/')}/setup#google")]


def test_claude_errors_are_explained_in_plain_english(real_mode):
    import anthropic
    import httpx2 as httpx  # the HTTP library the Anthropic SDK (1.x) uses
    import llm

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    bad_key = anthropic.AuthenticationError("invalid x-api-key", response=httpx.Response(401, request=req), body=None)
    assert "key isn't working" in llm.friendly_error(bad_key) and "/setup#claude" in llm.friendly_error(bad_key)
    no_credit = anthropic.BadRequestError("Your credit balance is too low to access the Anthropic API",
                                          response=httpx.Response(400, request=req), body=None)
    assert "credit has run out" in llm.friendly_error(no_credit)


def test_bot_token_never_appears_in_errors(real_mode, monkeypatch):
    import requests
    import telegram_bot

    def fail(url, **kw):  # like a real 401 from Telegram: the message includes the URL
        raise requests.HTTPError(f"401 Client Error: Unauthorized for url: {url}")
    monkeypatch.setattr(telegram_bot.requests, "post", fail)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:SECRET-TOKEN")
    with pytest.raises(RuntimeError) as err:
        telegram_bot.call("getMe")
    assert "SECRET-TOKEN" not in str(err.value) and "<bot-token>" in str(err.value)
