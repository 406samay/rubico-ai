import chat_listener
import reminders


def test_reminder_commands(sent):
    chat_listener.handle_message("remind me tomorrow to submit the form")
    assert "reminder #1" in sent[-1] and "submit the form" in sent[-1]

    chat_listener.handle_message("/reminders")
    assert "#1" in sent[-1]

    chat_listener.handle_message("/cancel 1")
    assert "Cancelled reminder #1" in sent[-1]
    assert reminders.list_active() == []

    chat_listener.handle_message("/cancel 42")
    assert "no active reminder #42" in sent[-1]


def test_bare_cancel_is_for_pending_email_actions(sent):
    chat_listener.handle_message("cancel")
    assert "Nothing pending" in sent[-1]


def test_needs_key_for_open_questions(sent):
    chat_listener.handle_message("what's on today?")
    assert "ANTHROPIC_API_KEY" in sent[-1]


def test_claude_json_actions_are_routed(sent, monkeypatch):
    monkeypatch.setattr(chat_listener.llm, "has_key", lambda: True)
    monkeypatch.setattr(chat_listener, "ask_claude",
                        lambda q, raw: '{"action": "add_reminder", "text": "Pay rent", "due": null}')
    chat_listener.handle_message("don't let me forget rent")
    assert "Pay rent" in sent[-1] and "next morning brief" in sent[-1]


def test_email_delete_goes_through_review_window(sent, monkeypatch):
    import pending_actions
    monkeypatch.setattr(chat_listener.llm, "has_key", lambda: True)
    monkeypatch.setattr(chat_listener, "ask_claude", lambda q, raw: (
        '{"action": "bulk_trash_promotions", "accounts": ["personal"]}'))
    chat_listener.handle_message("delete the promo junk")
    assert "Reply CANCEL" in sent[-1]
    assert pending_actions.get_latest_pending()["type"] == "gmail_bulk_trash"
    chat_listener.handle_message("cancel")
    assert pending_actions.get_latest_pending() is None
