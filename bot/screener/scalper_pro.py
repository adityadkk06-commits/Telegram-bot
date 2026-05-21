"""
SCALPER PRO — Professional intraday scalping screener.

Filters (all must pass):
1.  RelVol  > 2.0          — active volume, market moving
2.  Value   > 2 Billion IDR — enough liquidity for quick in/out
3.  pct_chg ∈ [0.3%, 4.5%] — moving but not overextended
4.  Price   > VWAP         — above intraday fair value (bullish bias)
5.  Price   > MA5          — short-term momentum intact
6.  MA5     > MA20         — trend alignment
7.  RSI     ∈ [38, 63]     — healthy zone, room to run without reversal
8.  MACD    > MACD_Signal  — momentum turning / confirming
9.  BandarScore > 5        — some smart-money interest
10. Intraday range  < 3%   — tight candle = clean setup, controlled risk
"""
from bot.utils.constants import MIN_VALUE_BIG

MIN_VALUE_SCALP = 2_000_000_000   # 2B IDR


def scalper_pro_filter(stock: dict) -> bool:
    price      = stock.get("price")
    prev_price = stock.get("prev_price")
    value      = stock.get("value")
    volume     = stock.get("volume")
    ma5        = stock.get("ma5")
    ma20       = stock.get("ma20")
    rel_vol    = stock.get("rel_vol")
    rsi        = stock.get("rsi")
    macd       = stock.get("macd")
    macd_sig   = stock.get("macd_signal")
    vwap       = stock.get("vwap")
    bandar_sc  = stock.get("bandar_score")
    high       = stock.get("high")
    low        = stock.get("low")

    # Reject if core fields missing
    if not all([price, prev_price, value, volume, ma5, ma20, rel_vol, rsi]):
        return False

    pct_chg = (price - prev_price) / prev_price * 100 if prev_price else 0

    # 1. Volume surge
    if rel_vol < 2.0:
        return False

    # 2. Minimum liquidity
    if value < MIN_VALUE_SCALP:
        return False

    # 3. Price movement in scalp-able range (not too cold, not already pumped)
    if not (0.3 <= pct_chg <= 4.5):
        return False

    # 4. Above VWAP — intraday bullish bias
    if vwap and price < vwap * 0.998:
        return False

    # 5. Price above MA5
    if price < ma5:
        return False

    # 6. MA5 > MA20 — short-term trend alignment
    if ma5 < ma20:
        return False

    # 7. RSI in healthy zone
    if not (38 <= rsi <= 63):
        return False

    # 8. MACD bullish crossover or positive histogram
    if macd is not None and macd_sig is not None:
        if macd < macd_sig:
            return False

    # 9. Some smart-money / bandar interest
    if bandar_sc is not None and bandar_sc < 5:
        return False

    # 10. Tight intraday candle (< 3% H-L range)
    if high and low and price > 0:
        intraday_range = (high - low) / price * 100
        if intraday_range > 3.0:
            return False

    return True
