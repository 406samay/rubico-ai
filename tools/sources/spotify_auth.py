"""
One-time login to Spotify, using Authorization Code with PKCE.

PKCE rather than the client-secret flow deliberately: a personal integration
running on a homelab has nowhere safe to keep a client secret, and PKCE
removes the need for one entirely. The code_verifier is generated per run,
never stored, and only the resulting tokens are written to disk.

Run: python tools/sources/spotify_auth.py   (setup.py runs it for you)

The redirect URI must be registered in the Spotify app settings as exactly
    http://127.0.0.1:8888/callback
Spotify rejects "localhost" - loopback redirects must use the literal IP.
"""

import base64
import hashlib
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
from sources.spotify import _save_tokens

REDIRECT_URI = "http://127.0.0.1:8888/callback"

SCOPES = [
    "user-read-recently-played",
    "user-top-read",
    "user-read-currently-playing",
]

_result = {}


def _pkce_pair():
    """code_verifier + S256 challenge, base64url without padding."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        code = query.get("code", [None])[0]
        error = query.get("error", [None])[0]

        if parsed.path != "/callback" or not (code or error):
            # Ignore favicon/prefetch noise rather than treating it as the
            # real callback and aborting on a state mismatch.
            self.send_response(404)
            self.end_headers()
            return

        _result["code"] = code
        _result["error"] = error
        _result["state"] = query.get("state", [None])[0]

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body style='font:16px system-ui;padding:40px;background:#121212;color:#fff'>"
            b"<b>Spotify connected.</b><br>You can close this tab.</body></html>"
        )

    def log_message(self, *args):
        pass


def main():
    CLIENT_ID = config.env("SPOTIFY_CLIENT_ID")
    if not CLIENT_ID:
        print("SPOTIFY_CLIENT_ID is missing from .env. Run: python setup.py --only spotify")
        return 1

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    auth_url = "https://accounts.spotify.com/authorize?" + urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    })

    print("Opening browser to authorise Spotify...")
    webbrowser.open(auth_url)

    server = HTTPServer(("127.0.0.1", 8888), CallbackHandler)
    print("Waiting for you to approve in the browser...")
    while "code" not in _result and "error" not in _result:
        server.handle_request()

    if _result.get("error"):
        print(f"Spotify returned an error: {_result['error']}")
        sys.exit(1)
    if _result.get("state") != state:
        print("State mismatch - aborting for safety.")
        sys.exit(1)

    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": _result["code"],
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "code_verifier": verifier,
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"Token exchange failed ({resp.status_code}): {resp.text[:400]}")
        sys.exit(1)

    tokens = resp.json()
    _save_tokens(tokens)

    print("Spotify connected.")
    print(f"Scopes granted: {tokens.get('scope')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
