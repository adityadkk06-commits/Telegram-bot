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
  (Net foreign buy streak ≥2 — approximated)
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
        r.max_score += 14; r.score += 7

    # 3. Price > MA20  (14 pts) — near: within -2%
    if ma20:
        gap = (price - ma20) / ma20 * 100
        r.add("Price>MA20", 14, 8,
              price > ma20,
              price >= ma20 * 0.98,
              f"{abs(gap):.1f}% below MA20 ({ma20:,.0f})")
    else:
        r.max_score += 14; r.score += 7

    # 4. MA20 > MA50  (14 pts) — near: within -2%
    if ma20 and ma50:
        gap = (ma20 - ma50) / ma50 * 100
        r.add("MA20>MA50", 14, 8,
              ma20 > ma50,
              ma20 >= ma50 * 0.98,
              f"MA20 is {abs(gap):.1f}% {'above' if gap>=0 else 'below'} MA50")
    else:
        r.max_score += 14; r.score += 7

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
        r.max_score += 14; r.score += 7

    # 7. Volume > 2× VolMA20  (14 pts) — near: >1.2
    if vol_ma20:
        r.add("Vol>2×MA20", 14, 8,
              rel_vol >= 2.0,
              rel_vol >= 1.2,
              f"RelVol {rel_vol:.2f}× (need ≥2.0)")
    else:
        r.max_score += 14; r.score += 7

    # 8. Foreign buy proxy: positive pct + rising volume (6 pts)
    foreign_signal = pct_chg > 0.5 and rel_vol > 1.2
    r.add("ForeignBuy", 6, 3,
          foreign_signal,
          pct_chg > 0,
          "no foreign buy signal")

    return r.finalise()


def bsjp_filter(stock: dict) -> bool:
    return bsjp_score(stock).status == "pass"
