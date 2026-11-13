# Personal Daily News Digest Agent

An automated, single-run daily news-digest CLI agent designed for a Computer Engineering student based in Italy finishing their degree, preparing for AI / SDE roles, monitoring European tech and the Turkish economy, and learning Italian and English.

Runs automatically via **GitHub Actions** and delivers daily summaries directly to **Telegram**.

---

## Architecture & Project Structure

- `sources.json`: Source configuration (name, category, source_type, feed_url) across Tech, World, Turkey, Europe, and Finance.
- `fetcher.py`: Fetches and cleans RSS/Atom feed entries (titles, snippets, links) without full-page scraping; catches feed errors.
- `dedup_filter.py`: State tracking (`state.json`), age filtering (<48h), heuristic pre-filtering, and story clustering.
- `llm_scorer.py`: Scores relevance (1–5) to user goals, summarizes strictly from feed text, formats Turkey multi-source comparisons, generates English/Italian vocabulary, and logs token usage/cost.
- `digest_generator.py`: Formats the Markdown output (`digest-YYYY-MM-DD.md`) matching the required schema. The digest is a local artifact delivered to Telegram — gitignored, never committed.
- `delivery.py`: Formats and chunks messages for Telegram API delivery (`https://api.telegram.org/bot<TOKEN>/sendMessage`).
- `main.py`: Command-line entrypoint that executes once and exits (0 error code).
- `.github/workflows/daily-digest.yml`: GitHub Actions automated daily cron workflow.
- `state.json`: Tracks seen URLs so duplicate articles are not processed in subsequent runs.
- `run-log.json`: Logs run metadata, item counts, token usage, and cost per run.

---

## 5-Minute Setup: GitHub Actions + Telegram Delivery

### Step 1: Create Your Telegram Bot & Get IDs (2 minutes)
1. **Bot Token**: In Telegram, search for `@BotFather`, send `/newbot`, follow the prompt, and copy your **`HTTP API Token`** (e.g. `123456789:ABCdefGHIjk...`).
2. **Chat ID**:
   - Send any message (e.g., `hi`) to your newly created bot.
   - Search for `@userinfobot` on Telegram and send `/start`. It will reply with your numerical **Id** (e.g., `987654321`).

### Step 2: Push to a GitHub Repository
In your terminal:
```bash
cd /Users/suleymanbdaziroglu/.gemini/antigravity/scratch/news-digest
git init
git add .
git commit -m "feat: initial daily news digest setup"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git push -u origin main
```

### Step 3: Add GitHub Repository Secrets
In your GitHub repository:
1. Go to **Settings** -> **Secrets and variables** -> **Actions**.
2. Click **New repository secret** and add:
   - `GEMINI_API_KEY`: Your Google AI Studio API key (or `OPENAI_API_KEY`)
   - `TELEGRAM_BOT_TOKEN`: Token received from `@BotFather`
   - `TELEGRAM_CHAT_ID`: Your numerical ID from `@userinfobot`

### Step 4: Test Immediately
- Go to the **Actions** tab in your repository.
- Select **Daily News Digest** on the left.
- Click **Run workflow** -> **Run workflow**.
- You will receive today's news digest on Telegram within ~30 seconds!

---

## Local Development & Testing

```bash
cd /Users/suleymanbdaziroglu/.gemini/antigravity/scratch/news-digest

# Virtual environment setup
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Run dry-run (no API keys, zero cost)
.venv/bin/python main.py --dry-run

# Run live with local Telegram dispatch
export GEMINI_API_KEY="your-gemini-key"
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"
.venv/bin/python main.py
```
