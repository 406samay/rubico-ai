# Workflow: Run Rubico in the cloud (Railway)

**Objective:** Rubico runs 24/7 without the user's computer, and is set up entirely in a browser (a phone is fine).

**User guide:** `docs/deploy-railway.md` (fork → Railway project → `DASHBOARD_PASSWORD` + `PORT=8080` → volume at `/data` → domain → `/setup`).

**How it works**
- `Dockerfile` builds the image and sets `RUBICO_CLOUD=1`. `railway.json` sets 1 replica, the `/healthz` health check, and restart on failure.
- Server mode (`tools/config.py → is_cloud()`, on unless a developer sets `RUBICO_CLOUD=0`) puts `config.yaml`, `secrets.env` and `rubico.db` on the volume (`RAILWAY_VOLUME_MOUNT_PATH`). It listens on `0.0.0.0:$PORT`, and links use `https://$RAILWAY_PUBLIC_DOMAIN`.
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
- Test the whole flow locally without Railway: `DASHBOARD_PASSWORD=dev PORT=8080 python run.py` (data goes in `./data`), then open http://localhost:8080/setup.
