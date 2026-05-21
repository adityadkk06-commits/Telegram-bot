"""
Background Scanner Engine.

Two independent scanners (run as APScheduler jobs):
  1. top_gainer_scan   — finds Top 5 IDX gainers, sends alert on changes
  2. golden_cross_scan — detects MA10 > MA20 crossovers, sends instant alert

Both scanners maintain state in module-level dicts to avoid duplicate alerts.
"""
import logging
from datetime import datetime, date
from typing import Optional
import pandas as pd
import pytz

from bot.services.data_service import get_market_snapshot, get_stock_data, compute_indicators
from bot.alerts.market_scheduler import is_market_open
from bot.alerts.signal_engine import generate_trade_signal, format_signal_message
from bot.alerts.notification import broadcast_alert
from bot.utils.constants import ALL_IDX_STOCKS

logger = logging.getLogger(__name__)
WIB = pytz.timezone("Asia/Jakarta")

# ─────────────────────────────────────────────────────────────────────────────
#  Shared state
# ─────────────────────────────────────────────────────────────────────────────

# Previous Top-5 gainer tickers (to detect ranking changes)
_prev_top5: list[str] = []

# Golden cross alerts already sent today: {ticker: date}
_gc_alerted: dict[str, date] = {}

# MA state from last scan: {ticker: (prev_ma10, prev_ma20)}
_prev_ma_state: dict[str, tuple] = {}


def _get_users(context) -> list[int]:
    """Load all registered user IDs from users.json."""
    import os, json
    path = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return list(set(json.load(f)))
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
#  Top Gainer Scanner
# ─────────────────────────────────────────────────────────────────────────────

async def top_gainer_scan(context) -> None:
    """
    APScheduler job: scan all IDX stocks, send alert if Top-5 ranking changes.
    Only runs during market hours.
    """
    global _prev_top5

    if not is_market_open():
        return

    try:
        snapshots = get_market_snapshot(ALL_IDX_STOCKS)
    except Exception as e:
        logger.warning(f"top_gainer_scan: data fetch error: {e}")
        return

    if not snapshots:
        return

    # Sort by pct_chg descending, take top 5
    ranked  = sorted(snapshots, key=lambda x: x.get("pct_chg", 0), reverse=True)
    top5    = [s for s in ranked[:10] if s.get("pct_chg", 0) > 0.5][:5]
    top5_tickers = [s["ticker"] for s in top5]

    if not top5:
        return

    # Check if ranking has changed
    if top5_tickers == _prev_top5:
        return

    logger.info(f"Top Gainer ranking changed: {_prev_top5} → {top5_tickers}")
    _prev_top5 = top5_tickers

    users = _get_users(context)
    if not users:
        return

    # Build summary + detailed alerts
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from bot.alerts.alert_chart import generate_alert_chart

    # Summary header
    header_lines = ["🏆 *IDX TOP 5 GAINER UPDATE*\n"]
    for i, s in enumerate(top5, 1):
        ticker = s["ticker"]
        pct    = s.get("pct_chg", 0)
        rv     = s.get("rel_vol", 1) or 1
        price  = s.get("price", 0)
        header_lines.append(
            f"{i}. *{ticker}* {price:,.0f} +{pct:.2f}% | Vol:{rv:.1f}×"
        )

    summary_text = "\n".join(header_lines)
    kb_summary = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📊 {s['ticker']}", callback_data=f"chart_{s['ticker']}")
         for s in top5[:3]],
    ])

    for uid in users:
        try:
            await context.bot.send_message(
                chat_id=uid, text=summary_text,
                parse_mode="Markdown", reply_markup=kb_summary,
            )
        except Exception as e:
            logger.debug(f"Summary send failed {uid}: {e}")

    import asyncio
    await asyncio.sleep(1)

    # Detailed analysis for Top 3 with chart
    for s in top5[:3]:
        ticker = s["ticker"]
        pct    = s.get("pct_chg", 0)

        try:
            sig   = generate_trade_signal(s)
            text  = format_signal_message(sig, pct, alert_type="gainer")
            chart = generate_alert_chart(ticker, sig)
        except Exception as e:
            logger.warning(f"Signal gen error for {ticker}: {e}")
            continue

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Full Chart",    callback_data=f"chart_{ticker}"),
             InlineKeyboardButton("🏦 Broker Flow",   callback_data=f"broker_{ticker}")],
            [InlineKeyboardButton("⭐ Add Watchlist", callback_data=f"watch_add_{ticker}"),
             InlineKeyboardButton("📈 Screener",      callback_data="menu_screener")],
        ])

        sent = await broadcast_alert(
            context.bot, users, text, ticker=ticker,
            photo=chart, reply_markup=kb,
        )
        logger.info(f"Gainer alert {ticker}: sent to {sent} users")
        await asyncio.sleep(0.5)


# ─────────────────────────────────────────────────────────────────────────────
#  Golden Cross Scanner
# ─────────────────────────────────────────────────────────────────────────────

async def golden_cross_scan(context) -> None:
    """
    APScheduler job: detect MA10 > MA20 crossovers across all IDX stocks.
    Sends instant notification. Only one alert per stock per trading day.
    Only runs during market hours.
    """
    global _prev_ma_state, _gc_alerted

    if not is_market_open():
        return

    today = datetime.now(WIB).date()

    try:
        snapshots = get_market_snapshot(ALL_IDX_STOCKS)
    except Exception as e:
        logger.warning(f"golden_cross_scan: fetch error: {e}")
        return

    crosses_found = []

    for snap in snapshots:
        ticker = snap.get("ticker")
        if not ticker:
            continue

        # Already alerted today?
        if _gc_alerted.get(ticker) == today:
            continue

        try:
            df = get_stock_data(ticker, period="1mo")
            if df is None or len(df) < 22:
                continue

            df = compute_indicators(df)
            df["MA10"] = df["Close"].rolling(10).mean()

            if len(df) < 2:
                continue

            latest = df.iloc[-1]
            prev   = df.iloc[-2]

            ma10_now  = float(latest["MA10"]) if pd.notna(latest["MA10"]) else 0
            ma20_now  = float(latest["MA20"]) if pd.notna(latest["MA20"]) else 0
            ma10_prev = float(prev["MA10"])   if pd.notna(prev["MA10"])   else 0
            ma20_prev = float(prev["MA20"])   if pd.notna(prev["MA20"])   else 0

            # Golden cross: MA10 crosses above MA20
            was_below = ma10_prev <= ma20_prev
            is_above  = ma10_now > ma20_now

            if was_below and is_above and ma10_now > 0 and ma20_now > 0:
                crosses_found.append(snap)
                _gc_alerted[ticker] = today
                logger.info(f"Golden Cross detected: {ticker} MA10={ma10_now:.0f} > MA20={ma20_now:.0f}")

        except Exception as e:
            logger.debug(f"GC check error for {ticker}: {e}")

    if not crosses_found:
        return

    users = _get_users(context)
    if not users:
        return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from bot.alerts.alert_chart import generate_alert_chart
    import asyncio

    for snap in crosses_found[:3]:    # cap at 3 concurrent GC alerts
        ticker = snap["ticker"]
        pct    = snap.get("pct_chg", 0)

        try:
            sig   = generate_trade_signal(snap)
            text  = format_signal_message(sig, pct, alert_type="golden_cross")
            # Override type label
            text  = text.replace("TOP GAINER ALERT", "GOLDEN CROSS ALERT ✨")
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
        logger.info(f"Golden Cross alert {ticker}: sent to {sent} users")
        await asyncio.sleep(0.5)


# ─────────────────────────────────────────────────────────────────────────────
#  Price Alert Check
# ─────────────────────────────────────────────────────────────────────────────

async def price_alert_check(context) -> None:
    """
    APScheduler job: check custom user price alerts.
    Fires instantly when a stock crosses its target price.
    """
    from bot.alerts.price_alerts import get_all_alert_tickers, check_and_fire_alerts
    from bot.alerts.alert_chart import generate_alert_chart
    from bot.alerts.notification import send_alert
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    import asyncio

    tickers = get_all_alert_tickers()
    if not tickers:
        return

    try:
        snapshots = get_market_snapshot(tickers)
    except Exception as e:
        logger.warning(f"price_alert_check fetch error: {e}")
        return

    fired = check_and_fire_alerts(snapshots)
    if not fired:
        return

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
        text   = (
            f"🔔 *PRICE ALERT TRIGGERED*\n\n"
            f"*{ticker}* {arrow} {target:,.0f}\n"
            f"Current price: *{price:,.0f}* ({sign}{pct:.2f}%)\n"
            f"Volume: {rv:.1f}× average\n\n"
        )

        # Add quick analysis if snapshot available
        snap = snap_map.get(ticker, {})
        if snap:
            try:
                sig  = generate_trade_signal(snap)
                text += (
                    f"*Quick Analysis:*\n"
                    f"🎯 Entry: {sig['entry']:,.0f}\n"
                    f"🎯 TP1:  {sig['tp1']:,.0f}  |  TP2: {sig['tp2']:,.0f}\n"
                    f"🛑 SL:   {sig['sl']:,.0f}\n"
                    f"Confidence: {sig['confidence']}/10\n"
                )
            except Exception:
                pass

        text += "\n_Alert has been cleared. Set a new one with /alert_"

        try:
            chart = generate_alert_chart(ticker, {}) if snap else None
        except Exception:
            chart = None

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Chart",          callback_data=f"chart_{ticker}"),
             InlineKeyboardButton("🏦 Broker",         callback_data=f"broker_{ticker}")],
            [InlineKeyboardButton("⭐ Add Watchlist",  callback_data=f"watch_add_{ticker}"),
             InlineKeyboardButton("🔔 New Alert",      callback_data="menu_main")],
        ])

        await send_alert(context.bot, uid, text, ticker=ticker, photo=chart, reply_markup=kb)
        logger.info(f"Price alert fired: {ticker} {direct} {target} → user {uid}")
        await asyncio.sleep(0.1)
