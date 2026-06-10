"""
Daily Market Open Summary — GitHub Actions mode.

Runs once at 09:00 WIB every trading day.
Sends a structured morning briefing to Telegram:
  • IHSG overnight status + trend
  • Previous day's Top 5 Gainers & Top 5 Losers
  • Today's Watchlist Candidates (uptrend + healthy volume)
  • Market session timing reminder

Usage:
    uv run python -m bot.run_daily_open

Required environment variables:
    TELEGRAM_BOT_TOKEN   — From @BotFather
    TELEGRAM_CHAT_ID     — Target chat / channel ID (e.g. "-100xxxxxxxxxx")
"""

import logging
import os
import sys
import time
from datetime import datetime

import pytz
import requests

from bot.services.data_service import get_market_snapshot, get_ihsg_data
from bot.utils.constants import ALL_IDX_STOCKS

# ─────────────────────────────────────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger("idx_open")

WIB   = pytz.timezone("Asia/Jakarta")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT  = os.environ.get("TELEGRAM_CHAT_ID",   "").strip()

SEP    = "━" * 29
SEP_SM = "─" * 29

# ─────────────────────────────────────────────────────────────────────────────
#  Telegram delivery
# ─────────────────────────────────────────────────────────────────────────────

def _tg_send(text: str, parse_mode: str = "Markdown") -> bool:
    if not TOKEN or not CHAT:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set")
        return False
    url     = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT, "text": text, "parse_mode": parse_mode,
               "disable_web_page_preview": True}
    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                return True
            if r.status_code == 429:
                retry_after = r.json().get("parameters", {}).get("retry_after", 5)
                logger.warning(f"Rate-limit: retry after {retry_after}s")
                time.sleep(retry_after + 1)
                continue
            try:
                err_desc = r.json().get("description", r.text)
            except Exception:
                err_desc = r.text
            logger.warning(f"Telegram HTTP {r.status_code}: {err_desc} [CHAT_ID={CHAT!r}]")
            return False
        except requests.exceptions.RequestException as e:
            logger.warning(f"Send attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(3)
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ihsg_block(ihsg: dict) -> str:
    if not ihsg:
        return "📊 *IHSG* — data tidak tersedia\n"
    price = ihsg.get("price", 0)
    pct   = ihsg.get("pct_chg", 0)
    high  = ihsg.get("high", 0)
    low   = ihsg.get("low", 0)
    arrow = "🟢" if pct >= 0 else "🔴"
    sign  = "+" if pct >= 0 else ""
    trend = "Bullish ↑" if pct >= 0.5 else ("Bearish ↓" if pct <= -0.5 else "Sideways →")
    return (
        f"📊 *IHSG*  {price:,.2f}  {arrow} {sign}{pct:.2f}%\n"
        f"   H: {high:,.2f}  |  L: {low:,.2f}  |  Trend: {trend}\n"
    )


def _movers_block(snapshots: list) -> tuple[str, str]:
    """Returns (gainers_text, losers_text)."""
    ranked = sorted(snapshots, key=lambda x: x.get("pct_chg", 0), reverse=True)
    gainers = [s for s in ranked if s.get("pct_chg", 0) > 0][:5]
    losers  = [s for s in ranked if s.get("pct_chg", 0) < 0][-5:]
    losers.reverse()  # worst first

    def _row(s: dict, i: int) -> str:
        t   = s["ticker"]
        p   = s.get("price", 0)
        pct = s.get("pct_chg", 0)
        rv  = s.get("rel_vol") or 1
        sign = "+" if pct >= 0 else ""
        return f"{i}. *{t}*  {p:,.0f}  {sign}{pct:.2f}%  Vol:{rv:.1f}×"

    g_lines = ["📈 *TOP 5 GAINERS (Kemarin)*\n"] + [_row(s, i) for i, s in enumerate(gainers, 1)]
    l_lines = ["📉 *TOP 5 LOSERS (Kemarin)*\n"] + [_row(s, i) for i, s in enumerate(losers, 1)]
    return "\n".join(g_lines), "\n".join(l_lines)


def _watchlist_block(snapshots: list) -> str:
    """
    Watchlist candidates for today:
      • RSI 40–65 (not overbought, not oversold)
      • Price > MA20 (uptrend)
      • RelVol > 1.2 (above-average interest)
      • pct_chg > -1 (not in freefall)
    Returns formatted text block.
    """
    candidates = []
    for s in snapshots:
        rsi   = s.get("rsi")
        price = s.get("price", 0)
        ma20  = s.get("ma20")
        rv    = s.get("rel_vol") or 0
        pct   = s.get("pct_chg", 0)

        if rsi  is None or ma20 is None: continue
        try:
            rsi_f  = float(rsi)
            ma20_f = float(ma20)
            rv_f   = float(rv)
        except (TypeError, ValueError):
            continue

        if not (40 <= rsi_f <= 65):  continue
        if price <= ma20_f:          continue
        if rv_f  < 1.2:              continue
        if pct   < -1:               continue

        candidates.append(s)

    if not candidates:
        return "🔍 *WATCHLIST HARI INI*\n_Tidak ada kandidat kuat pagi ini._\n"

    candidates.sort(key=lambda x: x.get("rel_vol") or 0, reverse=True)

    lines = ["🔍 *WATCHLIST HARI INI*\n"]
    for i, s in enumerate(candidates[:6], 1):
        t    = s["ticker"]
        p    = s.get("price", 0)
        pct  = s.get("pct_chg", 0)
        rsi  = float(s.get("rsi") or 0)
        rv   = float(s.get("rel_vol") or 1)
        sign = "+" if pct >= 0 else ""
        lines.append(
            f"{i}. *{t}*  {p:,.0f}  {sign}{pct:.2f}%  "
            f"RSI:{rsi:.0f}  Vol:{rv:.1f}×"
        )

    lines.append(f"\n_RSI 40-65 | Di atas MA20 | Volume > rata-rata_")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

def run_daily_open() -> int:
    now_wib = datetime.now(WIB)
    logger.info("=" * 50)
    logger.info(f"IDX DAILY OPEN SUMMARY: {now_wib.strftime('%Y-%m-%d %H:%M:%S WIB')}")
    logger.info("=" * 50)

    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Aborting.")
        return 1
    if not CHAT:
        logger.error("TELEGRAM_CHAT_ID is not set. Aborting.")
        return 1

    # Connectivity check
    test_url = f"https://api.telegram.org/bot{TOKEN}/getMe"
    try:
        tr = requests.get(test_url, timeout=10)
        if tr.status_code == 200:
            bot_name = tr.json().get("result", {}).get("username", "?")
            logger.info(f"Bot connected: @{bot_name}")
        else:
            logger.error(f"Bot token invalid! HTTP {tr.status_code}")
            return 1
    except Exception as e:
        logger.error(f"Connectivity test failed: {e}")
        return 1

    # ── Fetch data ────────────────────────────────────────────────────────────
    logger.info("Fetching IHSG data…")
    ihsg = get_ihsg_data()
    logger.info(f"  IHSG: {ihsg.get('price', 'N/A')}  {ihsg.get('pct_chg', 'N/A'):.2f}%" if ihsg else "  IHSG: unavailable")

    logger.info(f"Fetching snapshots for {len(ALL_IDX_STOCKS)} stocks…")
    snapshots = get_market_snapshot(ALL_IDX_STOCKS)
    logger.info(f"  Snapshots: {len(snapshots)} / {len(ALL_IDX_STOCKS)}")

    # ── Build message blocks ──────────────────────────────────────────────────
    date_str     = now_wib.strftime("%A, %d %b %Y")
    ihsg_txt     = _ihsg_block(ihsg)
    watchlist_txt = _watchlist_block(snapshots) if snapshots else "🔍 *WATCHLIST* — data tidak tersedia\n"

    # ── Send: Morning header ──────────────────────────────────────────────────
    header = (
        f"{SEP}\n"
        f"🌅 *SELAMAT PAGI — IDX MARKET OPEN*\n"
        f"📅 {date_str}\n"
        f"⏰ Sesi 1: 09:00 – 12:00 WIB\n"
        f"⏰ Sesi 2: 13:30 – 15:45 WIB\n"
        f"{SEP}\n\n"
        f"{ihsg_txt}"
    )
    _tg_send(header)
    time.sleep(0.8)

    # ── Send: Movers ──────────────────────────────────────────────────────────
    if snapshots:
        gainers_txt, losers_txt = _movers_block(snapshots)
        _tg_send(f"{gainers_txt}\n\n{SEP_SM}\n\n{losers_txt}")
        time.sleep(0.8)

    # ── Send: Watchlist ───────────────────────────────────────────────────────
    _tg_send(
        f"{watchlist_txt}\n\n"
        f"{SEP_SM}\n"
        f"⚡ Auto scan tiap 15 menit selama market.\n"
        f"📲 Sinyal masuk otomatis ke chat ini.\n"
        f"{SEP}"
    )

    logger.info("Daily open summary sent successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(run_daily_open())
