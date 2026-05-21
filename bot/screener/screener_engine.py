import logging
from bot.services.data_service import get_market_snapshot
from bot.bandarmology.broker_analyzer import estimate_broker_signal
from bot.services.ai_service import generate_full_analysis
from bot.utils.constants import IDX_STOCKS, ALL_IDX_STOCKS

logger = logging.getLogger(__name__)


def _get_sector(ticker: str) -> str:
    for sector, stocks in IDX_STOCKS.items():
        if ticker in stocks:
            return sector
    return "Other"


def _calc_momentum_score(stock: dict) -> float:
    score = 50.0
    price      = stock.get("price", 0)
    pct_chg    = stock.get("pct_chg", 0)
    ma5        = stock.get("ma5")
    ma20       = stock.get("ma20")
    ma50       = stock.get("ma50")
    rel_vol    = stock.get("rel_vol", 1) or 1
    rsi        = stock.get("rsi")
    macd       = stock.get("macd")
    macd_sig   = stock.get("macd_signal")

    if ma5   and price > ma5:            score += 5
    if ma20  and price > ma20:           score += 8
    if ma50  and price > ma50:           score += 5
    if ma20  and ma50 and ma20 > ma50:   score += 7

    if pct_chg > 5:    score += 12
    elif pct_chg > 2:  score += 7
    elif pct_chg > 0:  score += 3
    elif pct_chg < -2: score -= 8

    if rel_vol >= 3:    score += 10
    elif rel_vol >= 2:  score += 7
    elif rel_vol >= 1.5: score += 4

    if rsi:
        if 45 < rsi < 65:  score += 8
        elif rsi > 70:     score -= 5
        elif rsi < 35:     score -= 5

    if macd and macd_sig and macd > macd_sig:
        score += 5

    return max(0, min(100, score))


def _calc_scalp_score(stock: dict) -> float:
    """Special score for scalper — rewards tight range + fast momentum."""
    score = 50.0
    pct_chg  = stock.get("pct_chg", 0)
    rel_vol  = stock.get("rel_vol", 1) or 1
    rsi      = stock.get("rsi")
    macd     = stock.get("macd")
    macd_sig = stock.get("macd_signal")
    high     = stock.get("high")
    low      = stock.get("low")
    price    = stock.get("price", 1) or 1
    vwap     = stock.get("vwap")

    if rel_vol >= 4:    score += 15
    elif rel_vol >= 3:  score += 10
    elif rel_vol >= 2:  score += 6

    if 1.0 <= pct_chg <= 3.0: score += 12
    elif 3.0 < pct_chg <= 4.5: score += 6

    if rsi and 45 <= rsi <= 58: score += 10

    if macd and macd_sig:
        diff = macd - macd_sig
        if diff > 0:
            score += min(10, diff * 5000)

    if high and low:
        rng = (high - low) / price * 100
        if rng < 1.0:   score += 12
        elif rng < 1.5: score += 7
        elif rng < 2.0: score += 3

    if vwap and price > vwap:
        score += 8

    return max(0, min(100, score))


def _calc_volume_score(stock: dict) -> float:
    rel_vol = stock.get("rel_vol", 1) or 1
    if rel_vol >= 3:    return 90
    elif rel_vol >= 2:  return 75
    elif rel_vol >= 1.5: return 60
    elif rel_vol >= 1:  return 45
    return 25


def run_screener(screener_type: str, max_results: int = 10) -> list[dict]:
    from bot.screener.ara_hunter import ara_hunter_filter
    from bot.screener.bsjp import bsjp_filter
    from bot.screener.big_accumulation import big_accumulation_filter
    from bot.screener.scalper_pro import scalper_pro_filter

    filter_map = {
        "ara_hunter":       ara_hunter_filter,
        "bsjp":             bsjp_filter,
        "big_accumulation": big_accumulation_filter,
        "scalper_pro":      scalper_pro_filter,
    }

    fn = filter_map.get(screener_type)
    if not fn:
        return []

    snapshots = get_market_snapshot(ALL_IDX_STOCKS)
    passed = []
    for stock in snapshots:
        try:
            if fn(stock):
                broker         = estimate_broker_signal(stock)
                is_scalp       = screener_type == "scalper_pro"
                momentum_score = _calc_scalp_score(stock) if is_scalp else _calc_momentum_score(stock)
                volume_score   = _calc_volume_score(stock)
                sector         = _get_sector(stock["ticker"])

                enriched = {
                    **stock,
                    "sector":         sector,
                    "broker_signal":  broker["signal"],
                    "broker_detail":  broker,
                    "momentum_score": momentum_score,
                    "volume_score":   volume_score,
                    "foreign_flow":   "Positive" if stock.get("pct_chg", 0) > 1 else "Neutral",
                }
                enriched["ai_analysis"] = generate_full_analysis(enriched, screener_type)
                passed.append(enriched)
        except Exception as e:
            logger.debug(f"Filter error for {stock.get('ticker')}: {e}")

    passed.sort(key=lambda x: x.get("momentum_score", 0), reverse=True)
    return passed[:max_results]
