# Workflow: Chat, email actions and reminders

**Objective:** Answer the user's Telegram messages and carry out safe actions.

**Entry point:** `tools/chat_listener.py → handle_message(text)`. `run.py` long-polls Telegram, and only messages from `TELEGRAM_CHAT_ID` are handled.

**Routing order (cheap and deterministic first, Claude last)**
1. `/help`, `/start`: help text.
2. `cancel` / `stop` / `no` / `abort`: cancel the newest pending email action.
3. `/reminders`: list. `/cancel N` or `cancel reminder N`: cancel reminder N.
4. `/brief`: run the morning brief now.
5. `search …`: web search (if `features.web_search`).
6. `studied …`: study reminders (if `features.study_reminders.enabled`).
7. Starts with "remind me" / "note to self" / "reminder" / "note:": `reminders.parse()`. Claude extracts `{text, due}` from today's date, with `simple_parse()` as a no-AI fallback. There's no need to fetch all the user's data for this.
8. Anything else: Claude gets all the data plus the list of actions and replies with plain text or a JSON action (`add_reminder`, `list_reminders`, `cancel_reminder`, `draft_reply`, `bulk_trash_promotions`, `delete_emails_matching`, `log_study_topic`).

**Reminder dates:** `due` is an ISO date, or `null`, which means "next brief". Past dates are clamped to today. The brief includes anything due on or before today.

**Safety rules (don't break these)**
- Email sends and trashes are only queued via `pending_actions`. They run after `review_window_minutes` unless the user says cancel.
- "Delete" means Gmail Trash (recoverable for 30 days), never a permanent delete.
- Promotions cleanup uses Gmail's own `CATEGORY_PROMOTIONS` label. Claude never picks emails to delete by itself.
