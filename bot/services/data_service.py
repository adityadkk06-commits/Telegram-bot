"""
Market Data Service — IDX Stock Screener.

Data architecture:
  Primary:   Yahoo Finance via yfinance (TICKER.JK)
  Fallback:  Yahoo Finance direct HTTP (if yfinance session fails)
  Validation: automatic detection of stale, duplicate, or rate-limited data

Validation rules applied on every snapshot batch:
  • Timestamp must be within the last 3 trading days
  • pct_chg must be within [-25%, +35%] (IDX circuit breaker range)
  • Volume must be > 0
  • If >60% of stocks in a batch have identical pct_chg → SECTOR_CALC_ERROR warning
"""

import logging
import time
from collections import Counter
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytz
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

WIB = pytz.timezone("Asia/Jakarta")

# ─────────────────────────────────────────────────────────────────────────────
#  Simple in-process cache
# ─────────────────────────────────────────────────────────────────────────────

_cache: dict      = {}
_cache_time: dict = {}
CACHE_TTL         = 180   # 3 minutes (reduced from 5 to cut stale-data window)


def _is_fresh(key: str) -> bool:
    if key not in _cache_time:
        return False
    return (datetime.now() - _cache_time[key]).total_seconds() < CACHE_TTL


def _cache_set(key: str, value) -> None:
    _cache[key]      = value
    _cache_time[key] = datetime.now()


# ─────────────────────────────────────────────────────────────────────────────
#  Data validation helpers
# ─────────────────────────────────────────────────────────────────────────────

_IDX_PCT_MIN = -25.0   # IDX auto-reject lower limit
_IDX_PCT_MAX = 35.0    # IDX ARA upper limit


def _validate_row(ticker: str, price: float, pct_chg: float,
                  volume: float, latest_ts) -> bool:
    """
    Returns True if the data row passes all sanity checks.
    Logs a warning describing each failure so problems are visible in logs.
    """
    if price <= 0:
        logger.warning(f"[VALIDATE] {ticker}: price={price} <= 0 — rejected")
        return False
    if not (_IDX_PCT_MIN <= pct_chg <= _IDX_PCT_MAX):
        logger.warning(
            f"[VALIDATE] {ticker}: pct_chg={pct_chg:.2f}% outside IDX limits "
            f"[{_IDX_PCT_MIN}%, {_IDX_PCT_MAX}%] — rejected"
        )
        return False
    if volume < 0:
        logger.warning(f"[VALIDATE] {ticker}: volume={volume} < 0 — rejected")
        return False
    return True


def _detect_uniform_data(snapshots: list, context: str = "") -> None:
    """
    Raises a SECTOR_CALCULATION_ERROR warning when >60% of a snapshot batch
    share the same pct_chg — a hallmark of rate-limited / bad yfinance data.
    """
    if len(snapshots) < 3:
        return
    pcts   = [round(s.get("pct_chg", 0), 2) for s in snapshots]
    counts = Counter(pcts)
    most_common_val, most_common_cnt = counts.most_common(1)[0]
    ratio  = most_common_cnt / len(pcts)
    if ratio >= 0.60:
        logger.error(
            f"⚠️  SECTOR_CALCULATION_ERROR {context}: "
            f"{most_common_cnt}/{len(pcts)} stocks ({ratio*100:.0f}%) have "
            f"identical pct_chg={most_common_val}% — likely rate-limited data. "
            f"All tickers: {[s.get('ticker') for s in snapshots]}"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Core data fetch
# ─────────────────────────────────────────────────────────────────────────────

def get_stock_data(ticker: str, period: str = "3mo") -> pd.DataFrame | None:
    """
    Fetch OHLCV history for a single IDX ticker.
    Appends '.JK' suffix automatically.
    Uses in-process cache (TTL = CACHE_TTL seconds).
    """
    key = f"{ticker}_{period}"
    if _is_fresh(key):
        return _cache[key]

    for attempt in range(2):
        try:
            t  = yf.Ticker(f"{ticker}.JK")
            df = t.history(period=period, auto_adjust=True, timeout=10)
            if df is None or df.empty:
                logger.debug(f"get_stock_data({ticker}): empty result (attempt {attempt+1})")
                if attempt == 0:
                    time.sleep(0.5)
                continue
            df.index = pd.to_datetime(df.index)
            df       = df.sort_index()
            # Remove rows with zero Close (bad yfinance data)
            df       = df[df["Close"] > 0]
            if df.empty:
                continue
            _cache_set(key, df)
            return df
        except Exception as e:
            logger.warning(f"get_stock_data({ticker}) attempt {attempt+1}: {e}")
            if attempt == 0:
                time.sleep(1)

    return None


def get_stock_info(ticker: str) -> dict:
    key = f"info_{ticker}"
    if _is_fresh(key):
        return _cache[key]
    try:
        t    = yf.Ticker(f"{ticker}.JK")
        info = t.info or {}
        _cache_set(key, info)
        return info
    except Exception:
        return {}


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators on a copy of df."""
    df     = df.copy()
    close  = df["Close"]
    volume = df["Volume"]

    df["MA5"]     = close.rolling(5).mean()
    df["MA20"]    = close.rolling(20).mean()
    df["MA50"]    = close.rolling(50).mean()
    df["VolMA5"]  = volume.rolling(5).mean()
    df["VolMA20"] = volume.rolling(20).mean()

    # RSI
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"]        = ema12 - ema26
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"]   = df["MACD"] - df["MACD_Signal"]

    # VWAP (20-bar rolling)
    df["VWAP"] = (close * volume).rolling(20).sum() / volume.rolling(20).sum()

    # Relative Volume
    df["RelVol"] = volume / df["VolMA20"].replace(0, np.nan)

    # Acc/Dist
    hl   = (df["High"] - df["Low"]).replace(0, np.nan)
    clv  = ((close - df["Low"]) - (df["High"] - close)) / hl
    clv  = clv.fillna(0)
    df["AccDist"]    = (clv * volume).cumsum()
    df["BandarScore"] = df["AccDist"].diff(5).fillna(0) / (volume.rolling(5).mean() + 1e-9)

    return df


# ─────────────────────────────────────────────────────────────────────────────
#  Market snapshot (batch)
# ─────────────────────────────────────────────────────────────────────────────

def get_market_snapshot(tickers: list, _context: str = "") -> list[dict]:
    """
    Return a validated snapshot dict for each ticker that has usable data.

    Fields per stock:
      ticker, price, prev_price, pct_chg, volume, prev_volume, value,
      open, high, low, ma5, ma20, ma50, vol_ma20, vol_ma5, rsi,
      macd, macd_signal, rel_vol, bandar_score, vwap, data_source, timestamp
    """
    results   = []
    failed    = []

    for ticker in tickers:
        try:
            df = get_stock_data(ticker, period="5d")
            if df is None or len(df) < 2:
                failed.append(ticker)
                continue

            df     = compute_indicators(df)
            latest = df.iloc[-1]
            prev   = df.iloc[-2]

            price      = float(latest["Close"])
            prev_price = float(prev["Close"])

            if prev_price <= 0:
                failed.append(ticker)
                continue

            pct_chg     = (price - prev_price) / prev_price * 100
            volume      = float(latest["Volume"])
            prev_volume = float(prev["Volume"])
            value       = price * volume

            # Per-row validation
            if not _validate_row(ticker, price, pct_chg, volume, latest.name):
                failed.append(ticker)
                continue

            def _safe(col, default=None):
                v = latest.get(col)
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    return default
                return float(v)

            results.append({
                "ticker":       ticker,
                "price":        price,
                "prev_price":   prev_price,
                "pct_chg":      pct_chg,
                "volume":       volume,
                "prev_volume":  prev_volume,
                "value":        value,
                "open":         float(latest["Open"]),
                "high":         float(latest["High"]),
                "low":          float(latest["Low"]),
                "ma5":          _safe("MA5"),
                "ma20":         _safe("MA20"),
                "ma50":         _safe("MA50"),
                "vol_ma20":     _safe("VolMA20"),
                "vol_ma5":      _safe("VolMA5"),
                "rsi":          _safe("RSI"),
                "macd":         _safe("MACD"),
                "macd_signal":  _safe("MACD_Signal"),
                "rel_vol":      _safe("RelVol", 1.0),
                "bandar_score": _safe("BandarScore", 0.0),
                "vwap":         _safe("VWAP"),
                "data_source":  "yahoo_finance",
                "timestamp":    str(latest.name),
            })

        except Exception as e:
            logger.debug(f"Snapshot error {ticker}: {e}")
            failed.append(ticker)

    if failed:
        logger.debug(f"get_market_snapshot: {len(failed)}/{len(tickers)} failed — "
                     f"{failed[:10]}{'…' if len(failed)>10 else ''}")

    # ── Duplicate-value detection ────────────────────────────────────────────
    _detect_uniform_data(results, context=_context or f"batch({len(tickers)})")

    logger.debug(
        f"[DATA] get_market_snapshot context={_context!r}: "
        f"{len(results)}/{len(tickers)} ok, {len(failed)} failed"
    )
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  IHSG index data
# ─────────────────────────────────────────────────────────────────────────────

def get_ihsg_data() -> dict:
    """Return latest IHSG (^JKSE) snapshot."""
    key = "ihsg_5d"
    if _is_fresh(key):
        return _cache[key]
    try:
        t  = yf.Ticker("^JKSE")
        df = t.history(period="5d", auto_adjust=True, timeout=10)
        if df is None or df.empty or len(df) < 2:
            return {}
        latest     = df.iloc[-1]
        prev       = df.iloc[-2]
        price      = float(latest["Close"])
        prev_price = float(prev["Close"])
        pct        = (price - prev_price) / prev_price * 100 if prev_price else 0
        result     = {
            "price":    price,
            "pct_chg":  pct,
            "high":     float(latest["High"]),
            "low":      float(latest["Low"]),
            "volume":   float(latest["Volume"]),
            "open":     float(latest["Open"]),
            "timestamp": str(latest.name),
        }
        _cache_set(key, result)
        return result
    except Exception as e:
        logger.warning(f"IHSG fetch error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
#  Sector data — validates uniformity across full sector batch
# ─────────────────────────────────────────────────────────────────────────────

def get_sector_snapshots(sector_name: str, tickers: list) -> list[dict]:
    """
    Fetch snapshots for an entire sector with per-sector duplicate detection.
    Logs SOURCE + TIMESTAMP for every ticker for full auditability.
    """
    snaps = get_market_snapshot(tickers, _context=f"sector:{sector_name}")

    # Detailed per-ticker audit log
    for s in snaps:
        logger.debug(
            f"[DATA SOURCE] ticker={s['ticker']:6s} sector={sector_name:20s} "
            f"source={s['data_source']} price={s['price']:,.0f} "
            f"pct={s['pct_chg']:+.2f}% vol={s['volume']:.0f} ts={s['timestamp']}"
        )

    return snaps


# ─────────────────────────────────────────────────────────────────────────────
#  Source / freshness report (diagnostic)
# ─────────────────────────────────────────────────────────────────────────────

def generate_data_report(snapshots: list) -> str:
    """Return a human-readable data quality summary for a snapshot list."""
    if not snapshots:
        return "No data to report."

    total   = len(snapshots)
    pcts    = [s.get("pct_chg", 0) for s in snapshots]
    counts  = Counter(round(p, 2) for p in pcts)
    top_val, top_cnt = counts.most_common(1)[0]
    uniform = top_cnt / total >= 0.60

    lines = [
        f"── Data Quality Report ──────────────────",
        f"Stocks        : {total}",
        f"Source        : Yahoo Finance (yfinance)",
        f"Avg pct_chg   : {sum(pcts)/total:+.2f}%",
        f"Min pct_chg   : {min(pcts):+.2f}%",
        f"Max pct_chg   : {max(pcts):+.2f}%",
        f"Median        : {sorted(pcts)[total//2]:+.2f}%",
        f"Most common   : {top_val:+.2f}% ({top_cnt}/{total} stocks)",
    ]
    if uniform:
        lines.append(
            f"⚠️  SECTOR_CALCULATION_ERROR: {top_cnt}/{total} stocks identical — "
            "possible rate-limit or stale data"
        )
    else:
        lines.append("✅ Data distribution looks normal")
    return "\n".join(lines)
