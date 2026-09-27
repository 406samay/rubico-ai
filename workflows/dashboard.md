# Workflow: Dashboard

**Objective:** A private web page with briefing history, active reminders and day-by-day charts.

- Served by `tools/dashboard_server.py` (started by `run.py` when `dashboard.enabled`).
- Data: `/api/metrics` (from `metrics_store`, one row per day in SQLite), `/api/briefings`, `/api/reminders`, `/api/config`.
- Charts are filled by each source's optional `collect()`, run by `tools/collect_metrics.py` every `metrics.collect_every_minutes`. The refresh button on the page triggers the same thing.
- `dashboard/index.html` is a single file with no build step. Cards only show for enabled sources. Always pass user or email text through `esc()` before putting it into HTML.
- Safety: it binds to `127.0.0.1` by default. If `dashboard.host` is opened up, set `DASHBOARD_PASSWORD` (HTTP basic auth).
