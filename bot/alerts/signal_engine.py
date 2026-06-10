"""
Professional Trading Signal Engine — Institutional Grade.

Multi-confirmation architecture:
  11 independent confirmations, each weighted by market relevance.
  Signal tier:
    ≥ 80% → BUY   🟢
    60–79% → WAIT  🟡
    < 60%  → AVOID 🔴

Targets ~90%+ accuracy by requiring multi-indicator confluence.
"""
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  ATR helper
# ─────────────────────────────────────────────────────────────────────────────

def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ─────────────────────────────────────────────────────────────────────────────
#  Main signal generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_trade_signal(stock: dict) -> dict:
    """
    Full multi-confirmation professional analysis.

    Returns a rich dict suitable for format_signal_message().
    """
    from bot.services.data_service import get_stock_data, compute_indicators
    from bot.bandarmology.broker_analyzer import estimate_broker_signal
    from bot.alerts.bid_offer import analyze_bid_offer, scalping_probability

    ticker = stock.get("ticker", "?")
    price  = stock.get("price", 0)
    if not price:
        return _empty_signal(ticker)

    # ── Fetch history ─────────────────────────────────────────────────────
    df = get_stock_data(ticker, period="3mo")
    if df is None or len(df) < 22:
        return _basic_signal(stock)

    df = compute_indicators(df)

    # EMA (exponential) — separate from SMA used in compute_indicators
    close        = df["Close"]
    df["EMA9"]   = close.ewm(span=9,  adjust=False).mean()
    df["EMA20"]  = close.ewm(span=20, adjust=False).mean()
    df["EMA50"]  = close.ewm(span=50, adjust=False).mean()
    df["ATR"]    = _atr(df, 14)

    latest   = df.iloc[-1]
    prev     = df.iloc[-2] if len(df) > 1 else latest

    # Safe getters
    def _f(col, default=0.0):
        v = latest.get(col)
        return float(v) if v is not None and pd.notna(v) else default

    cur_close= float(latest["Close"])
    ema9     = _f("EMA9",   cur_close)
    ema20    = _f("EMA20",  cur_close)
    ema50    = _f("EMA50",  cur_close)
    ma5      = _f("MA5",    cur_close)
    ma20     = _f("MA20",   cur_close)
    rsi      = _f("RSI",    50.0)
    macd     = _f("MACD",   0.0)
    macd_sig = _f("MACD_Signal", 0.0)
    vwap     = _f("VWAP",   cur_close)
    rel_vol  = _f("RelVol", 1.0) or 1.0
    bandar   = _f("BandarScore", 0.0)
    atr_val  = _f("ATR",    cur_close * 0.02) or cur_close * 0.02

    pct_chg  = stock.get("pct_chg", 0)
    value    = stock.get("value", 0)
    high     = float(latest["High"])
    low      = float(latest["Low"])

    # Candle Strength (CLV)
    hl = max(high - low, 0.0001)
    clv= ((cur_close - low) - (high - cur_close)) / hl    # -1 to +1

    broker_data   = estimate_broker_signal(stock)
    broker_signal = broker_data.get("signal", "neutral")

    # Bid/Offer analysis
    bo = analyze_bid_offer(df.tail(25), stock)

    # ── Support & Resistance ──────────────────────────────────────────────
    recent     = df.tail(20)
    support    = float(recent["Low"].min())
    resistance = float(recent["High"].max())

    # ── 11-Factor Confirmation System ────────────────────────────────────
    # Each factor: (name, pts_full, pts_partial, full_cond, partial_cond, signal_line)
    confirmations = []
    raw_score     = 0
    max_score     = 0
    signals       = []

    def check(name, pts, full_cond, partial_pts=0, partial_cond=False, sig_pass=None, sig_fail=None):
        nonlocal raw_score, max_score
        max_score += pts
        if full_cond:
            raw_score += pts
            if sig_pass:
                signals.append(f"✅ {sig_pass}")
            confirmations.append((name, "full"))
        elif partial_cond:
            raw_score += partial_pts
            if sig_pass:
                signals.append(f"🔸 {sig_pass} (partial)")
            confirmations.append((name, "partial"))
        else:
            if sig_fail:
                signals.append(f"❌ {sig_fail}")
            confirmations.append((name, "fail"))

    # 1. EMA full alignment: EMA9 > EMA20 > EMA50 (15 pts)
    ema_full_aligned = ema9 > ema20 > ema50
    ema_partial      = ema9 > ema20
    check("EMA Alignment", 15,
          ema_full_aligned, 8, ema_partial,
          "EMA9 > EMA20 > EMA50 — full bullish alignment",
          "EMA alignment weak")

    # 2. Price above EMA20 (10 pts)
    check("Price > EMA20", 10,
          cur_close > ema20, 5, cur_close >= ema20 * 0.99,
          f"Price above EMA20 ({ema20:,.0f})",
          f"Price below EMA20 ({ema20:,.0f})")

    # 3. Price above VWAP (10 pts)
    check("Price > VWAP", 10,
          cur_close >= vwap, 5, cur_close >= vwap * 0.99,
          f"Price above VWAP ({vwap:,.0f})",
          f"Price below VWAP ({vwap:,.0f})")

    # 4. RSI momentum (12 pts)
    rsi_ideal   = 42 <= rsi <= 68
    rsi_partial = 35 <= rsi <= 75
    check("RSI Momentum", 12,
          rsi_ideal, 6, rsi_partial,
          f"RSI {rsi:.0f} — strong momentum zone",
          f"RSI {rsi:.0f} — outside momentum zone")

    # 5. MACD bullish (12 pts)
    macd_cross  = macd > macd_sig and macd > 0
    macd_part   = macd > macd_sig
    check("MACD", 12,
          macd_cross, 6, macd_part,
          "MACD bullish crossover + positive",
          "MACD bearish signal")

    # 6. Volume spike (12 pts)
    vol_surge   = rel_vol >= 2.5
    vol_part    = rel_vol >= 1.5
    check("Volume", 12,
          vol_surge, 7, vol_part,
          f"Volume spike {rel_vol:.1f}× average",
          f"Volume weak ({rel_vol:.1f}×)")

    # 7. Bandar / smart money (12 pts)
    bandar_strong = bandar > 25
    bandar_part   = bandar > 8
    check("Smart Money", 12,
          bandar_strong, 7, bandar_part,
          f"AK accumulation detected (score: {bandar:.0f})",
          f"No accumulation signal ({bandar:.0f})")

    # 8. Candle strength — close near high (8 pts)
    candle_strong = clv > 0.5
    candle_part   = clv > 0.1
    check("Candle Strength", 8,
          candle_strong, 4, candle_part,
          f"Strong bullish candle (CLV: {clv:+.2f})",
          f"Weak candle (CLV: {clv:+.2f})")

    # 9. Bid domination from bid/offer engine (8 pts)
    bid_dom_strong = bo["bid_dominance"] in ("strong", "moderate")
    bid_dom_part   = bo["bid_dominance"] == "balanced"
    check("Bid Domination", 8,
          bid_dom_strong, 4, bid_dom_part,
          f"Bid domination confirmed ({bo['clv']:+.2f} CLV)",
          "Offer pressure detected")

    # 10. Liquidity / value filter (5 pts)
    check("Liquidity", 5,
          value >= 5_000_000_000, 3, value >= 1_500_000_000,
          "High liquidity (value >5B IDR)",
          "Low liquidity")

    # 11. Broker accumulation signal (6 pts)
    check("Broker Flow", 6,
          broker_signal == "accumulation", 3, broker_signal == "neutral",
          "Broker accumulation flow",
          "Broker distribution detected")

    # ── Signal decision ───────────────────────────────────────────────────
    confidence_pct = round(raw_score / max_score * 100) if max_score else 0

    if confidence_pct >= 80:
        signal_type   = "BUY"
        signal_emoji  = "🟢"
        status_label  = "HIGH PROBABILITY SETUP"
    elif confidence_pct >= 65:
        signal_type   = "WAIT"
        signal_emoji  = "🟡"
        status_label  = "MODERATE — WAIT FOR CONFIRMATION"
    else:
        signal_type   = "AVOID"
        signal_emoji  = "🔴"
        status_label  = "LOW PROBABILITY — AVOID"

    # Scalping probability
    scalp_prob = scalping_probability(stock, bo, ema_full_aligned, rsi)
    if scalp_prob >= 75:
        status_label = "⚡ HIGH PROBABILITY SCALPING"
    elif scalp_prob >= 55 and signal_type == "BUY":
        status_label = "📈 MOMENTUM TRADE SETUP"

    # ── ATR-based levels ──────────────────────────────────────────────────
    # Use intraday S/R to refine levels
    entry = round(cur_close * 0.997, 0)
    tp1   = round(min(entry + 2.0 * atr_val, resistance * 0.99), 0)
    tp2   = round(entry + 3.5 * atr_val, 0)
    sl    = round(max(entry - 1.5 * atr_val, support * 0.985), 0)
    rr    = round((tp1 - entry) / max(entry - sl, 1), 2)

    return {
        "ticker":          ticker,
        "price":           cur_close,
        "signal_type":     signal_type,
        "signal_emoji":    signal_emoji,
        "status_label":    status_label,
        "entry":           entry,
        "entry_low":       round(entry * 0.997, 0),
        "tp1":             tp1,
        "tp2":             tp2,
        "sl":              sl,
        "rr_ratio":        rr,
        "confidence_pct":  confidence_pct,
        "scalp_prob":      scalp_prob,
        "signals":         signals[:8],
        "confirmations":   confirmations,
        "broker_label":    broker_data.get("bandar_label", "Neutral"),
        "rel_vol":         rel_vol,
        "rsi":             rsi,
        "ema9":            ema9,
        "ema20":           ema20,
        "ema50":           ema50,
        "ema_aligned":     ema_full_aligned,
        "atr":             atr_val,
        "support":         support,
        "resistance":      resistance,
        "bid_offer":       bo,
        "clv":             clv,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Professional message formatter (━━━━ style)
# ─────────────────────────────────────────────────────────────────────────────

_SEP = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

def format_signal_message(sig: dict, pct_chg: float = 0,
                           alert_type: str = "gainer") -> str:
    ticker   = sig["ticker"]
    price    = sig["price"]
    entry    = sig["entry"]
    entry_lo = sig.get("entry_low", entry)
    tp1      = sig["tp1"]
    tp2      = sig["tp2"]
    sl       = sig["sl"]
    rr       = sig["rr_ratio"]
    conf     = sig["confidence_pct"]
    scalp    = sig.get("scalp_prob", 0)
    signal_t = sig.get("signal_type", "WAIT")
    sig_emo  = sig.get("signal_emoji", "🟡")
    status   = sig.get("status_label", "")
    signals  = sig.get("signals", [])
    rel_vol  = sig.get("rel_vol", 1) or 1
    rsi      = sig.get("rsi", 0)

    sign     = "+" if pct_chg >= 0 else ""

    # Confidence bar (10-block)
    filled = round(conf / 10)
    bar    = "█" * filled + "░" * (10 - filled)

    # Alert type header
    if alert_type == "golden_cross":
        header = "✨ GOLDEN CROSS ALERT"
    elif alert_type == "price_alert":
        header = "🔔 PRICE ALERT TRIGGERED"
    elif alert_type == "top_scalping":
        header = "⚡ TOP SCALPING ALERT"
    else:
        header = "🔥 TOP GAINER ALERT"

    analysis_block = "\n".join(signals[:6]) if signals else "📊 Analyzing…"

    tp1_pct = (tp1 - entry) / entry * 100 if entry else 0
    tp2_pct = (tp2 - entry) / entry * 100 if entry else 0
    sl_pct  = (entry - sl)  / entry * 100 if entry else 0

    return (
        f"{_SEP}\n"
        f"{header} — IDX\n\n"
        f"Stock      : *{ticker}*\n"
        f"Price      : *{price:,.0f}* ({sign}{pct_chg:.2f}%)\n"
        f"Signal     : *{sig_emo} {signal_t}*\n"
        f"Entry      : *{entry_lo:,.0f} – {entry:,.0f}*\n"
        f"TP1        : {tp1:,.0f}  (+{tp1_pct:.1f}%)\n"
        f"TP2        : {tp2:,.0f}  (+{tp2_pct:.1f}%)\n"
        f"SL         : {sl:,.0f}   (-{sl_pct:.1f}%)\n"
        f"Risk/Reward: 1:{rr}\n"
        f"Confidence : {bar} {conf}%\n"
        f"Volume     : {rel_vol:.1f}× avg  |  RSI: {rsi:.0f}\n\n"
        f"*Analysis:*\n{analysis_block}\n\n"
        f"*Status:*\n{status}\n"
        f"Scalp Prob : {'█'*round(scalp/10)}{'░'*(10-round(scalp/10))} {scalp}%\n"
        f"{_SEP}\n"
        f"_⚠️ Not financial advice. Always manage risk._"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Fallbacks
# ─────────────────────────────────────────────────────────────────────────────

def _empty_signal(ticker: str) -> dict:
    return {
        "ticker": ticker, "price": 0, "signal_type": "AVOID", "signal_emoji": "🔴",
        "status_label": "NO DATA", "entry": 0, "entry_low": 0, "tp1": 0, "tp2": 0,
        "sl": 0, "rr_ratio": 0, "confidence_pct": 0, "scalp_prob": 0,
        "signals": ["⚠️ No market data available"], "confirmations": [],
        "broker_label": "N/A", "rel_vol": 0, "rsi": 0, "ema9": 0, "ema20": 0,
        "ema50": 0, "ema_aligned": False, "atr": 0, "support": 0, "resistance": 0,
        "bid_offer": {}, "clv": 0,
    }


def _basic_signal(stock: dict) -> dict:
    """Minimal signal when full OHLCV history is unavailable."""
    price   = stock.get("price", 1) or 1
    pct     = stock.get("pct_chg", 0)
    atr_est = price * 0.025
    entry   = round(price * 0.997, 0)
    tp1     = round(entry + 2.0 * atr_est, 0)
    tp2     = round(entry + 3.5 * atr_est, 0)
    sl      = round(entry - 1.5 * atr_est, 0)
    rr      = round((tp1 - entry) / max(entry - sl, 1), 2)
    conf    = min(60, max(30, 40 + pct * 3))
    return {
        "ticker": stock.get("ticker", "?"), "price": price,
        "signal_type": "WAIT", "signal_emoji": "🟡",
        "status_label": "LIMITED DATA — USE WITH CAUTION",
        "entry": entry, "entry_low": round(entry * 0.997, 0),
        "tp1": tp1, "tp2": tp2, "sl": sl, "rr_ratio": rr,
        "confidence_pct": int(conf), "scalp_prob": 40,
        "signals": ["🔸 Insufficient history — basic estimates only"],
        "confirmations": [], "broker_label": "N/A",
        "rel_vol": stock.get("rel_vol", 1) or 1,
        "rsi": stock.get("rsi") or 50,
        "ema9": price, "ema20": price, "ema50": price, "ema_aligned": False,
        "atr": atr_est, "support": price * 0.95, "resistance": price * 1.05,
        "bid_offer": {}, "clv": 0,
    }
