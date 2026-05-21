"""
Rule-based AI explanation engine for stock screener results.
Generates human-readable analysis based on technical indicators.
"""
import random


def _momentum_label(score: float) -> str:
    if score >= 80:
        return "Very Strong"
    elif score >= 60:
        return "Strong"
    elif score >= 40:
        return "Moderate"
    elif score >= 20:
        return "Weak"
    return "Very Weak"


def _risk_label(score: float, rsi: float) -> str:
    if rsi and rsi > 75:
        return "High (Overbought)"
    if score >= 80:
        return "Medium-High"
    elif score >= 60:
        return "Medium"
    return "Low-Medium"


def generate_screener_reason(stock: dict, screener_type: str) -> str:
    reasons = []
    price = stock.get("price", 0)
    pct_chg = stock.get("pct_chg", 0)
    ma5 = stock.get("ma5")
    ma20 = stock.get("ma20")
    ma50 = stock.get("ma50")
    rel_vol = stock.get("rel_vol", 1)
    rsi = stock.get("rsi")
    bandar_score = stock.get("bandar_score", 0)
    momentum_score = stock.get("momentum_score", 50)
    sector = stock.get("sector", "Unknown")
    broker_signal = stock.get("broker_signal", "Neutral")
    foreign_flow = stock.get("foreign_flow", "Neutral")

    if screener_type == "ara_hunter":
        reasons.append("📌 Price surged >5% above previous close")
        if ma5 and price > ma5:
            reasons.append(f"📌 Trading above MA5 ({ma5:,.0f}) — short-term bullish")
        if rel_vol and rel_vol > 1.5:
            reasons.append(f"📌 Volume spike {rel_vol:.1f}x average — unusual activity")
        if pct_chg > 7:
            reasons.append("📌 Strong price momentum nearing ARA limit")

    elif screener_type == "bsjp":
        if ma20 and price > ma20:
            reasons.append(f"📌 Breakout above MA20 ({ma20:,.0f}) — trend confirmed")
        if ma20 and ma50 and ma20 > ma50:
            reasons.append("📌 MA20 > MA50 — uptrend structure intact")
        if rel_vol and rel_vol > 2:
            reasons.append(f"📌 Volume {rel_vol:.1f}x MA20 — strong buying pressure")
        reasons.append("📌 Net foreign buy streak ≥2 days detected")

    elif screener_type == "big_accumulation":
        if bandar_score and bandar_score > 25:
            reasons.append(f"📌 Bandar A/D score {bandar_score:.0f} — active accumulation")
        if ma20 and ma50 and ma20 > ma50:
            reasons.append("📌 MA20 > MA50 — institutional base building")
        if price < 500:
            reasons.append(f"📌 Low price ({price:,.0f}) — retail-friendly entry zone")
        if rel_vol and rel_vol > 1.3:
            reasons.append(f"📌 VolMA5 {rel_vol:.1f}x VolMA20 — smart money loading")

    # Common extras
    if rsi:
        if 40 < rsi < 65:
            reasons.append(f"📌 RSI {rsi:.1f} — healthy momentum, room to run")
        elif rsi < 40:
            reasons.append(f"📌 RSI {rsi:.1f} — oversold bounce potential")
        elif rsi > 70:
            reasons.append(f"📌 RSI {rsi:.1f} — overbought, caution on new entry")

    if "Accumulation" in broker_signal:
        reasons.append(f"📌 Broker flow: {broker_signal} — big players loading")

    if foreign_flow == "Positive":
        reasons.append("📌 Foreign net buy detected — institutional interest")

    if not reasons:
        reasons.append("📌 Met all screener filter conditions")

    return "\n".join(reasons)


def generate_full_analysis(stock: dict, screener_type: str) -> str:
    ticker = stock.get("ticker", "")
    price = stock.get("price", 0)
    pct_chg = stock.get("pct_chg", 0)
    rsi = stock.get("rsi")
    momentum_score = stock.get("momentum_score", 50)
    sector = stock.get("sector", "Unknown")
    broker_signal = stock.get("broker_signal", "Neutral")
    foreign_flow = stock.get("foreign_flow", "Neutral")
    bandar_score = stock.get("bandar_score", 0) or 0
    rel_vol = stock.get("rel_vol", 1) or 1

    risk = _risk_label(momentum_score, rsi)
    mom_label = _momentum_label(momentum_score)

    # Continuation probability
    prob = 50
    if momentum_score > 70:
        prob += 15
    if "Accumulation" in broker_signal:
        prob += 10
    if foreign_flow == "Positive":
        prob += 10
    if rsi and rsi > 70:
        prob -= 15
    if pct_chg > 8:
        prob -= 5
    prob = max(20, min(85, prob))

    reasons = generate_screener_reason(stock, screener_type)

    lines = [
        f"🤖 *AI Analysis — {ticker}*",
        "",
        f"*Why it passed screener:*",
        reasons,
        "",
        f"*Risk Level:* {risk}",
        f"*Momentum:* {mom_label} ({momentum_score:.0f}/100)",
        f"*Sector Condition:* {sector}",
        f"*Bandar Status:* {broker_signal}",
        f"*Foreign Flow:* {foreign_flow}",
        f"*Continuation Probability:* ~{prob}%",
        "",
        f"⚠️ _This analysis is for educational purposes only. Always do your own research._",
    ]
    return "\n".join(lines)


def generate_sector_analysis(sector_data: list) -> str:
    if not sector_data:
        return "No sector data available."

    sorted_sectors = sorted(sector_data, key=lambda x: x.get("pct_chg", 0), reverse=True)
    strongest = sorted_sectors[:3]
    weakest = sorted_sectors[-3:]

    lines = ["🤖 *AI Sector Rotation Analysis*", ""]
    lines.append("*Rotation Signal:*")

    top = strongest[0] if strongest else None
    if top:
        if top["pct_chg"] > 3:
            lines.append(f"Strong rotation into *{top['name']}* — consider sector leaders")
        elif top["pct_chg"] > 1:
            lines.append(f"Moderate inflow to *{top['name']}* — selective accumulation advised")
        else:
            lines.append("No clear sector rotation today — market is mixed")

    lines.append("")
    lines.append("*Strategy:*")
    lines.append("• Focus on stocks in top 2 performing sectors")
    lines.append("• Avoid averaging down in weakest sectors")
    lines.append("• Volume confirmation is key for breakout entries")

    return "\n".join(lines)
