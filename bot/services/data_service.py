import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

_cache: dict = {}
_cache_time: dict = {}
CACHE_TTL = 300  # 5 minutes


def _is_fresh(key: str) -> bool:
    if key not in _cache_time:
        return False
    return (datetime.now() - _cache_time[key]).total_seconds() < CACHE_TTL


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
        logger.warning(f"Failed to fetch {ticker}: {e}")
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
    close  = df["Close"]
    volume = df["Volume"]

    df["MA5"]    = close.rolling(5).mean()
    df["MA20"]   = close.rolling(20).mean()
    df["MA50"]   = close.rolling(50).mean()
    df["VolMA5"] = volume.rolling(5).mean()
    df["VolMA20"]= volume.rolling(20).mean()

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

    # Bandar A/D score (CLV-based)
    high    = df["High"]
    low     = df["Low"]
    hl_rng  = (high - low).replace(0, np.nan)
    clv     = ((close - low) - (high - close)) / hl_rng
    df["AccDist"]    = (clv * volume).cumsum()
    df["BandarScore"]= clv.rolling(5).mean() * 100

    return df


def get_market_snapshot(tickers: list) -> list[dict]:
    results = []
    for ticker in tickers:
        try:
            df = get_stock_data(ticker, period="5d")
            if df is None or len(df) < 2:
                continue
            df = compute_indicators(df)
            latest = df.iloc[-1]
            prev   = df.iloc[-2]

            price      = latest["Close"]
            prev_price = prev["Close"]
            pct_chg    = (price - prev_price) / prev_price * 100 if prev_price else 0
            volume     = latest["Volume"]
            prev_volume= prev["Volume"]          # ← real previous-day volume (bug fix)
            value      = price * volume

            results.append({
                "ticker":       ticker,
                "price":        price,
                "prev_price":   prev_price,
                "pct_chg":      pct_chg,
                "volume":       volume,
                "prev_volume":  prev_volume,     # ← now always available
                "value":        value,
                "open":         latest["Open"],
                "high":         latest["High"],
                "low":          latest["Low"],
                "ma5":          latest.get("MA5"),
                "ma20":         latest.get("MA20"),
                "ma50":         latest.get("MA50"),
                "vol_ma20":     latest.get("VolMA20"),
                "vol_ma5":      latest.get("VolMA5"),
                "rsi":          latest.get("RSI"),
                "macd":         latest.get("MACD"),
                "macd_signal":  latest.get("MACD_Signal"),
                "rel_vol":      latest.get("RelVol"),
                "bandar_score": latest.get("BandarScore"),
                "vwap":         latest.get("VWAP"),
            })
        except Exception as e:
            logger.debug(f"Snapshot error for {ticker}: {e}")
    return results


def get_ihsg_data() -> dict:
    try:
        t  = yf.Ticker("^JKSE")
        df = t.history(period="5d")
        if df.empty:
            return {}
        latest     = df.iloc[-1]
        prev       = df.iloc[-2] if len(df) > 1 else latest
        price      = latest["Close"]
        prev_price = prev["Close"]
        pct        = (price - prev_price) / prev_price * 100
        return {
            "price":    price,
            "pct_chg":  pct,
            "high":     latest["High"],
            "low":      latest["Low"],
            "volume":   latest["Volume"],
        }
    except Exception as e:
        logger.warning(f"IHSG fetch error: {e}")
        return {}
