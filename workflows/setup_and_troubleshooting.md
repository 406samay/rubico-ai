# Workflow: Setup and fixing things

**Where setup happens:** only on the `/setup` web page (`tools/web_setup.py`), usually on the user's Railway server. There's no terminal setup.
- **Getting it running:** `docs/deploy-railway.md` (fork → Railway → `DASHBOARD_PASSWORD` + `PORT=8080` → volume at `/data` → domain).
- **Cards, in order:** Claude key → Telegram bot + chat link → about you (city gives timezone and currency) → data sources → personality → Google / Monzo / Spotify (only shown when switched on).
- **Starting the bot:** `run.py` starts it by itself once the Claude key, bot token and chat link exist. No restart needed.
- **Changing anything later:** the same page (the ⚙️ button on the dashboard).

**Common fixes**
| Symptom | Cause | Fix |
|---|---|---|
| Brief says a Gmail/Calendar account is unreachable | Google login expired or revoked | The brief links to `/setup#google`. Sign in with Google again there |
| Logged out every 7 days | Google OAuth app still in "Testing" | Publish it on the Audience page in Google Cloud |
| `access_denied` / 403 at Google login | App unpublished and address not a test user | Publish the app, or add the address as a test user |
| `redirect_uri_mismatch` | Google client missing the callback | Add the exact address shown on the Google card, on a **Web application** client |
| Page says it needs a password (503) | `DASHBOARD_PASSWORD` not set | Add it in Railway → Variables |
| Settings vanish after an update | No volume attached | Add a volume at `/data` |
| "Couldn't check Telegram" when linking | Another copy of Rubico is using the same bot | Only one running copy per bot |
| Monzo history missing, balance fine | Monzo needs re-approval in the app | Approve in the Monzo app. Balance keeps working meanwhile |
| Spotify gaps on the dashboard | More than 50 plays between polls | Lower `metrics.collect_every_minutes` |

**For developers:** run it locally exactly like on Railway with `DASHBOARD_PASSWORD=dev PORT=8080 python run.py`, then open http://localhost:8080/setup (see `CONTRIBUTING.md`).
