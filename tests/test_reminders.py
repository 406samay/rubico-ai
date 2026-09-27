import datetime

import pytest

import llm
import reminders

BASE = datetime.date(2026, 9, 27)  # a Sunday


@pytest.mark.parametrize("message, text, due", [
    ("remind me tomorrow to submit the form", "submit the form", BASE + datetime.timedelta(days=1)),
    ("note to self: call the dentist", "call the dentist", None),
    ("remind me in 3 days to renew my passport", "renew my passport", BASE + datetime.timedelta(days=3)),
    ("remind me on friday about the invoice", "about the invoice", datetime.date(2026, 10, 2)),
    ("remind me next monday to book flights", "book flights", datetime.date(2026, 9, 28)),
    ("remind me 5th oct to pay rent", "pay rent", datetime.date(2026, 10, 5)),
    ("remind me to pay rent on 1 jan", "pay rent", datetime.date(2027, 1, 1)),
    ("remind me in 2 weeks to check the boiler", "check the boiler", BASE + datetime.timedelta(days=14)),
    ("remind me today to water the plants", "water the plants", BASE),
])
def test_simple_parse(message, text, due):
    got_text, got_due = reminders.simple_parse(message, BASE)
    assert got_due == due
    assert text in got_text


def test_add_list_cancel_and_briefing_selection():
    today = reminders.today()
    a = reminders.add("next brief note", None)
    b = reminders.add("due today", today)
    c = reminders.add("overdue", today - datetime.timedelta(days=2))
    d = reminders.add("future", today + datetime.timedelta(days=5))

    assert [r["id"] for r in reminders.list_active()][0] == a  # no-date first
    due_ids = {r["id"] for r in reminders.due_for_briefing()}
    assert due_ids == {a, b, c}

    assert reminders.cancel(d) is True
    assert reminders.cancel(d) is False  # already cancelled
    reminders.mark_delivered(list(due_ids))
    assert reminders.list_active() == []


def test_claude_parse_uses_returned_date(monkeypatch):
    monkeypatch.setattr(llm, "ask", lambda *a, **k: '{"text": "Submit the form", "due": "2026-09-28"}')
    assert reminders.parse_with_claude("remind me tomorrow to submit the form", BASE) == (
        "Submit the form", datetime.date(2026, 9, 28))


def test_claude_parse_null_means_next_brief_and_past_dates_clamp(monkeypatch):
    monkeypatch.setattr(llm, "ask", lambda *a, **k: '{"text": "Call mum", "due": null}')
    assert reminders.parse_with_claude("note: call mum", BASE)[1] is None
    monkeypatch.setattr(llm, "ask", lambda *a, **k: '{"text": "Old", "due": "2020-01-01"}')
    assert reminders.parse_with_claude("x", BASE)[1] == BASE
