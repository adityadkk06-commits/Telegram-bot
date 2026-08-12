"""
Data Service — Realtime + Historical Data Layer.

Two-tier caching:
  • SNAPSHOT_TTL   = 90s  — realtime price snapshots (intraday 5-min bars via yf.download)
  • INDICATOR_TTL  = 900s — MA/RSI/MACD/BandarScore computed from daily bars
  • CACHE_TTL      = 300s — historical OHLCV used in chart rendering / /chart command

── FIX LOG (patched) ──────────────────────────────────────────────────────────
Previously, get_market_snapshot()'s primary (bulk intraday) path returned
ma5/ma20/ma50/vol_ma5/vol_ma20/rsi/macd/macd_signal/bandar_score/vwap as
hardcoded None. Nothing downstream (screener_engine.py) ever filled them back
in, so every screener's indicator-based criteria silently degraded to
"no data — neutral" for the entire trading day. Combined with
filter_engine.py's PASS_THRESHOLD=82, this made PASS status mathematically
unreachable for ARA Hunter / BSJP / Scalper Pro, and even NEAR unreachable
for Big Accumulation, during live market hours.

Fix: a new batched daily-bar indicator pass (_daily_indicators_bulk) computes
real MA/RSI/MACD/BandarScore for the whole universe and is merged into the
live snapshot. Real intraday VWAP is computed directly from the 5-min bars
already downloaded for the price snapshot (no extra HTTP calls needed).

Both the intraday price pull and the new indicator pull are now CHUNKED and
run in parallel batches, so a full 700+ ticker universe is actually covered
instead of relying on one unbounded yf.download() call that risks silent
partial failures / timeouts under GitHub Actions constraints.
"""

import math
import hashlib
import logging
from collections import Counter
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import pytz
import yfinance as yf

logger = logging.getLogger(__name__)
WIB = pytz.timezone("Asia/Jakarta")

# ── Historical data cache (charts, indicators) ─────────────────────────────
_cache: dict = {}
_cache_time: dict = {}
CACHE_TTL = 300  # 5 min — historical daily data

# ── Realtime snapshot cache ─────────────────────────────────────────────────
_snapshot_cache: dict = {}
_snapshot_cache_time: dict = {}
SNAPSHOT_TTL = 90  # 90 sec — intraday snapshot

# ── Daily-bar indicator cache (MA/RSI/MACD/BandarScore) ─────────────────────
_indicator_cache: dict = {}
_indicator_cache_time: dict = {}
INDICATOR_TTL = 900  # 15 min — indicators don't need 90s freshness

MAX_DATA_AGE_MIN = 20  # mark data stale if older than this

# ── Batching config (keeps full-universe scans reliable & within timeouts) ──
BATCH_SIZE = 100
MAX_WORKERS = 4


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _safe_num(v, default: float = 0.0) -> float:
    """Return a clean float, replacing None / NaN / inf with default."""
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _is_fresh(key: str) -> bool:
    if key not in _cache_time:
        return False
    return (datetime.now() - _cache_time[key]).total_seconds() < CACHE_TTL


def _is_snapshot_fresh(key: str) -> bool:
    if key not in _snapshot_cache_time:
        return False
    return (datetime.now() - _snapshot_cache_time[key]).total_seconds() < SNAPSHOT_TTL


def _is_indicator_fresh(key: str) -> bool:
    if key not in _indicator_cache_time:
        return False
    return (datetime.now() - _indicator_cache_time[key]).total_seconds() < INDICATOR_TTL


def _chunk(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _tickers_key(tickers: list) -> str:
    """
    Stable cache key derived from the ACTUAL ticker set, not just its length.
    Fixes a bug where two unrelated callers requesting different tickers of
    the same list length (e.g. a user's watchlist vs. a quick top-40 scan)
    could silently receive each other's cached snapshot within the TTL window.
    """
    joined = ",".join(sorted(set(tickers)))
    return hashlib.md5(joined.encode()).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────────────────────
# Historical data (charts, EMA/RSI/MACD, golden cross) — unchanged
# ─────────────────────────────────────────────────────────────────────────────
def get_stock_data(ticker: str, period: str = "3mo") -> pd.DataFrame | None:
    key = f"{ticker}_{period}"
    if _is_fresh(key):
        return _cache[key]
    try:
        t = yf.Ticker(f"{ticker}.JK")
        df = t.history(period=period)
        if df.empty:
            return None
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)
        _cache[key] = df
        _cache_time[key] = datetime.now()
        return df
    except Exception as e:
        logger.warning(f"get_stock_data failed {ticker}: {e}")
        return None


def get_stock_info(ticker: str) -> dict:
    key = f"info_{ticker}"
    if _is_fresh(key):
        return _cache[key]
    try:
        t = yf.Ticker(f"{ticker}.JK")
        info = t.info or {}
        _cache[key] = info
        _cache_time[key] = datetime.now()
        return info
    except Exception:
        return {}


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]
    volume = df["Volume"]

    df["MA5"] = close.rolling(5).mean()
    df["MA20"] = close.rolling(20).mean()
    df["MA50"] = close.rolling(50).mean()
    df["VolMA5"] = volume.rolling(5).mean()
    df["VolMA20"] = volume.rolling(20).mean()

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

    # VWAP (20-bar rolling, daily-bar approximation — real intraday VWAP is
    # computed separately in _intraday_bulk from 5-min bars)
    vol_safe = volume.replace(0, np.nan)
    df["VWAP"] = (close * volume).rolling(20).sum() / vol_safe.rolling(20).sum()

    # Relative Volume
    df["RelVol"] = volume / df["VolMA20"].replace(0, np.nan)

    # Bandar A/D score (CLV-based)
    high = df["High"]
    low = df["Low"]
    hl_rng = (high - low).replace(0, np.nan)
    clv = ((close - low) - (high - close)) / hl_rng
    df["AccDist"] = (clv * volume).cumsum()
    df["BandarScore"] = clv.rolling(5).mean() * 100

    return df


def _compute_indicator_row(df: pd.DataFrame) -> dict:
    """Given an ascending-sorted daily OHLCV dataframe, return the latest-bar
    indicator snapshot (MA/RSI/MACD/BandarScore) as plain floats."""
    if df is None or len(df) < 5:
        return {}
    try:
        df = compute_indicators(df)
        last = df.iloc[-1]
        return {
            "ma5": _safe_num(last.get("MA5")) or None,
            "ma20": _safe_num(last.get("MA20")) or None,
            "ma50": _safe_num(last.get("MA50")) or None,
            "vol_ma5": _safe_num(last.get("VolMA5")) or None,
            "vol_ma20": _safe_num(last.get("VolMA20")) or None,
            "rsi": _safe_num(last.get("RSI"), 50.0),
            "macd": _safe_num(last.get("MACD")),
            "macd_signal": _safe_num(last.get("MACD_Signal")),
            "bandar_score": _safe_num(last.get("BandarScore")),
        }
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Batched daily-bar indicator pull (MA/RSI/MACD/BandarScore for FULL universe)
# ─────────────────────────────────────────────────────────────────────────────
def _fetch_daily_batch(jk_batch: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    try:
        raw = yf.download(
            jk_batch, period="4mo", interval="1d",
            progress=False, auto_adjust=True, group_by="ticker", threads=True,
        )
    except Exception as e:
        logger.warning(f"Daily indicator batch failed ({len(jk_batch)} tickers): {e}")
        return out

    if raw is None or raw.empty:
        return out

    for jk_t in jk_batch:
        try:
            if len(jk_batch) == 1:
                df = raw
            else:
                if jk_t not in set(raw.columns.get_level_values(0)):
                    continue
                df = raw[jk_t]
            df = df.dropna(how="all")
            if df.empty:
                continue
            out[jk_t] = _compute_indicator_row(df)
        except Exception as e:
            logger.debug(f"Daily indicator parse error {jk_t}: {e}")
    return out


def _daily_indicators_bulk(tickers: list[str]) -> dict[str, dict]:
    """
    Batched + parallel daily-bar download to compute MA5/MA20/MA50/VolMA5/
    VolMA20/RSI/MACD/BandarScore for the whole scanned universe.
    Cached for INDICATOR_TTL (15 min) — these don't need 90s-fresh updates,
    so this is far cheaper than re-downloading every snapshot cycle.
    """
    cache_key = f"_daily_ind_{_tickers_key(tickers)}"
    if _is_indicator_fresh(cache_key):
        return _indicator_cache[cache_key]

    jk_map = {t: f"{t}.JK" for t in tickers}
    batches = list(_chunk(list(jk_map.values()), BATCH_SIZE))

    merged: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(_fetch_daily_batch, b) for b in batches]
        for fut in as_completed(futures):
            try:
                merged.update(fut.result())
            except Exception as e:
                logger.warning(f"Daily indicator batch worker error: {e}")

    base_results = {
        base_t: merged[jk_t] for base_t, jk_t in jk_map.items() if jk_t in merged
    }

    _indicator_cache[cache_key] = base_results
    _indicator_cache_time[cache_key] = datetime.now()
    logger.info(f"Daily indicators ready: {len(base_results)}/{len(tickers)} tickers "
                f"({len(batches)} batches)")
    return base_results


# ─────────────────────────────────────────────────────────────────────────────
# Realtime market snapshot (intraday 5-min bars, batched bulk download)
# ─────────────────────────────────────────────────────────────────────────────
def _fetch_intraday_batch(jk_batch: list[str], jk_to_base: dict[str, str]) -> dict[str, dict]:
    """
    Download 5-min intraday bars for one batch of tickers.
    Returns {base_ticker: {price, prev_close, pct_chg, volume, prev_volume,
    rel_vol, open, high, low, vwap, data_ts, data_age_min}}
    """
    today_d = datetime.now(WIB).date()
    try:
        raw = yf.download(
            jk_batch, period="2d", interval="5m",
            progress=False, auto_adjust=True, threads=True,
        )
    except Exception as e:
        logger.warning(f"Intraday batch failed ({len(jk_batch)} tickers): {e}")
        return {}

    if raw is None or raw.empty:
        return {}

    try:
        close_df = raw["Close"]
        volume_df = raw["Volume"]
        open_df = raw["Open"]
        high_df = raw["High"]
        low_df = raw["Low"]
    except KeyError as e:
        logger.warning(f"Field access error in intraday batch: {e}")
        return {}

    if isinstance(close_df, pd.Series):
        only_t = jk_batch[0]
        close_df = close_df.to_frame(name=only_t)
        volume_df = volume_df.to_frame(name=only_t)
        open_df = open_df.to_frame(name=only_t)
        high_df = high_df.to_frame(name=only_t)
        low_df = low_df.to_frame(name=only_t)

    results: dict[str, dict] = {}
    for jk_t in jk_batch:
        base_t = jk_to_base.get(jk_t)
        if base_t is None or jk_t not in close_df.columns:
            continue
        try:
            closes = close_df[jk_t].dropna()
            volumes = volume_df[jk_t]
            if closes.empty:
                continue

            idx_wib = closes.index.tz_convert(WIB)
            today_m = pd.array([d == today_d for d in idx_wib.date])
            yest_m = pd.array([d != today_d for d in idx_wib.date])
            if not any(today_m):
                continue

            today_closes = closes[today_m]
            today_volumes = volumes[today_m].fillna(0)
            current_price = _safe_num(today_closes.iloc[-1])
            current_vol = _safe_num(today_volumes.sum())
            data_ts = idx_wib[today_m][-1]

            now_wib = datetime.now(WIB)
            data_age_min = (now_wib - data_ts).total_seconds() / 60

            if any(yest_m):
                yest_closes = closes[yest_m]
                yest_volumes = volumes[yest_m].fillna(0)
                prev_close = _safe_num(yest_closes.iloc[-1], current_price)
                prev_vol = _safe_num(yest_volumes.sum(), current_vol or 1)
            else:
                prev_close = _safe_num(today_closes.iloc[0], current_price) if len(today_closes) > 1 else current_price
                prev_vol = current_vol or 1

            pct_chg = (current_price - prev_close) / prev_close * 100 if prev_close else 0.0
            rel_vol = _safe_num(current_vol / prev_vol if prev_vol > 0 else 1.0, 1.0)

            today_opens = open_df[jk_t][today_m].dropna()
            today_highs = high_df[jk_t][today_m].dropna()
            today_lows = low_df[jk_t][today_m].dropna()

            # Real intraday VWAP from today's 5-min bars (no extra HTTP call needed)
            vol_sum = today_volumes.sum()
            vwap = _safe_num((today_closes * today_volumes).sum() / vol_sum) if vol_sum else None

            results[base_t] = {
                "price": current_price,
                "prev_price": prev_close,
                "pct_chg": pct_chg,
                "volume": current_vol,
                "prev_volume": prev_vol,
                "open": _safe_num(today_opens.iloc[0]) if not today_opens.empty else current_price,
                "high": _safe_num(today_highs.max()) if not today_highs.empty else current_price,
                "low": _safe_num(today_lows.min()) if not today_lows.empty else current_price,
                "rel_vol": rel_vol,
                "vwap": vwap,
                "data_ts": data_ts,
                "data_age_min": data_age_min,
            }
        except Exception as e:
            logger.debug(f"Intraday parse error {base_t}: {e}")

    return results


def _intraday_bulk(tickers: list[str]) -> dict[str, dict]:
    """
    Batched + parallel intraday download so the full scanned universe (e.g.
    700+ IDX stocks) is covered reliably instead of one unbounded
    yf.download() call.
    """
    jk_map = {t: f"{t}.JK" for t in tickers}
    jk_to_base = {v: k for k, v in jk_map.items()}
    batches = list(_chunk(list(jk_map.values()), BATCH_SIZE))

    merged: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(_fetch_intraday_batch, b, jk_to_base) for b in batches]
        for fut in as_completed(futures):
            try:
                merged.update(fut.result())
            except Exception as e:
                logger.warning(f"Intraday batch worker error: {e}")

    logger.info(f"Intraday bulk: {len(merged)}/{len(tickers)} tickers loaded "
                f"({len(batches)} batches)")
    return merged


def _snapshot_from_daily(tickers: list[str]) -> list[dict]:
    """
    Fallback: per-ticker daily data snapshot (old method).
    Used for any tickers the batched intraday pull couldn't cover.
    """
    results = []
    for ticker in tickers:
        try:
            df = get_stock_data(ticker, period="5d")
            if df is None or len(df) < 2:
                continue
            df = compute_indicators(df)
            latest = df.iloc[-1]
            prev = df.iloc[-2]

            price = _safe_num(latest["Close"])
            prev_price = _safe_num(prev["Close"], price)
            pct_chg = (price - prev_price) / prev_price * 100 if prev_price else 0.0
            volume = _safe_num(latest["Volume"])
            vol_ma20 = _safe_num(latest.get("VolMA20"))
            rel_vol = _safe_num(volume / vol_ma20 if vol_ma20 > 0 else 1.0, 1.0)

            results.append({
                "ticker": ticker,
                "price": price,
                "prev_price": prev_price,
                "pct_chg": pct_chg,
                "volume": volume,
                "prev_volume": _safe_num(prev["Volume"]),
                "value": price * volume,
                "open": _safe_num(latest["Open"]),
                "high": _safe_num(latest["High"]),
                "low": _safe_num(latest["Low"]),
                "ma5": _safe_num(latest.get("MA5")) or None,
                "ma20": _safe_num(latest.get("MA20")) or None,
                "ma50": _safe_num(latest.get("MA50")) or None,
                "vol_ma20": vol_ma20 or None,
                "vol_ma5": _safe_num(latest.get("VolMA5")) or None,
                "rsi": _safe_num(latest.get("RSI"), 50.0),
                "macd": _safe_num(latest.get("MACD")),
                "macd_signal": _safe_num(latest.get("MACD_Signal")),
                "rel_vol": rel_vol,
                "bandar_score": _safe_num(latest.get("BandarScore")),
                "vwap": _safe_num(latest.get("VWAP")),
                "data_ts": None,
                "data_age_min": 999,
                "data_source": "yahoo_finance_daily_fallback",
                "timestamp": str(latest.name),
            })
        except Exception as e:
            logger.debug(f"Daily snapshot error {ticker}: {e}")
    return results


def get_market_snapshot(tickers: list, _context: str = "") -> list[dict]:
    """
    Returns a fresh realtime snapshot for every ticker, WITH real indicators.

    Primary path: batched bulk intraday download (price/volume/VWAP) merged
    with batched daily-bar indicators (MA/RSI/MACD/BandarScore).
    Fallback: per-ticker daily data for any ticker either pull couldn't cover.

    Each result dict has:
      ticker, price, prev_price, pct_chg, volume, prev_volume, value,
      open, high, low, ma5, ma20, ma50, vol_ma5, vol_ma20, rsi, macd,
      macd_signal, rel_vol, bandar_score, vwap, data_ts, data_age_min
    """
    cache_key = f"_bulk_snapshot_{_tickers_key(tickers)}"
    if _is_snapshot_fresh(cache_key):
        return _snapshot_cache[cache_key]

    logger.info(f"Fetching realtime intraday snapshot for {len(tickers)} tickers…")
    intraday = _intraday_bulk(tickers)
    daily_ind = _daily_indicators_bulk(tickers)

    results: list[dict] = []
    missing: list[str] = []

    for t in tickers:
        if t in intraday:
            d = intraday[t]
            ind = daily_ind.get(t, {})
            results.append({
                "ticker": t,
                "price": d["price"],
                "prev_price": d["prev_price"],
                "pct_chg": d["pct_chg"],
                "volume": d["volume"],
                "prev_volume": d["prev_volume"],
                "value": d["price"] * d["volume"],
                "open": d["open"],
                "high": d["high"],
                "low": d["low"],
                "ma5": ind.get("ma5"),
                "ma20": ind.get("ma20"),
                "ma50": ind.get("ma50"),
                "vol_ma20": ind.get("vol_ma20"),
                "vol_ma5": ind.get("vol_ma5"),
                "rsi": ind.get("rsi"),
                "macd": ind.get("macd"),
                "macd_signal": ind.get("macd_signal"),
                "rel_vol": d["rel_vol"],
                "bandar_score": ind.get("bandar_score"),
                "vwap": d.get("vwap"),
                "data_ts": d.get("data_ts"),
                "data_age_min": d.get("data_age_min", 0),
                "data_source": "yahoo_finance_intraday",
                "timestamp": str(d.get("data_ts", "")),
            })
        else:
            missing.append(t)

    if missing:
        logger.info(f"Fallback to daily for {len(missing)} tickers")
        fallback = _snapshot_from_daily(missing)
        results.extend(fallback)

    _snapshot_cache[cache_key] = results
    _snapshot_cache_time[cache_key] = datetime.now()
    logger.info(f"Snapshot ready: {len(results)}/{len(tickers)} tickers "
                f"(intraday={len(intraday)}, indicators={len(daily_ind)}, fallback={len(missing)})")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Sector and data-quality compatibility helpers
# ─────────────────────────────────────────────────────────────────────────────
def get_sector_snapshots(sector_name: str, tickers: list) -> list[dict]:
    """Fetch a sector snapshot while retaining the caller's diagnostic context."""
    return get_market_snapshot(tickers, _context=f"sector:{sector_name}")


def generate_data_report(snapshots: list) -> str:
    """Return a human-readable data quality summary for a snapshot list."""
    if not snapshots:
        return "No data to report."

    total = len(snapshots)
    pcts = [s.get("pct_chg", 0) for s in snapshots]
    counts = Counter(round(p, 2) for p in pcts)
    top_val, top_cnt = counts.most_common(1)[0]
    uniform = top_cnt / total >= 0.60

    lines = [
        "── Data Quality Report ──────────────────",
        f"Stocks        : {total}",
        "Source        : Yahoo Finance (yfinance)",
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


# ─────────────────────────────────────────────────────────────────────────────
# IHSG Index — unchanged
# ─────────────────────────────────────────────────────────────────────────────
def get_ihsg_data() -> dict:
    try:
        t = yf.Ticker("^JKSE")
        df = t.history(period="5d")
        if df.empty:
            return {}
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        price = _safe_num(latest["Close"])
        prev_price = _safe_num(prev["Close"], price)
        pct = (price - prev_price) / prev_price * 100 if prev_price else 0.0
        return {
            "price": price,
            "pct_chg": pct,
            "high": _safe_num(latest["High"]),
            "low": _safe_num(latest["Low"]),
            "volume": _safe_num(latest["Volume"]),
        }
    except Exception as e:
        logger.warning(f"IHSG fetch error: {e}")
        return {}