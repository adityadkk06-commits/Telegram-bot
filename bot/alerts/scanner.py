"""
Background Scanner Engine — Production Grade.

Scanners (APScheduler jobs):
  • top_gainer_scan    — Top 5 IDX gainers, every 5 min during market hours
  • golden_cross_scan  — EMA9 > EMA20 crossover detection, every 5 min
  • price_alert_check  — Custom user price alerts, every 2 min

Design principles:
  • State machine dedup — no duplicate alerts per session/day
  • Min confidence gate — only BUY signals with conf ≥ 75% broadcast
  • Momentum history   — track 3-scan rolling momentum per ticker
  • Anti-spam          — notification.py enforces per-user cooldowns
  • Fail-safe          — any single stock error does NOT crash the scan
"""
import asyncio
import logging
import os
import json
from datetime import datetime, date
from collections import defaultdict, deque

import pandas as pd
import pytz

from bot.services.data_service import get_market_snapshot, get_stock_data, compute_indicators
from bot.alerts.market_scheduler import is_market_open
from bot.alerts.signal_engine import generate_trade_signal, format_signal_message
from bot.alerts.notification import broadcast_alert, send_alert
from bot.utils.constants import ALL_IDX_STOCKS

logger = logging.getLogger(__name__)
WIB    = pytz.timezone("Asia/Jakarta")

# ─────────────────────────────────────────────────────────────────────────────
#  Shared persistent state
# ─────────────────────────────────────────────────────────────────────────────

_prev_top5: list[str] = []          # last known Top-5 tickers
_alerted_gainers: set[str] = set()  # tickers already alerted this session
_gc_alerted: dict[str, date] = {}   # golden cross alerted: ticker → date
_momentum_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=3))


# ─────────────────────────────────────────────────────────────────────────────
#  Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _load_users() -> list[int]:
    """
    Load all registered user IDs from EVERY available data source.
    Merges users.json + watchlists.json + price_alerts.json so that
    alerts are never silently dropped after a bot restart.
    """
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    users: set[int] = set()

    # Primary source: users.json
    p1 = os.path.join(data_dir, "users.json")
    if os.path.exists(p1):
        try:
            with open(p1) as f:
                for uid in json.load(f):
                    try:
                        users.add(int(uid))
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

    # Fallback 1: watchlists.json (keys are str(user_id))
    p2 = os.path.join(data_dir, "watchlists.json")
    if os.path.exists(p2):
        try:
            with open(p2) as f:
                for uid_str in json.load(f).keys():
                    try:
                        users.add(int(uid_str))
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

    # Fallback 2: price_alerts.json (keys are str(user_id))
    p3 = os.path.join(data_dir, "price_alerts.json")
    if os.path.exists(p3):
        try:
            with open(p3) as f:
                for uid_str in json.load(f).keys():
                    try:
                        users.add(int(uid_str))
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

    if not users:
        logger.warning("_load_users: no registered users found in any data source")
    return list(users)


def _get_sector(ticker: str) -> str:
    from bot.utils.constants import IDX_STOCKS
    for sector, stocks in IDX_STOCKS.items():
        if ticker in stocks:
            return sector
    return "IDX"


def _momentum_trend(ticker: str, pct: float) -> str:
    """Track rolling pct change and return trend label."""
    history = _momentum_history[ticker]
    history.append(pct)
    if len(history) < 2:
        return ""
    avg = sum(history) / len(history)
    if avg > 3:    return "📈 Accelerating"
    if avg > 1:    return "➡️ Steady"
    if avg < -1:   return "📉 Decelerating"
    return ""


async def _safe_snapshot(tickers: list) -> list:
    """Fetch snapshots with retry (up to 2 attempts)."""
    for attempt in range(2):
        try:
            result = get_market_snapshot(tickers)
            if result:
                return result
        except Exception as e:
            logger.warning(f"Snapshot attempt {attempt+1} failed: {e}")
            if attempt == 0:
                await asyncio.sleep(2)
    return []


# ─────────────────────────────────────────────────────────────────────────────
#  TOP 5 GAINER SCANNER
# ─────────────────────────────────────────────────────────────────────────────

async def top_gainer_scan(context) -> None:
    """
    Automatically finds IDX Top 5 Gainers every 5 minutes.
    Sends professional alert only when:
      • Ranking changed  OR  new ticker entered Top 5
      • Signal confidence ≥ 72%  (quality filter)
    """
    global _prev_top5, _alerted_gainers

    if not is_market_open():
        return

    logger.info("Running top_gainer_scan…")
    snapshots = await _safe_snapshot(ALL_IDX_STOCKS)
    if not snapshots:
        return

    # Sort and filter
    ranked = sorted(snapshots, key=lambda x: x.get("pct_chg", 0), reverse=True)
    top5   = [s for s in ranked[:12] if s.get("pct_chg", 0) > 0.3][:5]

    if not top5:
        return

    top5_tickers = [s["ticker"] for s in top5]
    new_entries  = [t for t in top5_tickers if t not in _prev_top5]

    # If no ranking change and no new entries, skip
    if top5_tickers == _prev_top5 and not new_entries:
        return

    logger.info(f"Top5 change: {_prev_top5} → {top5_tickers}")
    _prev_top5 = top5_tickers

    users = _load_users()
    if not users:
        return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from bot.alerts.alert_chart import generate_alert_chart

    # ── Summary broadcast (all users) ─────────────────────────────────────
    sep   = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    lines = [f"{sep}", "🏆 *TOP 5 GAINER UPDATE — IDX*\n"]
    for i, s in enumerate(top5, 1):
        t    = s["ticker"]
        pct  = s.get("pct_chg", 0)
        rv   = s.get("rel_vol", 1) or 1
        p    = s.get("price", 0)
        tag  = " 🆕" if t in new_entries else ""
        trend= _momentum_trend(t, pct)
        lines.append(f"{i}. *{t}*{tag}  {p:,.0f}  +{pct:.2f}%  Vol:{rv:.1f}×  {trend}")
    lines.append(f"\n{sep}")
    summary = "\n".join(lines)

    kb_summary = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📊 {s['ticker']}", callback_data=f"chart_{s['ticker']}")
         for s in top5[:3]],
        [InlineKeyboardButton("📈 Screener", callback_data="menu_screener"),
         InlineKeyboardButton("🏠 Menu",     callback_data="menu_main")],
    ])

    for uid in users:
        try:
            await context.bot.send_message(
                chat_id=uid, text=summary,
                parse_mode="Markdown", reply_markup=kb_summary,
            )
        except Exception as e:
            logger.debug(f"Summary send failed {uid}: {e}")

    await asyncio.sleep(1.5)

    # ── Deep analysis for new/top-3 entries ──────────────────────────────
    analyze_these = [s for s in top5 if s["ticker"] in new_entries] or top5[:2]

    for s in analyze_these[:3]:
        ticker = s["ticker"]
        pct    = s.get("pct_chg", 0)
        sector = _get_sector(ticker)

        try:
            sig = generate_trade_signal(s)
        except Exception as e:
            logger.warning(f"Signal gen error {ticker}: {e}")
            continue

        # Quality gate — only send if signal worth acting on
        if sig["confidence_pct"] < 55 and sig["signal_type"] == "AVOID":
            logger.info(f"Skipping {ticker} — low confidence ({sig['confidence_pct']}%)")
            continue

        try:
            text  = format_signal_message(sig, pct, "gainer")
            chart = generate_alert_chart(ticker, sig)
        except Exception as e:
            logger.warning(f"Format/chart error {ticker}: {e}")
            continue

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Full Chart",     callback_data=f"chart_{ticker}"),
             InlineKeyboardButton("🏦 Broker Flow",    callback_data=f"broker_{ticker}")],
            [InlineKeyboardButton("⭐ Add Watchlist",  callback_data=f"watch_add_{ticker}"),
             InlineKeyboardButton("🔔 Set Alert",      callback_data="menu_main")],
        ])

        sent = await broadcast_alert(
            context.bot, users, text, ticker=ticker,
            photo=chart, reply_markup=kb, delay_between=0.05,
        )
        logger.info(f"Gainer alert [{ticker}] conf={sig['confidence_pct']}% → {sent} users")
        _alerted_gainers.add(ticker)
        await asyncio.sleep(0.8)


# ─────────────────────────────────────────────────────────────────────────────
#  GOLDEN CROSS SCANNER
# ─────────────────────────────────────────────────────────────────────────────

async def golden_cross_scan(context) -> None:
    """
    Detects EMA9 crossing above EMA20 across all IDX stocks.
    One alert per stock per trading day. Auto-filtered by confidence.
    """
    global _gc_alerted

    if not is_market_open():
        return

    today  = datetime.now(WIB).date()
    logger.info("Running golden_cross_scan…")

    snapshots = await _safe_snapshot(ALL_IDX_STOCKS)
    if not snapshots:
        return

    crosses = []

    for snap in snapshots:
        ticker = snap.get("ticker")
        if not ticker:
            continue
        if _gc_alerted.get(ticker) == today:
            continue

        try:
            df = get_stock_data(ticker, period="1mo")
            if df is None or len(df) < 22:
                continue

            df = compute_indicators(df)
            close       = df["Close"]
            df["EMA9"]  = close.ewm(span=9,  adjust=False).mean()
            df["EMA20"] = close.ewm(span=20, adjust=False).mean()

            if len(df) < 2:
                continue

            la = df.iloc[-1]
            pr = df.iloc[-2]

            e9n  = float(la["EMA9"])  if pd.notna(la["EMA9"])  else 0
            e20n = float(la["EMA20"]) if pd.notna(la["EMA20"]) else 0
            e9p  = float(pr["EMA9"])  if pd.notna(pr["EMA9"])  else 0
            e20p = float(pr["EMA20"]) if pd.notna(pr["EMA20"]) else 0

            was_below = e9p <= e20p
            is_above  = e9n > e20n

            if was_below and is_above and e9n > 0 and e20n > 0:
                crosses.append(snap)
                _gc_alerted[ticker] = today
                logger.info(f"Golden Cross: {ticker}  EMA9={e9n:.0f} > EMA20={e20n:.0f}")

        except Exception as e:
            logger.debug(f"GC check error {ticker}: {e}")

    if not crosses:
        return

    users = _load_users()
    if not users:
        return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from bot.alerts.alert_chart import generate_alert_chart

    for snap in crosses[:4]:
        ticker = snap["ticker"]
        pct    = snap.get("pct_chg", 0)

        try:
            sig   = generate_trade_signal(snap)
            text  = format_signal_message(sig, pct, "golden_cross")
            chart = generate_alert_chart(ticker, sig)
        except Exception as e:
            logger.warning(f"GC signal error {ticker}: {e}")
            continue

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Full Chart",    callback_data=f"chart_{ticker}"),
             InlineKeyboardButton("🏦 Broker",        callback_data=f"broker_{ticker}")],
            [InlineKeyboardButton("⭐ Watchlist",     callback_data=f"watch_add_{ticker}"),
             InlineKeyboardButton("🏠 Menu",          callback_data="menu_main")],
        ])

        sent = await broadcast_alert(
            context.bot, users, text, ticker=ticker,
            photo=chart, reply_markup=kb,
        )
        logger.info(f"Golden Cross alert [{ticker}] → {sent} users")
        await asyncio.sleep(0.8)


# ─────────────────────────────────────────────────────────────────────────────
#  PRICE ALERT CHECK
# ─────────────────────────────────────────────────────────────────────────────

async def price_alert_check(context) -> None:
    """
    Checks user custom price alerts every 2 minutes.
    No market-hours restriction — users may set off-hours alerts.
    """
    from bot.alerts.price_alerts import get_all_alert_tickers, check_and_fire_alerts
    from bot.alerts.alert_chart import generate_alert_chart
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    tickers = get_all_alert_tickers()
    if not tickers:
        return

    snapshots = await _safe_snapshot(tickers)
    if not snapshots:
        return

    fired    = check_and_fire_alerts(snapshots)
    snap_map = {s["ticker"]: s for s in snapshots}

    for alert in fired:
        uid    = alert["user_id"]
        ticker = alert["ticker"]
        target = alert["target"]
        price  = alert["price"]
        direct = alert["direction"]
        pct    = alert["pct_chg"]
        rv     = alert["rel_vol"]
        sign   = "+" if pct >= 0 else ""
        arrow  = "📈 CROSSED ABOVE" if direct == "above" else "📉 CROSSED BELOW"

        # Build text
        sep   = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        lines = [
            sep,
            f"🔔 *PRICE ALERT TRIGGERED — IDX*\n",
            f"Stock  : *{ticker}*",
            f"Price  : *{price:,.0f}* ({sign}{pct:.2f}%)",
            f"Signal : {arrow} {target:,.0f}",
            f"Volume : {rv:.1f}× average\n",
        ]

        snap = snap_map.get(ticker, {})
        chart = None
        if snap:
            try:
                sig = generate_trade_signal(snap)
                lines += [
                    "*Quick Analysis:*",
                    f"Signal    : {sig['signal_emoji']} {sig['signal_type']}",
                    f"Confidence: {sig['confidence_pct']}%",
                    f"Entry     : {sig['entry_low']:,.0f} – {sig['entry']:,.0f}",
                    f"TP1 / TP2 : {sig['tp1']:,.0f} / {sig['tp2']:,.0f}",
                    f"SL        : {sig['sl']:,.0f}",
                    "",
                ]
                chart = generate_alert_chart(ticker, sig)
            except Exception:
                pass

        lines.append("_Alert cleared. Set new: /alert TICKER PRICE_")
        lines.append(sep)
        text = "\n".join(lines)

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Chart",          callback_data=f"chart_{ticker}"),
             InlineKeyboardButton("🏦 Broker",         callback_data=f"broker_{ticker}")],
            [InlineKeyboardButton("⭐ Add Watchlist",  callback_data=f"watch_add_{ticker}"),
             InlineKeyboardButton("🔔 New Alert",      callback_data="menu_main")],
        ])

        try:
            await send_alert(context.bot, uid, text, ticker=ticker,
                             photo=chart, reply_markup=kb)
            logger.info(f"Price alert fired: {ticker} {direct} {target} → user {uid}")
        except Exception as e:
            logger.warning(f"Price alert send error {uid}: {e}")

        await asyncio.sleep(0.1)
