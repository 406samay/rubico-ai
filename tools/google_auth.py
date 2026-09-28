"""
Shared Google OAuth login helper, used by anything that talks to Gmail or
Google Calendar for one of your accounts.

How it stays private:
  - You create your OWN Google Cloud "OAuth client" (the /setup page walks
    you through it), so the login goes straight from Google to your Rubico.
    No third party - including whoever wrote this code - is ever involved.
  - The saved login lands in tokens/google_<nickname>.json on your own
    storage volume. Remove the account on /setup (or revoke access at
    https://myaccount.google.com/permissions) and the access is gone.

You sign in on the /setup page ("Sign in with Google"). Everything else
only ever *uses* a saved login - it never tries to open a login window.

One login per Google account covers everything that account is used for
(Gmail and/or Calendar), so you only click through Google's screens once.

GMAIL_SCOPES and CALENDAR_SCOPES live here as the single source of truth -
Google narrows a saved token's granted scope to whatever was last requested
on refresh, so if different scripts request different scope lists for the
same token file, whichever one refreshes last silently downgrades what the
others can do. Every script must go through scopes_for() instead.
"""

import json
import os

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

import config

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",  # read emails for the brief
    "https://www.googleapis.com/auth/gmail.send",      # send replies you approve
    "https://www.googleapis.com/auth/gmail.modify",    # move emails you approve to Trash
]

CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",  # read today's events, add study reviews
]


def scopes_for(label):
    scopes = []
    if label in (config.source("gmail").get("accounts") or []):
        scopes += GMAIL_SCOPES
    if label in (config.source("calendar").get("accounts") or []):
        scopes += CALENDAR_SCOPES
    return scopes


def all_labels():
    labels = []
    for name in ("gmail", "calendar"):
        for label in config.source(name).get("accounts") or []:
            if label not in labels:
                labels.append(label)
    return labels


def token_file(label):
    return config.token_path(f"google_{label}.json")


def client_config():
    """Your Google OAuth client (saved from the /setup page), or None."""
    client_id = config.env("GOOGLE_CLIENT_ID")
    client_secret = config.env("GOOGLE_CLIENT_SECRET")
    if not (client_id and client_secret):
        return None
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def _save_token(creds, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    try:
        os.chmod(path, 0o600)  # only your user account can read it
    except OSError:
        pass


def _granted_scopes(path):
    try:
        with open(path, encoding="utf-8") as f:
            return set(json.load(f).get("scopes") or [])
    except (OSError, json.JSONDecodeError):
        return set()


def login_needed_message(label):
    return (f"The Google login for '{label}' needs renewing - sign in again at "
            f"{config.dashboard_url().rstrip('/')}/setup#google")


def get_credentials(label, scopes=None):
    """Return usable credentials for one account, refreshing if needed.

    Never opens a login window: if the login is missing or dead, it raises
    with a message saying where to sign in again, so the morning brief can
    report it instead of hanging.
    """
    scopes = scopes or scopes_for(label)
    if not scopes:
        raise ValueError(
            f"'{label}' isn't set up for Gmail or Calendar - add it on the /setup page."
        )
    path = token_file(label)

    creds = None
    # A token from before a service was switched on lacks that scope - a
    # fresh login is the only way to add it, so treat it like no token.
    if path.exists() and set(scopes) <= _granted_scopes(path):
        creds = Credentials.from_authorized_user_file(str(path), scopes)
    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds, path)
            return creds
        except RefreshError:
            # Google revoked the refresh token (e.g. access was revoked, or
            # it went unused past Google's inactivity window).
            pass

    raise RefreshError(login_needed_message(label))


def account_email(label):
    """Which real Google address a nickname is logged in as (for setup checks)."""
    from googleapiclient.discovery import build

    creds = get_credentials(label)
    scopes = scopes_for(label)
    if GMAIL_SCOPES[0] in scopes:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return service.users().getProfile(userId="me").execute().get("emailAddress")
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return service.calendars().get(calendarId="primary").execute().get("id")


# ---------------------------------------------------------------- web login
# Used by the setup page (tools/web_setup.py). Google sends you back to
#   https://<your-rubico-address>/setup/google/callback
# which must be listed under "Authorized redirect URIs" on a *Web application*
# OAuth client in Google Cloud Console.

def _web_client_config(redirect_uri):
    client = client_config()
    if not client:
        raise RuntimeError("Add your Google OAuth Client ID and secret first.")
    info = dict(client["web"])
    info["redirect_uris"] = [redirect_uri]
    return {"web": info}


def _web_flow(label, redirect_uri, state=None, code_verifier=None):
    from google_auth_oauthlib.flow import Flow

    # Google may report scopes in a different order/format than requested;
    # that's not an error for us.
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    if redirect_uri.startswith("http://"):
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # local testing only (http://127.0.0.1)
    return Flow.from_client_config(
        _web_client_config(redirect_uri), scopes=scopes_for(label), redirect_uri=redirect_uri,
        state=state, code_verifier=code_verifier, autogenerate_code_verifier=code_verifier is None,
    )


def web_login_url(label, redirect_uri):
    """Returns (url to send the browser to, state, code_verifier)."""
    flow = _web_flow(label, redirect_uri)
    url, state = flow.authorization_url(access_type="offline", prompt="consent")
    return url, state, flow.code_verifier


def web_login_finish(label, redirect_uri, state, code_verifier, callback_url):
    """Swaps the code Google sent back for a saved login. Returns the email."""
    flow = _web_flow(label, redirect_uri, state=state, code_verifier=code_verifier)
    flow.fetch_token(authorization_response=callback_url)
    _save_token(flow.credentials, token_file(label))
    try:
        return account_email(label)
    except Exception:
        return None
