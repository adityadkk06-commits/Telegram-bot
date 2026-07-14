"""
ARA HUNTER screener — scoring version.

Original rules (strict):
  Price > MA5
  Price > 1.05 × prev_price  (near ARA — dynamic per price band)
  Price > Open
  Volume > 0.2 × prev_volume     (uses REAL previous-day volume)
  Value  > 5 Billion IDR
"""
from bot.screener.filter_engine import FilterResult


def _ara_limit(price: float) -> float:
    """
    IDX Auto-Rejection Above (ARA) limit by price band.
      < Rp 200   → +35%
      200–5000   → +25%
      > Rp 5000  → +20%
    """
    if price < 200:   return 35.0
    if price <= 5000: return 25.0
    return 20.0


def ara_hunter_score(stock: dict) -> FilterResult:
    r           = FilterResult()
    price       = stock.get("price") or 0
    prev_price  = stock.get("prev_price") or 0
    open_price  = stock.get("open") or 0
    volume      = stock.get("volume") or 0
    prev_volume = stock.get("prev_volume") or volume
    value       = stock.get("value") or 0
    ma5         = stock.get("ma5") or 0

    if not price or not prev_price:
        r.status = "fail"; return r

    pct_chg   = (price - prev_price) / prev_price * 100
    ara_limit = _ara_limit(price)

    # 1. Price > MA5  (20 pts)
    if ma5:
        gap = (price - ma5) / ma5 * 100
        r.add("Price>MA5", 20, 12,
              price > ma5,
              price >= ma5 * 0.98,
              f"price is {abs(gap):.1f}% {'above' if gap>=0 else 'below'} MA5")
    else:
        r.add_missing("Price>MA5", 20)

    # 2. Near ARA — dynamic per price band (25 pts) — near: >1%
    near_ara  = pct_chg >= (ara_limit * 0.80)   # within 20% of ARA limit
    close_ara = pct_chg >= 1.0
    r.add("NearARA", 25, 14,
          near_ara,
          close_ara,
          f"+{pct_chg:.2f}% (need ≥{ara_limit*0.80:.1f}% for this price band, ARA={ara_limit:.0f}%)")

    # 3. Price > Open  (15 pts) — near: within -0.5%
    if open_price:
        above_open = (price - open_price) / open_price * 100
        r.add("Price>Open", 15, 8,
              price > open_price,
              price >= open_price * 0.995,
              f"{abs(above_open):.1f}% below open")
    else:
        r.add_missing("Price>Open", 15)

    # 4. Volume > 0.2× prev_day_vol  (15 pts) — near: >0.1
    if prev_volume:
        vol_ratio = volume / prev_volume
        r.add("Vol>0.2×prev", 15, 8,
              vol_ratio >= 0.2,
              vol_ratio >= 0.1,
              f"vol ratio {vol_ratio:.2f} (need ≥0.20)")
    else:
        r.add_missing("Vol>0.2×prev", 15)

    # 5. Value > 5B IDR  (25 pts) — near: >1.5B
    r.add("Value>5B", 25, 14,
          value >= 5_000_000_000,
          value >= 1_500_000_000,
          f"value {value/1e9:.1f}B (need ≥5B)")

    return r.finalise()


def ara_hunter_output(stock: dict) -> dict:
    """
    Compute trade setup for an ARA Hunter candidate.
    Returns entry range, TP1/TP2 (toward ARA), SL, RR, risk level.
    """
    price      = stock.get("price") or 0
    prev_price = stock.get("prev_price") or price
    if not price:
        return {}

    pct_chg   = (price - prev_price) / prev_price * 100 if prev_price else 0
    ara_limit = _ara_limit(price)

    # Entry: chase only within 0.5% of current price
    entry_low  = round(price * 1.000, 0)
    entry_high = round(price * 1.005, 0)

    # TP1: midpoint to ARA; TP2: 85% of ARA limit from current
    remaining_to_ara = ara_limit - pct_chg
    tp1 = round(price * (1 + remaining_to_ara * 0.50 / 100), 0)
    tp2 = round(price * (1 + remaining_to_ara * 0.85 / 100), 0)

    # SL: tight below open or -3% if open not available
    sl  = round(price * 0.970, 0)
    rr  = round((tp1 - price) / max(price - sl, 1), 2)

    risk_level = "High" if pct_chg > 15 else ("Medium" if pct_chg > 5 else "Low")

    return {
        "entry_low":   entry_low,
        "entry_high":  entry_high,
        "tp1":         tp1,
        "tp2":         tp2,
        "sl":          sl,
        "rr":          rr,
        "risk_level":  risk_level,
        "ara_limit":   ara_limit,
    }


def ara_hunter_filter(stock: dict) -> bool:
    return ara_hunter_score(stock).status == "pass"
