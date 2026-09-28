"""Browser setup page (tools/web_setup.py): logins coming back from Google,
Monzo and Spotify, with their token servers faked locally."""

import json
from urllib.parse import parse_qs, urlparse

import pytest

import config
import db
import google_auth
import web_setup
from test_real_paths import FakeServer

BASE = "https://rubico.example.app"


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setenv("RUBICO_DEMO", "0")
    config.reload()


def test_page_renders_and_hides_secrets(real_mode, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SECRET")
    html = web_setup.render(BASE)
    assert "Claude API key" in html and "sk-ant-SECRET" not in html
    assert 'name="csrf"' in html


def test_forms_need_the_csrf_token(real_mode):
    loc = web_setup.handle_post("sources", b"csrf=wrong&weather=on", BASE)
    assert "out+of+date" in loc


def test_google_login_round_trip(real_mode, monkeypatch):
    token_server = FakeServer(lambda path, body: {
        "access_token": "ya29.test", "refresh_token": "1//refresh", "expires_in": 3600,
        "token_type": "Bearer", "scope": " ".join(google_auth.GMAIL_SCOPES)})
    # The fake token server is plain http; real Google is https, and the login
    # library rightly refuses http unless told this is a test.
    monkeypatch.setenv("OAUTHLIB_INSECURE_TRANSPORT", "1")
    monkeypatch.setattr(google_auth, "client_config", lambda: {"web": {
        "client_id": "abc.apps.googleusercontent.com", "client_secret": "shh",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": token_server.url + "/token"}})
    try:
        csrf = web_setup.csrf_token()
        url = web_setup.handle_post("google-start", f"csrf={csrf}&label=Personal&gmail=on".encode(), BASE)
        q = parse_qs(urlparse(url).query)
        assert q["redirect_uri"] == [f"{BASE}/setup/google/callback"] and q["access_type"] == ["offline"]
        assert config.source("gmail")["accounts"] == ["personal"] and config.source_enabled("gmail")

        state = q["state"][0]
        path = f"/setup/google/callback?state={state}&code=4/abc&scope=x"
        loc = web_setup.handle_callback("google", path.split("?", 1)[1], BASE, path)
        assert loc.startswith("/setup?ok=") and "personal%27+connected" in loc, loc
        saved = json.loads(google_auth.token_file("personal").read_text())
        assert saved["refresh_token"] == "1//refresh"

        # the same link can't be replayed
        loc = web_setup.handle_callback("google", path.split("?", 1)[1], BASE, path)
        assert "expired" in loc
    finally:
        token_server.close()


def test_spotify_and_monzo_logins_save_tokens(real_mode, monkeypatch):
    from sources import monzo, monzo_auth, spotify, spotify_auth

    class Resp:
        ok = True
        status_code = 200
        def __init__(self, data): self._d = data
        def json(self): return self._d
        def raise_for_status(self): pass

    sent = []
    def fake_post(url, data=None, timeout=None, **kw):
        sent.append((url, data))
        return Resp({"access_token": "a", "refresh_token": "r", "expires_in": 3600})
    monkeypatch.setattr(spotify_auth.requests, "post", fake_post)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "spot")
    monkeypatch.setenv("MONZO_CLIENT_ID", "mon")
    monkeypatch.setenv("MONZO_CLIENT_SECRET", "sec")

    csrf = web_setup.csrf_token()
    url = web_setup.handle_post("spotify-start", f"csrf={csrf}".encode(), BASE)
    state = parse_qs(urlparse(url).query)["state"][0]
    loc = web_setup.handle_callback("spotify", f"state={state}&code=c1", BASE, "")
    assert "Spotify+connected" in loc and spotify.token_file().exists()
    assert sent[-1][1]["code_verifier"]  # PKCE verifier from the start step was used

    url = web_setup.handle_post("monzo-start", f"csrf={csrf}".encode(), BASE)
    state = parse_qs(urlparse(url).query)["state"][0]
    loc = web_setup.handle_callback("monzo", f"state={state}&code=c2", BASE, "")
    assert "Approve" in loc and monzo.token_file().exists()
    assert sent[-1][1]["redirect_uri"] == f"{BASE}/setup/monzo/callback"


def test_cancelled_login_is_explained(real_mode):
    loc = web_setup.handle_callback("google", "error=access_denied&state=x", BASE, "")
    assert "cancelled" in loc


def test_cloud_mode_keeps_everything_on_the_volume(monkeypatch, tmp_path):
    monkeypatch.setenv("RUBICO_DEMO", "0")
    monkeypatch.delenv("RUBICO_CONFIG", raising=False)
    monkeypatch.delenv("RUBICO_DATA_DIR", raising=False)
    monkeypatch.setenv("RUBICO_CLOUD", "1")
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "my-rubico.up.railway.app")
    monkeypatch.setenv("PORT", "9999")
    cfg = config.reload()
    assert config.config_path() == tmp_path / "config.yaml"
    assert config.data_dir() == tmp_path and db.db_path().parent == tmp_path
    assert cfg["dashboard"]["host"] == "0.0.0.0" and cfg["dashboard"]["port"] == 9999
    assert config.dashboard_url() == "https://my-rubico.up.railway.app/"
    assert not config.dashboard_is_local()
    import sources
    assert sources.get("gmail").fix_command() == "open https://my-rubico.up.railway.app/setup#google"
    config.save_secret("TELEGRAM_CHAT_ID", "42")
    assert "TELEGRAM_CHAT_ID=42" in (tmp_path / "secrets.env").read_text()
