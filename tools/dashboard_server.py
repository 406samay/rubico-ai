"""
Serves the dashboard and its data.

  GET  /                -> dashboard/index.html
  GET  /api/metrics     -> the day-indexed metrics store as JSON
  GET  /api/briefings   -> every saved morning brief
  GET  /api/reminders   -> active reminders
  GET  /api/config      -> display settings (currency, city, which sources are on)
  POST /api/collect     -> kicks off a collection run in the background
  GET  /setup           -> setup in the browser (tools/web_setup.py)
  GET  /healthz         -> "ok" (no password; for hosting health checks)

Demo mode only (python demo.py) - a Telegram-style chat in the browser, so
you can text the bot before connecting anything:
  GET  /chat            -> dashboard/chat.html
  GET  /api/chat        -> the conversation so far
  POST /api/chat        -> send a message, get the bot's replies
These don't exist in a real install - there, you chat on Telegram itself.

Safety: by default it only listens on 127.0.0.1, meaning only THIS computer
can open it - the page can show a live bank balance. To reach it from your
phone, change dashboard.host in config.yaml (e.g. to your Tailscale IP, or
0.0.0.0 for your whole home network) and set DASHBOARD_PASSWORD in .env.
"""

import base64
import hmac
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import db
import llm
import metrics_store
import reminders
import sources

DASHBOARD_DIR = config.ROOT / "dashboard"

_collect_lock = threading.Lock()
_collecting = False


def _run_collection():
    global _collecting
    try:
        import collect_metrics
        collect_metrics.collect()
    except Exception as exc:
        print(f"collection failed: {type(exc).__name__}: {exc}")
    finally:
        with _collect_lock:
            _collecting = False


# ---------------------------------------------------------------- demo chat

_chat_lock = threading.Lock()
demo_chat_history = []  # [{"from": "bot"|"you", "text": ...}], seeded by demo.py


def demo_chat_send(text):
    """Runs a message through the real chat handler, catching what the bot
    would have sent to Telegram instead of sending it."""
    import chat_listener
    import telegram_bot

    import datetime

    now = datetime.datetime.now(config.tz()).strftime("%H:%M")
    replies = []
    with _chat_lock:
        demo_chat_history.append({"from": "you", "text": text, "time": now})
        real_send = telegram_bot.send_message
        telegram_bot.send_message = replies.append
        try:
            chat_listener.handle_message(text)
            chat_listener.process_due_sends()
        except Exception as e:
            replies.append(f"Something went wrong: {type(e).__name__}: {e}")
        finally:
            telegram_bot.send_message = real_send
        new = [{"from": "bot", "text": r, "time": now} for r in replies]
        demo_chat_history.extend(new)
    return new


def _briefings(limit=120):
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at, date, text, broken FROM briefings ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r, broken=json.loads(r["broken"] or "[]")) for r in rows]


def _public_config():
    cfg = config.get()
    return {
        "assistant": config.assistant_name(),
        "user": config.user_name(),
        "currency": cfg["currency"],
        "locale": cfg["locale"],
        "location": cfg["location"]["name"],
        "timezone": cfg["timezone"],
        "demo": config.is_demo(),
        "claude": llm.has_key(),
        "sources": {s.name: s.enabled for s in sources.all_sources()},
        "chat_url": _chat_url(),
    }


def _chat_url():
    """Where the dashboard's "Open chat" button goes."""
    if config.is_demo():
        return "chat"
    username = db.kv_get("bot_username")
    return f"https://t.me/{username}" if username else None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body=b"", content_type="text/plain; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload, code=200):
        return self._send(code, json.dumps(payload).encode(), "application/json; charset=utf-8")

    def _authorised(self):
        """Password check (DASHBOARD_PASSWORD). Any username works.
        Always required, except for the local demo (fake data only)."""
        if config.is_demo():
            return True
        password = config.env("DASHBOARD_PASSWORD")
        if not password:
            if config.is_cloud():
                self._send(503, "Rubico needs a password before it can be opened on the internet.\n\n"
                                "In Railway: open your Rubico service -> Variables -> add "
                                "DASHBOARD_PASSWORD with a password of your choice.".encode())
                return False
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                _, _, given = base64.b64decode(header[6:]).decode().partition(":")
            except Exception:
                given = ""
            if hmac.compare_digest(given, password):
                return True
        self._send(401, b"password required", extra={"WWW-Authenticate": 'Basic realm="Rubico"'})
        return False

    def _base_url(self):
        """This server's address as the browser sees it (for login redirects)."""
        if config.is_cloud() and config.public_url():
            return config.public_url().rstrip("/")
        proto = self.headers.get("X-Forwarded-Proto", "http").split(",")[0].strip()
        return f"{proto}://{self.headers.get('Host', 'localhost')}"

    def _redirect(self, location):
        return self._send(303, b"", extra={"Location": location})

    def _same_origin(self):
        """Blocks other websites from submitting forms to Rubico (CSRF)."""
        from urllib.parse import urlparse

        source = self.headers.get("Origin") or self.headers.get("Referer")
        if not source or source == "null":
            return True  # non-browser clients (curl) don't send one
        return urlparse(source).netloc == self.headers.get("Host", "")

    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/healthz":
            return self._send(200, b"ok")
        if not self._authorised():
            return
        query = self.path.split("?", 1)[1] if "?" in self.path else ""

        if path.startswith("/setup") and config.is_demo():
            return self._send(404, b"Setup isn't available in the demo. See docs/deploy-railway.md")
        if path == "/setup":
            import web_setup
            return self._send(200, web_setup.render(self._base_url(), query).encode(), "text/html; charset=utf-8")
        if path in ("/setup/google/callback", "/setup/monzo/callback", "/setup/spotify/callback"):
            import web_setup
            kind = path.split("/")[2]
            return self._redirect(web_setup.handle_callback(kind, query, self._base_url(), self.path))
        if path in ("/", "/index.html") and not config.is_demo():
            import web_setup
            if config.is_cloud() and not web_setup.essentials_done():
                return self._redirect("/setup")

        if path in ("/", "/index.html"):
            index = DASHBOARD_DIR / "index.html"
            if not index.exists():
                return self._send(404, b"dashboard/index.html missing")
            return self._send(200, index.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/metrics":
            return self._json(metrics_store.load())
        if path == "/api/briefings":
            return self._json(_briefings())
        if path == "/api/reminders":
            items = reminders.list_active()
            for r in items:
                r["when"] = reminders.describe_due(r)
            return self._json(items)
        if path == "/api/config":
            return self._json(_public_config())
        if config.is_demo() and path == "/chat":
            return self._send(200, (DASHBOARD_DIR / "chat.html").read_bytes(), "text/html; charset=utf-8")
        if config.is_demo() and path == "/api/chat":
            with _chat_lock:
                return self._json(list(demo_chat_history))
        if path == "/api/status":
            with _collect_lock:
                busy = _collecting
            return self._json({"collecting": busy})
        return self._send(404, b"not found")

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        if not self._authorised():
            return
        if not self._same_origin():
            return self._send(403, b"blocked: request came from another website")
        path = self.path.split("?", 1)[0].rstrip("/")
        if path.startswith("/setup/"):
            if config.is_demo():
                return self._send(404, b"Setup isn't available in the demo.")
            import web_setup
            length = min(int(self.headers.get("Content-Length") or 0), 20000)
            body = self.rfile.read(length)
            return self._redirect(web_setup.handle_post(path[len("/setup/"):], body, self._base_url()))
        if config.is_demo() and path == "/api/chat":
            length = min(int(self.headers.get("Content-Length") or 0), 4000)
            try:
                text = (json.loads(self.rfile.read(length) or b"{}").get("text") or "").strip()[:1000]
            except (ValueError, AttributeError):
                text = ""
            if not text:
                return self._json({"error": "empty message"}, 400)
            return self._json(demo_chat_send(text))
        if path != "/api/collect":
            return self._send(404, b"not found")

        global _collecting
        with _collect_lock:
            already = _collecting
            if not already:
                _collecting = True
        if not already and not config.is_demo():
            threading.Thread(target=_run_collection, daemon=True).start()
        elif not already:
            with _collect_lock:
                _collecting = False
        return self._send(202, json.dumps({"started": not already, "collecting": True}).encode(),
                          "application/json; charset=utf-8")

    def log_message(self, fmt, *args):
        pass  # quiet: no line per request


class QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # A browser closing a tab mid-request isn't worth a stack trace.
        if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def make_server(host=None, port=None):
    dash = config.get()["dashboard"]
    host = host or dash.get("host", "127.0.0.1")
    port = int(port or dash.get("port", 8600))
    return QuietServer((host, port), Handler)


def main():
    server = make_server()
    print(f"Dashboard on http://{server.server_address[0]}:{server.server_address[1]}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
