"""
Spotify login, used by the /setup page (tools/web_setup.py).

Uses Authorization Code with PKCE: there's no client secret at all, so
there's nothing to leak. The code_verifier is made per login, kept only
until Spotify sends you back, and only the resulting tokens are saved.

Your Spotify app's Redirect URI must be exactly
    https://<your-rubico-address>/setup/spotify/callback
(the Spotify card on /setup shows it).
"""

import base64
import hashlib
import os
import secrets
import sys
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

import config
from sources.spotify import _save_tokens

SCOPES = [
    "user-read-recently-played",
    "user-top-read",
    "user-read-currently-playing",
]


def _pkce_pair():
    """code_verifier + S256 challenge, base64url without padding."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def login_url(redirect_uri, state, challenge):
    return "https://accounts.spotify.com/authorize?" + urlencode({
        "client_id": config.env("SPOTIFY_CLIENT_ID"),
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    })


def exchange_code(code, redirect_uri, verifier):
    """Swaps Spotify's one-time code for tokens and saves them."""
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": config.env("SPOTIFY_CLIENT_ID"),
            "code_verifier": verifier,
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Spotify token exchange failed ({resp.status_code}): {resp.text[:300]}")
    tokens = resp.json()
    _save_tokens(tokens)
    return tokens
