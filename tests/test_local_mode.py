"""Running Rubico on your own computer (python run.py --local, or the start
files), next to the Railway mode that the rest of the tests cover."""

import http.client
import os
import shutil
import subprocess
import sys
import threading

import pytest

import config
import dashboard_server
import web_setup

ROOT = config.ROOT


@pytest.fixture
def local_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("RUBICO_DEMO", "0")
    monkeypatch.setenv("RUBICO_CLOUD", "0")
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    for key in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DASHBOARD_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    config.reload()


@pytest.fixture
def local_server(local_mode):
    server = dashboard_server.make_server(host="127.0.0.1", port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


def fetch(port, path, host=None, method="GET", headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    all_headers = dict(headers or {})
    if host:
        all_headers["Host"] = host
    conn.request(method, path, headers=all_headers)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8", "replace")
    out = (resp.status, dict(resp.getheaders()), body)
    conn.close()
    return out


# ---------------------------------------------------------------- the switch

def _fresh_python(code, **env):
    """Runs a snippet in a new Python, because run.py reads its flag at import."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("RUBICO_", "RAILWAY_"))}
    clean.update(env)
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                         env=clean, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_local_flag_switches_off_server_mode_and_is_removed_from_argv():
    got = _fresh_python("import sys; sys.argv = ['run.py', '--local']; import run, config; "
                        "print(config.is_cloud(), config.is_local(), sys.argv)")
    assert got == "False True ['run.py']"


def test_without_the_flag_it_is_still_server_mode():
    got = _fresh_python("import sys; sys.argv = ['run.py']; import run, config; print(config.is_cloud())")
    assert got == "True"


def test_local_mode_keeps_files_next_to_the_code_and_the_page_private():
    got = _fresh_python(
        "import sys; sys.argv = ['run.py', '--local']; import run, config; cfg = config.get(); "
        "print(config.config_path() == config.ROOT / 'config.yaml'); "
        "print(config.secrets_file() == config.ROOT / '.env'); "
        "print(config.data_dir() == config.ROOT / 'data'); "
        "print(cfg['dashboard']['host'], cfg['dashboard']['port']); "
        "print(config.local_setup_url())")
    assert got.splitlines() == ["True", "True", "True", "127.0.0.1 8600", "http://127.0.0.1:8600/setup"]


def test_server_mode_is_unchanged_on_railway(monkeypatch, tmp_path):
    monkeypatch.setenv("RUBICO_DEMO", "0")
    monkeypatch.setenv("RUBICO_CLOUD", "1")
    monkeypatch.setenv("PORT", "8080")
    cfg = config.reload()
    assert config.is_cloud() and not config.is_local()
    assert cfg["dashboard"]["host"] == "0.0.0.0" and cfg["dashboard"]["port"] == 8080


# ---------------------------------------------------------------- the pages

def test_first_visit_goes_to_setup(local_server):
    status, headers, _ = fetch(local_server, "/")
    assert status == 303 and headers["Location"] == "/setup"


def test_setup_page_works_without_a_password_on_this_computer(local_server):
    status, _, body = fetch(local_server, "/setup", host=f"127.0.0.1:{local_server}")
    assert status == 200 and "Claude API key" in body


def test_logins_show_the_laptop_address_to_copy(local_server):
    """Google, Spotify and Monzo need this exact address. On a laptop it's 127.0.0.1."""
    config.save_user_config({"sources": {"gmail": {"enabled": True, "accounts": []},
                                         "spotify": {"enabled": True}, "monzo": {"enabled": True}}})
    _, _, body = fetch(local_server, "/setup", host=f"127.0.0.1:{local_server}")
    for service in ("google", "spotify", "monzo"):
        assert f"http://127.0.0.1:{local_server}/setup/{service}/callback" in body, service


def test_setup_page_has_no_railway_warnings_on_a_laptop(local_server, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "short")
    _, _, body = fetch(local_server, "/setup")  # a short password is fine on your own computer
    assert "No storage volume" not in body and "Add Volume" not in body
    assert "is on the" not in body and "on the internet" not in body


def test_localhost_name_also_works(local_server):
    assert fetch(local_server, "/setup", host=f"localhost:{local_server}")[0] == 200


def test_other_website_names_are_refused(local_server):
    """DNS rebinding: a website pointing its own name at 127.0.0.1 must not read the dashboard."""
    for path in ("/", "/setup", "/api/metrics", "/api/briefings"):
        status, _, body = fetch(local_server, path, host="evil.example.com")
        assert status == 403, path
        assert "blocked" in body
    status, _, _ = fetch(local_server, "/setup/sources", host="evil.example.com", method="POST")
    assert status == 403


def test_other_names_are_still_fine_on_a_server(monkeypatch):
    """The name check is only for laptops. Railway's own address must keep working."""
    monkeypatch.setenv("RUBICO_DEMO", "0")
    monkeypatch.setenv("RUBICO_CLOUD", "1")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "a-long-enough-password")
    monkeypatch.setenv("PORT", "0")
    config.reload()
    server = dashboard_server.make_server(host="127.0.0.1", port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        assert fetch(port, "/healthz", host="my-rubico.up.railway.app")[0] == 200
        # no password still means locked out on a server
        assert fetch(port, "/setup", host="my-rubico.up.railway.app")[0] == 401
    finally:
        server.shutdown()


def test_saving_a_key_lands_in_the_env_file_next_to_the_code(local_mode, tmp_path):
    config.save_secret("TELEGRAM_CHAT_ID", "42")
    assert "TELEGRAM_CHAT_ID=42" in (tmp_path / ".env").read_text()


def test_setup_finishes_by_itself_and_links_to_the_dashboard(local_mode, monkeypatch):
    assert not web_setup.essentials_done()
    for key in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.setenv(key, "x")
    assert web_setup.essentials_done()
    assert "Rubico is running" in web_setup.render("http://127.0.0.1:8600")


# ---------------------------------------------------------------- opening the browser

def test_browser_opens_for_setup_unless_switched_off(monkeypatch, local_mode):
    import run

    opened = []
    monkeypatch.setattr(run.webbrowser, "open", opened.append)
    monkeypatch.delenv("RUBICO_NO_BROWSER", raising=False)
    run.open_in_browser("http://127.0.0.1:8600/setup")
    assert opened == ["http://127.0.0.1:8600/setup"]

    monkeypatch.setenv("RUBICO_NO_BROWSER", "1")
    run.open_in_browser("http://127.0.0.1:8600/setup")
    assert len(opened) == 1


def test_a_browser_that_fails_to_open_does_not_stop_rubico(monkeypatch, local_mode):
    import run

    def boom(url):
        raise RuntimeError("no browser here")

    monkeypatch.setattr(run.webbrowser, "open", boom)
    monkeypatch.delenv("RUBICO_NO_BROWSER", raising=False)
    run.open_in_browser("http://127.0.0.1:8600/setup")  # must not raise


# ---------------------------------------------------------------- start files

def test_start_files_run_in_local_mode_and_offer_the_demo():
    for name in ("start.sh", "start.bat"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "run.py --local" in text, name
        assert "demo.py" in text, name
    assert "start.sh" in (ROOT / "start.command").read_text(encoding="utf-8")


# On Windows, "bash" is often a stub that can't read Windows paths. The shell start
# files are checked on Mac and Linux, and start.bat is run for real on Windows by
# tests/smoke_start_file.py in the GitHub check.
@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="needs a real bash")
def test_shell_start_files_are_valid_bash():
    for name in ("start.sh", "start.command"):
        assert subprocess.run(["bash", "-n", str(ROOT / name)]).returncode == 0, name


def test_line_endings_are_pinned_so_start_files_work_on_every_system():
    rules = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in rules
    assert "*.command text eol=lf" in rules
    assert "*.bat text eol=crlf" in rules


# ---------------------------------------------------------------- Railway or this computer

class FakeTerminal:
    """Stands in for a person sitting at the terminal."""
    def isatty(self):
        return True


@pytest.fixture
def at_a_terminal(local_mode, monkeypatch):
    import run

    monkeypatch.setattr(sys, "stdin", FakeTerminal())
    opened = []
    monkeypatch.setattr(run, "open_in_browser", opened.append)

    def answers(*given):
        queue = iter(given)
        monkeypatch.setattr("builtins.input", lambda *_: next(queue))
        return opened

    return run, answers


def test_first_start_on_a_computer_asks_railway_or_this_computer(at_a_terminal, capsys):
    run, answers = at_a_terminal
    answers("2")
    assert run.ask_where_it_runs() is True
    out = capsys.readouterr().out
    assert "Railway (recommended)" in out and "$5 a month" in out and "On this computer" in out


def test_choosing_this_computer_carries_on_and_is_remembered(at_a_terminal):
    run, answers = at_a_terminal
    answers("2")
    assert run.ask_where_it_runs() is True
    assert config.load_user_file()["where"] == "laptop"
    answers()  # a second start must not ask again, so any input() call would fail
    assert run.ask_where_it_runs() is True


def test_choosing_railway_opens_the_guide_and_stops(at_a_terminal, capsys):
    run, answers = at_a_terminal
    opened = answers("1")
    assert run.ask_where_it_runs() is False
    assert opened == [run.DEPLOY_URL]
    out = capsys.readouterr().out
    assert "deploy-railway.md" in out and run.DEPLOY_URL in out
    assert "where" not in config.load_user_file()  # nothing saved, so it asks again next time


def test_a_wrong_answer_asks_again(at_a_terminal, capsys):
    run, answers = at_a_terminal
    answers("maybe", "", "2")
    assert run.ask_where_it_runs() is True
    assert capsys.readouterr().out.count("Please type 1 or 2") == 2


def test_it_does_not_ask_when_nobody_is_there_to_answer(local_mode, monkeypatch):
    import run

    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("must not ask without a terminal"))
    assert run.ask_where_it_runs() is True  # pytest's stdin is not a terminal, like the GitHub checks


def test_it_does_not_ask_once_setup_is_finished(at_a_terminal, monkeypatch):
    run, answers = at_a_terminal
    for key in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.setenv(key, "x")
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("already set up, must not ask"))
    assert run.ask_where_it_runs() is True


def test_it_never_asks_on_railway(monkeypatch):
    import run

    monkeypatch.setenv("RUBICO_DEMO", "0")
    monkeypatch.setenv("RUBICO_CLOUD", "1")
    config.reload()
    monkeypatch.setattr(sys, "stdin", FakeTerminal())
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("Railway has no terminal to ask in"))
    assert run.ask_where_it_runs() is True


def test_setup_page_offers_railway_on_a_computer_but_not_on_railway(local_mode, monkeypatch):
    assert "Run it on Railway" in web_setup.render("http://127.0.0.1:8600")
    monkeypatch.setenv("RUBICO_CLOUD", "1")
    config.reload()
    assert "Run it on Railway" not in web_setup.render("https://my-rubico.up.railway.app")
