# Workflow: Morning brief

**Objective:** Once a day, send the user a short, useful brief on Telegram and save a copy for the dashboard.

**Trigger:** `run.py` checks every 30 seconds and runs it at `briefing.time` in the user's `timezone`. It runs once per day. If Rubico was off at that time, it still runs within `briefing.catch_up_minutes`, and after that it skips the day rather than arriving at lunchtime. You can also run it by hand: `python tools/orchestrator.py` (add `--no-send` to only print it).

**Steps (all in `tools/orchestrator.py → run_briefing`)**
1. `data_sources.build_raw_data()` calls `fetch()` + `format()` on every enabled source in `tools/sources/`. One failing source becomes an "(unavailable)" note plus an entry in `broken`. It never stops the brief.
2. `reminders.due_for_briefing()` returns reminders with no date, due today, or overdue.
3. Claude writes the brief (`write_brief`) in the voice from `assistant.voice`.
4. Code, not Claude, adds the reminders list, the dashboard link, and a "Couldn't reach …" section with the exact fix command for each broken source. This guarantees reminders are never dropped.
5. Send via `telegram_bot.send_message`, mark reminders delivered, save to the `briefings` table, and set `last_briefing_date`.

**Edge cases**
- The Claude API fails: a short error message is still sent **with the reminders**.
- A Google login has died: scheduled runs use `allow_browser=False`, so they report the problem instead of hanging on a browser login nobody will see. Fix with `python tools/reauth_google.py`.
- Monzo returns `403 verification_required` for history queries of 90+ days. Keep `window_days` ≤ 85. Balance still works while it's blocked.
- Spotify only exposes the last 50 plays, so collection must run at least every ~3 hours.
