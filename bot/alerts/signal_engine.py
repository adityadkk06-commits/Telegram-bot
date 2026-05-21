"""
Professional Trading Analysis Engine.

Generates trade signals using:
  - ATR-based entry / TP / SL levels
  - Broker accumulation score (BandarScore)
  - Momentum indicators (RSI, MACD, MA cross)
  - Volume spike detection
  - Breakout confirmation
  - Risk/Reward ratio
"""
import logging
import numpy as np
import pandas as pd
from bot.services.data_service import get_stock_data, compute_indicators
from bot.bandarmology.broker_analyzer import estimate_broker_signal

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Core signal generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_trade_signal(stock: dict) -> dict:
    """
    Full professional analysis for one stock snapshot.

    Returns dict with:
        entry, tp1, tp2, sl, rr_ratio,
        confidence (0–10), signals (list of str),
        analysis_lines (list of str)
    """
    ticker  = stock.get("ticker", "?")
    price   = stock.get("price", 0)
    if not price:
        return _empty_signal(ticker)

    # Fetch OHLCV and compute full indicators
    df = get_stock_data(ticker, period="3mo")
    if df is None or len(df) < 20:
        return _basic_signal(stock)

    df = compute_indicators(df)

    # Add MA10 locally (not in main compute_indicators — stays non-destructive)
    df["MA10"] = df["Close"].rolling(10).mean()
    df["ATR"]  = _compute_atr(df, 14)

    latest   = df.iloc[-1]
    prev     = df.iloc[-2] if len(df) > 1 else latest
    prev2    = df.iloc[-3] if len(df) > 2 else prev

    close    = float(latest["Close"])
    ma10     = float(latest["MA10"]) if pd.notna(latest["MA10"]) else close
    ma20     = float(latest["MA20"]) if pd.notna(latest["MA20"]) else close
    ma50     = float(latest["MA50"]) if pd.notna(latest["MA50"]) else close
    rsi      = float(latest["RSI"])  if pd.notna(latest["RSI"])  else 50
    macd     = float(latest["MACD"]) if pd.notna(latest["MACD"]) else 0
    macd_sig = float(latest["MACD_Signal"]) if pd.notna(latest["MACD_Signal"]) else 0
    rel_vol  = float(latest["RelVol"]) if pd.notna(latest["RelVol"]) else 1
    bandar   = float(latest["BandarScore"]) if pd.notna(latest["BandarScore"]) else 0
    atr      = float(latest["ATR"]) if pd.notna(latest["ATR"]) else close * 0.02

    pct_chg  = stock.get("pct_chg", 0)
    value    = stock.get("value", 0)

    broker = estimate_broker_signal(stock)
    broker_signal = broker.get("signal", "neutral")

    # ── Support & Resistance (pivot from last 20 bars) ────────────────────
    recent    = df.tail(20)
    support   = float(recent["Low"].min())
    resistance= float(recent["High"].max())

    # ── Signal checklist ──────────────────────────────────────────────────
    signals    = []
    score      = 0.0

    # MA10 > MA20 (golden cross zone)
    if ma10 > ma20:
        signals.append("✅ MA10 > MA20 bullish alignment")
        score += 1.5
    if float(prev["MA10"]) < float(prev["MA20"]) and ma10 > ma20:
        signals.append("🔥 Fresh Golden Cross detected!")
        score += 1.0

    # Price above MAs
    if close > ma20:
        signals.append("✅ Price above MA20 (bullish zone)")
        score += 1.0
    if close > ma50:
        signals.append("✅ Price above MA50 (strong uptrend)")
        score += 0.5

    # Volume spike
    if rel_vol >= 3.0:
        signals.append(f"✅ Volume surge {rel_vol:.1f}× average")
        score += 1.5
    elif rel_vol >= 2.0:
        signals.append(f"✅ Volume spike {rel_vol:.1f}× average")
        score += 1.0
    elif rel_vol >= 1.5:
        signals.append(f"🔸 Above-avg volume {rel_vol:.1f}×")
        score += 0.5

    # MACD
    if macd > macd_sig:
        signals.append("✅ MACD bullish crossover")
        score += 1.0
    if macd > 0:
        signals.append("✅ MACD positive histogram")
        score += 0.5

    # RSI
    if 40 <= rsi <= 65:
        signals.append(f"✅ RSI {rsi:.1f} (healthy momentum zone)")
        score += 1.0
    elif 65 < rsi <= 75:
        signals.append(f"🔸 RSI {rsi:.1f} (high momentum, watch for reversal)")
        score += 0.3
    elif rsi < 40:
        signals.append(f"⚠️ RSI {rsi:.1f} (weak momentum)")
        score -= 0.3

    # Bandar / smart money
    if bandar > 25:
        signals.append(f"✅ Strong bandar accumulation (score: {bandar:.0f})")
        score += 1.5
    elif bandar > 10:
        signals.append(f"✅ Bandar accumulation detected (score: {bandar:.0f})")
        score += 1.0
    elif bandar < -10:
        signals.append(f"⚠️ Bandar distribution signal ({bandar:.0f})")
        score -= 0.5

    # Broker signal
    if broker_signal == "accumulation":
        signals.append("✅ Broker accumulation detected")
        score += 1.0
    elif broker_signal == "distribution":
        signals.append("⚠️ Broker distribution detected")
        score -= 0.5

    # Price strength
    if pct_chg >= 5:
        signals.append(f"✅ Strong breakout momentum +{pct_chg:.1f}%")
        score += 0.5
    elif pct_chg >= 2:
        signals.append(f"✅ Positive momentum +{pct_chg:.1f}%")
        score += 0.3

    # Liquidity
    if value >= 10_000_000_000:
        signals.append("✅ High liquidity (value >10B IDR)")
        score += 0.5
    elif value >= 3_000_000_000:
        signals.append("✅ Good liquidity (value >3B IDR)")
        score += 0.3

    # ── Entry / TP / SL via ATR ───────────────────────────────────────────
    # Entry: slight dip from current (0.3% below)
    entry    = round(close * 0.997, 0)
    tp1      = round(entry + 2.0 * atr, 0)
    tp2      = round(entry + 3.5 * atr, 0)
    sl       = round(max(entry - 1.5 * atr, support * 0.98), 0)
    rr       = round((tp1 - entry) / max(entry - sl, 1), 2)

    # Clamp confidence to 0–10
    confidence = round(min(max(score, 0), 10), 1)

    return {
        "ticker":         ticker,
        "price":          close,
        "entry":          entry,
        "tp1":            tp1,
        "tp2":            tp2,
        "sl":             sl,
        "rr_ratio":       rr,
        "confidence":     confidence,
        "signals":        signals[:6],    # cap display
        "broker_label":   broker.get("bandar_label", "Neutral"),
        "rel_vol":        rel_vol,
        "rsi":            rsi,
        "ma10":           ma10,
        "ma20":           ma20,
        "atr":            atr,
        "support":        support,
        "resistance":     resistance,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["High"]
    low  = df["Low"]
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _empty_signal(ticker: str) -> dict:
    return {
        "ticker": ticker, "price": 0, "entry": 0, "tp1": 0, "tp2": 0, "sl": 0,
        "rr_ratio": 0, "confidence": 0, "signals": ["⚠️ No data available"],
        "broker_label": "N/A", "rel_vol": 0, "rsi": 0, "ma10": 0, "ma20": 0,
        "atr": 0, "support": 0, "resistance": 0,
    }


def _basic_signal(stock: dict) -> dict:
    """Fallback when only snapshot data is available (no OHLCV history)."""
    price  = stock.get("price", 0) or 1
    atr_est= price * 0.025
    entry  = round(price * 0.997, 0)
    tp1    = round(entry + 2.0 * atr_est, 0)
    tp2    = round(entry + 3.5 * atr_est, 0)
    sl     = round(entry - 1.5 * atr_est, 0)
    rr     = round((tp1 - entry) / max(entry - sl, 1), 2)
    return {
        "ticker": stock.get("ticker", "?"), "price": price,
        "entry": entry, "tp1": tp1, "tp2": tp2, "sl": sl,
        "rr_ratio": rr, "confidence": 5.0,
        "signals": ["🔸 Limited data — basic analysis only"],
        "broker_label": "N/A", "rel_vol": stock.get("rel_vol", 1) or 1,
        "rsi": stock.get("rsi") or 50, "ma10": 0, "ma20": 0,
        "atr": atr_est, "support": price * 0.95, "resistance": price * 1.05,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Format alert message
# ─────────────────────────────────────────────────────────────────────────────

def format_signal_message(sig: dict, pct_chg: float = 0, alert_type: str = "gainer") -> str:
    ticker    = sig["ticker"]
    price     = sig["price"]
    entry     = sig["entry"]
    tp1       = sig["tp1"]
    tp2       = sig["tp2"]
    sl        = sig["sl"]
    rr        = sig["rr_ratio"]
    conf      = sig["confidence"]
    signals   = sig.get("signals", [])
    rel_vol   = sig.get("rel_vol", 1) or 1
    rsi       = sig.get("rsi", 0)
    sign      = "+" if pct_chg >= 0 else ""
    type_label= "TOP GAINER ALERT" if alert_type == "gainer" else "GOLDEN CROSS ALERT"

    # Confidence bar
    bars = round(conf)
    bar  = "█" * bars + "░" * (10 - bars)

    analysis_block = "\n".join(signals[:5]) if signals else "📊 Analyzing…"

    return (
        f"🚨 *{type_label} — IDX*\n\n"
        f"*Stock:* {ticker}\n"
        f"*Price:* {price:,.0f} ({sign}{pct_chg:.2f}%)\n"
        f"*Volume:* {rel_vol:.1f}× avg  |  RSI: {rsi:.0f}\n\n"
        f"*Analysis:*\n{analysis_block}\n\n"
        f"*Trade Plan:*\n"
        f"🎯 Entry:  {entry:,.0f} – {round(price):,.0f}\n"
        f"🎯 TP1:   {tp1:,.0f}  (+{(tp1-entry)/entry*100:.1f}%)\n"
        f"🎯 TP2:   {tp2:,.0f}  (+{(tp2-entry)/entry*100:.1f}%)\n"
        f"🛑 SL:    {sl:,.0f}   (-{(entry-sl)/entry*100:.1f}%)\n"
        f"⚖️ R/R:   1:{rr}\n\n"
        f"*Confidence:*\n"
        f"{bar} {conf}/10\n\n"
        f"_⚠️ Not financial advice. Manage risk._"
    )
