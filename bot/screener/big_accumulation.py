"""
BIG ACCUMULATION screener — scoring version.

Original rules:
  BandarScore > 25
  Value > 3B
  MA20 > MA50
  Price < 500
  VolMA5 > 1.3 × VolMA20
  Price > prev_price
"""
from bot.screener.filter_engine import FilterResult


def big_accumulation_score(stock: dict) -> FilterResult:
    r           = FilterResult()
    price       = stock.get("price") or 0
    prev_price  = stock.get("prev_price") or 0
    value       = stock.get("value") or 0
    ma20        = stock.get("ma20") or 0
    ma50        = stock.get("ma50") or 0
    vol_ma5     = stock.get("vol_ma5") or 0
    vol_ma20    = stock.get("vol_ma20") or 0
    bandar_sc   = stock.get("bandar_score")

    if not price or not prev_price:
        r.status = "fail"; return r

    pct_chg = (price - prev_price) / prev_price * 100

    # 1. Bandar A/D score > 25  (22 pts) — near: >10
    if bandar_sc is not None:
        r.add("Bandar>25", 22, 12,
              bandar_sc > 25,
              bandar_sc > 10,
              f"score {bandar_sc:.1f} (need >25)")
    else:
        r.add_missing("Bandar>25", 22)

    # 2. Value > 3B  (16 pts) — near: >1B
    r.add("Value>3B", 16, 9,
          value >= 3_000_000_000,
          value >= 1_000_000_000,
          f"value {value/1e9:.1f}B (need ≥3B)")

    # 3. MA20 > MA50  (22 pts) — near: within -2%
    if ma20 and ma50:
        gap = (ma20 - ma50) / ma50 * 100
        r.add("MA20>MA50", 22, 13,
              ma20 > ma50,
              ma20 >= ma50 * 0.98,
              f"MA20 {abs(gap):.1f}% {'above' if gap>=0 else 'below'} MA50")
    else:
        r.add_missing("MA20>MA50", 22)

    # 4. Price < 500  (14 pts) — near: <800
    r.add("Price<500", 14, 8,
          price < 500,
          price < 800,
          f"price {price:,.0f} (need <500)")

    # 5. VolMA5 > 1.3× VolMA20  (14 pts) — near: >1.05
    if vol_ma20:
        vol_ratio = vol_ma5 / vol_ma20 if vol_ma5 else 0
        r.add("VolMA5>1.3×", 14, 8,
              vol_ratio >= 1.3,
              vol_ratio >= 1.05,
              f"VolMA5/MA20 ratio {vol_ratio:.2f} (need ≥1.3)")
    else:
        r.add_missing("VolMA5>1.3×", 14)

    # 6. Price > prev  (12 pts) — near: within -0.5%
    r.add("Price>prev", 12, 7,
          pct_chg > 0,
          pct_chg >= -0.5,
          f"price {pct_chg:.2f}% vs prev (need >0)")

    return r.finalise()


def big_accumulation_output(stock: dict) -> dict:
    """
    Trade setup for a Big Accumulation (penny/small-cap) candidate.
    Wider TP targets due to lower-price stock volatility.
    """
    price       = stock.get("price") or 0
    ma5         = stock.get("ma5") or price * 0.97
    bandar_sc   = stock.get("bandar_score") or 0
    high        = stock.get("high") or price
    low         = stock.get("low") or price
    if not price:
        return {}

    atr_proxy  = max(high - low, price * 0.015)

    entry_low  = round(price * 1.000, 0)
    entry_high = round(price * 1.010, 0)
    tp1        = round(price + 3.0 * atr_proxy, 0)
    tp2        = round(price + 6.0 * atr_proxy, 0)
    sl         = round(min(ma5 * 0.99, price * 0.965), 0)
    rr         = round((tp1 - price) / max(price - sl, 1), 2)

    # Accumulation strength from BandarScore
    if bandar_sc > 50:     acc_strength = "Very Strong"
    elif bandar_sc > 25:   acc_strength = "Strong"
    elif bandar_sc > 10:   acc_strength = "Moderate"
    else:                  acc_strength = "Weak"

    return {
        "entry_low":            entry_low,
        "entry_high":           entry_high,
        "tp1":                  tp1,
        "tp2":                  tp2,
        "sl":                   sl,
        "rr":                   rr,
        "risk_level":           "Medium",
        "accumulation_strength": acc_strength,
    }


def big_accumulation_filter(stock: dict) -> bool:
    return big_accumulation_score(stock).status == "pass"
