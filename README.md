# 🇮🇩 IDX Stock Screener Bot

AI-powered Indonesian Stock Market (IDX/IHSG) screener that runs entirely on **GitHub Actions + Telegram** — no VPS, no Railway, no Render required.

---

## How It Works

```
GitHub Actions (cron every 15 min)
        │
        ▼
  bot/run_scan.py   ←── one-shot, exits after completion
        │
        ├── Fetch live IDX snapshots (yfinance .JK)
        ├── Run scanners:
        │     • Top Gainers (rank change in Top 5)
        │     • Top Scalping (Price<500, +3%, Vol>500k, Value>5B, Price>MA5)
        │     • Golden Cross (EMA9 crosses above EMA20)
        ├── Generate 11-factor trade signals
        └── Send alerts → Telegram Bot API → your chat/channel
```

No infinite loops. No polling. No web server. Each run starts, scans, sends, and exits.

---

## Quick Setup

### 1. Fork or clone this repo to your GitHub account

### 2. Create a Telegram Bot

1. Open [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy your **Bot Token** (format: `123456:ABC-DEF1234...`)

### 3. Get your Chat ID

- For a personal chat: start your bot, then visit  
  `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`  
  and find `"chat":{"id": ...}` in the response
- For a channel: add the bot as admin, send a message, use the same URL.  
  Channel IDs look like `-100xxxxxxxxxx`

### 4. Add GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat or channel ID |

### 5. Enable GitHub Actions

Go to the **Actions** tab in your repo and click **"I understand my workflows, go ahead and enable them"** if prompted.

That's it — the scanner will start running automatically during market hours.

---

## Workflows

### `market-scan.yml` — Market Scanner

| Property | Value |
|---|---|
| Schedule | Every 15 min, Mon–Fri |
| Market hours | 09:00–15:45 WIB (02:00–08:45 UTC) |
| Trigger | Auto (cron) + Manual (workflow_dispatch) |
| Runtime | ~2–5 minutes per run |
| Timeout | 13 minutes |

**What it does each run:**
1. Checks out code
2. Installs Python 3.11 + uv + all dependencies
3. Runs `bot/run_scan.py` which:
   - Fetches snapshots for all ~130 IDX stocks
   - Applies 3 scan strategies
   - Generates institutional-grade trade signals (entry, TP1, TP2, SL, confidence %)
   - Sends alerts + summary to your Telegram chat
4. Exits with code 0 (success) or 1 (send failures)

**GitHub Actions log output:**
```
=== IDX MARKET SCAN ===
UTC time  : Tue Jun 10 02:00:01 UTC 2026
WIB time  : Tue Jun 10 09:00:01 WIB 2026
...
[INFO] idx_scan: Step 1/4 — Fetching market snapshots…
[INFO] idx_scan:   Snapshots received: 128 / 130 (took 18.4s)
[INFO] idx_scan: Step 2/4 — Running scanners…
[INFO] idx_scan:   Top Gainers   : 3 found
[INFO] idx_scan:   Top Scalping  : 2 found
[INFO] idx_scan:   Golden Cross  : 1 found
[INFO] idx_scan: Step 3/4 — Generating trade signals…
[INFO] idx_scan:   ✔ BBRI   | gainer         | conf=82% | BUY
[INFO] idx_scan: Step 4/4 — Sending alerts to Telegram…
[INFO] idx_scan:   ✅ Delivered: BBRI (gainer)
[INFO] idx_scan: SCAN COMPLETE
[INFO] idx_scan:   Stocks scanned : 128
[INFO] idx_scan:   Signals found  : 4
[INFO] idx_scan:   Alerts sent    : 4
[INFO] idx_scan:   Duration       : 142.3s
```

### `ci.yml` — Continuous Integration

Runs on every push and pull request to `main`:
- Python syntax checks on all bot modules
- Node.js dependency install + API server build
- Typecheck

---

## Scan Strategies

### ⚡ Top Scalping
| Filter | Value |
|---|---|
| Price | < 500 |
| 1-Day Return | ≥ 3% |
| Volume | > 500,000 |
| Transaction Value | > Rp 5,000,000,000 |
| Price vs MA5 | Price > MA5 |

### 🔥 Top Gainers
Detects new entries or ranking changes in the IDX Top 5 gainers by percentage change.

### ✨ Golden Cross
Detects EMA9 crossing above EMA20 — a classic momentum reversal signal.

---

## Signal Format

Each alert includes:
- Entry zone (low–high)
- Take Profit 1 & 2 with % upside
- Stop Loss with % downside
- Risk/Reward ratio
- 11-factor confidence bar (0–100%)
- Scalping probability score
- Full analysis breakdown

---

## Manual Trigger

You can trigger a scan at any time (outside market hours for testing):

1. Go to **Actions → IDX Market Scan**
2. Click **Run workflow**
3. Optionally set `debug: true` for verbose output
4. Click **Run workflow**

---

## Local Development

```bash
# Install Python deps
uv sync

# Set env vars
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"

# Run one-shot scan
uv run python -m bot.run_scan

# Or run the full interactive Telegram bot (requires TELEGRAM_BOT_TOKEN)
python -m bot.main
```

---

## Project Structure

```
bot/
  run_scan.py           ← one-shot GitHub Actions entry point
  main.py               ← interactive Telegram bot (polling mode)
  alerts/
    scanner.py          ← background scanner jobs (for polling mode)
    signal_engine.py    ← 11-factor trade signal generator
    notification.py     ← rate-limited broadcast utility
  services/
    data_service.py     ← yfinance data + indicator computation
  screener/             ← ARA Hunter, BSJP, Big Accumulation screeners
  utils/
    constants.py        ← IDX stock universe (~130 tickers)
.github/
  workflows/
    market-scan.yml     ← scheduled market scanner (GitHub Actions)
    ci.yml              ← CI: syntax check + build
```

---

## Notes

- **Market hours**: IDX trades 09:00–16:00 WIB (UTC+7). The scanner runs until 15:45 WIB to allow the last signal before close.
- **Frequency filter**: The "Frequency > 3,000" criterion (transaction count) is not available via yfinance. The filter is applied only when the data field is present; otherwise it passes through.
- **Rate limits**: Telegram allows 30 messages/second per bot. The scanner caps at 8 alerts per cycle with 0.6s delays between sends.
- **Data source**: Yahoo Finance (yfinance) with `.JK` suffix. Free, no API key needed.
- **No always-on server needed**: GitHub Actions provides 2,000 free minutes/month (public repos: unlimited). At ~3 min/run × 28 runs/day × 22 trading days = ~1,848 min/month — fits within the free tier.
