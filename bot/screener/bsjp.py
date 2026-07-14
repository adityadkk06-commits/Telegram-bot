"""
BSJP screener — scoring version.

Original rules:
  Value  > 10B
  Volume > 1.2 × prev_volume
  Price  > MA20
  MA20   > MA50
  Price  > 1.01 × prev_price
  Price  >= MA5
  Volume > 2 × VolMA20
  (Net foreign buy streak ≥2 — approximated as price+volume momentum)
"""
from bot.screener.filter_engine import FilterResult


def bsjp_score(stock: dict) -> FilterResult:
    r           = FilterResult()
    price       = stock.get("price") or 0
    prev_price  = stock.get("prev_price") or 0
    value       = stock.get("value") or 0
    volume      = stock.get("volume") or 0
    prev_volume = stock.get("prev_volume") or volume
    ma5         = stock.get("ma5") or 0
    ma20        = stock.get("ma20") or 0
    ma50        = stock.get("ma50") or 0
    vol_ma20    = stock.get("vol_ma20") or 0
    rel_vol     = stock.get("rel_vol") or 1

    if not price or not prev_price:
        r.status = "fail"; return r

    pct_chg = (price - prev_price) / prev_price * 100

    # 1. Value > 10B  (14 pts) — near: >4B
    r.add("Value>10B", 14, 8,
          value >= 10_000_000_000,
          value >= 4_000_000_000,
          f"value {value/1e9:.1f}B (need ≥10B)")

    # 2. Volume > 1.2× prev_vol  (14 pts) — near: >0.85
    if prev_volume:
        vol_prev_ratio = volume / prev_volume
        r.add("Vol>1.2×prev", 14, 8,
              vol_prev_ratio >= 1.2,
              vol_prev_ratio >= 0.85,
              f"vol {vol_prev_ratio:.2f}× prev (need ≥1.20)")
    else:
        r.add_missing("Vol>1.2×prev", 14)

    # 3. Price > MA20  (14 pts) — near: within -2%
    if ma20:
        gap = (price - ma20) / ma20 * 100
        r.add("Price>MA20", 14, 8,
              price > ma20,
              price >= ma20 * 0.98,
              f"{abs(gap):.1f}% below MA20 ({ma20:,.0f})")
    else:
        r.add_missing("Price>MA20", 14)

    # 4. MA20 > MA50  (14 pts) — near: within -2%
    if ma20 and ma50:
        gap = (ma20 - ma50) / ma50 * 100
        r.add("MA20>MA50", 14, 8,
              ma20 > ma50,
              ma20 >= ma50 * 0.98,
              f"MA20 is {abs(gap):.1f}% {'above' if gap>=0 else 'below'} MA50")
    else:
        r.add_missing("MA20>MA50", 14)

    # 5. Price > 1.01× prev  (10 pts) — near: >1.002
    r.add("Gain>1%", 10, 5,
          pct_chg >= 1.0,
          pct_chg >= 0.2,
          f"+{pct_chg:.2f}% (need ≥1%)")

    # 6. Price >= MA5  (14 pts) — near: within -1%
    if ma5:
        gap = (price - ma5) / ma5 * 100
        r.add("Price≥MA5", 14, 8,
              price >= ma5,
              price >= ma5 * 0.99,
              f"{abs(gap):.1f}% below MA5 ({ma5:,.0f})")
    else:
        r.add_missing("Price≥MA5", 14)

    # 7. Volume > 2× VolMA20  (14 pts) — near: >1.2
    if vol_ma20:
        r.add("Vol>2×MA20", 14, 8,
              rel_vol >= 2.0,
              rel_vol >= 1.2,
              f"RelVol {rel_vol:.2f}× (need ≥2.0)")
    else:
        r.add_missing("Vol>2×MA20", 14)

    # 8. Price+Vol momentum proxy (replaces foreign buy, labelled honestly)
    momentum_signal = pct_chg > 0.5 and rel_vol > 1.2
    r.add("Momentum+Vol", 6, 3,
          momentum_signal,
          pct_chg > 0,
          "no positive price+volume momentum")

    return r.finalise()


def bsjp_output(stock: dict) -> dict:
    """
    Trade setup for a BSJP breakout candidate.
    Entry near current price, TP using 2.5×/5× ATR proxy, SL below MA5.
    """
    price  = stock.get("price") or 0
    ma5    = stock.get("ma5") or price * 0.98
    ma20   = stock.get("ma20") or price * 0.96
    high   = stock.get("high") or price
    low    = stock.get("low") or price
    if not price:
        return {}

    # ATR proxy: today's high-low range
    atr_proxy = max(high - low, price * 0.01)

    entry_low  = round(price * 1.000, 0)
    entry_high = round(price * 1.008, 0)
    tp1        = round(price + 2.5 * atr_proxy, 0)
    tp2        = round(price + 5.0 * atr_proxy, 0)
    sl         = round(min(ma5 * 0.995, price * 0.970), 0)
    rr         = round((tp1 - price) / max(price - sl, 1), 2)

    # Trend quality: how far MA20 is above MA50
    ma50       = stock.get("ma50") or ma20
    trend_gap  = ((ma20 - ma50) / ma50 * 100) if ma50 else 0
    if trend_gap > 3:   trend_quality = "Strong Uptrend"
    elif trend_gap > 0: trend_quality = "Mild Uptrend"
    elif trend_gap > -2:trend_quality = "Flat / Consolidating"
    else:               trend_quality = "Downtrend"

    return {
        "entry_low":     entry_low,
        "entry_high":    entry_high,
        "tp1":           tp1,
        "tp2":           tp2,
        "sl":            sl,
        "rr":            rr,
        "risk_level":    "Medium",
        "trend_quality": trend_quality,
    }


def bsjp_filter(stock: dict) -> bool:
    return bsjp_score(stock).status == "pass"
