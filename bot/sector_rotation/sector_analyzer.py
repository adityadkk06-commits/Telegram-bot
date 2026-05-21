import logging
from bot.services.data_service import get_market_snapshot
from bot.utils.constants import IDX_STOCKS
from bot.services.ai_service import generate_sector_analysis

logger = logging.getLogger(__name__)


def analyze_sectors() -> dict:
    sector_results = []

    for sector, tickers in IDX_STOCKS.items():
        snapshots = get_market_snapshot(tickers[:6])  # limit per sector for speed
        if not snapshots:
            continue

        avg_pct = sum(s.get("pct_chg", 0) for s in snapshots) / len(snapshots)
        total_value = sum(s.get("value", 0) for s in snapshots)
        avg_rsi = sum(s.get("rsi", 50) or 50 for s in snapshots) / len(snapshots)
        avg_rel_vol = sum(s.get("rel_vol", 1) or 1 for s in snapshots) / len(snapshots)

        # Rotation score
        score = 50.0
        if avg_pct > 2:
            score += 20
        elif avg_pct > 0:
            score += 10
        elif avg_pct < -2:
            score -= 20
        elif avg_pct < 0:
            score -= 10
        if avg_rel_vol > 1.5:
            score += 10
        if avg_rsi and 45 < avg_rsi < 65:
            score += 5

        score = max(0, min(100, score))

        # Best candidates in sector
        candidates = sorted(snapshots, key=lambda x: x.get("pct_chg", 0), reverse=True)[:3]

        sector_results.append({
            "name": sector,
            "pct_chg": avg_pct,
            "total_value": total_value,
            "avg_rsi": avg_rsi,
            "avg_rel_vol": avg_rel_vol,
            "rotation_score": score,
            "candidates": candidates,
            "stocks": snapshots,
        })

    sector_results.sort(key=lambda x: x.get("pct_chg", 0), reverse=True)

    ai_note = generate_sector_analysis(sector_results)

    return {
        "sectors": sector_results,
        "ai_note": ai_note,
    }


def format_sector_rotation(data: dict) -> str:
    sectors = data.get("sectors", [])
    ai_note = data.get("ai_note", "")

    if not sectors:
        return "❌ Unable to fetch sector data. Please try again."

    lines = ["🔄 *IDX Sector Rotation Today*", ""]

    strongest = sectors[:3]
    weakest = sectors[-3:]

    lines.append("🔥 *Strongest Sectors:*")
    for i, s in enumerate(strongest, 1):
        sign = "+" if s["pct_chg"] >= 0 else ""
        lines.append(f"  {i}. *{s['name']}* {sign}{s['pct_chg']:.2f}% | Score: {s['rotation_score']:.0f}/100")

    lines.append("")
    lines.append("⚠️ *Weakest Sectors:*")
    for s in weakest:
        sign = "+" if s["pct_chg"] >= 0 else ""
        lines.append(f"  • {s['name']} {sign}{s['pct_chg']:.2f}%")

    lines.append("")
    lines.append("🎯 *Recommended Candidates (Top Sector):*")
    if strongest:
        for c in strongest[0].get("candidates", [])[:3]:
            ticker = c.get("ticker", "")
            pct = c.get("pct_chg", 0)
            sign = "+" if pct >= 0 else ""
            lines.append(f"  • *{ticker}* {sign}{pct:.2f}%")

    lines += ["", ai_note]
    return "\n".join(lines)
