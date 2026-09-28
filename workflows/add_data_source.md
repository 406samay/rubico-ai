# Workflow: Add a new data source

**Objective:** Plug a new service into the brief without touching the core.

1. Copy `tools/sources/_template.py` to `tools/sources/<name>.py`. Implement `fetch()`, `demo()` and `format()` (optionally `problems()`, `collect()`, `demo_history()`).
2. Register the class in `ALL` in `tools/sources/__init__.py`.
3. Add `<name>: {enabled: false, ...}` to `config.example.yaml` **and** `DEFAULTS["sources"]` in `tools/config.py`.
4. Add any secrets to `.env.example` with a comment on where to get them.
5. If it needs a key or login, add a card to `tools/web_setup.py` (copy the Spotify card), set `setup_card` on the source, and store tokens with `config.token_path()`.
6. Verify: `python demo.py`, `python -m pytest`, then `DASHBOARD_PASSWORD=dev PORT=8080 python run.py` → connect it on `/setup` → text `/brief`.

Full guide with the interface table: `CONTRIBUTING.md`.
