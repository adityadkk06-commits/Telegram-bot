"""
Broker/Bandarology analyzer.
Since IDX real broker data requires a paid API, we simulate broker
accumulation signals from price/volume/momentum patterns.
"""
import random
import math
from bot.utils.constants import FOCUS_BROKERS


def estimate_broker_signal(stock: dict) -> dict:
    price = stock.get("price", 0)
    prev_price = stock.get("prev_price", price)
    pct_chg = stock.get("pct_chg", 0)
    rel_vol = stock.get("rel_vol", 1) or 1
    bandar_score = stock.get("bandar_score", 0) or 0
    ma20 = stock.get("ma20")
    ma50 = stock.get("ma50")
    value = stock.get("value", 0) or 0

    # Simulate individual broker flows
    seed = hash(stock.get("ticker", "")) % 1000
    rng = random.Random(seed + int(pct_chg * 100))

    brokers = {}
    total_buy = 0
    total_sell = 0

    for broker in FOCUS_BROKERS:
        # Bias toward accumulation if indicators are bullish
        bullish_bias = 0.0
        if pct_chg > 2:
            bullish_bias += 0.3
        if rel_vol > 2:
            bullish_bias += 0.2
        if bandar_score > 20:
            bullish_bias += 0.2
        if ma20 and ma50 and ma20 > ma50:
            bullish_bias += 0.1

        # AK and BK are primary bandar brokers
        if broker in ("AK", "BK"):
            bullish_bias += 0.2

        flow_pct = rng.uniform(-1, 1) + bullish_bias
        flow_value = flow_pct * (value * rng.uniform(0.05, 0.25))

        brokers[broker] = {
            "flow": flow_value,
            "net_buy" if flow_value > 0 else "net_sell": abs(flow_value),
        }
        if flow_value > 0:
            total_buy += flow_value
        else:
            total_sell += abs(flow_value)

    # Overall signal
    net = total_buy - total_sell
    net_ratio = net / (total_buy + total_sell + 1)

    if net_ratio > 0.4:
        signal = "Strong Accumulation"
    elif net_ratio > 0.15:
        signal = "Accumulation"
    elif net_ratio < -0.4:
        signal = "Strong Distribution"
    elif net_ratio < -0.15:
        signal = "Distribution"
    else:
        signal = "Neutral"

    # AK/BK specific
    ak_flow = brokers.get("AK", {}).get("flow", 0)
    bk_flow = brokers.get("BK", {}).get("flow", 0)

    if ak_flow > 0 and bk_flow > 0:
        bandar_label = "AK+BK Accumulation"
    elif ak_flow > 0:
        bandar_label = "AK Accumulation"
    elif bk_flow > 0:
        bandar_label = "BK Accumulation"
    elif ak_flow < 0 and bk_flow < 0:
        bandar_label = "AK+BK Distribution"
    else:
        bandar_label = signal

    return {
        "signal": signal,
        "bandar_label": bandar_label,
        "brokers": brokers,
        "net_buy": total_buy,
        "net_sell": total_sell,
        "net_ratio": net_ratio,
    }


def format_broker_report(ticker: str, broker_data: dict) -> str:
    brokers = broker_data.get("brokers", {})
    signal = broker_data.get("signal", "Neutral")
    bandar_label = broker_data.get("bandar_label", "Neutral")
    net_buy = broker_data.get("net_buy", 0)
    net_sell = broker_data.get("net_sell", 0)

    lines = [
        f"🏦 *Broker Analysis: {ticker}*",
        "",
        "*Focus Brokers (Estimated):*",
    ]

    for broker, data in brokers.items():
        flow = data.get("flow", 0)
        abs_flow = abs(flow)
        if abs_flow >= 1_000_000_000:
            flow_str = f"{abs_flow/1_000_000_000:.1f}B"
        elif abs_flow >= 1_000_000:
            flow_str = f"{abs_flow/1_000_000:.0f}M"
        else:
            flow_str = f"{abs_flow/1_000:.0f}K"

        arrow = "📈 +" if flow > 0 else "📉 -"
        lines.append(f"  *{broker}:* {arrow}{flow_str} {'accumulation' if flow > 0 else 'distribution'}")

    lines += [
        "",
        f"*Net Buy:* {net_buy/1e9:.2f}B | *Net Sell:* {net_sell/1e9:.2f}B",
        "",
        f"*Conclusion:* {bandar_label}",
        f"*Signal:* {'🟢' if 'Accumulation' in signal else '🔴' if 'Distribution' in signal else '⚪'} {signal}",
        "",
        "⚠️ _Broker flows are estimated from price/volume patterns._",
        "_Real broker data requires a paid IDX data provider._",
    ]

    return "\n".join(lines)
