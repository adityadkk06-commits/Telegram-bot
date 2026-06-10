"""
IDX Market Heatmap — visual grid of all scanned stocks.

Fix applied:
  • Sector filter now uses official IDX sector names from constants.IDX_STOCKS
  • Color scale correctly maps [-5%, +5%] range with neutral grey at 0
"""

import io
import logging
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import LinearSegmentedColormap

from bot.services.data_service import get_sector_snapshots, get_market_snapshot
from bot.utils.constants import IDX_STOCKS, SECTOR_ICONS

logger = logging.getLogger(__name__)


def _pct_to_color(pct: float, cmap) -> tuple:
    norm = max(-5, min(5, pct)) / 10.0 + 0.5
    return cmap(norm)


def generate_heatmap(sector_filter: str = None) -> io.BytesIO | None:
    """
    Generate a heatmap image (PNG) for all IDX stocks or a single sector.

    Args:
        sector_filter: official IDX sector name, e.g. "Finance", "Technology"
                       Pass None or "all" for the full market heatmap.
    """
    cmap = LinearSegmentedColormap.from_list(
        "rdgn",
        ["#c62828", "#e53935", "#ef9a9a", "#37474f", "#a5d6a7", "#43a047", "#1b5e20"],
    )

    # ── Determine which sectors to show ─────────────────────────────────────
    if sector_filter and sector_filter in IDX_STOCKS:
        sectors_to_show = {sector_filter: IDX_STOCKS[sector_filter]}
        title_label     = f"{SECTOR_ICONS.get(sector_filter, '📊')} {sector_filter}"
    else:
        # Full market — show all sectors but limit to 10 stocks each for layout
        sectors_to_show = IDX_STOCKS
        title_label     = "All Sectors"

    # ── Fetch data ───────────────────────────────────────────────────────────
    all_data = []
    for sector, tickers in sectors_to_show.items():
        limit = 10 if len(sectors_to_show) > 1 else len(tickers)
        snaps = get_sector_snapshots(sector, tickers[:limit])
        for s in snaps:
            s["sector"] = sector
            all_data.append(s)

    if not all_data:
        logger.warning(f"generate_heatmap: no data for filter={sector_filter!r}")
        return None

    # ── Sort by absolute pct_chg (biggest movers first) ─────────────────────
    all_data.sort(key=lambda x: abs(x.get("pct_chg", 0)), reverse=True)

    # ── Layout ───────────────────────────────────────────────────────────────
    n    = len(all_data)
    cols = min(8, n)
    rows = (n + cols - 1) // cols

    fig_w = max(14, cols * 1.8)
    fig_h = max(8,  rows * 1.6 + 2)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_facecolor("#0d1117")
    fig.patch.set_facecolor("#0d1117")
    ax.set_xlim(0, cols)
    ax.set_ylim(0, rows + 0.5)
    ax.axis("off")

    fig.suptitle(
        f"IDX Heatmap — {title_label}",
        color="#c9d1d9", fontsize=14, fontweight="bold", y=0.98,
    )

    for i, stock in enumerate(all_data):
        col    = i % cols
        row    = rows - 1 - (i // cols)
        pct    = stock.get("pct_chg", 0)
        ticker = stock.get("ticker", "")
        price  = stock.get("price", 0)
        rv     = stock.get("rel_vol", 1) or 1

        color       = _pct_to_color(pct, cmap)
        size_factor = min(1.0, max(0.75, 0.75 + rv * 0.05))
        pad         = (1 - size_factor) / 2

        rect = patches.FancyBboxPatch(
            (col + pad + 0.02, row + pad + 0.02),
            size_factor - 0.04, size_factor - 0.04,
            boxstyle="round,pad=0.02",
            linewidth=0.5,
            edgecolor="#21262d",
            facecolor=color,
        )
        ax.add_patch(rect)

        cx, cy    = col + 0.5, row + 0.5
        sign      = "+" if pct >= 0 else ""
        pct_str   = f"{sign}{pct:.1f}%"
        price_str = f"{price:,.0f}" if price < 10_000 else f"{price/1_000:.1f}K"
        text_clr  = "white" if abs(pct) > 1.5 else "#c9d1d9"

        ax.text(cx, cy + 0.14, ticker,   ha="center", va="center",
                color=text_clr, fontsize=7.5, fontweight="bold")
        ax.text(cx, cy - 0.05, pct_str,  ha="center", va="center",
                color=text_clr, fontsize=7)
        ax.text(cx, cy - 0.22, price_str,ha="center", va="center",
                color=text_clr, fontsize=6, alpha=0.8)

    # ── Color bar ────────────────────────────────────────────────────────────
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(-5, 5))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, orientation="horizontal",
                        fraction=0.02, pad=0.01, aspect=50)
    cbar.set_label("% Change", color="#8b949e", fontsize=9)
    cbar.ax.tick_params(colors="#8b949e", labelsize=8)

    # ── Footer summary ───────────────────────────────────────────────────────
    gainers      = sorted(all_data, key=lambda x: x.get("pct_chg", 0), reverse=True)[:3]
    losers       = sorted(all_data, key=lambda x: x.get("pct_chg", 0))[:3]
    vol_leaders  = sorted(all_data, key=lambda x: x.get("rel_vol", 0) or 0, reverse=True)[:3]

    g_str = " | ".join(f"{s['ticker']} +{s['pct_chg']:.1f}%" for s in gainers)
    l_str = " | ".join(f"{s['ticker']} {s['pct_chg']:.1f}%"  for s in losers)
    v_str = " | ".join(f"{s['ticker']} {(s.get('rel_vol') or 1):.1f}x" for s in vol_leaders)

    sy = -0.3
    ax.text(cols / 2, sy + 0.2, f"🟢 Top Gainers: {g_str}",
            ha="center", color="#00e676", fontsize=7.5)
    ax.text(cols / 2, sy,       f"🔴 Top Losers: {l_str}",
            ha="center", color="#ff5252", fontsize=7.5)
    ax.text(cols / 2, sy - 0.2, f"⚡ Vol Leaders: {v_str}",
            ha="center", color="#f9a825", fontsize=7.5)

    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                    facecolor="#0d1117", edgecolor="none")
        plt.close(fig)
    except Exception as e:
        logger.error(f"Heatmap render error: {e}")
        plt.close("all")
        return None

    buf.seek(0)
    return buf
