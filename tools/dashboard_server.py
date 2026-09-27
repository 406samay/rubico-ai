"""
Serves the dashboard and its data.

  GET  /                -> dashboard/index.html
  GET  /api/metrics     -> the day-indexed metrics store as JSON
  GET  /api/briefings   -> every saved morning brief
  GET  /api/reminders   -> active reminders
  GET  /api/config      -> display settings (currency, city, which sources are on)
  POST /api/collect     -> kicks off a collection run in the background

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
        "sources": {s.name: s.enabled for s in sources.all_sources()},
    }


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
        """Optional password (DASHBOARD_PASSWORD in .env). Any username works."""
        password = config.env("DASHBOARD_PASSWORD")
        if not password:
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

    def do_GET(self):
        if not self._authorised():
            return
        path = self.path.split("?", 1)[0].rstrip("/") or "/"

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
        path = self.path.split("?", 1)[0].rstrip("/")
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
    if host not in ("127.0.0.1", "localhost", "::1") and not config.env("DASHBOARD_PASSWORD"):
        print(f"⚠️  Dashboard is reachable from other devices ({host}) with no password. "
              "Set DASHBOARD_PASSWORD in .env to lock it.")
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
