"""
Advanced Bid/Offer Analysis Engine.

Since IDX L2 order book data is unavailable via yfinance, this module
approximates bid/offer dynamics using OHLCV price structure — the same
methodology used by professional algorithmic systems when order book
data is absent.

Key estimates:
  CLV  (Close Location Value) = (Close-Low - High-Close) / (High-Low)
       → +1.0 = close at high = bid domination
       → -1.0 = close at low  = offer domination

  Spread estimate  = ATR_3 / Price × 10000  (in basis points)
  Large lot proxy  = high volume + small HL range → absorption detected
  Broker estimate  = BandarScore (CLV-based cumulative A/D)
"""
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Core bid/offer metrics
# ─────────────────────────────────────────────────────────────────────────────

def analyze_bid_offer(df: pd.DataFrame, snap: dict) -> dict:
    """
    Full bid/offer analysis from OHLCV dataframe.

    Returns:
        bid_strength      : 0–100  (100 = bids fully dominating)
        offer_strength    : 0–100
        clv               : -1 to +1 (Close Location Value, last bar)
        clv_5             : CLV average over last 5 bars
        spread_bps        : estimated spread in basis points
        absorption        : True if large-lot absorption detected
        absorption_level  : 0–100 absorption score
        bid_dominance     : "strong" | "moderate" | "balanced" | "weak" | "distribution"
        layering_signal   : "bullish_stack" | "neutral" | "bearish_stack"
        smart_money       : True if smart money accumulation detected
        broker_signal     : "accumulation" | "distribution" | "neutral"
        scalp_spread_ok   : True if spread acceptable for scalping
        intraday_support  : estimated intraday support level
        intraday_resist   : estimated intraday resistance level
        summary_lines     : list[str] — human-readable findings
    """
    if df is None or len(df) < 5:
        return _empty_bid_offer(snap)

    df    = df.copy()
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    vol   = df["Volume"]
    price = float(close.iloc[-1])

    # ── CLV (Close Location Value) ────────────────────────────────────────
    hl_rng = (high - low).replace(0, np.nan)
    clv    = ((close - low) - (high - close)) / hl_rng
    clv_last  = float(clv.iloc[-1]) if pd.notna(clv.iloc[-1]) else 0
    clv_5     = float(clv.tail(5).mean()) if len(clv) >= 5 else clv_last

    bid_strength  = round((clv_last + 1) / 2 * 100, 1)   # map [-1,+1] → [0,100]
    offer_strength= round(100 - bid_strength, 1)

    # ── Spread estimate (ATR_3-based) ─────────────────────────────────────
    hl3       = (high - low).tail(3).mean()
    spread_bps= round((hl3 / max(price, 1)) * 10000, 1) if price > 0 else 0

    # ── Large-lot absorption detection ───────────────────────────────────
    # High volume + small intraday range = big players absorbing supply
    vol_ma20   = vol.rolling(20).mean().iloc[-1] or 1
    vol_now    = float(vol.iloc[-1])
    range_pct  = float(hl_rng.iloc[-1] / price * 100) if price > 0 else 5
    rel_vol    = vol_now / vol_ma20

    absorption_score = 0
    if rel_vol > 2.0 and range_pct < 2.0:
        absorption_score = 90
    elif rel_vol > 1.5 and range_pct < 3.0:
        absorption_score = 65
    elif rel_vol > 1.3:
        absorption_score = 40
    absorption = absorption_score >= 65

    # ── Bid dominance classification ──────────────────────────────────────
    if clv_5 > 0.5:
        bid_dominance = "strong"
    elif clv_5 > 0.2:
        bid_dominance = "moderate"
    elif clv_5 > -0.2:
        bid_dominance = "balanced"
    elif clv_5 > -0.5:
        bid_dominance = "weak"
    else:
        bid_dominance = "distribution"

    # ── Layering signal ───────────────────────────────────────────────────
    # Bullish stacking: recent CLVs improving (each bar closing higher in range)
    recent_clv = clv.tail(3).values
    clv_trend  = 0
    for i in range(1, len(recent_clv)):
        if pd.notna(recent_clv[i]) and pd.notna(recent_clv[i-1]):
            clv_trend += 1 if recent_clv[i] > recent_clv[i-1] else -1

    if clv_trend >= 2:
        layering = "bullish_stack"
    elif clv_trend <= -2:
        layering = "bearish_stack"
    else:
        layering = "neutral"

    # ── Smart money detection ─────────────────────────────────────────────
    bandar_sc   = snap.get("bandar_score", 0) or 0
    smart_money = (clv_5 > 0.3 and rel_vol > 1.5 and bandar_sc > 10)

    # ── Broker signal ─────────────────────────────────────────────────────
    if bandar_sc > 20 and clv_5 > 0.2:
        broker_signal = "accumulation"
    elif bandar_sc < -10 or clv_5 < -0.3:
        broker_signal = "distribution"
    else:
        broker_signal = "neutral"

    # ── Scalp spread filter ───────────────────────────────────────────────
    scalp_spread_ok = spread_bps < 150   # < 1.5% intraday spread → scalp-able

    # ── Intraday S/R ──────────────────────────────────────────────────────
    recent_20       = df.tail(20)
    intraday_support= float(recent_20["Low"].min())
    intraday_resist = float(recent_20["High"].max())

    # ── Summary lines ─────────────────────────────────────────────────────
    lines = []
    if bid_dominance in ("strong", "moderate"):
        lines.append(f"✅ Bid domination (CLV: {clv_last:+.2f})")
    elif bid_dominance == "distribution":
        lines.append(f"⚠️ Offer pressure (CLV: {clv_last:+.2f})")

    if absorption:
        lines.append(f"✅ Large lot absorption ({absorption_score}%)")

    if smart_money:
        lines.append("✅ Smart money accumulation detected")

    if layering == "bullish_stack":
        lines.append("✅ Bullish bid stacking pattern")
    elif layering == "bearish_stack":
        lines.append("⚠️ Bearish offer stacking pattern")

    if scalp_spread_ok:
        lines.append(f"✅ Spread acceptable ({spread_bps:.0f} bps)")
    else:
        lines.append(f"⚠️ Wide spread ({spread_bps:.0f} bps)")

    broker_labels = {
        "accumulation": "✅ AK/BK accumulation detected",
        "distribution": "⚠️ Broker distribution signal",
        "neutral":      "🔸 Broker flow neutral",
    }
    lines.append(broker_labels.get(broker_signal, ""))

    return {
        "bid_strength":     bid_strength,
        "offer_strength":   offer_strength,
        "clv":              round(clv_last, 3),
        "clv_5":            round(clv_5, 3),
        "spread_bps":       spread_bps,
        "absorption":       absorption,
        "absorption_level": absorption_score,
        "bid_dominance":    bid_dominance,
        "layering_signal":  layering,
        "smart_money":      smart_money,
        "broker_signal":    broker_signal,
        "scalp_spread_ok":  scalp_spread_ok,
        "intraday_support": intraday_support,
        "intraday_resist":  intraday_resist,
        "rel_vol":          round(rel_vol, 2),
        "summary_lines":    [l for l in lines if l],
    }


def _empty_bid_offer(snap: dict) -> dict:
    price = snap.get("price", 1) or 1
    return {
        "bid_strength": 50, "offer_strength": 50, "clv": 0, "clv_5": 0,
        "spread_bps": 200, "absorption": False, "absorption_level": 0,
        "bid_dominance": "balanced", "layering_signal": "neutral",
        "smart_money": False, "broker_signal": "neutral",
        "scalp_spread_ok": True, "intraday_support": price * 0.97,
        "intraday_resist": price * 1.03, "rel_vol": 1.0, "summary_lines": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Scalping probability score
# ─────────────────────────────────────────────────────────────────────────────

def scalping_probability(snap: dict, bo: dict, ema_aligned: bool, rsi: float) -> int:
    """
    Returns 0–100 scalping probability score.
    High (≥75) = ideal scalp setup.
    """
    score = 0

    rv = snap.get("rel_vol", 1) or 1
    pct= snap.get("pct_chg", 0)

    if rv >= 3.0:   score += 20
    elif rv >= 2.0: score += 14
    elif rv >= 1.5: score += 8

    if bo["bid_dominance"] in ("strong", "moderate"): score += 18
    elif bo["bid_dominance"] == "balanced":            score += 8

    if bo["scalp_spread_ok"]:  score += 10
    if bo["absorption"]:       score += 12

    if ema_aligned:            score += 15

    if 40 <= rsi <= 65:        score += 15
    elif 65 < rsi <= 72:       score +=  7

    if 0.5 <= pct <= 5.0:      score += 10
    elif 0.2 <= pct <= 8.0:    score +=  5

    return min(score, 100)
