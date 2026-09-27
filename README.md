# Rubico ☀️

**Your own AI morning brief and assistant on Telegram, running on your own computer.**

Every morning Rubico reads your email, calendar, bank, music and the weather.
Claude turns all of that into a short brief telling you what actually matters today,
and Rubico sends it to you on Telegram. During the day you can text Rubico to ask
questions, draft email replies, clear out junk mail, search the web, or save a
reminder for later. A web dashboard keeps a history of every brief and your data.

![Rubico dashboard (demo data)](docs/dashboard.png)

> **Fully open source and self-hosted.** Rubico has no server and no account.
> It runs on your machine using your own API keys, and your data never passes
> through anyone else, including the people who wrote this code. [More on privacy ↓](#-privacy--safety)

---

## What it does

| | |
|---|---|
| ☀️ **Morning brief** | Arrives at a time you choose. Flags emails that need a reply, lists today's events, warns you about rain, sums up yesterday's spending, and ends with one thing to focus on. |
| 💬 **Chat** | "What's on today?" · "Reply to Jordan saying I'm in" · "Delete the login alerts from my bank" · `search who won the f1` |
| 📌 **Notes & reminders** | Text *"remind me tomorrow to submit the form"* and it comes back in tomorrow's brief. `/reminders` lists them and `/cancel 3` removes one. |
| 📊 **Dashboard** | Every brief you've received, your reminders, and charts of spending, listening and weather. |
| 🔌 **Pick your sources** | Gmail, Google Calendar, Monzo, Spotify and weather. Turn each on or off, and use as few as you like. |
| 🛡️ **Safe by default** | Email sends and deletes wait 10 minutes for you to reply `CANCEL`. Deleted mail goes to Gmail's Trash, so you can get it back. |

---

## 🧪 Try it in 1 minute (no accounts needed)

Demo mode uses a fake inbox, calendar, bank account and music history, so you can
see what the brief and dashboard look like before connecting anything real.

```bash
git clone https://github.com/406samay/rubico-ai.git
cd rubico-ai
python -m pip install -r requirements.txt
python demo.py
```

The terminal prints a sample morning brief and the dashboard opens in your browser.
Add `--chat` to try texting the bot right in the terminal (`python demo.py --chat`).
If you already have an Anthropic key in `.env`, Claude writes the demo brief live.

---

## What you need

- **Python 3.10 or newer**. Check with `python --version`. You can get it from [python.org](https://www.python.org/downloads/). On Windows, tick *"Add Python to PATH"* when installing.
- **An Anthropic API key**, so Claude can write your brief. It usually costs a few cents a day.
- **Telegram** on your phone. It's free.
- **Optional:** a Google account (Gmail/Calendar), a UK Monzo account, Spotify.
- A computer that's on in the morning: your laptop, a Raspberry Pi, or a home server.

---

## Setup, step by step

### 1. Download Rubico and install its packages

```bash
git clone https://github.com/406samay/rubico-ai.git
cd rubico-ai

# Optional but recommended: a private "virtual environment" for Rubico's packages
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

python -m pip install -r requirements.txt
```

> On Mac/Linux, if `python` isn't found, type `python3` instead everywhere.

### 2. Run the setup wizard

```bash
python setup.py
```

It walks you through everything, opens the right web pages for you, and checks each
key works before moving on:

1. **Anthropic key.** Create one at [console.anthropic.com](https://console.anthropic.com/settings/keys).
2. **Telegram bot.** Message [@BotFather](https://t.me/BotFather), send `/newbot`, and paste the token. Then press *Start* on your new bot so it knows which chat is yours. You'll get a test message.
3. **About you.** Your name, city (for weather and timezone) and what time the brief should arrive.
4. **Pick data sources.** Say yes or no to each one.
5. **Connect the sources you picked.** Your browser opens so you can log in. For Google, see the next section.

Your answers are saved to `.env` (secrets) and `config.yaml` (settings). Both stay on
your computer and are never uploaded to GitHub.

### 3. Start it

```bash
python run.py
```

That one command runs the Telegram chat, sends the brief every morning, and serves the
dashboard at <http://127.0.0.1:8600>. Leave it running. Text your bot `/help` to see
what it can do, or send a brief right now with:

```bash
python tools/orchestrator.py
```

Check everything is healthy any time with `python setup.py --check`.

---

## 🔐 Connecting Google (Gmail & Calendar), with safety first

`setup.py` walks you through this, but here's what happens and why it's safe.

**You make your own Google "OAuth client".** It's a free key you create in Google
Cloud Console, and it lets *your* copy of Rubico ask Google for access to *your*
account. Because you made it yourself:

- Your login goes **straight from Google to your computer**. There's no Rubico server,
  company or author in the middle.
- The login is saved in `data/tokens/google_<nickname>.json` on your computer only
  (it's gitignored).
- **You can revoke access any time** at [myaccount.google.com/permissions](https://myaccount.google.com/permissions),
  or by deleting that file.

**What Rubico asks Google for, and why:**

| Permission | Used for |
|---|---|
| Read Gmail | Your last 24h of email, for the brief |
| Send Gmail | Replies **you asked for**, after a 10-minute cancel window |
| Modify Gmail | Moving emails **you asked to delete** to Trash (recoverable for 30 days). Rubico never permanently deletes anything. |
| Calendar events | Reading today's events, and adding study review events if you turn that on |

**The steps** (about 5 minutes, once):

1. [Create a project](https://console.cloud.google.com/projectcreate) called "Rubico".
2. Enable the [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com) and/or the [Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com).
3. Set up the [consent screen](https://console.cloud.google.com/auth/branding). App name: *Rubico*, audience: *External*.
4. On [Audience](https://console.cloud.google.com/auth/audience), either add your Gmail address(es) as **test users**, or click **Publish app**. In "Testing" mode Google logs you out every 7 days. Publishing keeps it working and it stays private, because it's your own client.
5. On [Clients](https://console.cloud.google.com/auth/clients), click *Create client*, choose **Desktop app**, and copy the ID and secret into setup.

When you log in, Google shows **"Google hasn't verified this app"**. That's expected,
because the app is *yours* and you haven't asked Google to review it. Click
**Advanced → Go to Rubico (unsafe) → Continue**.

You can connect several Google accounts (e.g. `personal` and `work`). Each one gets a
nickname, and you choose whether each is used for Gmail, Calendar or both.

> **Running on a server with no screen?** Google's login needs a browser on the same
> machine. Run `python setup.py --only google` on your laptop, then copy the
> `data/tokens/` folder to the server.

---

## 🔒 Privacy & safety

- **Nothing is hosted.** Rubico is a set of Python scripts on your computer. There's no
  Rubico account, server or analytics.
- **Where your data goes:** only to Anthropic (Claude reads your data to write the brief.
  Anthropic doesn't train on API data by default), to Telegram (to deliver messages to
  you), and to the services you connect.
- **Secrets stay local.** `.env`, `config.yaml` and `data/` are all in `.gitignore`.
- **The bot only talks to you.** Messages from any chat except your own `TELEGRAM_CHAT_ID` are ignored.
- **The dashboard is private by default.** It only listens on `127.0.0.1`, so only your
  computer can open it. If you open it up to other devices, set `DASHBOARD_PASSWORD`.
- **No surprise actions.** Email sends and deletes are shown to you first and wait
  `review_window_minutes` (default 10) for a `CANCEL`.

---

## Using it

| Text your bot | What happens |
|---|---|
| anything | Answered from your data ("any emails I need to reply to?") |
| `remind me tomorrow to submit the form` | Saved, and comes back in tomorrow's brief |
| `remind me on friday to call Priya` / `in 3 days` / `on 5 oct` | Saved for that day |
| `note to self: buy milk` | No date given, so it shows up in the next brief |
| `/reminders` · `/cancel 3` | List reminders · cancel #3 |
| `reply to Jordan saying yes I'm in` | Drafts it and sends after 10 minutes unless you say `cancel` |
| `delete the promo emails` | Uses Gmail's own Promotions tab, then waits 10 minutes |
| `delete the login alerts from my bank` | Turns that into a Gmail search and shows you what matched first |
| `search <question>` | Live web search |
| `studied <topic>` | Review reminders at 1, 3, 7, 14 and 30 days (if turned on) |
| `/brief` · `/help` | Send the brief now · show help |

---

## Configuration

All settings live in `config.yaml`, and every option is explained in
[`config.example.yaml`](config.example.yaml). Some favourites:

```yaml
briefing:
  time: "07:30"
assistant:
  voice: >
    Dry British humour, very concise, no emoji.
sources:
  spotify:
    enabled: false
```

Restart `run.py` after changing it.

---

## Keeping it running

`run.py` needs to be running for the morning brief to go out. If the computer was
off at brief time, Rubico still sends it when it starts, as long as that's within
`catch_up_minutes` (default 90). Some ways to keep it running:

- **Linux / Raspberry Pi (systemd):** create `/etc/systemd/system/rubico.service`:
  ```ini
  [Unit]
  Description=Rubico
  After=network-online.target

  [Service]
  WorkingDirectory=/home/YOU/rubico
  ExecStart=/home/YOU/rubico/venv/bin/python run.py
  Restart=always
  User=YOU

  [Install]
  WantedBy=multi-user.target
  ```
  Then run `sudo systemctl enable --now rubico`.
- **Mac / Windows:** keep a terminal open with `python run.py`, or add it to your
  login items / Task Scheduler ("At log on").

---

## ➕ Adding a new data source

Each source is one small file in [`tools/sources/`](tools/sources/) with the same few
methods: `fetch()` gets real data, `demo()` returns fake data, and `format()` turns it
into text for Claude. Copy [`tools/sources/_template.py`](tools/sources/_template.py),
fill it in, and register it in `tools/sources/__init__.py`. The full walkthrough is in
[CONTRIBUTING.md](CONTRIBUTING.md). Pull requests for new sources are very welcome!

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Brief says "Couldn't reach Gmail personal" | `python tools/reauth_google.py` |
| "Google hasn't verified this app" | Expected, see [Connecting Google](#-connecting-google-gmail--calendar-with-safety-first) |
| `Error 403: access_denied` from Google | Add that address as a test user (step 4 above) |
| Google logs you out every 7 days | Publish your app on the Audience page (step 4 above) |
| Bot doesn't reply | Is `python run.py` running? Run `python setup.py --check` |
| Monzo transactions missing | Approve access in the Monzo app. Balance still works without it. |
| Anything else | `python setup.py --check` shows what's missing |

**Upgrading from the older JSON-file version?** Run `python tools/migrate_from_json.py`
to move your notes, dashboard history, study topics and Monzo/Spotify logins into the
new database, then `python setup.py` (Google needs one fresh login).

---

## Project layout

```
run.py                 start everything
setup.py               guided setup + health check
demo.py                try it with fake data
config.example.yaml    every setting, explained
.env.example           every secret, with where to get it
tools/                 the scripts that do the work (see CLAUDE.md)
  orchestrator.py        builds and sends the morning brief
  chat_listener.py       Telegram chat, actions and commands
  reminders.py           notes & reminders
  sources/               one file per data source
workflows/             plain-English guides for each job
dashboard/index.html   the dashboard (a single file, no build step)
data/                  your database and logins (created at runtime, gitignored)
```

Tests: `python -m pip install pytest && python -m pytest`

## License

[MIT](LICENSE). Free to use, change and share.
