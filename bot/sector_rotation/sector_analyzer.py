"""
Sector Rotation Analyzer — Official IDX 11-Sector Classification.

Calculates per sector:
  • Equal-weight average return
  • Median return (robust to outliers)
  • Volume-weighted return
  • Rotation score (0–100)

Root-cause fix for identical-value bug:
  • Old code used tickers[:6] — too few samples, bias from bad yfinance responses
  • New code uses ALL tickers per sector (no artificial cap)
  • Outlier stocks (pct_chg outside IDX range) already rejected in data_service
  • Uniform-data warning fired in data_service._detect_uniform_data()
"""

import logging
import statistics
from bot.services.data_service import get_sector_snapshots, generate_data_report
from bot.services.ai_service import generate_sector_analysis
from bot.utils.constants import IDX_STOCKS, SECTOR_ICONS

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Core analyzer
# ─────────────────────────────────────────────────────────────────────────────

def _weighted_return(snapshots: list) -> float:
    """Volume-weighted average return — avoids large-cap bias of value-weighting."""
    total_vol = sum(s.get("volume", 0) for s in snapshots)
    if total_vol <= 0:
        return 0.0
    return sum(s.get("pct_chg", 0) * s.get("volume", 0) for s in snapshots) / total_vol


def _sector_score(avg_pct: float, avg_rel_vol: float, avg_rsi: float) -> float:
    """
    Rotation score 0–100.
    Component weights:
      • Return momentum  (50 pts)
      • Volume surge     (30 pts)
      • RSI momentum     (20 pts)
    """
    score = 0.0

    # Return momentum
    if avg_pct >= 4:      score += 50
    elif avg_pct >= 2:    score += 38
    elif avg_pct >= 1:    score += 27
    elif avg_pct >= 0:    score += 15
    elif avg_pct >= -1:   score += 8
    elif avg_pct >= -2:   score += 3
    # below -2 → 0 pts

    # Volume surge
    if avg_rel_vol >= 2.0:   score += 30
    elif avg_rel_vol >= 1.5: score += 22
    elif avg_rel_vol >= 1.2: score += 15
    elif avg_rel_vol >= 1.0: score += 8

    # RSI momentum (ideal zone 45–65)
    if 45 <= avg_rsi <= 65:       score += 20
    elif 35 <= avg_rsi <= 75:     score += 10
    elif avg_rsi > 75:            score += 5   # overbought = some momentum
    # oversold or no data → 0

    return round(max(0.0, min(100.0, score)), 1)


def analyze_sectors() -> dict:
    """
    Fetch live data for ALL tickers in every IDX sector and compute:
      - equal-weight avg return
      - median return
      - volume-weighted return
      - rotation score
      - top-3 candidates

    Returns:
      {
        "sectors": [ { name, icon, pct_chg, median_pct, weighted_pct,
                        avg_rsi, avg_rel_vol, rotation_score, total_value,
                        stock_count, candidates, data_quality } ],
        "ai_note": str,
        "data_report": str,
      }
    """
    sector_results = []
    all_snapshots  = []

    for sector_name, tickers in IDX_STOCKS.items():
        icon = SECTOR_ICONS.get(sector_name, "📊")

        # ── Fetch ALL tickers for this sector (no artificial cap) ────────────
        snaps = get_sector_snapshots(sector_name, tickers)

        if not snaps:
            logger.warning(f"analyze_sectors: no data for sector '{sector_name}'")
            continue

        all_snapshots.extend(snaps)

        pcts     = [s.get("pct_chg",  0)   for s in snaps]
        rvols    = [s.get("rel_vol",   1.0) or 1.0 for s in snaps]
        rsis     = [s.get("rsi",       50)  or 50   for s in snaps]
        values   = [s.get("value",     0)   for s in snaps]

        avg_pct     = sum(pcts)   / len(pcts)
        avg_rel_vol = sum(rvols)  / len(rvols)
        avg_rsi     = sum(rsis)   / len(rsis)
        total_value = sum(values)
        median_pct  = statistics.median(pcts) if pcts else 0.0
        w_pct       = _weighted_return(snaps)
        score       = _sector_score(avg_pct, avg_rel_vol, avg_rsi)

        # Top candidates: sort by pct_chg desc, take top 3
        candidates  = sorted(snaps, key=lambda x: x.get("pct_chg", 0), reverse=True)[:3]

        # Data quality flag
        pct_rounded  = [round(p, 2) for p in pcts]
        most_common  = max(set(pct_rounded), key=pct_rounded.count)
        uniform_cnt  = pct_rounded.count(most_common)
        data_quality = "⚠️ SUSPECT" if uniform_cnt / len(pcts) >= 0.6 else "✅ OK"

        logger.info(
            f"[SECTOR] {icon} {sector_name:20s} | "
            f"n={len(snaps):3d} | avg={avg_pct:+6.2f}% | med={median_pct:+6.2f}% | "
            f"wgt={w_pct:+6.2f}% | score={score:5.1f} | "
            f"relVol={avg_rel_vol:.2f}x | RSI={avg_rsi:.1f} | {data_quality}"
        )

        sector_results.append({
            "name":          sector_name,
            "icon":          icon,
            "pct_chg":       round(avg_pct,    2),
            "median_pct":    round(median_pct, 2),
            "weighted_pct":  round(w_pct,      2),
            "total_value":   total_value,
            "avg_rsi":       round(avg_rsi,    1),
            "avg_rel_vol":   round(avg_rel_vol,2),
            "rotation_score":score,
            "stock_count":   len(snaps),
            "candidates":    candidates,
            "data_quality":  data_quality,
            "stocks":        snaps,
        })

    # Sort by equal-weight average return (primary) then score (tie-break)
    sector_results.sort(key=lambda x: (x["pct_chg"], x["rotation_score"]), reverse=True)

    # ── AI note ──────────────────────────────────────────────────────────────
    ai_note = generate_sector_analysis(sector_results)

    # ── Data quality report ──────────────────────────────────────────────────
    data_report = generate_data_report(all_snapshots)
    logger.info(f"\n{data_report}")

    return {
        "sectors":     sector_results,
        "ai_note":     ai_note,
        "data_report": data_report,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Telegram message formatter
# ─────────────────────────────────────────────────────────────────────────────

def format_sector_rotation(data: dict) -> str:
    sectors = data.get("sectors", [])
    ai_note = data.get("ai_note", "")

    if not sectors:
        return "❌ Unable to fetch sector data. Please try again."

    sep = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    lines = [sep, "🔄 *IDX Sector Rotation*", ""]

    # ── Strongest (top 4) ────────────────────────────────────────────────────
    strongest = sectors[:4]
    lines.append("🔥 *Strongest Sectors:*")
    for i, s in enumerate(strongest, 1):
        sign = "+" if s["pct_chg"] >= 0 else ""
        dq   = " ⚠️" if s["data_quality"] == "⚠️ SUSPECT" else ""
        lines.append(
            f"  {i}. {s['icon']} *{s['name']}*{dq}  "
            f"{sign}{s['pct_chg']:.2f}%  "
            f"(med {s['median_pct']:+.2f}%)  "
            f"Score: {s['rotation_score']:.0f}/100"
        )

    lines.append("")

    # ── Weakest (bottom 3) ───────────────────────────────────────────────────
    weakest = sectors[-3:]
    lines.append("⚠️ *Weakest Sectors:*")
    for s in weakest:
        sign = "+" if s["pct_chg"] >= 0 else ""
        lines.append(
            f"  • {s['icon']} {s['name']}  {sign}{s['pct_chg']:.2f}%"
        )

    lines.append("")

    # ── Top candidates from #1 sector ────────────────────────────────────────
    lines.append(f"🎯 *Top Picks — {strongest[0]['icon']} {strongest[0]['name']}:*")
    for c in strongest[0].get("candidates", [])[:3]:
        ticker = c.get("ticker", "")
        pct    = c.get("pct_chg", 0)
        rv     = c.get("rel_vol", 1) or 1
        sign   = "+" if pct >= 0 else ""
        lines.append(f"  • *{ticker}*  {sign}{pct:.2f}%  Vol:{rv:.1f}×")

    lines.append("")
    lines.append(sep)
    lines += ["", ai_note]
    return "\n".join(lines)
