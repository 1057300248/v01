# Safe Cloud Deployment

This branch is designed for a private Telegram bot that uses a standard Chromium browser to check Google One / Google AI offers visible to an account.

## Required environment variables

- `TELEGRAM_BOT_TOKEN` — token from BotFather
- `ADMIN_TELEGRAM_ID` — your numeric Telegram user ID; strongly recommended

Optional:

- `HEADLESS=true`
- `LOG_LEVEL=INFO`
- `WEBDRIVER_TIMEOUT=30`
- `IMPLICIT_WAIT=5`
- `PAGE_LOAD_TIMEOUT=60`

Do not commit real secrets to GitHub. Add them in your cloud provider's Variables / Secrets settings.

## Railway

1. Create a new Railway project from this GitHub repository.
2. Select branch `safe-cloud-deploy`.
3. Railway should detect `Dockerfile` automatically.
4. Add `TELEGRAM_BOT_TOKEN` and `ADMIN_TELEGRAM_ID` under Variables.
5. Deploy. No public HTTP port is required because the Telegram bot uses long polling.
6. Open deployment logs and look for `Bot is running`.

## Docker VPS

```bash
git clone https://github.com/1057300248/v01.git
cd v01
git checkout safe-cloud-deploy
docker build -t v01-safe .
docker run -d --restart unless-stopped \
  --name v01-safe \
  -e TELEGRAM_BOT_TOKEN='YOUR_TOKEN' \
  -e ADMIN_TELEGRAM_ID='YOUR_TELEGRAM_ID' \
  v01-safe
```

View logs:

```bash
docker logs -f v01-safe
```

## Usage

Open your Telegram bot and run:

- `/start`
- `/login`
- `/check_offer`
- `/get_link`
- `/status`

Credentials and the optional TOTP secret are stored only in process memory and are lost when the container restarts.

If Google requests an additional verification challenge, the automation stops and asks you to complete it manually in your own browser rather than attempting to bypass the challenge.
