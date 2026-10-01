# Run Rubico on Railway

This is the best way to run Rubico. Your computer doesn't need to stay on, and you can do the whole thing from your phone. Rubico runs on a small private server that you rent from [Railway](https://railway.com), and setup happens on a web page instead of in a terminal. If you'd rather use your own computer, see [the README](../README.md#run-it-on-your-own-computer).

<img src="web-setup.png" alt="Rubico's browser setup page on a phone" width="320">

## Good to know before you start

It costs about $5 a month on Railway's Hobby plan, which is plenty for Rubico, and you can check [railway.com/pricing](https://railway.com/pricing) for today's price. Claude usage is extra, and it's usually a few cents a day.

It's your server in your Railway account. Your keys, logins and data live on your own storage volume there, and nobody else can see them, including the people who wrote Rubico. The only difference from your own computer is that Railway runs the machine, like any cloud service.

Setup takes about 15 minutes, plus a few more for each extra service like Google. A Telegram bot can only be used by one running Rubico at a time, so if you ever run a second copy, give it its own bot.

You'll need a free [GitHub](https://github.com) account, the Telegram app and an [Anthropic API key](https://console.anthropic.com/settings/keys).

## Step 1, copy Rubico into your GitHub

Open [github.com/406samay/rubico-ai](https://github.com/406samay/rubico-ai) and sign in. Tap Fork, then Create fork, and you'll have your own copy.

## Step 2, create your server on Railway

Go to [railway.com](https://railway.com) and tap Login, then Login with GitHub. Tap New Project (or + New), then Deploy from GitHub repo, and pick your rubico-ai fork. If it asks, allow Railway to see that repository. Railway starts building straight away, and the first build takes a couple of minutes.

## Step 3, add a password and a port

Open the rubico-ai service, go to the Variables tab and add two variables. The first is `DASHBOARD_PASSWORD`, which is a password you choose and will use to open your setup page and dashboard, so make it long. The second is `PORT`, which should be set to `8080`.

Your Rubico is on the internet, so it refuses to open without a password.

## Step 4, add storage so nothing is lost when Rubico updates

In your project, tap + Create (or + New), then Volume. Attach it to the rubico-ai service with the mount path `/data`. Without this, your settings and logins are wiped every time Railway rebuilds, and the setup page shows a red warning if the volume is missing.

## Step 5, give it a web address

In the service, open Settings, then Networking, then Generate Domain. If it asks for a port, enter `8080`. You'll get an address like `https://rubico-ai-production-1234.up.railway.app`. Railway redeploys automatically after these changes, so wait until the deployment shows Active in green.

## Step 6, open your setup page

Go to your address with `/setup` on the end.

```
https://rubico-ai-production-1234.up.railway.app/setup
```

Log in with any username and your `DASHBOARD_PASSWORD`, then go down the cards. The first card is the Claude API key, which you paste in and Rubico checks that it works. The second is the Telegram bot. Make a bot with [@BotFather](https://t.me/BotFather) in the Telegram app by sending `/newbot`, paste the token, then open your bot in Telegram and press Start. Back on the page, tap "I've sent it, link my chat" and you'll get a tick message in Telegram. The third card is About you, which has your name, your city (it sets the weather, timezone and currency) and your brief time. The fourth is Data sources, where you tick what you want, and weather needs no login.

As soon as the Claude key and Telegram are done, Rubico starts by itself. Text your bot `/help` and you're up and running. Your dashboard is at your web address without `/setup`, and the link at the bottom of every brief opens it from your phone too.

## Connecting Google

You create your own free Google OAuth client, so your login goes straight from Google to your Rubico, and [the README explains why that's safe](../README.md#google). It takes about five minutes and you only do it once.

First, [create a project](https://console.cloud.google.com/projectcreate) called Rubico. Then enable the [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com), the [Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com) or both. Next, open the [consent screen](https://console.cloud.google.com/auth/branding), set the app name to Rubico and the audience to External. On the [Audience](https://console.cloud.google.com/auth/audience) page, tap Publish app, because if you only add yourself as a test user, Google logs you out every 7 days.

Then open [Clients](https://console.cloud.google.com/auth/clients) and tap Create client, and choose the type Web application. Under Authorized redirect URIs, add the address your setup page shows, which looks like this.

```
https://rubico-ai-production-1234.up.railway.app/setup/google/callback
```

Paste the Client ID and secret into the Google card, then tap Sign in with Google. Google will say it "hasn't verified this app", which is expected because it's your own app. Tap Advanced, then Go to Rubico, then Continue.

Monzo and Spotify work the same way. Their cards show the exact redirect address to paste into the Monzo or Spotify developer site.

## Updating Rubico

When new features come out, open your fork on GitHub and tap Sync fork, then Update branch. Railway rebuilds automatically, and your settings and logins are kept on the volume.

## Troubleshooting

If you see "Rubico needs a password before it can be opened", add `DASHBOARD_PASSWORD` in Variables, which is Step 3. If you see a red "No storage volume" warning, or your settings reset after an update, add the volume at `/data`, which is Step 4.

If the web address doesn't load, check that the deployment is Active and that the domain's port is `8080`. If Google says `redirect_uri_mismatch`, the redirect address in Google Cloud has to match the one on your setup page character for character. If Google says `access_denied`, publish the app or add your address as a test user, as in the Google steps above.

If linking Telegram says it couldn't check, another copy of Rubico is using the bot, so stop it and try again. For anything else, open the service, go to Deployments, then View logs, because Rubico explains what it's doing there.

## For the repo owner, a one tap Deploy on Railway button

A Railway template turns Steps 1 to 5 into a single button, and you only create it once. In Railway, open Templates from your workspace menu and tap New Template. Add a service from the GitHub repo `406samay/rubico-ai`. In the template editor, add the variable `DASHBOARD_PASSWORD` as required, with the description "Choose a password for your Rubico pages", and add `PORT` set to `8080`. You can also add `ANTHROPIC_API_KEY` and `TELEGRAM_BOT_TOKEN` as required variables, so people paste them while deploying. Set a volume with the mount path `/data`, and enable a public domain on port `8080`.

Then publish the template and copy its link, which looks like `https://railway.com/deploy/xxxx`. Add this line near the top of the README's Railway section, with your link in it.

```markdown
[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/xxxx)
```

People then tap the button, fill in a password and go straight to Step 6.
