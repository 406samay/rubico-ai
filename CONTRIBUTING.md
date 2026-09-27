# Contributing to Rubico

Thanks for helping! The most useful contribution is **a new data source**: Strava,
Todoist, GitHub, Notion, Outlook, Apple Health exports, other banks, news, stocks and
so on. Every new source makes the morning brief more useful for someone.

Beginners are welcome. If you get stuck, open a draft pull request and ask.

## How the project is organised

Rubico follows the **WAT** pattern described in [CLAUDE.md](CLAUDE.md):

- **Workflows** (`workflows/*.md`): plain-English instructions for each job.
- **Agent**: Claude, deciding what to do and writing the words.
- **Tools** (`tools/*.py`): deterministic Python that does the actual work
  (API calls, the database, sending messages).

Data sources are tools. They fetch facts and hand plain text to Claude. They
shouldn't try to be clever, because Claude does the thinking.

## Adding a data source (step by step)

Every source is one file in `tools/sources/` and follows the same interface
(`tools/sources/base.py`):

| Method | Required? | What it does |
|---|---|---|
| `fetch(allow_browser=True)` | ✅ | Gets today's real data. **Raise an exception** if something is wrong. The core catches it, keeps the rest of the brief, and tells the user how to fix it. |
| `demo()` | ✅ | Returns realistic but **fake** data in exactly the same shape as `fetch()`. This powers `demo.py` and the tests. |
| `format(data)` | ✅ | Turns that data into plain text for Claude, starting with a `--- Title ---` line. |
| `problems()` | optional | Lists what's missing (keys, logins) for `setup.py --check`. The default checks `env_vars`. |
| `broken_parts(data)` | optional | For multi-account sources, reports which accounts failed. |
| `collect(store, log)` | optional | Saves day-by-day numbers for dashboard charts. |
| `demo_history(dates)` | optional | Fake dashboard history for demo mode. |

Plus a few attributes: `name` (its config key), `title`, `description`
(shown in setup), `env_vars` (secrets it needs) and `fix_hint` (the command to
run when it breaks).

### 1. Copy the template

```bash
cp tools/sources/_template.py tools/sources/strava.py
```

Fill in every `TODO`. Look at `tools/sources/weather.py` for the simplest real
example, or `tools/sources/monzo.py` for one with OAuth and dashboard history.

### 2. Register it

In `tools/sources/__init__.py`:

```python
from sources.strava import StravaSource
ALL = [GmailSource, CalendarSource, WeatherSource, MonzoSource, SpotifySource, StravaSource]
```

### 3. Add its settings

- `config.example.yaml`: under `sources:`, add `strava: {enabled: false}` plus any options, with comments.
- `tools/config.py`: add the same block to `DEFAULTS["sources"]` (a test checks the two match).
- `.env.example`: add any secrets, with a comment saying **exactly where to get them**.

### 4. Help people connect it

If it needs a login or a key, add a `step_<name>()` function to `setup.py` that
explains, in beginner-friendly steps, where to click, and then saves the key with
`save_env()`. Look at `step_spotify()` for a short example. If it uses OAuth, put
the login script next to your source (like `sources/spotify_auth.py`) and save
tokens with `config.token_path("<name>.json")`, so they land in the gitignored
`data/tokens/` folder.

### 5. Test it

```bash
python demo.py                 # your demo() data shows up in the sample brief
python -m pytest               # includes checks every source has demo data + config
python setup.py --check        # your problems() show up correctly
python tools/orchestrator.py --no-send   # a real brief with your source, printed not sent
```

### Rules of thumb

- **Never hardcode anything personal**: no names, paths, IDs, cities or timezones.
  Settings go in `config.yaml` and secrets go in `.env`. A test scans for this.
- **Read-only by default.** If your source can *change* things (send, delete, pay),
  route it through `pending_actions.py` so the user gets a cancel window.
- **Ask for the smallest permissions** the API offers, and explain each one in setup.
- **Fail loudly, not silently.** Raise with a message that says how to fix it.
- **Keep dependencies light.** Prefer `requests` over a big SDK where it's easy.

## Other contributions

Bug fixes, docs, dashboard improvements and new chat actions are all welcome.
Please run `python -m pytest` before opening a pull request, and keep the tone of
user-facing text friendly and plain-English.

By contributing you agree your work is released under the [MIT License](LICENSE).
