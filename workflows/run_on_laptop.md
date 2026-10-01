# Workflow: Run Rubico on the user's own computer

**Objective:** the free option for people who don't want Railway. Same setup page and same bot, but it only works while the computer is on and awake at brief time. Railway is the recommended way for a daily brief.

**User guide:** the "Run it on your own computer" section of `README.md`. They double click `start.bat` (Windows), `start.command` (Mac) or run `./start.sh` (Linux). The first run makes `.venv`, installs `requirements.txt`, then starts `python run.py --local` and opens `http://127.0.0.1:8600/setup`. `start.bat demo` or `./start.sh demo` runs `demo.py` with fake data.

**How it works**
- `run.py --local` sets `RUBICO_CLOUD=0` before `tools/config.py` is imported. `config.is_local()` is true (not cloud, not demo).
- Local mode keeps `config.yaml`, `.env` and `data/` next to the code (all gitignored). The dashboard listens on `127.0.0.1:8600` only, and needs no password.
- `run.py` opens the setup page in the browser and waits until the Claude key, bot token and chat ID exist, then starts the bot. `RUBICO_NO_BROWSER=1` stops the browser opening (the tests and GitHub checks set it). `RUBICO_NO_PAUSE=1` stops `start.bat` waiting for a key press.
- The setup page builds its Google, Spotify and Monzo callback addresses from the browser's address, so on a laptop they start with `http://127.0.0.1:8600`. Spotify only accepts `127.0.0.1`, not `localhost`, so `config.local_setup_url()` always uses it.

**Safety rules (don't break these)**
- In local mode the dashboard only answers to the names `127.0.0.1`, `localhost` and `::1` (`Handler._host_ok`). That blocks DNS rebinding, where a website points its own name at 127.0.0.1 to read the dashboard. It must not apply in cloud mode, where Railway's own address is the Host.
- Never bind the laptop dashboard to `0.0.0.0` without `DASHBOARD_PASSWORD`.
- `make_server(port=0)` means any free port. Tests rely on that, so don't treat 0 as "use the default".

**Edge cases**
- Catch up: if the computer was off at brief time, the brief still goes out when Rubico starts, within `briefing.catch_up_minutes` (90). After that the day is skipped.
- `.gitattributes` pins `*.sh` and `*.command` to LF and `*.bat` to CRLF. A Windows checkout with the wrong endings breaks the Mac and Linux start files.
- Windows needs the `tzdata` package (it's in `requirements.txt`), or time zone lookups fail and the brief could go out at the wrong time.

**Checks that must pass (GitHub, `.github/workflows/tests.yml`)**
- `python -m pytest` on Ubuntu, Windows and macOS with Python 3.10, 3.12 and 3.13.
- `python tests/smoke_start_file.py` on each system. It runs the real start file in a fresh folder, checks the first visit goes to `/setup`, a foreign Host name gets 403, and the port closes when it's stopped. Run it only in a fresh copy, because it creates and removes `config.yaml`.
- The Railway container: build the `Dockerfile`, run it with `PORT`, `DASHBOARD_PASSWORD` and a volume, check `/healthz`, the password and `/setup`, then `docker stop` must exit 0 in under 8 seconds.
