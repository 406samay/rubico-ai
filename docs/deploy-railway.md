# ☁️ Run Rubico in the cloud with Railway (no computer needed)

Your computer doesn't need to stay on, and you can do the whole thing **from your phone**.
Rubico runs on a small private server that *you* rent from [Railway](https://railway.com).
Setup happens on a web page instead of in a terminal.

<img src="web-setup.png" alt="Rubico's browser setup page on a phone" width="320">

**Good to know before you start**

| | |
|---|---|
| 💷 **Cost** | Railway's Hobby plan, currently about **$5/month**, which is plenty for Rubico. Check [railway.com/pricing](https://railway.com/pricing) for today's price. Claude usage is extra, usually a few cents a day. |
| 🔒 **Privacy** | It's *your* server in *your* Railway account. Your keys, logins and data live on your own storage volume there. Nobody else, including whoever wrote Rubico, can see them. The difference from running on your own computer is that Railway (the hosting company) runs the machine, like any cloud service. |
| ⏱️ **Time** | About 15 minutes, plus a few more for each extra service (Google etc.). |
| ⚠️ **One copy per bot** | A Telegram bot can only be used by one running Rubico at a time. If you ever run a second copy, give it its own bot. |

**You'll need:** a free [GitHub](https://github.com) account, the Telegram app, and an
[Anthropic API key](https://console.anthropic.com/settings/keys).

---

## Step 1: Copy Rubico into your GitHub

1. Open [github.com/406samay/rubico-ai](https://github.com/406samay/rubico-ai) and sign in.
2. Tap **Fork**, then **Create fork**. You now have your own copy.

## Step 2: Create your server on Railway

1. Go to [railway.com](https://railway.com) and tap **Login → Login with GitHub**.
2. Tap **New Project** (or **+ New**), then **Deploy from GitHub repo**, and pick your **rubico-ai** fork.
   (If it asks, allow Railway to see that repository.)
3. Railway starts building straight away. The first build takes a couple of minutes.

## Step 3: Add a password and port

Open the **rubico-ai** service, go to the **Variables** tab, and add:

| Name | Value |
|---|---|
| `DASHBOARD_PASSWORD` | A password you choose. You'll use it to open your setup page and dashboard. Make it long. |
| `PORT` | `8080` |

> Your Rubico is on the internet, so it **refuses to open without a password**.

## Step 4: Add storage (so nothing is lost when Rubico updates)

1. In your project, tap **+ Create** (or **+ New**), then **Volume**.
2. Attach it to the **rubico-ai** service with the mount path **`/data`**.

Without this, your settings and logins are wiped every time Railway rebuilds. The setup
page shows a red warning if the volume is missing.

## Step 5: Give it a web address

In the service, open **Settings → Networking → Generate Domain**. If it asks for a port,
enter **8080**. You'll get an address like `https://rubico-ai-production-1234.up.railway.app`.

Railway redeploys automatically after these changes. Wait until the deployment shows **Active** (green).

## Step 6: Open your setup page

Go to your address with **`/setup`** on the end:

```
https://rubico-ai-production-1234.up.railway.app/setup
```

Log in with **any username** and your `DASHBOARD_PASSWORD`, then go down the cards:

1. **Claude API key.** Paste it in. Rubico checks it works.
2. **Telegram bot.** Make a bot with [@BotFather](https://t.me/BotFather) in the Telegram app (`/newbot`) and paste
   the token. Then open your bot in Telegram, press **Start**, and tap **"I've sent it - link my chat"**.
   You'll get a ✅ message in Telegram.
3. **About you.** Your name, city (sets weather, timezone and currency) and brief time.
4. **Data sources.** Tick what you want. Weather needs no login.

As soon as steps 1 and 2 are done, **Rubico starts by itself**. Text your bot `/help` 🎉

Your dashboard is at your web address without `/setup`. The link at the bottom of every
brief now opens it from your phone too.

---

## Connecting Google (Gmail & Calendar)

You create your own free Google "OAuth client", so your login goes straight from Google to
your Rubico ([why this is safe](../README.md#-connecting-google-gmail--calendar-with-safety-first)).
It takes about 5 minutes, once:

1. [Create a project](https://console.cloud.google.com/projectcreate) called Rubico.
2. Enable the [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
   and/or the [Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com).
3. [Consent screen](https://console.cloud.google.com/auth/branding): app name Rubico, audience **External**.
4. [Audience](https://console.cloud.google.com/auth/audience): tap **Publish app**. (If you only add
   yourself as a test user instead, Google logs you out every 7 days.)
5. [Clients](https://console.cloud.google.com/auth/clients), then **Create client**. Choose type **Web application**. Under
   **Authorized redirect URIs**, add the address your setup page shows. It looks like:
   ```
   https://rubico-ai-production-1234.up.railway.app/setup/google/callback
   ```
6. Paste the Client ID and secret into the **Google** card, then tap **Sign in with Google**.
   Google will say it "hasn't verified this app". That's expected, because it's *your own* app:
   tap **Advanced → Go to Rubico → Continue**.

**Monzo** and **Spotify** work the same way: their cards show the exact redirect address
to paste into the Monzo or Spotify developer site.

---

## Updating Rubico

When new features come out, open your fork on GitHub and tap **Sync fork → Update branch**.
Railway rebuilds automatically, and your settings and logins are kept on the volume.

## Troubleshooting

| What you see | Fix |
|---|---|
| "Rubico needs a password before it can be opened" | Add `DASHBOARD_PASSWORD` in Variables (Step 3) |
| Red "No storage volume" warning, or settings reset after an update | Add the volume at `/data` (Step 4) |
| The web address doesn't load | Check the deployment is **Active**, and that the domain's port is **8080** |
| Google says `redirect_uri_mismatch` | The redirect URI in Google Cloud must match the one on your setup page *exactly* |
| Google says `access_denied` | Publish the app, or add your address as a test user (Google step 4) |
| "Couldn't check Telegram" when linking | Another copy of Rubico is using the bot. Stop it, then try again |
| Anything else | Open the service → **Deployments → View logs**. Rubico explains what it's doing there |

---

## For the repo owner: make it a one-tap "Deploy on Railway" button

A Railway **template** turns Steps 1-5 into a single button. You create it once:

1. In Railway, open **Templates** (in your workspace menu) and tap **New Template**.
2. Add a service from the GitHub repo **406samay/rubico-ai**.
3. In the service's settings in the template editor:
   - **Variables:** `DASHBOARD_PASSWORD` (required, with the description "Choose a password
     for your Rubico pages") and `PORT` = `8080`.
     Optionally add `ANTHROPIC_API_KEY` and `TELEGRAM_BOT_TOKEN` as required variables, so
     people paste them while deploying.
   - **Volume:** mount path `/data`.
   - **Networking:** enable a public domain on port `8080`.
4. **Publish** the template and copy its link (it looks like `https://railway.com/deploy/xxxx`).
5. Add this to the top of the README's cloud section, with your link in it:
   ```markdown
   [![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/xxxx)
   ```

People then tap the button, fill in a password, and go straight to Step 6.
