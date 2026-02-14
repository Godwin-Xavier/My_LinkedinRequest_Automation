# LinkedIn Recruiter Outreach Automation

> **⚠️ AUTHENTICATION ISSUE? COOKIES EXPIRED?**  
> If you see "Failed to log in with provided cookies", your LinkedIn cookies have expired.  
> **Quick fix:** Double-click `refresh_cookies.bat` or see [README_COOKIE_FIX.md](./README_COOKIE_FIX.md) for detailed instructions.

---


Automated daily outreach to global recruiters using stealth browser automation, AI-powered search, and Telegram notifications. Designed for deployment on Claw Cloud.

## Features

- 🕵️ **Stealth Mode**: Uses undetected-chromedriver + selenium-stealth to avoid bot detection
- 🤖 **AI-Powered Search**: Gemini API generates diverse recruiter search queries
- 📨 **Daily Automation**: Sends 14 connection requests per day at 9:30 AM IST
- 📱 **Telegram Notifications**: Daily summaries and error alerts
- 🗄️ **Duplicate Prevention**: SQLite database tracks sent invites
- 🐳 **Docker Ready**: One-command deployment to Claw Cloud

## Quick Start

### 1. Set Up Environment Variables

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# LinkedIn li_at cookie value (just the value, no JSON needed)
LINKEDIN_LI_AT=your_li_at_cookie_value_here

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Optional: Gemini API for AI-powered search queries
GEMINI_API_KEY=your_gemini_api_key_here
```

### 2. Get LinkedIn li_at Cookie

1. Log into LinkedIn in your browser
2. Press F12 > Application tab > Cookies > linkedin.com
3. Find the `li_at` cookie and copy its **Value**
4. Paste the value into `LINKEDIN_LI_AT` in your `.env` file

### 3. Get Telegram Bot Token

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Create a new bot with `/newbot`
3. Copy the token to `TELEGRAM_BOT_TOKEN`
4. Message [@userinfobot](https://t.me/userinfobot) to get your Chat ID

### 4. Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Test login
python main.py --test-login

# Dry run (no invites sent)
python main.py --run-now --dry-run

# Send 1 invite for testing
python main.py --run-now --limit 1
```

### 5. Deploy to Claw Cloud

#### Option A: Using Docker Image

```bash
# Build Docker image
docker build -t linkedin-automation .

# Push to Docker Hub (replace with your username)
docker tag linkedin-automation your-dockerhub-username/linkedin-automation:latest
docker push your-dockerhub-username/linkedin-automation:latest
```

Then in Claw Cloud:
1. Go to **Run** > **Deploy** > **From Docker Image**
2. Enter your image: `your-dockerhub-username/linkedin-automation:latest`
3. Add environment variables from your `.env` file
4. Deploy!

#### Option B: Local Docker

```bash
docker-compose up -d
```

View logs:
```bash
docker-compose logs -f
```

### 6. Run Daily on GitHub Actions (Free)

This repo now includes a scheduler workflow at `.github/workflows/linkedin-automation.yml`.

- Schedule: **09:00 IST daily** (cron `30 3 * * *` in UTC)
- Also supports manual run from Actions tab (`workflow_dispatch`)

Set these GitHub Repository Secrets:

- `LINKEDIN_LI_AT`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GEMINI_API_KEY` (optional)

How to enable:

1. Push this project to GitHub
2. Open **Settings -> Secrets and variables -> Actions**
3. Add the secrets listed above
4. Open **Actions -> LinkedIn Automation** and click **Run workflow** once to verify

Notes:

- Telegram summary/error alerts are sent by the Python app
- Workflow also sends a fallback Telegram alert if the job itself fails early
- LinkedIn cookie refresh: update `LINKEDIN_LI_AT` in both local `.env` and GitHub Secret
- Invite database is cached between runs in GitHub Actions to preserve history

## CLI Commands

| Command | Description |
|---------|-------------|
| `python main.py` | Start scheduler (runs daily at 9:30 AM IST) |
| `python main.py --run-now` | Run outreach immediately |
| `python main.py --dry-run` | Simulate without sending invites |
| `python main.py --limit 5` | Override daily limit |
| `python main.py --test-login` | Test cookie authentication |

## File Structure

```
├── .env.example          # Environment template
├── .env                   # Your secrets (gitignored)
├── config.py              # Configuration loader
├── main.py                # Entry point + scheduler
├── Dockerfile             # Container definition
├── docker-compose.yml     # Local dev setup
├── requirements.txt       # Python dependencies
├── src/
│   ├── browser_stealth.py # Stealth Chrome setup
│   ├── linkedin_client.py # LinkedIn interactions
│   ├── telegram_notifier.py # Telegram notifications
│   ├── recruiter_search.py # AI search queries
│   └── db_manager.py      # SQLite database
└── data/
    └── agent_state.db     # Invite tracking database
```

## Troubleshooting

### 🔴 Authentication Failed / Cookies Expired

**Symptoms:**
- Script shows: "Failed to log in with provided cookies"
- Browser redirects to login page
- "li_at cookie missing or expired" error

**Quick Fix (5 minutes):**

1. **Export Fresh Cookies**
   - Install [Cookie Editor Extension](https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm)
   - Login to LinkedIn in your browser
   - Click Cookie Editor → Export
   - Save to `linkedin_cookies.json` in project root

2. **Run Cookie Refresher**
   ```powershell
   # Option 1: Double-click this file
   refresh_cookies.bat
   
   # Option 2: Run manually
   python src/cookie_refresher.py
   ```

3. **Test Login**
   ```powershell
   python main.py --test-login
   ```

**📖 Detailed Guide:** See [README_COOKIE_FIX.md](./README_COOKIE_FIX.md) for complete step-by-step instructions with screenshots.

---


### Rate Limited
LinkedIn may temporarily restrict your account if you're sending too many requests. The default limit of 14/day is conservative. If you get restricted:
1. Wait 24-48 hours
2. Consider reducing `DAILY_INVITE_LIMIT`

### Browser Crashes
If Chrome keeps crashing in Docker:
1. Ensure `HEADLESS=true` in `.env`
2. Check container memory (needs ~1GB minimum)

## Safety Notes

⚠️ **Use at your own risk**. LinkedIn automation violates their Terms of Service. This tool includes many stealth features, but detection is always possible.

Recommendations:
- Use on a secondary LinkedIn account
- Keep invite limits conservative (14/day)
- Don't run during unusual hours
- Monitor for any LinkedIn warnings
