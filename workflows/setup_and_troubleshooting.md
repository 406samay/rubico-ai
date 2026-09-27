# Workflow: Setup and fixing things

**First-time setup:** `python setup.py`. It's resumable, so re-running keeps what works. Steps: Anthropic key → Telegram bot and chat link → name/city/time → pick sources → connect each (Google, Monzo, Spotify).

**Health check:** `python setup.py --check` (changes nothing, exit code 1 if anything is missing).

**Redo one part:** `python setup.py --only google|telegram|anthropic|basics|sources|monzo|spotify`

**Common fixes**
| Symptom | Cause | Fix |
|---|---|---|
| Brief says a Gmail/Calendar account is unreachable | Google login expired or revoked | `python tools/reauth_google.py` |
| Logged out every 7 days | Google OAuth app still in "Testing" | Publish it on the Audience page in Google Cloud |
| `access_denied` / 403 at Google login | Address not added as a test user | Add it on the Audience page |
| Setup on a headless server can't log in to Google | No browser on that machine | Log in on a laptop, copy `data/tokens/` over |
| Monzo history missing, balance fine | Monzo needs re-approval in the app | Approve in the Monzo app; balance keeps working meanwhile |
| Spotify gaps on the dashboard | More than 50 plays between polls | Lower `metrics.collect_every_minutes` |

**Upgrading from the old JSON-file version:** `python tools/migrate_from_json.py --from <old folder>`, then `python setup.py --only google`.
