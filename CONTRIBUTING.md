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

## Running Rubico on your own computer (for development)

People *use* Rubico on Railway ([guide](docs/deploy-railway.md)), but you can develop
and test everything locally. You need Python 3.10+:

```bash
git clone https://github.com/YOUR-USERNAME/rubico-ai.git && cd rubico-ai
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt pytest

python demo.py        # fake data: a sample brief, the dashboard and a Telegram-style chat
python -m pytest      # the tests, no keys needed

# the real thing, exactly like on Railway (data goes in ./data, which git ignores)
DASHBOARD_PASSWORD=dev PORT=8080 python run.py
# then open http://localhost:8080/setup (any username, password "dev")
```

Google, Monzo and Spotify sign-ins also work locally: add the `http://localhost:8080/...`
callback address shown on the setup page to your developer app.

## Adding a data source (step by step)

Every source is one file in `tools/sources/` and follows the same interface
(`tools/sources/base.py`):

| Method | Required? | What it does |
|---|---|---|
| `fetch()` | ✅ | Gets today's real data. **Raise an exception** if something is wrong. The core catches it, keeps the rest of the brief, and tells the user how to fix it. |
| `demo()` | ✅ | Returns realistic but **fake** data in exactly the same shape as `fetch()`. This powers `demo.py` and the tests. |
| `format(data)` | ✅ | Turns that data into plain text for Claude, starting with a `--- Title ---` line. |
| `problems()` | optional | Lists what's missing (keys, logins). The default checks `env_vars`. |
| `broken_parts(data)` | optional | For multi-account sources, reports which accounts failed. |
| `collect(store, log)` | optional | Saves day-by-day numbers for dashboard charts. |
| `demo_history(dates)` | optional | Fake dashboard history for demo mode. |

Plus a few attributes: `name` (its config key), `title`, `description`
(shown on the setup page), `env_vars` (secret keys it needs) and `setup_card` (the
setup-page card that fixes it when it breaks. The brief links straight to it).

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
- `.env.example`: list any secret keys, with a comment saying **exactly where to get them**.

### 4. Help people connect it

If it needs a key or a login, add a card for it to `tools/web_setup.py` (the
`/setup` page). Copy `_spotify_card()` and `act_spotify_client()`: explain, in
beginner-friendly steps, where to click, then save keys with `config.save_secret()`.
If it uses OAuth, put the login helpers next to your source (like
`sources/spotify_auth.py`), send people back to `/setup/<name>/callback`, and save
tokens with `config.token_path("<name>.json")` so they land on the user's volume.

### 5. Test it

```bash
python demo.py                 # your demo() data shows up in the sample brief
python -m pytest               # includes checks every source has demo data + config
DASHBOARD_PASSWORD=dev PORT=8080 python run.py   # connect it on /setup, then text /brief
```

### Rules of thumb

- **Never hardcode anything personal**: no names, paths, IDs, cities or timezones.
  Settings go in `config.yaml` and secrets are saved through the setup page. A test scans for this.
- **Read-only by default.** If your source can *change* things (send, delete, pay),
  route it through `pending_actions.py` so the user gets a cancel window.
- **Ask for the smallest permissions** the API offers, and explain each one on its setup card.
- **Fail loudly, not silently.** Raise with a message that says how to fix it.
- **Keep dependencies light.** Prefer `requests` over a big SDK where it's easy.

## Other contributions

Bug fixes, docs, dashboard improvements and new chat actions are all welcome.
Please run `python -m pytest` before opening a pull request, and keep the tone of
user-facing text friendly and plain-English.

By contributing you agree your work is released under the [MIT License](LICENSE).
