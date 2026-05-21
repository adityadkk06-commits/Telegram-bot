import io
import logging
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import LinearSegmentedColormap
from bot.services.data_service import get_market_snapshot
from bot.utils.constants import IDX_STOCKS

logger = logging.getLogger(__name__)


def _pct_to_color(pct: float, cmap) -> tuple:
    norm = max(-5, min(5, pct)) / 10 + 0.5
    return cmap(norm)


def generate_heatmap(sector_filter: str = None) -> io.BytesIO | None:
    cmap = LinearSegmentedColormap.from_list(
        "rdgn",
        ["#c62828", "#e53935", "#ef9a9a", "#37474f", "#a5d6a7", "#43a047", "#1b5e20"],
    )

    sectors_to_show = {}
    if sector_filter and sector_filter in IDX_STOCKS:
        sectors_to_show = {sector_filter: IDX_STOCKS[sector_filter]}
    else:
        sectors_to_show = IDX_STOCKS

    all_data = []
    for sector, tickers in sectors_to_show.items():
        snaps = get_market_snapshot(tickers[:8])
        for s in snaps:
            s["sector"] = sector
            all_data.append(s)

    if not all_data:
        return None

    # Sort by absolute pct change for layout
    all_data.sort(key=lambda x: abs(x.get("pct_chg", 0)), reverse=True)

    # Layout
    n = len(all_data)
    cols = min(8, n)
    rows = (n + cols - 1) // cols

    fig_w = max(14, cols * 1.8)
    fig_h = max(8, rows * 1.6 + 2)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_facecolor("#0d1117")
    fig.patch.set_facecolor("#0d1117")
    ax.set_xlim(0, cols)
    ax.set_ylim(0, rows + 0.5)
    ax.axis("off")

    title = f"IDX Heatmap — {sector_filter or 'All Sectors'}"
    fig.suptitle(title, color="#c9d1d9", fontsize=14, fontweight="bold", y=0.98)

    for i, stock in enumerate(all_data):
        col = i % cols
        row = rows - 1 - (i // cols)
        pct = stock.get("pct_chg", 0)
        ticker = stock.get("ticker", "")
        price = stock.get("price", 0)
        sector = stock.get("sector", "")
        rel_vol = stock.get("rel_vol", 1) or 1

        color = _pct_to_color(pct, cmap)
        # Size based on relative volume
        size_factor = min(1.0, max(0.75, 0.75 + rel_vol * 0.05))
        pad = (1 - size_factor) / 2

        rect = patches.FancyBboxPatch(
            (col + pad + 0.02, row + pad + 0.02),
            size_factor - 0.04, size_factor - 0.04,
            boxstyle="round,pad=0.02",
            linewidth=0.5,
            edgecolor="#21262d",
            facecolor=color,
        )
        ax.add_patch(rect)

        cx = col + 0.5
        cy = row + 0.5

        sign = "+" if pct >= 0 else ""
        pct_str = f"{sign}{pct:.1f}%"
        price_str = f"{price:,.0f}" if price < 10000 else f"{price/1000:.1f}K"

        text_color = "white" if abs(pct) > 1.5 else "#c9d1d9"

        ax.text(cx, cy + 0.14, ticker, ha="center", va="center",
                color=text_color, fontsize=7.5, fontweight="bold")
        ax.text(cx, cy - 0.05, pct_str, ha="center", va="center",
                color=text_color, fontsize=7)
        ax.text(cx, cy - 0.22, price_str, ha="center", va="center",
                color=text_color, fontsize=6, alpha=0.8)

    # Color scale legend
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(-5, 5))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, orientation="horizontal",
                        fraction=0.02, pad=0.01, aspect=50)
    cbar.set_label("% Change", color="#8b949e", fontsize=9)
    cbar.ax.tick_params(colors="#8b949e", labelsize=8)

    # Gainers/losers summary
    gainers = sorted(all_data, key=lambda x: x.get("pct_chg", 0), reverse=True)[:3]
    losers = sorted(all_data, key=lambda x: x.get("pct_chg", 0))[:3]
    vol_leaders = sorted(all_data, key=lambda x: x.get("rel_vol", 0) or 0, reverse=True)[:3]

    summary_y = -0.3
    g_str = " | ".join(f"{s['ticker']} +{s['pct_chg']:.1f}%" for s in gainers)
    l_str = " | ".join(f"{s['ticker']} {s['pct_chg']:.1f}%" for s in losers)
    v_str = " | ".join(f"{s['ticker']} {(s.get('rel_vol') or 1):.1f}x" for s in vol_leaders)

    ax.text(cols / 2, summary_y + 0.2, f"🟢 Top Gainers: {g_str}",
            ha="center", color="#00e676", fontsize=7.5)
    ax.text(cols / 2, summary_y, f"🔴 Top Losers: {l_str}",
            ha="center", color="#ff5252", fontsize=7.5)
    ax.text(cols / 2, summary_y - 0.2, f"⚡ Vol Leaders: {v_str}",
            ha="center", color="#f9a825", fontsize=7.5)

    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                    facecolor="#0d1117", edgecolor="none")
        plt.close(fig)
    except Exception as e:
        logger.error(f"Heatmap error: {e}")
        plt.close("all")
        return None

    buf.seek(0)
    return buf
