# IDX Stock Screener Bot

AI-powered Telegram bot for Indonesian Stock Market (IDX/IHSG) screening, analysis, and charting.

## Run & Operate

- `python -m bot.main` — start the Telegram bot
- Required env: `TELEGRAM_BOT_TOKEN` — Telegram bot token from @BotFather

## Stack

- Python 3.11
- python-telegram-bot (v20+ async)
- yfinance — IDX stock data via Yahoo Finance (.JK suffix)
- mplfinance + matplotlib — candlestick charts (dark theme)
- pandas + ta — technical indicators (MA, RSI, MACD, VWAP)
- APScheduler (via job-queue) — watchlist alert scheduler

## Where things live

```
bot/
  main.py               — entry point, workflow registration
  handlers/
    command_handlers.py — /start, /screener, /chart, /heatmap, etc.
    callback_handlers.py— inline keyboard callback router
  services/
    data_service.py     — yfinance data fetch + indicator computation
    ai_service.py       — rule-based AI explanations
  screener/
    screener_engine.py  — runs screeners, enriches with scores/broker
    ara_hunter.py       — ARA Hunter filter
    bsjp.py             — BSJP filter
    big_accumulation.py — Big Accumulation filter
  charts/
    chart_generator.py  — mplfinance dark-theme candlestick charts
  heatmap/
    heatmap_generator.py— matplotlib sector heatmap image
  sector_rotation/
    sector_analyzer.py  — per-sector performance and rotation score
  bandarmology/
    broker_analyzer.py  — broker/bandar accumulation signal estimator
  data/
    watchlist.py        — JSON-based per-user watchlist
  utils/
    constants.py        — IDX stock universe, sectors, broker list
    formatters.py       — price/volume/score formatting helpers
```

## Architecture decisions

- yfinance with `.JK` suffix is used for IDX data (free, no API key needed)
- Broker/bandar flows are estimated from price+volume patterns since real IDX broker data requires a paid provider (Stockbit, RTI Business)
- AI explanations are rule-based (no LLM cost); can be upgraded to Gemini/OpenAI
- Watchlist stored in `bot/data/watchlists.json` (simple, portable)
- All Telegram interactions use inline keyboards for smooth navigation

## Product

- **3 screeners**: ARA Hunter, BSJP, Big Accumulation
- **Heatmap**: Sector-based with color scale, filterable by sector
- **Sector Rotation**: Daily ranking with rotation score and buy candidates
- **Bandar Detector**: AK/BK/YP/CC/PD/XL broker accumulation analysis
- **Charts**: Candlestick + MA5/20/50 + RSI + MACD + buy/sell signals
- **Watchlist**: Per-user with auto breakout/volume alerts every 5 minutes
- **Market Breadth**: Advance/Decline ratio, RSI extremes
- **Top Momentum**: Sorted by % change with relative volume

## Auto Alert Scanners

Four background jobs run during IDX market hours (09:00–16:00 WIB):

| Scanner | Trigger | Interval |
|---|---|---|
| Top 5 Gainer | Ranking change OR new entry in Top 5 | Every 5 min |
| Golden Cross | EMA9 crosses above EMA20 | Every 5 min |
| Top Scalping | Price<500, +3%, Vol>500k, Value>5B, Price>MA5 | Every 5 min |
| Price Alert | User-set custom price levels crossed | Every 2 min |

All scanners feed into the same signal engine (11-factor confidence) and notification system. The Top Scalping scanner is an **additional trigger source** — it expands the stock universe without modifying any existing alert logic.

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

- IDX market hours: 09:00–16:00 WIB (UTC+7). Outside hours, yfinance returns last close data.
- Broker flow analysis is simulated — label it clearly to users (done in the UI).
- `/TICKER` commands (e.g. `/bbca`) are handled via a regex message handler, not individual CommandHandlers.
- Always run `python -m bot.main` from the workspace root so relative imports resolve.
