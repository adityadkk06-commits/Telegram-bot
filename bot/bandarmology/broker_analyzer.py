"""
Technical Momentum Analyzer.

IMPORTANT: IDX real-time per-broker flow data (e.g. AK, BK, YP net buy/sell)
requires a paid IDX data provider and is NOT available via yfinance.

This module produces a Technical Momentum Bias derived entirely from real,
computable price/volume indicators:
  - BandarScore:  CLV-based Acc/Dist momentum (real, from data_service.py)
  - RelVol:       volume vs 20-day average (real)
  - pct_chg:      current day's return (real)
  - MA alignment: short > long trend confirmation (real)

No simulated broker flows. No random numbers.
"""
import math


def estimate_broker_signal(stock: dict) -> dict:
    """
    Returns a Technical Momentum Bias dict derived from real indicators.
    Does NOT simulate per-broker flows.
    """
    pct_chg     = stock.get("pct_chg", 0) or 0
    rel_vol     = stock.get("rel_vol", 1) or 1
    bandar_sc   = stock.get("bandar_score", 0) or 0
    ma20        = stock.get("ma20")
    ma50        = stock.get("ma50")
    value       = stock.get("value", 0) or 0

    # ── Scoring: 0 = max bearish, 100 = max bullish ──────────────────────────
    bias = 50.0   # neutral baseline

    # 1. BandarScore (CLV-based Acc/Dist 5-period momentum)
    #    Positive = net accumulation, negative = net distribution
    if bandar_sc > 50:     bias += 18
    elif bandar_sc > 20:   bias += 12
    elif bandar_sc > 5:    bias +=  6
    elif bandar_sc < -20:  bias -= 12
    elif bandar_sc < -5:   bias -=  6

    # 2. Price momentum
    if pct_chg > 3:     bias += 12
    elif pct_chg > 1:   bias +=  7
    elif pct_chg > 0:   bias +=  3
    elif pct_chg < -2:  bias -= 10
    elif pct_chg < 0:   bias -=  3

    # 3. Relative volume (accumulation of large orders pushes RelVol up)
    if rel_vol >= 3:     bias += 10
    elif rel_vol >= 2:   bias +=  6
    elif rel_vol >= 1.5: bias +=  3
    elif rel_vol < 0.8:  bias -=  4

    # 4. MA trend alignment
    if ma20 and ma50:
        if ma20 > ma50:   bias += 6
        elif ma20 < ma50: bias -= 4

    bias = max(0.0, min(100.0, bias))

    # ── Signal label ─────────────────────────────────────────────────────────
    if bias >= 72:
        signal = "Strong Accumulation"
    elif bias >= 58:
        signal = "Accumulation"
    elif bias <= 28:
        signal = "Strong Distribution"
    elif bias <= 42:
        signal = "Distribution"
    else:
        signal = "Neutral"

    return {
        "signal":       signal,
        "bias_score":   round(bias, 1),
        "bandar_score": round(bandar_sc, 2),
        "rel_vol":      round(rel_vol, 2),
        "data_source":  "technical_indicators",
    }


def format_broker_report(ticker: str, broker_data: dict) -> str:
    signal      = broker_data.get("signal", "Neutral")
    bias        = broker_data.get("bias_score", 50.0)
    bandar_sc   = broker_data.get("bandar_score", 0.0)
    rel_vol     = broker_data.get("rel_vol", 1.0)

    signal_emoji = "🟢" if "Accumulation" in signal else ("🔴" if "Distribution" in signal else "⚪")
    bar_filled   = int(bias / 10)
    bar          = "█" * bar_filled + "░" * (10 - bar_filled)

    lines = [
        f"📊 *Technical Momentum: {ticker}*",
        "",
        f"*Signal:* {signal_emoji} {signal}",
        f"*Bias Score:* {bias:.0f}/100  [{bar}]",
        "",
        "*Indicator Breakdown:*",
        f"  • BandarScore (Acc/Dist): `{bandar_sc:+.1f}`",
        f"  • Relative Volume:       `{rel_vol:.2f}×`",
        "",
        "⚠️ _Technical bias only — no real per-broker IDX flow data._",
        "_Real AK/BK/YP broker data requires a paid IDX data provider._",
    ]
    return "\n".join(lines)
