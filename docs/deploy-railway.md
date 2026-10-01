# Run Rubico on Railway

Railway rents you a small private server, so Rubico keeps running and your brief arrives every morning even when your computer is off. It takes about 15 minutes, and you can do it all from your phone. If you'd rather use your own computer, see [the README](../README.md#run-it-on-your-own-computer).

<img src="web-setup.png" alt="Rubico's setup page on a phone" width="320">

## Before you start

You'll need a free [GitHub](https://github.com) account, the Telegram app and an [Anthropic API key](https://console.anthropic.com/settings/keys) for Claude.

Railway gives new accounts a free trial with $5 of credit for 30 days, and no card is needed. After that the Hobby plan costs $5 a month and includes $5 of usage, which is plenty for Rubico. Check [railway.com/pricing](https://railway.com/pricing) for today's prices. Claude is paid separately to Anthropic, and a daily brief usually costs a few cents.

## Step 1. Copy Rubico to your GitHub

1. Open [github.com/406samay/rubico-ai](https://github.com/406samay/rubico-ai) and sign in.
2. Tap **Fork**, then **Create fork**.

You now have your own copy, called **rubico-ai**, on your GitHub account.

## Step 2. Let Railway see your copy

This is the step people miss. Signing in to Railway with GitHub is not enough on its own, because Railway also needs permission to read your copy of Rubico.

1. Go to [railway.com](https://railway.com) and sign in with **GitHub**.
2. Open [github.com/apps/railway-app/installations/new](https://github.com/apps/railway-app/installations/new).
3. Pick your GitHub account.
4. Choose **Only select repositories**, then pick **rubico-ai**.
5. Tap **Install** (or **Save** if it was installed before).

You can check it worked on GitHub under **Settings**, then **Applications**. **Railway App** should be listed under **Installed GitHub Apps**.

## Step 3. Create your Rubico on Railway

1. On Railway, tap **New Project**, then **GitHub repo**.
2. Pick **rubico-ai**.
3. Tap **Add variables**, and add these two.

| Name | Value |
|---|---|
| `DASHBOARD_PASSWORD` | A password you make up, at least 10 characters. You'll use it to open your setup page and dashboard. |
| `PORT` | `8080` |

4. Tap **Deploy**.

The first build takes a couple of minutes.

## Step 4. Add storage

Storage keeps your settings and logins safe when Rubico updates. Without it they're wiped every time.

1. Right click an empty part of your project's page and choose **Volume**. On a phone, or if right click doesn't work, press **Ctrl+K** (or **⌘K** on a Mac) and type **volume**.
2. Connect it to the **rubico-ai** service.
3. Set the mount path to `/data`.

## Step 5. Get your web address

1. Tap the **rubico-ai** service, then the **Settings** tab.
2. Under **Networking**, tap **Generate Domain**. If it asks for a port, type `8080`.

You'll get an address like `https://rubico-ai-production-1234.up.railway.app`. Wait until the deployment says **Active** in green.

## Step 6. Set up Rubico in your browser

1. Open your address with `/setup` on the end, like `https://rubico-ai-production-1234.up.railway.app/setup`.
2. Log in with any username and your `DASHBOARD_PASSWORD`.
3. Follow the cards from top to bottom. They ask for your Claude key, your Telegram bot, your city and the data sources you want.

For the Telegram card, message [@BotFather](https://t.me/BotFather) in the Telegram app, send `/newbot` and paste the token it gives you. Then open your new bot, press **Start**, and tap the link button on the card.

As soon as the Claude key and Telegram are done, Rubico starts by itself. Text your bot `/help` to check. Your dashboard is your address without `/setup`.

## If something goes wrong

**"Failed to fetch repository files", or rubico-ai isn't in the list.** Railway can't read your copy yet. Do Step 2 again and make sure **rubico-ai** is ticked, then refresh Railway and try again.

**"Rubico needs a password before it can be opened".** Add `DASHBOARD_PASSWORD` under the service's **Variables** tab, as in Step 3.

**A red "No storage volume" warning, or your settings reset after an update.** Add the volume at `/data`, as in Step 4.

**The web address doesn't load.** Check the deployment says **Active**, and that the domain's port is `8080`.

**Telegram says it couldn't check, when you link your chat.** Another copy of Rubico is using the same bot. Stop the other copy, or make a new bot for this one.

**Anything else.** Open the service, then **Deployments**, then **View logs**. Rubico explains what it's doing there in plain English.

## Connecting Google

You make your own free Google OAuth client, so your login goes straight from Google to your Rubico. [The README explains why that's safe](../README.md#google). It takes about five minutes, once.

1. [Create a project](https://console.cloud.google.com/projectcreate) called Rubico.
2. Turn on the [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com), the [Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com) or both.
3. Open the [consent screen](https://console.cloud.google.com/auth/branding), set the app name to Rubico and the audience to **External**.
4. On the [Audience](https://console.cloud.google.com/auth/audience) page, tap **Publish app**. If you skip this, Google logs you out every 7 days.
5. Open [Clients](https://console.cloud.google.com/auth/clients), tap **Create client** and choose **Web application**.
6. Under **Authorized redirect URIs**, add the address shown on your Google card. It looks like `https://rubico-ai-production-1234.up.railway.app/setup/google/callback`.
7. Paste the Client ID and secret into the Google card and tap **Sign in with Google**.

Google will say it "hasn't verified this app". That's expected, because it's your own app. Tap **Advanced**, then **Go to Rubico**, then **Continue**.

If Google says `redirect_uri_mismatch`, the address in step 6 has to match your Google card character for character. If it says `access_denied`, go back to step 4 and publish the app.

Monzo and Spotify work the same way. Their cards show the exact address to paste into the Monzo or Spotify developer site.

## Updating Rubico

When there's a new version, open your copy on GitHub and tap **Sync fork**, then **Update branch**. Railway rebuilds by itself, and your settings stay on the volume.
