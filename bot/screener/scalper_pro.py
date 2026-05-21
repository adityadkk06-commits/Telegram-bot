"""
SCALPER PRO screener — scoring version.

10 professional intraday criteria (10 pts each = 100 max).

Full match (≥82 pts / ≥8.2 criteria):  ✅ PASS
Near miss (≥58 pts / ≥5.8 criteria):   🔶 NEAR
"""
from bot.screener.filter_engine import FilterResult

MIN_VALUE_SCALP = 2_000_000_000   # 2B IDR


def scalper_pro_score(stock: dict) -> FilterResult:
    r          = FilterResult()
    price      = stock.get("price") or 0
    prev_price = stock.get("prev_price") or 0
    value      = stock.get("value") or 0
    ma5        = stock.get("ma5") or 0
    ma20       = stock.get("ma20") or 0
    rel_vol    = stock.get("rel_vol") or 0
    rsi        = stock.get("rsi")
    macd       = stock.get("macd")
    macd_sig   = stock.get("macd_signal")
    vwap       = stock.get("vwap")
    bandar_sc  = stock.get("bandar_score")
    high       = stock.get("high") or price
    low        = stock.get("low") or price

    if not price or not prev_price:
        r.status = "fail"; return r

    pct_chg = (price - prev_price) / prev_price * 100

    # 1. Volume surge: RelVol > 2.0  (10 pts) — near: >1.3
    r.add("RelVol>2×", 10, 6,
          rel_vol >= 2.0,
          rel_vol >= 1.3,
          f"RelVol {rel_vol:.2f}× (need ≥2.0)")

    # 2. Liquidity: Value > 2B  (10 pts) — near: >0.8B
    r.add("Value>2B", 10, 6,
          value >= MIN_VALUE_SCALP,
          value >= 800_000_000,
          f"value {value/1e9:.1f}B (need ≥2B)")

    # 3. Price move in scalp range [0.3%, 4.5%]  (10 pts) — near: [0.05%, 7%]
    in_strict = 0.3 <= pct_chg <= 4.5
    in_near   = 0.05 <= pct_chg <= 7.0
    r.add("Move[0.3-4.5%]", 10, 6,
          in_strict,
          in_near and not in_strict,
          f"move {pct_chg:.2f}% (need 0.3–4.5%)")

    # 4. Above VWAP  (10 pts) — near: within -1%
    if vwap and vwap > 0:
        vwap_gap = (price - vwap) / vwap * 100
        r.add("Price>VWAP", 10, 6,
              price >= vwap,
              price >= vwap * 0.99,
              f"{abs(vwap_gap):.1f}% below VWAP ({vwap:,.0f})")
    else:
        # No VWAP data — give partial credit
        r.max_score += 10; r.score += 5

    # 5. Price > MA5  (10 pts) — near: within -1%
    if ma5:
        gap5 = (price - ma5) / ma5 * 100
        r.add("Price>MA5", 10, 6,
              price >= ma5,
              price >= ma5 * 0.99,
              f"{abs(gap5):.1f}% below MA5 ({ma5:,.0f})")
    else:
        r.max_score += 10; r.score += 5

    # 6. MA5 > MA20 trend alignment  (10 pts) — near: within -1%
    if ma5 and ma20:
        gap_ma = (ma5 - ma20) / ma20 * 100
        r.add("MA5>MA20", 10, 6,
              ma5 >= ma20,
              ma5 >= ma20 * 0.99,
              f"MA5 {abs(gap_ma):.1f}% {'above' if gap_ma>=0 else 'below'} MA20")
    else:
        r.max_score += 10; r.score += 5

    # 7. RSI in [38, 63]  (10 pts) — near: [30, 72]
    if rsi is not None:
        rsi_strict = 38 <= rsi <= 63
        rsi_near   = 30 <= rsi <= 72
        r.add("RSI[38-63]", 10, 6,
              rsi_strict,
              rsi_near and not rsi_strict,
              f"RSI {rsi:.1f} (need 38–63)")
    else:
        r.max_score += 10; r.score += 5

    # 8. MACD > Signal (momentum)  (10 pts) — near: within -15%
    if macd is not None and macd_sig is not None:
        macd_gap = macd - macd_sig
        macd_ref = abs(macd_sig) if macd_sig != 0 else 0.0001
        r.add("MACD>Signal", 10, 6,
              macd >= macd_sig,
              macd >= macd_sig * 0.85 if macd_sig > 0 else macd >= macd_sig * 1.15,
              f"MACD {macd:.4f} vs sig {macd_sig:.4f}")
    else:
        r.max_score += 10; r.score += 5

    # 9. Bandar interest (smart money)  (10 pts) — near: > -10
    if bandar_sc is not None:
        r.add("BandarScore>5", 10, 6,
              bandar_sc > 5,
              bandar_sc > -10,
              f"bandar score {bandar_sc:.1f} (need >5)")
    else:
        r.max_score += 10; r.score += 5

    # 10. Tight intraday candle < 3%  (10 pts) — near: <5%
    if price > 0:
        rng_pct = (high - low) / price * 100
        r.add("Range<3%", 10, 6,
              rng_pct < 3.0,
              rng_pct < 5.0,
              f"range {rng_pct:.1f}% (need <3%)")
    else:
        r.max_score += 10; r.score += 5

    return r.finalise()


def scalper_pro_filter(stock: dict) -> bool:
    return scalper_pro_score(stock).status == "pass"
