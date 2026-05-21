def fmt_price(p):
    if p is None or p != p:
        return "N/A"
    return f"{p:,.0f}"

def fmt_volume(v):
    if v is None or v != v:
        return "N/A"
    if v >= 1_000_000_000:
        return f"{v/1_000_000_000:.2f}B"
    elif v >= 1_000_000:
        return f"{v/1_000_000:.2f}M"
    elif v >= 1_000:
        return f"{v/1_000:.2f}K"
    return str(int(v))

def fmt_value(v):
    if v is None or v != v:
        return "N/A"
    if v >= 1_000_000_000:
        return f"Rp {v/1_000_000_000:.1f}B"
    elif v >= 1_000_000:
        return f"Rp {v/1_000_000:.1f}M"
    return f"Rp {v:,.0f}"

def fmt_pct(p):
    if p is None or p != p:
        return "N/A"
    sign = "+" if p >= 0 else ""
    return f"{sign}{p:.2f}%"

def fmt_score(s):
    return f"{int(s)}/100"

def score_emoji(s):
    if s >= 80:
        return "🟢"
    elif s >= 60:
        return "🟡"
    elif s >= 40:
        return "🟠"
    return "🔴"

def pct_change_emoji(p):
    if p is None:
        return ""
    if p > 2:
        return "🚀"
    elif p > 0:
        return "📈"
    elif p < -2:
        return "💥"
    elif p < 0:
        return "📉"
    return "➡️"

def broker_signal_emoji(signal):
    if "Strong Accumulation" in signal:
        return "🏦💚"
    elif "Accumulation" in signal:
        return "🏦🟢"
    elif "Distribution" in signal:
        return "🏦🔴"
    elif "Neutral" in signal:
        return "🏦⚪"
    return "🏦"
