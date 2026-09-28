"""
One-time login to Monzo. Opens a browser to Monzo's login page, catches the
redirect locally, and exchanges the code for an access + refresh token.

After this runs, check your phone - Monzo sends a push notification asking
you to approve third-party access. Nothing works until you tap Approve.

Run: python tools/sources/monzo_auth.py   (setup.py runs it for you)

In your Monzo developer client, the redirect URL must be exactly:
    http://localhost:8085/monzo/callback
"""

import os
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

import config
from sources.monzo import _save_tokens

REDIRECT_URI = "http://localhost:8085/monzo/callback"

_result = {}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        code = query.get("code", [None])[0]

        if parsed.path != "/monzo/callback" or not code:
            # Ignore stray requests (favicon, prefetch, etc.) - don't treat as the real callback.
            self.send_response(404)
            self.end_headers()
            return

        _result["code"] = code
        _result["state"] = query.get("state", [None])[0]

        try:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Login received - you can close this tab.</body></html>")
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # The browser often drops the socket the instant it has the code,
            # before we finish writing the courtesy page. We already captured
            # the code above, so this is cosmetic - don't dump a scary trace.
            pass

    def log_message(self, format, *args):
        pass


def login_url(redirect_uri, state):
    return "https://auth.monzo.com/?" + urlencode({
        "client_id": config.env("MONZO_CLIENT_ID"),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    })


def exchange_code(code, redirect_uri):
    """Swaps Monzo's one-time code for tokens and saves them."""
    resp = requests.post("https://api.monzo.com/oauth2/token", data={
        "grant_type": "authorization_code",
        "client_id": config.env("MONZO_CLIENT_ID"),
        "client_secret": config.env("MONZO_CLIENT_SECRET"),
        "redirect_uri": redirect_uri,
        "code": code,
    }, timeout=30)
    resp.raise_for_status()
    _save_tokens(resp.json())


def main():
    CLIENT_ID = config.env("MONZO_CLIENT_ID")
    CLIENT_SECRET = config.env("MONZO_CLIENT_SECRET")
    if not (CLIENT_ID and CLIENT_SECRET):
        print("MONZO_CLIENT_ID / MONZO_CLIENT_SECRET are missing from .env.")
        print("Run: python setup.py --only monzo")
        return 1

    state = secrets.token_urlsafe(16)
    auth_url = login_url(REDIRECT_URI, state)

    print("Opening browser to log in to Monzo...")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", 8085), CallbackHandler)
    print("Waiting for you to complete login in the browser...")
    while "code" not in _result:
        server.handle_request()

    if _result.get("state") != state:
        print("State mismatch - aborting for safety.")
        sys.exit(1)

    code = _result.get("code")
    if not code:
        print("No code received. Did the login fail?")
        sys.exit(1)

    exchange_code(code, REDIRECT_URI)

    print("Logged in and saved token.")
    print("\nIMPORTANT: check your phone now - Monzo sends a push notification")
    print("asking you to approve this access. Nothing works until you tap Approve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
