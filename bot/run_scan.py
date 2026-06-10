"""
One-shot IDX Market Scanner — GitHub Actions mode.

Runs the full market scan (Top Gainers, Golden Cross, Top Scalping),
generates trade signals, sends results directly to Telegram, then exits.

Usage:
    uv run python -m bot.run_scan

Required environment variables:
    TELEGRAM_BOT_TOKEN   — From @BotFather
    TELEGRAM_CHAT_ID     — Target chat / channel ID (e.g. "-100xxxxxxxxxx")
"""

import logging
import os
import sys
import time
from datetime import datetime

import pandas as pd
import pytz
import requests

from bot.services.data_service import get_market_snapshot, get_stock_data, compute_indicators
from bot.alerts.signal_engine import generate_trade_signal, format_signal_message
from bot.utils.constants import ALL_IDX_STOCKS

# ─────────────────────────────────────────────────────────────────────────────
#  Logging — stdout so GitHub Actions captures every line
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger("idx_scan")

WIB   = pytz.timezone("Asia/Jakarta")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT  = os.environ.get("TELEGRAM_CHAT_ID",   "").strip()

SEP = "━" * 29

# ─────────────────────────────────────────────────────────────────────────────
#  Telegram delivery (direct REST — no polling, no bot instance)
# ─────────────────────────────────────────────────────────────────────────────

def _tg_send(text: str, parse_mode: str = "Markdown") -> bool:
    """POST a message to the Telegram Bot API.  Returns True on success."""
    if not TOKEN or not CHAT:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set — skipping send")
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT, "text": text, "parse_mode": parse_mode,
               "disable_web_page_preview": True}
    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                return True
            if r.status_code == 429:          # rate limit — back off
                retry_after = r.json().get("parameters", {}).get("retry_after", 5)
                logger.warning(f"Telegram rate-limit: retry after {retry_after}s")
                time.sleep(retry_after + 1)
                continue
            logger.warning(f"Telegram HTTP {r.status_code}: {r.text[:200]}")
            return False
        except requests.exceptions.RequestException as e:
            logger.warning(f"Telegram send attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(3)
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  Scanner helpers
# ─────────────────────────────────────────────────────────────────────────────

def _scan_top_gainers(snapshots: list) -> list:
    """Return top-5 gainers with pct_chg > 0.3."""
    ranked = sorted(snapshots, key=lambda x: x.get("pct_chg", 0), reverse=True)
    return [s for s in ranked[:12] if s.get("pct_chg", 0) > 0.3][:5]


def _scan_top_scalping(snapshots: list) -> list:
    """
    Top Scalping filter set:
      Price < 500 | Return ≥ 3% | Volume > 500k | Value > 5B | Price > MA5
      Frequency > 3,000 (skipped when not in snapshot data)
    """
    hits = []
    for snap in snapshots:
        price   = float(snap.get("price",   0) or 0)
        pct_chg = float(snap.get("pct_chg", 0) or 0)
        volume  = float(snap.get("volume",  0) or 0)
        value   = float(snap.get("value",   0) or 0)
        ma5     = snap.get("ma5")
        freq    = snap.get("frequency")

        if price  <= 0 or price  >= 500:               continue
        if pct_chg < 3:                                 continue
        if volume  <= 500_000:                          continue
        if value   <= 5_000_000_000:                    continue
        if ma5 is not None and price <= float(ma5):     continue
        if freq is not None and float(freq) <= 3_000:   continue

        hits.append(snap)

    hits.sort(key=lambda x: x.get("value", 0), reverse=True)
    return hits[:6]


def _scan_golden_cross(snapshots: list) -> list:
    """
    EMA9 crossing above EMA20 (today vs yesterday).
    Pre-filters with snapshots (pct > 0) to avoid fetching history for losers.
    """
    logger.info("Golden Cross: fetching historical data for positive movers…")
    positive = [s for s in snapshots if s.get("pct_chg", 0) > 0]
    logger.info(f"  Pre-filtered to {len(positive)} positive stocks")

    crosses = []
    for snap in positive:
        ticker = snap.get("ticker")
        if not ticker:
            continue
        try:
            df = get_stock_data(ticker, period="1mo")
            if df is None or len(df) < 22:
                continue
            df   = compute_indicators(df)
            close = df["Close"]
            df["EMA9"]  = close.ewm(span=9,  adjust=False).mean()
            df["EMA20"] = close.ewm(span=20, adjust=False).mean()

            la, pr = df.iloc[-1], df.iloc[-2]
            e9n  = float(la["EMA9"])  if pd.notna(la.get("EMA9"))  else 0
            e20n = float(la["EMA20"]) if pd.notna(la.get("EMA20")) else 0
            e9p  = float(pr["EMA9"])  if pd.notna(pr.get("EMA9"))  else 0
            e20p = float(pr["EMA20"]) if pd.notna(pr.get("EMA20")) else 0

            if e9p <= e20p and e9n > e20n and e9n > 0:
                logger.info(f"  Golden Cross: {ticker} EMA9={e9n:.0f} > EMA20={e20n:.0f}")
                crosses.append(snap)
        except Exception as e:
            logger.debug(f"  GC check error {ticker}: {e}")

    return crosses[:4]


# ─────────────────────────────────────────────────────────────────────────────
#  Main one-shot entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_scan() -> int:
    start_wib = datetime.now(WIB)
    logger.info("=" * 50)
    logger.info(f"IDX MARKET SCAN START: {start_wib.strftime('%Y-%m-%d %H:%M:%S WIB')}")
    logger.info(f"Stock universe: {len(ALL_IDX_STOCKS)} tickers")
    logger.info("=" * 50)

    # ── Validate credentials ─────────────────────────────────────────────────
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Aborting.")
        return 1
    if not CHAT:
        logger.error("TELEGRAM_CHAT_ID is not set. Aborting.")
        return 1

    # ── 1. Fetch market snapshots ────────────────────────────────────────────
    logger.info("Step 1/4 — Fetching market snapshots…")
    t0 = time.time()
    snapshots = get_market_snapshot(ALL_IDX_STOCKS)
    logger.info(f"  Snapshots received: {len(snapshots)} / {len(ALL_IDX_STOCKS)} "
                f"(took {time.time()-t0:.1f}s)")

    if not snapshots:
        logger.error("No snapshots returned — market may be closed or data unavailable.")
        _tg_send(f"⚠️ *IDX Scan* — No market data at "
                 f"{start_wib.strftime('%H:%M WIB')}. Market may be closed.")
        return 0

    # ── 2. Run scanners ──────────────────────────────────────────────────────
    logger.info("Step 2/4 — Running scanners…")

    gainers  = _scan_top_gainers(snapshots)
    logger.info(f"  Top Gainers   : {len(gainers)} found")

    scalpers = _scan_top_scalping(snapshots)
    logger.info(f"  Top Scalping  : {len(scalpers)} found")

    gc_hits  = _scan_golden_cross(snapshots)
    logger.info(f"  Golden Cross  : {len(gc_hits)} found")

    # Collect unique candidates (scalpers first — highest priority)
    seen     = set()
    candidates = []
    for snap, alert_type in (
        [(s, "top_scalping") for s in scalpers] +
        [(s, "golden_cross") for s in gc_hits]  +
        [(s, "gainer")       for s in gainers]
    ):
        t = snap.get("ticker")
        if t and t not in seen:
            seen.add(t)
            candidates.append((snap, alert_type))

    logger.info(f"  Unique candidates: {len(candidates)}")

    # ── 3. Generate signals ──────────────────────────────────────────────────
    logger.info("Step 3/4 — Generating trade signals…")
    signals = []
    for snap, alert_type in candidates:
        ticker = snap.get("ticker", "?")
        try:
            sig = generate_trade_signal(snap)
            signals.append((snap, sig, alert_type))
            logger.info(f"  ✔ {ticker:6s} | {alert_type:14s} | "
                        f"conf={sig['confidence_pct']}% | {sig['signal_type']}")
        except Exception as e:
            logger.warning(f"  ✘ {ticker}: signal error — {e}")

    logger.info(f"  Signals generated: {len(signals)}")

    # ── 4. Send to Telegram ──────────────────────────────────────────────────
    logger.info("Step 4/4 — Sending alerts to Telegram…")
    sent = failed = 0

    # Opening banner
    _tg_send(
        f"{SEP}\n"
        f"🇮🇩 *IDX AUTO SCAN*\n"
        f"⏰ {start_wib.strftime('%H:%M WIB')}  |  "
        f"📊 {len(snapshots)} stocks  |  ⚡ {len(signals)} signals\n"
        f"{SEP}"
    )
    time.sleep(0.5)

    for snap, sig, alert_type in signals[:8]:   # cap at 8 per cycle
        ticker = snap.get("ticker", "?")
        pct    = snap.get("pct_chg", 0)
        text   = format_signal_message(sig, pct, alert_type)
        ok     = _tg_send(text)
        if ok:
            sent += 1
            logger.info(f"  ✅ Delivered: {ticker} ({alert_type})")
        else:
            failed += 1
            logger.warning(f"  ❌ Failed: {ticker}")
        time.sleep(0.6)   # avoid Telegram rate limit (30 msgs/sec per bot)

    # ── Summary ──────────────────────────────────────────────────────────────
    end_wib  = datetime.now(WIB)
    duration = (end_wib - start_wib).total_seconds()

    logger.info("=" * 50)
    logger.info(f"SCAN COMPLETE")
    logger.info(f"  Start time     : {start_wib.strftime('%H:%M:%S WIB')}")
    logger.info(f"  End time       : {end_wib.strftime('%H:%M:%S WIB')}")
    logger.info(f"  Duration       : {duration:.1f}s")
    logger.info(f"  Stocks scanned : {len(snapshots)}")
    logger.info(f"  Signals found  : {len(signals)}")
    logger.info(f"  Alerts sent    : {sent}")
    logger.info(f"  Failed sends   : {failed}")
    logger.info("=" * 50)

    no_signal_note = "\n_No matching signals this cycle._" if not signals else ""
    _tg_send(
        f"{SEP}\n"
        f"📋 *SCAN SUMMARY*\n\n"
        f"⏰ {start_wib.strftime('%H:%M')} – {end_wib.strftime('%H:%M WIB')}\n"
        f"📈 Stocks scanned : {len(snapshots)}\n"
        f"⚡ Signals found  : {len(signals)}\n"
        f"✅ Alerts sent    : {sent}\n"
        f"❌ Failed sends   : {failed}\n"
        f"⏱ Duration       : {duration:.0f}s"
        f"{no_signal_note}\n"
        f"{SEP}"
    )

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_scan())
