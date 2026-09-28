"""
Monzo login, used by the /setup page (tools/web_setup.py).

Flow: setup sends you to Monzo's login page -> Monzo sends you back to
https://<your-rubico-address>/setup/monzo/callback with a one-time code ->
exchange_code() swaps it for tokens and saves them on your volume.

Afterwards Monzo sends a push notification asking you to approve access in
the Monzo app. Nothing works until you tap Approve.

Your Monzo developer client's redirect URL must match the callback address
exactly - the Monzo card on /setup shows it.
"""

import os
import sys
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

import config
from sources.monzo import _save_tokens


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
