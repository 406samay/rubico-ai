# Rubico

Rubico is your own AI assistant that texts you a morning brief, and lets you text it back.

Every morning it reads your email, calendar, bank, music and the weather, and Claude turns it into a short brief on Telegram. It tells you what needs a reply, what's on today and the one thing worth focusing on. You can text it through the day to ask questions, reply to emails or set reminders, and everything also lands on a private dashboard so you can look back through it.

<table>
<tr>
<th width="36%">On Telegram, for every day</th>
<th>On the dashboard, to look back and spot patterns</th>
</tr>
<tr>
<td valign="top"><img src="docs/telegram.png" alt="Rubico's morning brief and reminders in a Telegram chat (demo data)"></td>
<td valign="top"><img src="docs/dashboard.png" alt="Rubico dashboard with brief history, reminders and charts (demo data)"></td>
</tr>
</table>

Rubico is open source and self hosted. There's no Rubico company, account or tracking. It runs in your own Railway account, or on your own computer, with your own keys, so nobody else sees your data, including the people who wrote it. More on that in [Privacy](#privacy).

## Where Rubico runs

Rubico only works while it's running, so it needs somewhere to live, and there are two ways to do it.

The best way is Railway, which rents you a small private server for about $5 a month. Your brief arrives every morning even when your laptop is shut, and you can set the whole thing up from your phone in about 15 minutes, with no coding and no terminal.

The other way is your own computer. That's free and good for trying Rubico out, but the brief only goes out while the computer is on and awake at brief time. If it was off, Rubico still sends the brief when it starts, as long as that's within 90 minutes of the time you chose, and after that it skips the day.

Either way, Claude writes the brief, so you'll need an Anthropic API key from [console.anthropic.com](https://console.anthropic.com/settings/keys). You add a few dollars of credit there, which goes to Anthropic and not to Rubico, and a daily brief usually costs a few cents.

## Run it on Railway

You'll need a free [GitHub](https://github.com) account, the Telegram app, your Anthropic API key and a [Railway](https://railway.com) account, which costs about $5 a month (see their [pricing](https://railway.com/pricing)).

Start by forking this repo with the Fork button at the top of this page. Then on Railway choose New Project, then Deploy from GitHub repo, and pick your fork. Add two variables, `DASHBOARD_PASSWORD` set to a password you choose and `PORT` set to `8080`. Add a volume at `/data` so your settings survive updates, and generate a domain. Then open your new address with `/setup` on the end and follow the cards, which ask for your Claude key, your Telegram bot, your city and the data sources you want.

As soon as the Claude key and Telegram are done, Rubico starts by itself, so text your bot `/help` and you're up and running.

The full guide has screenshots and fixes for the usual problems, and it's in [docs/deploy-railway.md](docs/deploy-railway.md).

<img src="docs/web-setup.png" alt="Rubico's setup page on a phone" width="300">

## Run it on your own computer

You'll need Python 3.10 or newer from [python.org/downloads](https://www.python.org/downloads/). On Windows, tick "Add python.exe to PATH" in the installer. Then click the green Code button above, choose Download ZIP and unzip it. If you'd rather use git, you can clone `https://github.com/406samay/rubico-ai.git` instead.

Open the folder and double click the start file for your system. That's `start.bat` on Windows, `start.command` on Mac (the first time, right click it and choose Open) and `./start.sh` in a terminal on Linux.

The first run installs what it needs, which takes about a minute. Then it asks whether you'd rather run Rubico on Railway or on this computer. If you type 1 it opens the Railway guide and stops, and if you type 2 it carries on and remembers your answer, so it only asks once. It then opens the setup page in your browser at `http://127.0.0.1:8600/setup`. It's the same page you get on Railway, with the same cards. Everything you enter is saved next to the code, in `.env`, `config.yaml` and the `data` folder, and none of it is ever uploaded to GitHub. The page only opens on your own computer, so it doesn't ask for a password. If you want to open it yourself later, use `127.0.0.1` and not `localhost`, because Spotify only accepts that address.

After setup, the same start file just starts Rubico, so leave its window open. To see Rubico with fake data first, with no accounts at all, run `start.bat demo` on Windows or `./start.sh demo` on Mac and Linux.

You can make Rubico start by itself when you log in. On Mac, add `start.command` to System Settings, General, Login Items. On Windows, put a shortcut to `start.bat` in your Startup folder, which you can open by pressing Win+R and typing `shell:startup`. The computer still has to be on at brief time though, so for a daily brief Railway is the better choice.

<details>
<summary>Prefer the terminal?</summary>

```bash
git clone https://github.com/406samay/rubico-ai.git
cd rubico-ai
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python demo.py          # try it with fake data
python run.py --local   # run it on this computer
```

On Windows, activate the environment with `.venv\Scripts\activate` instead. On Mac or Linux, use `python3` if `python` isn't found.
</details>

## Telegram

Your morning brief arrives at the time you choose, and you reply to it like you'd text a friend. Ask "any emails I need to reply to?" and it answers from your data. Say "remind me tomorrow to submit the form", or "remind me on friday to call Priya", "in 3 days" or "on 5 oct", and it's saved for that day. A note with no date, like "note to self, buy milk", turns up in your next brief. Send `/reminders` to see them all and `/cancel 3` to cancel number three.

It can handle email too. "Reply to Jordan saying yes I'm in" drafts the reply and sends it after ten minutes unless you say `cancel`. "Delete the promo emails" uses Gmail's own Promotions tab and waits ten minutes as well, and "delete the login alerts from my bank" finds the matching emails and shows them to you first. Send `search` followed by a question for a live web search, or `studied` followed by a topic to get review reminders after 1, 3, 7, 14 and 30 days. `/brief` sends the brief now and `/help` shows everything it can do.

The menu button next to the message box in Telegram lists the commands. Your bot only ever replies to you, and messages from anyone else are ignored.

## Dashboard

On Railway, open your web address, or tap the link at the bottom of any brief. It works on your phone or in any browser, and it's protected by your password. On your own computer, go to `http://127.0.0.1:8600`.

It keeps every morning brief you've received, with a day strip you can flick back through, plus your reminders and when each one will come back. There are charts for spending, listening and weather over 7, 30 or 90 days, and they pick out patterns like "you spend £17 more on rainy days". An Open chat button jumps straight to your bot in Telegram, and the Settings button lets you change anything you set up.

## What it connects to

Everything is optional except Claude and Telegram, and you pick what you want on the setup page. Weather is free and on by default. Gmail adds emails that need a reply and lets you reply and clean up by chat, and Google Calendar adds today's events, and both need a Google account. Monzo adds your balance and yesterday's spending and needs a UK Monzo account. Spotify adds what you've been listening to and needs a Spotify account.

You can also set Rubico's personality on the setup page, which covers how it talks, how it writes your email replies and how long the brief is. If you want another source, like Strava, Todoist or Outlook, see [Contributing](#contributing).

## Google

The Google card on your setup page walks you through this and shows the exact address to copy. Here's what happens and why it's safe.

You make your own Google OAuth client, which is a free key you create in Google Cloud Console. It lets your copy of Rubico ask Google for access to your account. Because you made it yourself, your login goes straight from Google to your own Rubico, with no company or author in the middle. The login is saved on your own storage and nowhere else. You can revoke access any time at [myaccount.google.com/permissions](https://myaccount.google.com/permissions), or with the Remove button on the setup page.

Rubico asks Google for four permissions. Read Gmail lets it see your last 24 hours of email for the brief. Send Gmail is for replies you asked for, after a ten minute cancel window. Modify Gmail is for moving emails you asked to delete into Trash, where they stay recoverable for 30 days, and Rubico never permanently deletes anything. Calendar events lets it read today's events, and add study review events if you turn that on.

The setup takes about five minutes and you only do it once. First, [create a project](https://console.cloud.google.com/projectcreate) called Rubico. Then enable the [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com) and the [Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com), depending on which you want. Next, set up the [consent screen](https://console.cloud.google.com/auth/branding) with the app name Rubico and the audience set to External. On the [Audience](https://console.cloud.google.com/auth/audience) page, click Publish app. If you add yourself as a test user instead, Google logs you out every 7 days. Last, on the [Clients](https://console.cloud.google.com/auth/clients) page, click Create client and choose Web application. Under Authorized redirect URIs, add the address your setup page shows, then paste the Client ID and secret into the Google card.

When you sign in, Google will say "Google hasn't verified this app". That's expected, because the app is yours and you haven't asked Google to review it. Tap Advanced, then Go to Rubico, then Continue. You can connect several Google accounts, like personal and work, and each one gets a nickname and can be used for Gmail, Calendar or both.

## Privacy

Nothing is hosted for you. There's no Rubico account, company server or analytics. If you use Railway, Railway runs the machine in your own account, like any cloud service. If you use your own computer, your data never leaves it except as described below.

Your data only goes to three places. It goes to Anthropic, because Claude reads it to write the brief (and Anthropic doesn't train on API data by default). It goes to Telegram, so it can deliver your messages. And it goes to the services you connect.

On Railway, every page needs your `DASHBOARD_PASSWORD`, and the setup forms only accept requests from your own page. On your own computer, the dashboard only listens on `127.0.0.1`, so only that computer can open it, and it refuses requests from other website names. Keys you paste are saved on your own storage and are never shown back on the page. Your Telegram bot token is also kept out of the logs. The bot only talks to you, so messages from any other chat are ignored. There are no surprise actions either, because email sends and deletes are shown to you first and wait ten minutes for a `CANCEL`.

## Updating

On Railway, open your fork on GitHub and tap Sync fork, then Update branch. Railway rebuilds by itself, and your settings and logins stay on the volume. On your own computer, download the newest ZIP and copy your `.env`, `config.yaml` and `data` folder into it, or run `git pull` if you used git.

## Contributing

Each data source is one small file in [`tools/sources/`](tools/sources/) with the same few methods. `fetch()` gets real data, `demo()` returns fake data and `format()` turns it into text for Claude. Copy [`tools/sources/_template.py`](tools/sources/_template.py), fill it in and register it in `tools/sources/__init__.py`. The full walkthrough is in [CONTRIBUTING.md](CONTRIBUTING.md), and pull requests for new sources are welcome. Every pull request is checked automatically on Windows, Mac and Linux, so you'll see quickly if something needs fixing.

## Troubleshooting

If the brief says it couldn't reach Gmail, tap the link in the brief to open your setup page and sign in with Google again. The "Google hasn't verified this app" message is expected, so see [Google](#google). If Google logs you out every 7 days, publish your app on Google Cloud's Audience page. If the bot doesn't reply, check that Rubico is running. On Railway that means the deployment is Active, and on your computer it means the start file's window is still open. If Monzo transactions are missing, approve access in the Monzo app, and your balance will still work without it. The [Railway guide](docs/deploy-railway.md) has a longer list of fixes that covers most other problems.

## Project layout

```
start.bat, .command, .sh   double click to run on your own computer
run.py                     starts everything, the web page, the bot and the morning brief
Dockerfile, railway.json   how Railway builds and runs Rubico
docs/deploy-railway.md     the Railway guide
tools/                     the scripts that do the work, see CLAUDE.md
  web_setup.py             the setup page
  orchestrator.py          builds and sends the morning brief
  chat_listener.py         Telegram chat, actions and commands
  reminders.py             notes and reminders
  sources/                 one file per data source
workflows/                 plain English guides for each job
dashboard/                 the dashboard page, one file with no build step
config.example.yaml        every setting, explained
demo.py, tests/            for trying it out and for contributors
.github/workflows/         the automatic checks that run on every change
```

To run the tests, use `python -m pip install pytest` and then `python -m pytest`.

## License

[MIT](LICENSE). Free to use, change and share.
