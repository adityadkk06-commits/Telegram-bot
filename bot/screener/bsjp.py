"""
BSJP screener — specification-compliant institutional-style scoring.

Specification (exact):
  Price between 50 and 2000 IDR [hard gate]
  Price > MA5
  Price > MA20
  MA20 > MA50
  Daily gain between +1% and +6% [hard gate]
  Volume > 2× Volume MA20
  Value traded > 10B IDR
  Foreign Buy Streak >= 2 (approximated from price+volume patterns)
  Bandar A/D > 20
  Close near high: (Close-Low)/(High-Low) > 0.7

AVOID: long upper wick, illiquid, weak continuation, extreme volatility, speculative pump.

OUTPUT: Institutional Score, Trend Quality, Accumulation Strength,
Foreign Flow Strength, Liquidity Quality, Continuation Probability,
Entry Area, TP/SL, Risk Rating.

── FIX LOG (patched) ──────────────────────────────────────────────────────────
"Bandar A/D > 20" previously did `stock.get("bandar_score") or 0`, so when
bandar_score was unavailable it silently scored as if the bandar score were
0 — always failing this criterion outright (0/8 pts), unlike every other
criterion in this file (and in ara_hunter.py / big_accumulation.py), which
give partial "no data — neutral" credit instead. Now consistent with the
rest of the codebase: missing data gets neutral partial credit, not an
automatic fail.
"""

from bot.screener.filter_engine import FilterResult


def bsjp_score(stock: dict) -> FilterResult:
    r = FilterResult()

    price = stock.get("price") or 0
    prev_price = stock.get("prev_price") or 0
    high = stock.get("high") or price
    low = stock.get("low") or price
    value = stock.get("value") or 0
    volume = stock.get("volume") or 0
    ma5 = stock.get("ma5") or 0
    ma20 = stock.get("ma20") or 0
    ma50 = stock.get("ma50") or 0
    vol_ma20 = stock.get("vol_ma20") or 0
    bandar_sc = stock.get("bandar_score")  # keep None distinguishable from 0

    if not price or not prev_price:
        r.status = "fail"; return r

    pct_chg = (price - prev_price) / prev_price * 100
    rel_vol = (volume / vol_ma20) if vol_ma20 and vol_ma20 > 0 else 1.0
    hl_range = max(high - low, price * 0.001)

    # ── Hard gates ─────────────────────────────────────────────────────────
    if not (50 <= price <= 2000):
        r.status = "fail"; return r
    if not (1.0 <= pct_chg <= 6.0):
        r.status = "fail"; return r

    # Speculative pump guard
    if rel_vol > 10 and pct_chg > 5:
        r.status = "fail"; return r

    # ── 1. Price > MA5 (12 pts) ─────────────────────────────────────────
    if ma5 and ma5 > 0:
        gap = (price - ma5) / ma5 * 100
        r.add("Price > MA5", 12, 7,
              price > ma5,
              price >= ma5 * 0.99,
              f"price {abs(gap):.1f}% {'above' if gap>=0 else 'below'} MA5 ({ma5:,.0f})")
    else:
        r.max_score += 12; r.score += 6

    # ── 2. Price > MA20 (12 pts) ────────────────────────────────────────
    if ma20 and ma20 > 0:
        gap = (price - ma20) / ma20 * 100
        r.add("Price > MA20", 12, 7,
              price > ma20,
              price >= ma20 * 0.98,
              f"price {abs(gap):.1f}% {'above' if gap>=0 else 'below'} MA20 ({ma20:,.0f})")
    else:
        r.max_score += 12; r.score += 6

    # ── 3. MA20 > MA50 (12 pts) ─────────────────────────────────────────
    if ma20 and ma50 and ma50 > 0:
        gap = (ma20 - ma50) / ma50 * 100
        r.add("MA20 > MA50", 12, 7,
              ma20 > ma50,
              ma20 >= ma50 * 0.98,
              f"MA20 {abs(gap):.1f}% {'above' if gap>=0 else 'below'} MA50 ({ma50:,.0f})")
    else:
        r.max_score += 12; r.score += 6

    # ── 4. Volume > 2× VolMA20 (22 pts) ────────────────────────────────
    if vol_ma20 and vol_ma20 > 0:
        r.add("Volume > 2× MA20", 22, 11,
              rel_vol >= 2.0,
              rel_vol >= 1.3,
              f"vol {rel_vol:.2f}× avg (need ≥2.0×)")
    else:
        r.max_score += 22; r.score += 11

    # ── 5. Value > 10B IDR (16 pts) ────────────────────────────────────
    r.add("Value > 10B IDR", 16, 9,
          value >= 10_000_000_000,
          value >= 5_000_000_000,
          f"value {value/1e9:.1f}B IDR (need ≥10B)")

    # ── 6. Close near high: (Close-Low)/(High-Low) > 0.7 (14 pts) ──────
    close_ratio = (price - low) / hl_range
    r.add("Close Near High (>0.70)", 14, 7,
          close_ratio > 0.70,
          close_ratio > 0.50,
          f"close ratio {close_ratio:.2f} (need >0.70)")

    # ── 7. Bandar A/D > 20 (8 pts) ─────────────────────────────────────
    if bandar_sc is not None:
        r.add("Bandar A/D > 20", 8, 4,
              bandar_sc > 20,
              bandar_sc > 8,
              f"bandar score {bandar_sc:.1f} (need >20)")
    else:
        r.max_score += 8; r.score += 4  # no data — neutral, same as other criteria

    # ── 8. Foreign Buy proxy: strong price + volume confirmation (4 pts)
    # Approximates foreign buy streak ≥2 from price-volume behavior
    foreign_signal = pct_chg > 1.5 and rel_vol >= 1.5
    r.add("Foreign Buy (proxy)", 4, 2,
          foreign_signal,
          pct_chg > 0.5,
          "foreign buy signal not confirmed")

    return r.finalise()


def bsjp_filter(stock: dict) -> bool:
    return bsjp_score(stock).status == "pass"


def bsjp_output(stock: dict) -> dict:
    """
    Returns all required output fields per BSJP spec:
    Institutional Score, Trend Quality, Accumulation Strength,
    Foreign Flow Strength, Liquidity Quality, Continuation Probability,
    Entry Area, TP/SL, Risk Rating.
    """
    r = bsjp_score(stock)
    price = stock.get("price") or 1
    prev = stock.get("prev_price") or price
    high = stock.get("high") or price
    low = stock.get("low") or price * 0.97
    value = stock.get("value") or 0
    vol_ma20 = stock.get("vol_ma20") or 1
    volume = stock.get("volume") or 0
    ma5 = stock.get("ma5") or price
    ma20 = stock.get("ma20") or price
    ma50 = stock.get("ma50") or price
    bandar = stock.get("bandar_score") or 0
    rsi = stock.get("rsi") or 50

    pct_chg = (price - prev) / prev * 100 if prev else 0
    rel_vol = volume / vol_ma20 if vol_ma20 else 1
    hl = max(high - low, price * 0.01)

    # Institutional Score (0-100)
    inst_score = min(100, max(0, r.pct + (5 if bandar > 20 else 0)))

    # Trend Quality
    if price > ma5 > ma20 > ma50: tq = "Excellent 🏆 (full bullish stack)"
    elif price > ma20 > ma50: tq = "Strong 💪"
    elif price > ma20: tq = "Moderate ➡️"
    else: tq = "Weak 🔻"

    # Accumulation Strength
    if bandar > 35: acc = "Strong 🔥"
    elif bandar > 20: acc = "Active ✅"
    elif bandar > 8: acc = "Moderate 🔸"
    else: acc = "Weak ⚠️"

    # Foreign Flow Strength (still a labeled proxy, not real foreign data)
    foreign_ok = pct_chg > 1.5 and rel_vol >= 1.5
    ff = "Positive (proxy) 🟢" if foreign_ok else ("Neutral (proxy) ⚪" if pct_chg > 0 else "Negative (proxy) 🔴")

    # Liquidity Quality
    if value >= 50e9: lq = "Excellent 🏆"
    elif value >= 20e9: lq = "High ✅"
    elif value >= 10e9: lq = "Adequate 🔸"
    else: lq = "Low ⚠️"

    # Continuation Probability
    prob = int(min(90, max(55, r.pct + (5 if bandar > 20 else 0) - (8 if rsi > 70 else 0))))

    # Risk Rating
    if rsi > 72 or pct_chg > 5: risk = "🔴 Medium-High"
    elif pct_chg >= 3: risk = "🟡 Medium"
    else: risk = "🟢 Low-Medium"

    # Entry / TP / SL
    atr_est = hl * 0.7
    entry_low = round(max(price * 0.994, low * 1.005), 0)
    entry_high = round(price, 0)
    tp = round(entry_high + 2.5 * atr_est, 0)
    sl = round(max(entry_low - 1.5 * atr_est, low * 0.985), 0)
    rr = round((tp - entry_high) / max(entry_high - sl, 1), 1)
    if rr < 2.0:
        tp = round(entry_high + 2.0 * max(entry_high - sl, atr_est), 0)
        rr = round((tp - entry_high) / max(entry_high - sl, 1), 1)

    return {
        "institutional_score": int(inst_score),
        "trend_quality": tq,
        "accumulation_strength": acc,
        "foreign_flow_strength": ff,
        "liquidity_quality": lq,
        "continuation_prob": prob,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "tp": tp,
        "sl": sl,
        "rr": rr,
        "risk_rating": risk,
        "filter_pct": round(r.pct, 1),
    }