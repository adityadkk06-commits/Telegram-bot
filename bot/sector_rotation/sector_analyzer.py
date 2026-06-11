"""
Sector Rotation Analyzer — Official IDX 11-Sector Classification.

Calculates per sector:
  • Equal-weight average return
  • Median return (robust to outliers)
  • Market-cap weighted return  (uses yfinance marketCap, falls back to value-weight)
  • Transaction value weighted return
  • Sector money flow score
  • Rotation score (0–100)
  • Improving / deteriorating flag

Sector strength formula (from prompt spec):
  score = (weighted_market_cap_return × 50%)
        + (weighted_transaction_value × 30%)
        + (relative_volume_strength × 20%)

Large-cap stocks influence sector performance more than micro-caps.
"""

import logging
import statistics
import time
import yfinance as yf

from bot.services.data_service import get_sector_snapshots, generate_data_report
from bot.services.ai_service    import generate_sector_analysis
from bot.utils.constants        import IDX_STOCKS, SECTOR_ICONS

logger = logging.getLogger(__name__)

# ── Market cap cache (lightweight, 30-min TTL) ────────────────────────────────
_MCAP_CACHE: dict = {}
_MCAP_TIME:  dict = {}
_MCAP_TTL = 1800   # 30 minutes

def _get_market_cap(ticker: str) -> float | None:
    now = time.time()
    if ticker in _MCAP_CACHE and (now - _MCAP_TIME.get(ticker, 0)) < _MCAP_TTL:
        return _MCAP_CACHE[ticker]
    try:
        info = yf.Ticker(f"{ticker}.JK").get_fast_info()
        mc   = getattr(info, "market_cap", None)
        if mc is None:
            # Fallback: try .info dict (slower but more complete)
            full = yf.Ticker(f"{ticker}.JK").info
            mc   = full.get("marketCap") or full.get("market_cap")
    except Exception:
        mc = None

    if mc:
        logger.debug(f"[MCAP] {ticker}: {mc:,.0f} IDR")
    else:
        logger.warning(f"[DATA] WARNING: {ticker} missing market_cap")

    _MCAP_CACHE[ticker] = mc
    _MCAP_TIME[ticker]  = now
    return mc


# ── Weighted return helpers ───────────────────────────────────────────────────

def _value_weighted_return(snapshots: list) -> float:
    """Transaction-value weighted return."""
    total = sum(s.get("value", 0) or 0 for s in snapshots)
    if total <= 0:
        return 0.0
    return sum(s.get("pct_chg", 0) * (s.get("value", 0) or 0)
               for s in snapshots) / total


def _mcap_weighted_return(snapshots: list) -> float:
    """
    Market-cap weighted return.
    Fetches market caps; falls back to value weighting if caps unavailable.
    """
    caps = {}
    for s in snapshots:
        t  = s.get("ticker", "")
        mc = _get_market_cap(t)
        caps[t] = mc or 0.0

    total_cap = sum(caps.values())
    if total_cap <= 0:
        logger.debug("[MCAP] No market caps available, falling back to value-weight")
        return _value_weighted_return(snapshots)

    return sum(
        s.get("pct_chg", 0) * caps.get(s.get("ticker", ""), 0)
        for s in snapshots
    ) / total_cap


def _money_flow_score(snapshots: list) -> float:
    """
    Money flow: net of (value of gainers) - (value of losers),
    expressed as % of total sector value.
    +100 = all money flowing in, -100 = all flowing out.
    """
    inflow   = sum(s.get("value", 0) or 0 for s in snapshots if s.get("pct_chg", 0) > 0)
    outflow  = sum(s.get("value", 0) or 0 for s in snapshots if s.get("pct_chg", 0) < 0)
    total    = inflow + outflow
    if total <= 0:
        return 0.0
    return round((inflow - outflow) / total * 100, 1)


# ── Rotation score ────────────────────────────────────────────────────────────

def _sector_score(
    mcap_w_pct:  float,
    val_w_pct:   float,
    avg_rel_vol: float,
    avg_rsi:     float,
) -> float:
    """
    Rotation score 0–100 using prompt spec formula:
      score = (mcap_weighted × 50%) + (value_weighted × 30%) + (vol_strength × 20%)
    """
    # Component 1: market-cap weighted return (50 pts)
    pct1 = mcap_w_pct
    if pct1 >= 3:      c1 = 50
    elif pct1 >= 2:    c1 = 40
    elif pct1 >= 1:    c1 = 30
    elif pct1 >= 0:    c1 = 18
    elif pct1 >= -1:   c1 = 8
    elif pct1 >= -2:   c1 = 3
    else:              c1 = 0

    # Component 2: value weighted return (30 pts)
    pct2 = val_w_pct
    if pct2 >= 3:      c2 = 30
    elif pct2 >= 2:    c2 = 24
    elif pct2 >= 1:    c2 = 17
    elif pct2 >= 0:    c2 = 10
    elif pct2 >= -1:   c2 = 4
    else:              c2 = 0

    # Component 3: volume strength (20 pts)
    if avg_rel_vol >= 2.0:    c3 = 20
    elif avg_rel_vol >= 1.5:  c3 = 14
    elif avg_rel_vol >= 1.2:  c3 = 9
    elif avg_rel_vol >= 1.0:  c3 = 4
    else:                     c3 = 0

    return round(max(0.0, min(100.0, c1 + c2 + c3)), 1)


# ── Core analyzer ─────────────────────────────────────────────────────────────

def analyze_sectors() -> dict:
    """
    Fetch live data for ALL tickers in every IDX sector and compute:
      - equal-weight avg return
      - median return
      - market-cap weighted return
      - transaction value weighted return
      - rotation score (prompt spec formula)
      - money flow score
      - improving / deteriorating flag

    Returns:
      {
        "sectors":     [sector_dict, ...],
        "strongest":   sector_name,
        "weakest":     sector_name,
        "improving":   sector_name,
        "deteriorating": sector_name,
        "highest_flow": sector_name,
        "ai_note":     str,
        "data_report": str,
      }
    """
    sector_results = []
    all_snapshots  = []

    for sector_name, tickers in IDX_STOCKS.items():
        icon = SECTOR_ICONS.get(sector_name, "📊")

        # ── Fetch ALL tickers for this sector ────────────────────────────────
        snaps = get_sector_snapshots(sector_name, tickers)
        if not snaps:
            logger.warning(
                f"[SECTOR] MISSING SECTOR DATA: '{sector_name}' — "
                f"no valid data for any of {tickers[:5]}…"
            )
            continue

        all_snapshots.extend(snaps)

        # ── Basic stats ───────────────────────────────────────────────────────
        pcts     = [s.get("pct_chg",  0)   for s in snaps]
        rvols    = [s.get("rel_vol",   1.0) or 1.0 for s in snaps]
        rsis     = [s.get("rsi",       50)  or 50   for s in snaps]
        values   = [s.get("value",     0)   for s in snaps]

        avg_pct     = sum(pcts)   / len(pcts)
        avg_rel_vol = sum(rvols)  / len(rvols)
        avg_rsi     = sum(rsis)   / len(rsis)
        total_value = sum(values)
        median_pct  = statistics.median(pcts) if pcts else 0.0

        # ── Weighted returns (market cap + value) ─────────────────────────────
        val_w_pct  = _value_weighted_return(snaps)
        mcap_w_pct = _mcap_weighted_return(snaps)

        # ── Rotation score ────────────────────────────────────────────────────
        score = _sector_score(mcap_w_pct, val_w_pct, avg_rel_vol, avg_rsi)

        # ── Money flow ────────────────────────────────────────────────────────
        flow = _money_flow_score(snaps)
        if flow > 20:
            flow_label = "💰 Inflow"
        elif flow < -20:
            flow_label = "🔴 Outflow"
        else:
            flow_label = "⚪ Neutral"

        # ── Data quality check ────────────────────────────────────────────────
        pct_rounded  = [round(p, 2) for p in pcts]
        most_common  = max(set(pct_rounded), key=pct_rounded.count)
        uniform_cnt  = pct_rounded.count(most_common)
        data_quality = "⚠️ SUSPECT" if uniform_cnt / len(pcts) >= 0.6 else "✅ OK"
        if data_quality == "⚠️ SUSPECT":
            logger.error(
                f"[SECTOR] SECTOR_CALCULATION_ERROR {sector_name}: "
                f"{uniform_cnt}/{len(pcts)} stocks share pct_chg={most_common}% — "
                f"possible rate-limit. Tickers: {[s['ticker'] for s in snaps]}"
            )

        # ── Improving/deteriorating proxy ─────────────────────────────────────
        # Improving: mcap_weighted > equal_weight (large caps outperforming avg)
        # Deteriorating: mcap_weighted < equal_weight by >0.5%
        diff = mcap_w_pct - avg_pct
        if diff > 0.5:
            rotation_direction = "📈 Improving"
        elif diff < -0.5:
            rotation_direction = "📉 Deteriorating"
        else:
            rotation_direction = "➡️ Stable"

        # ── Top candidates ────────────────────────────────────────────────────
        candidates = sorted(snaps, key=lambda x: x.get("pct_chg", 0), reverse=True)[:3]

        logger.info(
            f"[SECTOR] {icon} {sector_name:20s} | "
            f"n={len(snaps):3d} | eq={avg_pct:+6.2f}% | "
            f"med={median_pct:+6.2f}% | "
            f"val_w={val_w_pct:+6.2f}% | "
            f"mcap_w={mcap_w_pct:+6.2f}% | "
            f"flow={flow:+5.1f}% | "
            f"score={score:5.1f} | "
            f"dir={rotation_direction} | {data_quality}"
        )

        sector_results.append({
            "name":               sector_name,
            "icon":               icon,
            "pct_chg":            round(avg_pct,      2),
            "median_pct":         round(median_pct,   2),
            "weighted_pct":       round(val_w_pct,    2),
            "mcap_weighted_pct":  round(mcap_w_pct,   2),
            "total_value":        total_value,
            "avg_rsi":            round(avg_rsi,      1),
            "avg_rel_vol":        round(avg_rel_vol,  2),
            "rotation_score":     score,
            "money_flow":         flow,
            "money_flow_label":   flow_label,
            "rotation_direction": rotation_direction,
            "stock_count":        len(snaps),
            "candidates":         candidates,
            "data_quality":       data_quality,
            "stocks":             snaps,
        })

    if not sector_results:
        return {"sectors": [], "ai_note": "No data", "data_report": "No data"}

    # ── Sort by market-cap weighted return (primary) + score (tie-break) ─────
    sector_results.sort(
        key=lambda x: (x["mcap_weighted_pct"], x["rotation_score"]),
        reverse=True
    )

    # ── Special rankings ──────────────────────────────────────────────────────
    strongest   = sector_results[0]["name"] if sector_results else ""
    weakest     = sector_results[-1]["name"] if sector_results else ""
    improving   = max(sector_results,
                      key=lambda x: x["mcap_weighted_pct"] - x["pct_chg"])["name"]
    deteriorating = min(sector_results,
                        key=lambda x: x["mcap_weighted_pct"] - x["pct_chg"])["name"]
    highest_flow  = max(sector_results, key=lambda x: x["money_flow"])["name"]

    # ── Cross-validation log (compare equal-weight vs mcap-weight) ───────────
    for sr in sector_results:
        deviation = abs(sr["mcap_weighted_pct"] - sr["pct_chg"])
        if deviation >= 0.5:
            logger.info(
                f"[SECTOR] SECTOR MISMATCH: {sr['name']:20s} "
                f"eq={sr['pct_chg']:+.2f}% "
                f"mcap_w={sr['mcap_weighted_pct']:+.2f}% "
                f"deviation={deviation:.2f}%"
            )

    # ── AI note ───────────────────────────────────────────────────────────────
    ai_note = generate_sector_analysis(sector_results)

    # ── Data quality report ───────────────────────────────────────────────────
    data_report = generate_data_report(all_snapshots)
    logger.info(f"\n{data_report}")

    return {
        "sectors":        sector_results,
        "strongest":      strongest,
        "weakest":        weakest,
        "improving":      improving,
        "deteriorating":  deteriorating,
        "highest_flow":   highest_flow,
        "ai_note":        ai_note,
        "data_report":    data_report,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Telegram message formatter
# ─────────────────────────────────────────────────────────────────────────────

def format_sector_rotation(data: dict) -> str:
    sectors = data.get("sectors",      [])
    ai_note = data.get("ai_note",      "")
    strong  = data.get("strongest",    "")
    weak    = data.get("weakest",      "")
    impr    = data.get("improving",    "")
    detr    = data.get("deteriorating","")
    hflow   = data.get("highest_flow", "")

    if not sectors:
        return "❌ Unable to fetch sector data. Please try again."

    sep = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    lines = [sep, "🔄 *IDX Sector Rotation*  _(mcap-weighted)_", ""]

    # ── Market rotation summary ───────────────────────────────────────────────
    lines += [
        f"🔥 *Strongest:*   {SECTOR_ICONS.get(strong,'')}{strong}",
        f"📉 *Weakest:*     {SECTOR_ICONS.get(weak,'')}{weak}",
        f"📈 *Improving:*   {SECTOR_ICONS.get(impr,'')}{impr}",
        f"💸 *Deteriorating:* {SECTOR_ICONS.get(detr,'')}{detr}",
        f"💰 *Highest Flow:*  {SECTOR_ICONS.get(hflow,'')}{hflow}",
        "",
    ]

    # ── Sector table ─────────────────────────────────────────────────────────
    lines.append("📊 *All Sectors:*")
    for s in sectors:
        eq   = s["pct_chg"]
        mw   = s["mcap_weighted_pct"]
        sign = "+" if mw >= 0 else ""
        dq   = " ⚠️" if s["data_quality"] == "⚠️ SUSPECT" else ""
        lines.append(
            f"  {s['icon']} *{s['name'][:14]:14s}*{dq} "
            f"{sign}{mw:.2f}% "
            f"(eq {eq:+.2f}%) "
            f"│ {s['money_flow_label']} "
            f"│ {s['rotation_direction']}"
        )

    lines.append("")

    # ── Top candidates from strongest sector ──────────────────────────────────
    top_s = sectors[0]
    lines.append(f"🎯 *Top Picks — {top_s['icon']} {top_s['name']}:*")
    for c in top_s.get("candidates", [])[:3]:
        t    = c.get("ticker",  "")
        pct  = c.get("pct_chg",  0)
        rv   = c.get("rel_vol",  1) or 1
        val  = c.get("value",    0)
        sign = "+" if pct >= 0 else ""
        lines.append(
            f"  • *{t}*  {sign}{pct:.2f}%  "
            f"Vol:{rv:.1f}×  Val:{val/1e9:.1f}B IDR"
        )

    lines.append("")
    lines.append(sep)
    lines += ["", ai_note]
    return "\n".join(lines)
