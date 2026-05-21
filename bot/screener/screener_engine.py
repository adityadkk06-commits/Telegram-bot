"""
Screener engine — collects full matches AND near-miss candidates.
"""
import logging
from bot.services.data_service import get_market_snapshot
from bot.bandarmology.broker_analyzer import estimate_broker_signal
from bot.services.ai_service import generate_full_analysis
from bot.utils.constants import IDX_STOCKS, ALL_IDX_STOCKS

logger = logging.getLogger(__name__)

# Score functions per screener
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


def _momentum_score(stock: dict) -> float:
    score      = 50.0
    price      = stock.get("price", 0)
    pct_chg    = stock.get("pct_chg", 0)
    ma5        = stock.get("ma5")
    ma20       = stock.get("ma20")
    ma50       = stock.get("ma50")
    rel_vol    = stock.get("rel_vol", 1) or 1
    rsi        = stock.get("rsi")
    macd       = stock.get("macd")
    macd_sig   = stock.get("macd_signal")

    if ma5  and price > ma5:           score += 5
    if ma20 and price > ma20:          score += 8
    if ma50 and price > ma50:          score += 5
    if ma20 and ma50 and ma20 > ma50:  score += 7

    if pct_chg > 5:    score += 12
    elif pct_chg > 2:  score += 7
    elif pct_chg > 0:  score += 3
    elif pct_chg < -2: score -= 8

    if rel_vol >= 3:     score += 10
    elif rel_vol >= 2:   score += 7
    elif rel_vol >= 1.5: score += 4

    if rsi:
        if 45 < rsi < 65:  score += 8
        elif rsi > 70:     score -= 5
        elif rsi < 35:     score -= 5

    if macd and macd_sig and macd > macd_sig:
        score += 5

    return max(0, min(100, score))


def _scalp_score(stock: dict) -> float:
    score    = 50.0
    pct_chg  = stock.get("pct_chg", 0)
    rel_vol  = stock.get("rel_vol", 1) or 1
    rsi      = stock.get("rsi")
    macd     = stock.get("macd")
    macd_sig = stock.get("macd_signal")
    high     = stock.get("high")
    low      = stock.get("low")
    price    = stock.get("price", 1) or 1
    vwap     = stock.get("vwap")

    if rel_vol >= 4:     score += 15
    elif rel_vol >= 3:   score += 10
    elif rel_vol >= 2:   score += 6

    if 1.0 <= pct_chg <= 3.0:   score += 12
    elif 3.0 < pct_chg <= 4.5:  score += 6

    if rsi and 45 <= rsi <= 58:  score += 10

    if macd and macd_sig and macd > macd_sig:
        score += min(10, (macd - macd_sig) * 5000)

    if high and low and price > 0:
        rng = (high - low) / price * 100
        if rng < 1.0:    score += 12
        elif rng < 1.5:  score += 7
        elif rng < 2.0:  score += 3

    if vwap and price > vwap:
        score += 8

    return max(0, min(100, score))


def _vol_score(stock: dict) -> float:
    rv = stock.get("rel_vol", 1) or 1
    if rv >= 3:     return 90
    elif rv >= 2:   return 75
    elif rv >= 1.5: return 60
    elif rv >= 1:   return 45
    return 25


def run_screener(
    screener_type: str,
    max_pass: int = 8,
    max_near: int = 5,
) -> dict:
    """
    Returns dict:
      {
        "pass": [...],   # full matches, sorted by momentum score desc
        "near": [...],   # near misses, sorted by filter_pct desc
      }
    Each item has all stock fields PLUS:
      filter_result, filter_pct, status, sector,
      broker_signal, broker_detail, momentum_score, volume_score,
      foreign_flow, ai_analysis, near_summary
    """
    score_fn = _get_score_fn(screener_type)
    if not score_fn:
        return {"pass": [], "near": []}

    snapshots = get_market_snapshot(ALL_IDX_STOCKS)
    passes = []
    nears  = []

    for stock in snapshots:
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
                "filter_result":  result,
                "filter_pct":     result.pct,
                "status":         result.status,
                "sector":         sector,
                "broker_signal":  broker["signal"],
                "broker_detail":  broker,
                "momentum_score": mom_sc,
                "volume_score":   vol_sc,
                "foreign_flow":   "Positive" if stock.get("pct_chg", 0) > 1 else "Neutral",
                "near_summary":   result.near_summary(3),
            }
            enriched["ai_analysis"] = generate_full_analysis(enriched, screener_type)

            if result.status == "pass":
                passes.append(enriched)
            else:
                nears.append(enriched)

        except Exception as e:
            logger.debug(f"Filter error for {stock.get('ticker')}: {e}")

    passes.sort(key=lambda x: (x["momentum_score"], x["filter_pct"]), reverse=True)
    nears.sort(key=lambda x: x["filter_pct"], reverse=True)

    return {
        "pass": passes[:max_pass],
        "near": nears[:max_near],
    }
