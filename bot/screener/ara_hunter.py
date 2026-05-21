"""
ARA HUNTER screener — scoring version.

Original rules (strict):
  Price > MA5
  Price > 1.05 × prev_price
  Price > Open
  Volume > 0.2 × prev_volume     (uses REAL previous-day volume now)
  Value  > 5 Billion IDR

Near-miss: ≥58 score out of 100.
"""
from bot.screener.filter_engine import FilterResult


def ara_hunter_score(stock: dict) -> FilterResult:
    r           = FilterResult()
    price       = stock.get("price") or 0
    prev_price  = stock.get("prev_price") or 0
    open_price  = stock.get("open") or 0
    volume      = stock.get("volume") or 0
    prev_volume = stock.get("prev_volume") or volume   # real prev-day vol
    value       = stock.get("value") or 0
    ma5         = stock.get("ma5") or 0

    if not price or not prev_price:
        r.status = "fail"; return r

    pct_chg = (price - prev_price) / prev_price * 100

    # 1. Price > MA5  (20 pts)
    if ma5:
        gap = (price - ma5) / ma5 * 100
        r.add("Price>MA5", 20, 12,
              price > ma5,
              price >= ma5 * 0.98,
              f"price is {abs(gap):.1f}% {'above' if gap>=0 else 'below'} MA5")
    else:
        r.max_score += 20          # no data — neutral, give partial credit
        r.score     += 10

    # 2. Price > 1.05× prev  (25 pts) — near: >1.01
    r.add("Surge>5%", 25, 14,
          pct_chg >= 5.0,
          pct_chg >= 1.0,
          f"only +{pct_chg:.2f}% (need ≥5%)")

    # 3. Price > Open  (15 pts) — near: within -0.5%
    if open_price:
        above_open = (price - open_price) / open_price * 100
        r.add("Price>Open", 15, 8,
              price > open_price,
              price >= open_price * 0.995,
              f"{abs(above_open):.1f}% below open")
    else:
        r.max_score += 15; r.score += 8

    # 4. Volume > 0.2× prev_day_vol  (15 pts) — near: >0.1
    if prev_volume:
        vol_ratio = volume / prev_volume
        r.add("Vol>0.2×prev", 15, 8,
              vol_ratio >= 0.2,
              vol_ratio >= 0.1,
              f"vol ratio {vol_ratio:.2f} (need ≥0.20)")
    else:
        r.max_score += 15; r.score += 8

    # 5. Value > 5B IDR  (25 pts) — near: >1.5B
    r.add("Value>5B", 25, 14,
          value >= 5_000_000_000,
          value >= 1_500_000_000,
          f"value {value/1e9:.1f}B (need ≥5B)")

    return r.finalise()


def ara_hunter_filter(stock: dict) -> bool:
    return ara_hunter_score(stock).status == "pass"
