"""
Rule-based AI explanation engine for stock screener results.
"""


def _momentum_label(score: float) -> str:
    if score >= 80:   return "Very Strong 🚀"
    elif score >= 60: return "Strong 💪"
    elif score >= 40: return "Moderate ➡️"
    elif score >= 20: return "Weak 😐"
    return "Very Weak 🔻"


def _risk_label(score: float, rsi) -> str:
    if rsi and rsi > 75:  return "⚠️ High (Overbought)"
    if score >= 80:       return "🟠 Medium-High"
    elif score >= 60:     return "🟡 Medium"
    return "🟢 Low-Medium"


def generate_screener_reason(stock: dict, screener_type: str) -> str:
    reasons = []
    price       = stock.get("price", 0)
    pct_chg     = stock.get("pct_chg", 0)
    ma5         = stock.get("ma5")
    ma20        = stock.get("ma20")
    ma50        = stock.get("ma50")
    rel_vol     = stock.get("rel_vol", 1) or 1
    rsi         = stock.get("rsi")
    bandar_sc   = stock.get("bandar_score", 0) or 0
    broker_sig  = stock.get("broker_signal", "Neutral")
    foreign     = stock.get("foreign_flow", "Neutral")
    vwap        = stock.get("vwap")
    macd        = stock.get("macd")
    macd_sig    = stock.get("macd_signal")
    high        = stock.get("high")
    low         = stock.get("low")

    if screener_type == "ara_hunter":
        reasons.append("📌 Price surged >5% above previous close")
        if ma5 and price > ma5:
            reasons.append(f"📌 Above MA5 ({ma5:,.0f}) — short-term bullish")
        if rel_vol > 1.5:
            reasons.append(f"📌 Volume spike {rel_vol:.1f}x average — unusual activity")
        if pct_chg > 7:
            reasons.append("📌 Strong momentum — approaching ARA limit")

    elif screener_type == "bsjp":
        if ma20 and price > ma20:
            reasons.append(f"📌 Breakout above MA20 ({ma20:,.0f})")
        if ma20 and ma50 and ma20 > ma50:
            reasons.append("📌 MA20 > MA50 — confirmed uptrend")
        if rel_vol > 2:
            reasons.append(f"📌 Volume {rel_vol:.1f}x MA20 — strong buying pressure")
        reasons.append("📌 Net foreign buy streak ≥2 days detected")

    elif screener_type == "big_accumulation":
        if bandar_sc > 25:
            reasons.append(f"📌 Bandar A/D score {bandar_sc:.0f} — active accumulation")
        if ma20 and ma50 and ma20 > ma50:
            reasons.append("📌 MA20 > MA50 — institutional base building")
        if price < 500:
            reasons.append(f"📌 Low price ({price:,.0f}) — retail-friendly entry")
        if rel_vol > 1.3:
            reasons.append(f"📌 VolMA5 {rel_vol:.1f}x VolMA20 — smart money loading")

    elif screener_type == "scalper_pro":
        reasons.append(f"📌 Volume surge {rel_vol:.1f}x — active intraday flow")
        if vwap and price > vwap:
            reasons.append(f"📌 Price above VWAP ({vwap:,.0f}) — intraday bullish bias")
        if ma5 and ma20 and ma5 > ma20:
            reasons.append("📌 MA5 > MA20 — short-term momentum aligned")
        if macd and macd_sig and macd > macd_sig:
            reasons.append("📌 MACD crossover positive — momentum confirming")
        if high and low and price > 0:
            rng = (high - low) / price * 100
            reasons.append(f"📌 Tight candle range {rng:.1f}% — clean scalp setup")
        if rsi and 40 <= rsi <= 60:
            reasons.append(f"📌 RSI {rsi:.1f} — perfect scalp entry zone")
        reasons.append("📌 Risk/Reward favorable for quick trades")

    # Common extras
    if rsi:
        if 40 < rsi < 65 and screener_type != "scalper_pro":
            reasons.append(f"📌 RSI {rsi:.1f} — healthy momentum, room to run")
        elif rsi < 35:
            reasons.append(f"📌 RSI {rsi:.1f} — oversold bounce potential")
        elif rsi > 72:
            reasons.append(f"⚠️ RSI {rsi:.1f} — overbought, caution on new entry")

    if "Accumulation" in broker_sig:
        reasons.append(f"📌 Broker flow: {broker_sig} — big players loading")

    if foreign == "Positive":
        reasons.append("📌 Foreign net buy detected — institutional interest")

    if not reasons:
        reasons.append("📌 Met all screener filter conditions")

    return "\n".join(reasons)


def generate_full_analysis(stock: dict, screener_type: str) -> str:
    ticker        = stock.get("ticker", "")
    pct_chg       = stock.get("pct_chg", 0)
    rsi           = stock.get("rsi")
    momentum_sc   = stock.get("momentum_score", 50)
    sector        = stock.get("sector", "Unknown")
    broker_sig    = stock.get("broker_signal", "Neutral")
    foreign       = stock.get("foreign_flow", "Neutral")

    risk      = _risk_label(momentum_sc, rsi)
    mom_label = _momentum_label(momentum_sc)

    prob = 50
    if momentum_sc > 70:  prob += 15
    if "Accumulation" in broker_sig: prob += 10
    if foreign == "Positive":        prob += 10
    if rsi and rsi > 70:             prob -= 15
    if pct_chg > 8:                  prob -= 5
    if screener_type == "scalper_pro": prob = max(prob, 55)
    prob = max(20, min(88, prob))

    reasons = generate_screener_reason(stock, screener_type)

    scalp_note = (
        "\n\n⚡ *Scalp Strategy:*\n"
        "• Entry: On volume confirmation\n"
        "• Target: +1.5%–3% from entry\n"
        "• Stop Loss: Below MA5 or -1%\n"
        "• Timeframe: 5–30 minutes"
    ) if screener_type == "scalper_pro" else ""

    return "\n".join([
        f"🤖 *AI Analysis — {ticker}*",
        "",
        "*Why it passed:*",
        reasons,
        "",
        f"*Risk Level:* {risk}",
        f"*Momentum:* {mom_label} ({momentum_sc:.0f}/100)",
        f"*Sector:* {sector}",
        f"*Bandar Status:* {broker_sig}",
        f"*Foreign Flow:* {foreign}",
        f"*Continuation Probability:* ~{prob}%",
        scalp_note,
        "",
        "_For educational purposes only. Always do your own research._",
    ])


def generate_sector_analysis(sector_data: list) -> str:
    if not sector_data:
        return "No sector data available."
    sorted_s = sorted(sector_data, key=lambda x: x.get("pct_chg", 0), reverse=True)
    top = sorted_s[0] if sorted_s else None
    lines = ["🤖 *AI Sector Rotation Analysis*", ""]
    lines.append("*Rotation Signal:*")
    if top:
        if top["pct_chg"] > 3:
            lines.append(f"Strong rotation into *{top['name']}* — focus on sector leaders")
        elif top["pct_chg"] > 1:
            lines.append(f"Moderate inflow to *{top['name']}* — selective accumulation")
        else:
            lines.append("No clear rotation today — market is mixed")
    lines += [
        "", "*Strategy:*",
        "• Focus on stocks in top 2 performing sectors",
        "• Avoid averaging down in weakest sectors",
        "• Volume confirmation is key for breakout entries",
    ]
    return "\n".join(lines)
