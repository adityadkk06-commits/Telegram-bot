"""
Screener engine — collects full matches AND near-miss candidates.

PATCHED:
  - Real technical indicators (MA5/20/50, RSI, MACD, VWAP, BandarScore) are
    fetched + computed per-candidate BEFORE scoring, instead of relying on the
    always-None placeholder fields returned by get_market_snapshot(). Only a
    bounded, pre-filtered subset of the universe is enriched to keep GitHub
    Actions runtime safe (13 min timeout).
  - "foreign_flow" no longer fakes real foreign-investor data from pct_chg.
    It's now honestly labeled as unavailable (yfinance has no foreign-flow
    field) instead of pretending to be a signal.
"""

import logging

from bot.services.data_service import get_market_snapshot, get_stock_data, compute_indicators
from bot.bandarmology.broker_analyzer import estimate_broker_signal
from bot.services.ai_service import generate_full_analysis
from bot.utils.constants import IDX_STOCKS, ALL_IDX_STOCKS

logger = logging.getLogger(__name__)

_SCORE_FN = {}


def _get_score_fn(screener_type: str):
    """Lazy-load and cache score functions."""
    if screener_type not in _SCORE_FN:
        if screener_type == "ara_hunter":
            from bot.screener.ara_hunter import ara_hunter_score
            _SCORE_FN[screener_type] = ara_hunter_score
        elif screener_type == "bsjp":
            from bot.screener.bsjp import bsjp_score
            _SCORE_FN[screener_type] = bsjp_score
        elif screener_type == "big_accumulation":
            from bot.screener.big_accumulation import big_accumulation_score
            _SCORE_FN[screener_type] = big_accumulation_score
        elif screener_type == "scalper_pro":
            from bot.screener.scalper_pro import scalper_pro_score
            _SCORE_FN[screener_type] = scalper_pro_score
    return _SCORE_FN.get(screener_type)


def _get_sector(ticker: str) -> str:
    for sector, stocks in IDX_STOCKS.items():
        if ticker in stocks:
            return sector
    return "Other"


# Fetching 3mo history for all ~130 tickers every 15-min cycle is too slow.
MIN_ENRICH_VALUE = 1_000_000_000
MAX_ENRICH_CANDIDATES = 40


def _quick_prefilter(snapshots: list) -> list:
    """Cheap filter using only snapshot-native (non-None) fields."""
    candidates = [
        s for s in snapshots
        if s.get("price", 0) > 0
        and abs(s.get("pct_chg", 0) or 0) > 0.1
        and (s.get("value", 0) or 0) >= MIN_ENRICH_VALUE
    ]
    candidates.sort(
        key=lambda x: (
            abs(x.get("pct_chg", 0) or 0),
            x.get("value", 0) or 0,
        ),
        reverse=True,
    )
    return candidates[:MAX_ENRICH_CANDIDATES]


def _enrich_with_real_indicators(stock: dict) -> dict:
    """
    Return a copy with real indicator values replacing the snapshot placeholders.
    Fall back to the original dict when history is unavailable.
    """
    ticker = stock.get("ticker")
    enriched = dict(stock)
    try:
        df = get_stock_data(ticker, period="3mo")
        if df is None or len(df) < 22:
            return enriched
        df = compute_indicators(df)
        latest = df.iloc[-1]

        def _f(col, default=None):
            v = latest.get(col)
            try:
                return float(v) if v is not None and v == v else default
            except (TypeError, ValueError):
                return default

        enriched["ma5"] = _f("MA5")
        enriched["ma20"] = _f("MA20")
        enriched["ma50"] = _f("MA50")
        enriched["vol_ma5"] = _f("VolMA5")
        enriched["vol_ma20"] = _f("VolMA20")
        enriched["rsi"] = _f("RSI", 50.0)
        enriched["macd"] = _f("MACD", 0.0)
        enriched["macd_signal"] = _f("MACD_Signal", 0.0)
        enriched["vwap"] = _f("VWAP")
        enriched["bandar_score"] = _f("BandarScore", 0.0)
    except Exception as e:
        logger.debug(f"Indicator enrichment failed for {ticker}: {e}")
    return enriched


def _momentum_score(stock: dict) -> float:
    score = 50.0
    price = stock.get("price", 0)
    pct_chg = stock.get("pct_chg", 0)
    ma5 = stock.get("ma5")
    ma20 = stock.get("ma20")
    ma50 = stock.get("ma50")
    rel_vol = stock.get("rel_vol", 1) or 1
    rsi = stock.get("rsi")
    macd = stock.get("macd")
    macd_sig = stock.get("macd_signal")

    if ma5 and price > ma5:
        score += 5
    if ma20 and price > ma20:
        score += 8
    if ma50 and price > ma50:
        score += 5
    if ma20 and ma50 and ma20 > ma50:
        score += 7
    if pct_chg > 5:
        score += 12
    elif pct_chg > 2:
        score += 7
    elif pct_chg > 0:
        score += 3
    elif pct_chg < -2:
        score -= 8
    if rel_vol >= 3:
        score += 10
    elif rel_vol >= 2:
        score += 7
    elif rel_vol >= 1.5:
        score += 4
    if rsi:
        if 45 < rsi < 65:
            score += 8
        elif rsi > 70 or rsi < 35:
            score -= 5
    if macd and macd_sig and macd > macd_sig:
        score += 5
    return max(0, min(100, score))


def _scalp_score(stock: dict) -> float:
    score = 50.0
    pct_chg = stock.get("pct_chg", 0)
    rel_vol = stock.get("rel_vol", 1) or 1
    rsi = stock.get("rsi")
    macd = stock.get("macd")
    macd_sig = stock.get("macd_signal")
    high = stock.get("high")
    low = stock.get("low")
    price = stock.get("price", 1) or 1
    vwap = stock.get("vwap")

    if rel_vol >= 4:
        score += 15
    elif rel_vol >= 3:
        score += 10
    elif rel_vol >= 2:
        score += 6
    if 1.0 <= pct_chg <= 3.0:
        score += 12
    elif 3.0 < pct_chg <= 4.5:
        score += 6
    if rsi and 45 <= rsi <= 58:
        score += 10
    if macd and macd_sig and macd > macd_sig:
        score += min(10, (macd - macd_sig) * 5000)
    if high and low and price > 0:
        rng = (high - low) / price * 100
        if rng < 1.0:
            score += 12
        elif rng < 1.5:
            score += 7
        elif rng < 2.0:
            score += 3
    if vwap and price > vwap:
        score += 8
    return max(0, min(100, score))


def _vol_score(stock: dict) -> float:
    rv = stock.get("rel_vol", 1) or 1
    if rv >= 3:
        return 90
    if rv >= 2:
        return 75
    if rv >= 1.5:
        return 60
    if rv >= 1:
        return 45
    return 25


def run_screener(
    screener_type: str,
    max_pass: int = 8,
    max_near: int = 5,
) -> dict:
    """
    Return full matches and near misses, enriched with real indicators.
    """
    score_fn = _get_score_fn(screener_type)
    if not score_fn:
        return {"pass": [], "near": []}

    snapshots = get_market_snapshot(ALL_IDX_STOCKS)
    candidates = _quick_prefilter(snapshots)
    logger.info(
        f"[{screener_type}] pre-filtered {len(candidates)}/{len(snapshots)} "
        "tickers for indicator enrichment"
    )

    passes = []
    nears = []
    for raw_stock in candidates:
        stock = _enrich_with_real_indicators(raw_stock)
        try:
            result = score_fn(stock)
            if result.status == "fail":
                continue

            broker = estimate_broker_signal(stock)
            is_scalp = screener_type == "scalper_pro"
            mom_sc = _scalp_score(stock) if is_scalp else _momentum_score(stock)
            vol_sc = _vol_score(stock)
            sector = _get_sector(stock["ticker"])
            enriched = {
                **stock,
                "filter_result": result,
                "filter_pct": result.pct,
                "status": result.status,
                "sector": sector,
                "broker_signal": broker["signal"],
                "broker_detail": broker,
                "broker_is_simulated": True,
                "momentum_score": mom_sc,
                "volume_score": vol_sc,
                "foreign_flow": "N/A (data source has no foreign-flow field)",
                "near_summary": result.near_summary(3),
            }
            enriched["ai_analysis"] = generate_full_analysis(enriched, screener_type)

            if result.status == "pass":
                passes.append(enriched)
            else:
                nears.append(enriched)
        except Exception as e:
            logger.debug(f"Filter error for {raw_stock.get('ticker')}: {e}")

    passes.sort(key=lambda x: (x["momentum_score"], x["filter_pct"]), reverse=True)
    nears.sort(key=lambda x: x["filter_pct"], reverse=True)
    return {"pass": passes[:max_pass], "near": nears[:max_near]}