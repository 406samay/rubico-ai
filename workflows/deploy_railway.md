# Workflow: Run Rubico in the cloud (Railway)

**Objective:** Rubico runs 24/7 without the user's computer, and is set up entirely in a browser (a phone is fine).

**User guide:** `docs/deploy-railway.md` (fork → Railway project → `DASHBOARD_PASSWORD` + `PORT=8080` → volume at `/data` → domain → `/setup`).

**How it works**
- `Dockerfile` builds the image and sets `RUBICO_CLOUD=1`. `railway.json` sets 1 replica, the `/healthz` health check, and restart on failure.
- Server mode (`tools/config.py → is_cloud()`, on unless `RUBICO_CLOUD=0`, which `python run.py --local` sets. See `workflows/run_on_laptop.md`) puts `config.yaml`, `secrets.env` and `rubico.db` on the volume (`RAILWAY_VOLUME_MOUNT_PATH`). It listens on `0.0.0.0:$PORT`, and links use `https://$RAILWAY_PUBLIC_DOMAIN`.
- `run.py` starts the web server first, waits until the essentials (Claude key, bot token, chat ID) exist, then starts the bot. No restart is needed after setup.
- `tools/web_setup.py` serves `/setup`. Keys are saved with `config.save_secret()` (to `secrets.env`, file mode 600). Google, Monzo and Spotify use web logins that return to `/setup/<service>/callback`.

**Safety rules (don't break these)**
- In cloud mode every page except `/healthz` needs `DASHBOARD_PASSWORD`. With no password set, everything is locked (503) with instructions.
- Setup forms need the CSRF token and a same-origin `Origin`/`Referer`. Secrets are never rendered back to the page.
- `/setup` is disabled in demo mode, so it can't overwrite real settings.

**Edge cases**
- No volume: the setup page shows a red warning, and data resets on every deploy.
- Only one running copy per Telegram bot. A second one gets 409 Conflict from `getUpdates`, which the chat loop retries with backoff.
- Google needs a **Web application** OAuth client whose redirect URI exactly matches `https://<domain>/setup/google/callback` (shown on the setup page).
- Test the whole flow locally without Railway: `DASHBOARD_PASSWORD=dev PORT=8080 python run.py` (data goes in `./data`), then open http://localhost:8080/setup. For the laptop version use `python run.py --local`.

**Security measures (keep them)**
- Wrong passwords: 10 from one address → locked out for 15 minutes (`dashboard_server._failures`). On Railway the real address is the *last* `X-Forwarded-For` entry.
- Every response sends `X-Frame-Options: DENY` + `frame-ancestors 'none'` (no clickjacking) and `Referrer-Policy: same-origin`. That policy matters: with `no-referrer`, browsers send `Origin: null` on your own form posts and the same-origin check can't work.
- Form posts with `Origin: null` are refused. The CSRF token is checked as well.
- The Telegram bot token is part of Telegram's URL, so `telegram_bot.call()` blanks it out of every error before it can reach logs or chat.
- `/setup` warns when `DASHBOARD_PASSWORD` is under 10 characters.
- Claude errors (bad key, no credit, rate limit) become plain-English messages with the fix (`llm.friendly_error`).

**How to verify a change end to end (lessons learned)**
- `python -m pytest`: it includes real-path tests against fake Telegram/Claude/Google servers.
- Browser click-through: drive `/setup` with Playwright at phone size (390×844). Wait for the page to load after every click, and click buttons (`button:has-text(...)`), not text: flash messages repeat button names.
- Container: Docker Hub often rate-limits (429) shared build machines. To test locally, build from the identical official mirror `mirror.gcr.io/library/python:3.12-slim` (don't change the real Dockerfile). Then run the tests inside the container, because it installs the newest package versions.
- Only a real deploy can check Railway's own UI, real Telegram delivery, and Monzo/Spotify/Google sign-in with real accounts.
