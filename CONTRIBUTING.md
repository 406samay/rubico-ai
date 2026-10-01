# Contributing to Rubico

Thanks for helping. The most useful thing you can add is a new data source, like Strava, Todoist, GitHub, Notion, Outlook, Apple Health exports, other banks, news or stocks. Every new source makes the morning brief more useful for someone. Beginners are welcome, and if you get stuck, open a draft pull request and ask.

## How the project is organised

Rubico follows the WAT pattern described in [CLAUDE.md](CLAUDE.md). Workflows in `workflows/*.md` are plain English instructions for each job. The agent is Claude, which decides what to do and writes the words. Tools in `tools/*.py` are plain Python that does the actual work, like API calls, the database and sending messages.

Data sources are tools. They fetch facts and hand plain text to Claude, and they shouldn't try to be clever, because Claude does the thinking.

## Running Rubico on your own computer

People use Rubico on Railway (see the [guide](docs/deploy-railway.md)) or on their own computer, and you can build and test everything on yours. You need Python 3.10 or newer.

```bash
git clone https://github.com/YOUR-USERNAME/rubico-ai.git
cd rubico-ai
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt pytest

python demo.py          # fake data, with a sample brief, the dashboard and a Telegram style chat
python -m pytest        # the tests, no keys needed
python run.py --local   # the real thing on this computer, then open the setup page it prints
```

On Windows, activate the environment with `.venv\Scripts\activate` instead. In `--local` mode your settings go in `.env`, `config.yaml` and `data/` next to the code, and git ignores all three. The setup page opens at `http://127.0.0.1:8600/setup` and needs no password, because only your computer can reach it. Google, Monzo and Spotify sign ins work there too, as long as you add the callback address shown on the setup page to your developer app.

To check the Railway style of running, set `DASHBOARD_PASSWORD=dev` and `PORT=8080`, and run `python run.py` without `--local`. Then open `http://localhost:8080/setup` with any username and the password `dev`.

## Adding a data source

Every source is one file in `tools/sources/` and follows the same interface, which lives in `tools/sources/base.py`.

Three methods are required. `fetch()` gets today's real data, and it should raise an exception if something is wrong, because the core catches it, keeps the rest of the brief and tells the user how to fix it. `demo()` returns realistic but fake data in the same shape as `fetch()`, and it powers `demo.py` and the tests. `format(data)` turns that data into plain text for Claude, starting with a `--- Title ---` line.

Four more are optional. `problems()` lists what's missing, like keys or logins, and the default checks `env_vars`. `broken_parts(data)` reports which accounts failed for sources with several accounts. `collect(store, log)` saves day by day numbers for the dashboard charts. `demo_history(dates)` gives fake dashboard history for demo mode.

A source also needs a few attributes. These are `name` (its config key), `title`, `description` (shown on the setup page), `env_vars` (the secret keys it needs) and `setup_card`, which is the setup page card that fixes it when it breaks. The brief links straight to that card.

### 1. Copy the template

```bash
cp tools/sources/_template.py tools/sources/strava.py
```

Fill in every `TODO`. `tools/sources/weather.py` is the simplest real example, and `tools/sources/monzo.py` is one with OAuth and dashboard history.

### 2. Register it

In `tools/sources/__init__.py`, add your source to the list.

```python
from sources.strava import StravaSource
ALL = [GmailSource, CalendarSource, WeatherSource, MonzoSource, SpotifySource, StravaSource]
```

### 3. Add its settings

In `config.example.yaml`, add `strava: {enabled: false}` under `sources:` along with any options, and comment them. Add the same block to `DEFAULTS["sources"]` in `tools/config.py`, because a test checks the two match. Then list any secret keys in `.env.example`, with a comment saying where to get them.

### 4. Help people connect it

If it needs a key or a login, add a card for it to `tools/web_setup.py`, which is the setup page. Copy `_spotify_card()` and `act_spotify_client()`, explain in simple steps where to click, and save keys with `config.save_secret()`. If it uses OAuth, put the login helpers next to your source, like `sources/spotify_auth.py`, send people back to `/setup/<name>/callback`, and save tokens with `config.token_path("<name>.json")` so they land on the user's own storage.

### 5. Test it

```bash
python demo.py          # your demo() data shows up in the sample brief
python -m pytest        # checks every source has demo data and config
python run.py --local   # connect it on the setup page, then text /brief
```

## A few rules

Never hardcode anything personal, like names, paths, IDs, cities or timezones. Settings go in `config.yaml` and secrets are saved through the setup page, and a test scans for this.

Keep sources read only by default. If yours can change things, like sending, deleting or paying, route it through `pending_actions.py` so the user gets a cancel window.

Ask for the smallest permissions the API offers, and explain each one on its setup card. Fail loudly and not silently, with a message that says how to fix the problem. Keep dependencies light, and prefer `requests` over a big SDK where you can.

## Other contributions

Bug fixes, docs, dashboard improvements and new chat actions are all welcome. Every pull request is checked automatically on Windows, Mac and Linux by the files in `.github/workflows/`, and you can run the same tests yourself with `python -m pytest`. You can also try the laptop start file with `python tests/smoke_start_file.py` in a fresh copy of the project. Keep any text users see friendly and in plain English, and never print a key, a token or a login link that holds one, because server logs are kept for days.

By contributing you agree your work is released under the [MIT License](LICENSE).
