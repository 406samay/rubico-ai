# Rubico ☀️

**Your own AI assistant that texts you a morning brief, and lets you text it back.**

Every morning Rubico reads your email, calendar, bank, music and the weather, and
Claude turns it into a short brief on **Telegram**: what needs a reply, what's on today,
and the one thing worth focusing on. Text it all day to ask questions, reply to emails
or set reminders. Everything also lands on a private **dashboard** you can look back through.

<table>
<tr>
<th width="36%">💬 On Telegram: use it every day</th>
<th>📊 On the dashboard: look back and spot patterns</th>
</tr>
<tr>
<td valign="top"><img src="docs/telegram.png" alt="Rubico's morning brief and reminders in a Telegram chat (demo data)"></td>
<td valign="top"><img src="docs/dashboard.png" alt="Rubico dashboard with brief history, reminders and charts (demo data)"></td>
</tr>
</table>

> **Fully open source and self-hosted.** No Rubico company server, no account, no tracking.
> It runs on your computer, or on your own private cloud server, with your own keys.
> Nobody else sees your data, including the people who wrote this code.
> [Privacy details ↓](#-privacy--safety)

---

## 🚀 Get started: pick where Rubico runs

Rubico needs to be running somewhere to send your morning brief. Choose one:

| | ☁️ **In the cloud** | 💻 **On your computer** |
|---|---|---|
| Needs a computer left on? | No | Yes, at brief time |
| Set up from your phone? | ✅ Yes, all in the browser | Needs a computer |
| Cost | Hosting ≈ $5/month ([Railway](https://railway.com/pricing)) | Free |
| Where your data lives | Your own private server | Only your computer |
| Guide | **[Deploy to Railway →](docs/deploy-railway.md)** | Below ↓ |

Either way you get the same Rubico: the Telegram assistant, the dashboard and every data
source. Claude usage costs a few cents a day with both.

### 💻 On your computer

1. **Install Python 3.10+** from [python.org/downloads](https://www.python.org/downloads/).
   On Windows, tick **"Add python.exe to PATH"** in the installer.
2. **Download Rubico:** click the green **Code** button above, then **Download ZIP**, and unzip it.
   (Or `git clone https://github.com/406samay/rubico-ai.git`.)
3. **Double-click the start file** in the folder:

   | Windows | Mac | Linux |
   |---|---|---|
   | `start.bat` | `start.command` (first time: right-click → Open) | run `./start.sh` in a terminal |

The first time, it installs what it needs (about a minute) and asks what you'd like to do:

- **1) Try the demo.** It uses fake data and needs no accounts. A Telegram-style chat and the
  dashboard open in your browser, so you can read a sample brief and text the bot
  ("remind me tomorrow to…", `/reminders`).
- **2) Set up Rubico.** The **Quick** setup takes about 3 minutes: Claude + Telegram + your city.
  That already gets you the morning brief, weather, reminders, web search and the dashboard.
  Connect Gmail, Calendar, your bank or Spotify whenever you like, later.

After that, the same start file simply starts Rubico. Leave it running.

<details>
<summary>Prefer the terminal?</summary>

```bash
git clone https://github.com/406samay/rubico-ai.git
cd rubico-ai
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt

python demo.py        # try it with fake data
python setup.py       # set it up for real
python run.py         # start it (leave running)
```
On Mac/Linux, use `python3` if `python` isn't found.
</details>

---

## 💬 Telegram: your daily assistant

Your morning brief arrives at the time you choose. Reply to it like you'd text a friend:

| Text your bot | What happens |
|---|---|
| *"any emails I need to reply to?"* | Answered from your data |
| *"remind me tomorrow to submit the form"* | Saved, and shows up in tomorrow's brief |
| *"remind me on friday to call Priya"* / *"in 3 days"* / *"on 5 oct"* | Saved for that day |
| *"note to self: buy milk"* | No date given, so it shows up in your next brief |
| `/reminders` · `/cancel 3` | List reminders · cancel #3 |
| *"reply to Jordan saying yes I'm in"* | Drafts it and sends after 10 minutes unless you say `cancel` |
| *"delete the promo emails"* | Uses Gmail's own Promotions tab, then waits 10 minutes |
| *"delete the login alerts from my bank"* | Finds matching emails and shows them to you first |
| `search <question>` | Live web search |
| `studied <topic>` | Review reminders at 1, 3, 7, 14 and 30 days (optional) |
| `/brief` · `/help` | Send the brief now · show everything it can do |

Tap the **menu button** next to the message box in Telegram to see the commands.
Your bot only ever replies to *you*. Messages from anyone else are ignored.

## 📊 Dashboard: your history at a glance

Go to <http://127.0.0.1:8600> on the computer running Rubico. Want it on your **phone**
too? Say yes when setup asks, and the dashboard opens on your home Wi-Fi with a password.
The link at the bottom of every brief then works from your phone.

- **Every morning brief you've received.** Flick the day strip to reread any day.
- **Your reminders**, and when each one will come back.
- **Charts** for spending, listening and weather over 7, 30 or 90 days, plus patterns like
  *"you spend £17 more on rainy days"*.
- An **Open chat** button that jumps straight to your bot in Telegram.

It's private by default, so only your own computer can open it (see [Privacy](#-privacy--safety)).
Using [Tailscale](https://tailscale.com)? Set `dashboard.host` to your Tailscale IP to open
it from anywhere.

---

## ✨ What it can connect to

Pick any mix. Everything is optional except Claude and Telegram.

| Source | Adds to your brief | Needs |
|---|---|---|
| 🌦️ Weather | Today's forecast | Nothing, it's free and on by default |
| 📧 Gmail | Emails that need a reply; lets you reply and clean up by chat | A Google account ([safe setup ↓](#-connecting-google-gmail--calendar-with-safety-first)) |
| 📅 Google Calendar | Today's events | A Google account |
| 🏦 Monzo | Balance and yesterday's spending | A UK Monzo account |
| 🎧 Spotify | What you've been listening to | A Spotify account |

Add or change sources any time: `python setup.py --add`. Want another one, like Strava,
Todoist or Outlook? [Add it!](#-adding-a-new-data-source)

---

## 🔐 Connecting Google (Gmail & Calendar), with safety first

`python setup.py --add` walks you through this step by step, with the right pages opened
for you. Here's what happens and why it's safe.

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

- **Nothing is hosted by us.** Rubico is a set of Python scripts that run on your computer,
  or on a cloud server *you* rent in *your* account. There's no Rubico account, company
  server or analytics.
- **Where your data goes:** only to Anthropic (Claude reads your data to write the brief.
  Anthropic doesn't train on API data by default), to Telegram (to deliver messages to
  you), and to the services you connect.
- **Secrets stay local.** `.env`, `config.yaml` and `data/` are all in `.gitignore`.
- **The bot only talks to you.** Messages from any chat except your own `TELEGRAM_CHAT_ID` are ignored.
- **The dashboard is private by default.** On your computer it only listens on `127.0.0.1`,
  so only that computer can open it. In the cloud it always needs your `DASHBOARD_PASSWORD`,
  and setup forms only accept requests from your own page.
- **No surprise actions.** Email sends and deletes are shown to you first and wait
  `review_window_minutes` (default 10) for a `CANCEL`.

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

Don't want to keep a computer on? [Run it on Railway instead](docs/deploy-railway.md).

`run.py` needs to be running for the morning brief to go out. If the computer was
off at brief time, Rubico still sends it when it starts, as long as that's within
`catch_up_minutes` (default 90). Some ways to keep it running:

- **Linux / Raspberry Pi (systemd):** create `/etc/systemd/system/rubico.service`:
  ```ini
  [Unit]
  Description=Rubico
  After=network-online.target

  [Service]
  WorkingDirectory=/home/YOU/rubico-ai
  ExecStart=/home/YOU/rubico-ai/.venv/bin/python run.py
  Restart=always
  User=YOU

  [Install]
  WantedBy=multi-user.target
  ```
  Then run `sudo systemctl enable --now rubico`.
- **Mac / Windows:** keep the start file's window open. To start it automatically, add
  `start.command` to *System Settings → General → Login Items* (Mac), or put a shortcut to
  `start.bat` in your Startup folder (Windows: press Win+R and type `shell:startup`).

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
| Running on Railway? | See the [cloud troubleshooting table](docs/deploy-railway.md#troubleshooting). Logins are fixed from your `/setup` page |

**Upgrading from the older JSON-file version?** Run `python tools/migrate_from_json.py`
to move your notes, dashboard history, study topics and Monzo/Spotify logins into the
new database, then `python setup.py` (Google needs one fresh login).

---

## Project layout

```
start.bat / .command / .sh   double-click to start (installs everything first time)
run.py                 start everything
setup.py               guided setup (--add for more sources, --check for health)
Dockerfile, railway.json   how it runs in the cloud (docs/deploy-railway.md)
demo.py                try it with fake data (chat + dashboard in your browser)
config.example.yaml    every setting, explained
.env.example           every secret, with where to get it
tools/                 the scripts that do the work (see CLAUDE.md)
  orchestrator.py        builds and sends the morning brief
  chat_listener.py       Telegram chat, actions and commands
  reminders.py           notes & reminders
  sources/               one file per data source
workflows/             plain-English guides for each job
dashboard/             the dashboard + the demo chat page (single files, no build step)
tools/web_setup.py     setup in the browser (/setup), used in the cloud
data/                  your database and logins (created at runtime, gitignored)
```

Tests: `python -m pip install pytest && python -m pytest`

## License

[MIT](LICENSE). Free to use, change and share.
