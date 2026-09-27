"""Every test runs in demo mode against a throwaway data folder, so tests
never need real keys and never touch your real database."""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUBICO_DEMO", "1")
    monkeypatch.setenv("RUBICO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RUBICO_CONFIG", str(tmp_path / "no-config.yaml"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import config
    config.reload()
    yield
    config.reload()


@pytest.fixture
def sent(monkeypatch):
    """Captures everything the bot would have sent on Telegram."""
    messages = []
    import telegram_bot
    monkeypatch.setattr(telegram_bot, "send_message", messages.append)
    return messages
