"""
Sector Momentum Chart — 5-day cumulative return per IDX sector.

Each sector's daily return = equal-weighted average of top 3 representative
stocks (first 3 in IDX_STOCKS, roughly largest-cap per sector).

Chart shows:
  • X-axis: last 5 trading days (D-4 → Today)
  • Y-axis: cumulative % return from D-5 close
  • Color: green if final cumulative > 0, red if < 0
  • Line thickness: fixed (all sectors equal weight for readability)
  • Endpoint labels showing final cumulative %
  • Summary bar at bottom: Best / Worst / Improving / Deteriorating
"""

import io
import logging
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.lines import Line2D

from bot.services.data_service import get_stock_data
from bot.utils.constants import IDX_STOCKS, SECTOR_ICONS

logger = logging.getLogger(__name__)

_BG = "#0d1117"
_GRID = "#21262d"
_TEXT = "#c9d1d9"
_MUTED = "#8b949e"

# ── Colour map for 11 sectors (distinct enough on dark background) ──────────
_SECTOR_COLORS = [
    "#58a6ff",  # Finance       — blue
    "#f78166",  # Basic Mat     — orange-red
    "#3fb950",  # Con Cyclical  — green
    "#a371f7",  # Con Staples   — purple
    "#ffa657",  # Energy        — amber
    "#79c0ff",  # Healthcare    — light blue
    "#d2a8ff",  # Industrials   — lavender
    "#ff7b72",  # Infrastructure— salmon
    "#56d364",  # Property      — bright green
    "#e3b341",  # Technology    — gold
    "#bc8cff",  # Transportation— violet
]


def _daily_returns_for_sector(sector_name: str, tickers: list, days: int = 5):
    """
    Returns a numpy array of length `days` with daily % changes for the sector.
    Uses equal-weighted average of up to 3 representative tickers.
    Returns None if insufficient data.
    """
    needed = days + 1   # need one extra bar for first day's return
    rep_returns = []    # list of return arrays

    for ticker in tickers[:3]:
        try:
            df = get_stock_data(ticker, period="1mo")
            if df is None or len(df) < needed:
                logger.debug(f"[TREND] {ticker}: only {0 if df is None else len(df)} bars")
                continue

            closes = df["Close"].values[-needed:]     # shape (needed,)
            if len(closes) < needed:
                continue
            # daily % returns: day 1..days
            rets = (closes[1:] / closes[:-1] - 1) * 100    # shape (days,)
            rep_returns.append(rets)
        except Exception as e:
            logger.debug(f"[TREND] {ticker}: {e}")

    if not rep_returns:
        return None

    return np.mean(rep_returns, axis=0)   # equal-weight average


def generate_sector_momentum_chart(days: int = 5) -> io.BytesIO | None:
    """
    Generate the 5-day sector momentum multi-line chart.
    Returns a BytesIO PNG or None on failure.
    """
    sector_names  = list(IDX_STOCKS.keys())
    sector_tickers= list(IDX_STOCKS.values())

    # ── Fetch returns ────────────────────────────────────────────────────────
    sector_data = {}   # name → cumulative_return_array (length days+1, starts at 0)
    for name, tickers in zip(sector_names, sector_tickers):
        daily = _daily_returns_for_sector(name, tickers, days)
        if daily is not None and len(daily) == days:
            # Cumulative return starting from 0 at day 0
            cum = np.concatenate([[0.0], np.cumsum(daily)])
            sector_data[name] = cum
            logger.info(
                f"[TREND] {name:20s}: "
                f"{' → '.join(f'{v:+.2f}%' for v in daily)}  "
                f"final: {cum[-1]:+.2f}%"
            )
        else:
            logger.warning(f"[TREND] {name}: no data for momentum chart")

    if len(sector_data) < 3:
        logger.error("[TREND] Insufficient sector data for momentum chart")
        return None

    # ── Day labels ───────────────────────────────────────────────────────────
    if days == 5:
        x_labels = ["D-4", "D-3", "D-2", "D-1", "D-0", "Today"][:days+1]
    else:
        x_labels = [f"D-{days-i}" if i < days else "Today" for i in range(days+1)]
    x_vals = np.arange(days + 1)

    # ── Compute summary stats ────────────────────────────────────────────────
    finals = {name: data[-1] for name, data in sector_data.items()}
    best   = max(finals, key=finals.get)
    worst  = min(finals, key=finals.get)

    # Improving: best daily return ON THE LAST DAY
    last_day_rets = {
        name: data[-1] - data[-2]
        for name, data in sector_data.items()
        if len(data) >= 2
    }
    improving   = max(last_day_rets, key=last_day_rets.get)
    deteriorating = min(last_day_rets, key=last_day_rets.get)

    # ── Figure ───────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(16, 9))
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)

    ax.grid(axis="y", color=_GRID, linewidth=0.5, alpha=0.6)
    ax.grid(axis="x", color=_GRID, linewidth=0.3, alpha=0.4)
    ax.axhline(0, color=_MUTED, linewidth=0.8, linestyle="--", alpha=0.5)

    plotted_sectors = list(sector_data.keys())

    for i, (name, cum) in enumerate(sector_data.items()):
        color    = _SECTOR_COLORS[sector_names.index(name) % len(_SECTOR_COLORS)]
        final    = cum[-1]
        is_best  = name == best
        is_worst = name == worst
        lw       = 2.5 if (is_best or is_worst) else 1.4
        alpha    = 1.0 if (is_best or is_worst) else 0.75
        ls       = "-"

        line, = ax.plot(x_vals, cum,
                        color=color, linewidth=lw, alpha=alpha,
                        linestyle=ls, zorder=3 if (is_best or is_worst) else 2)

        # Endpoint label
        icon  = SECTOR_ICONS.get(name, "")
        short = name[:10]
        sign  = "+" if final >= 0 else ""
        label = f"{icon}{short}\n{sign}{final:.2f}%"
        fontsize = 7.5

        # Offset labels to avoid overlap — alternate above/below
        y_offset = 0.15 if i % 2 == 0 else -0.25

        ax.annotate(
            label,
            xy=(x_vals[-1], cum[-1]),
            xytext=(x_vals[-1] + 0.06, cum[-1] + y_offset),
            fontsize=fontsize,
            color=color,
            ha="left", va="center",
            fontweight="bold" if (is_best or is_worst) else "normal",
            path_effects=[pe.withStroke(linewidth=2, foreground=_BG)],
        )

    # ── Axes formatting ──────────────────────────────────────────────────────
    ax.set_xticks(x_vals)
    ax.set_xticklabels(x_labels, color=_TEXT, fontsize=10)
    ax.tick_params(axis="y", colors=_TEXT, labelsize=9)
    ax.set_xlim(-0.2, x_vals[-1] + 2.4)   # extra room for right-side labels

    for spine in ax.spines.values():
        spine.set_color(_GRID)

    ymin = min(np.min(d) for d in sector_data.values())
    ymax = max(np.max(d) for d in sector_data.values())
    pad  = max(0.5, (ymax - ymin) * 0.15)
    ax.set_ylim(ymin - pad, ymax + pad)

    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.1f}%"))

    # ── Title & summary footer ───────────────────────────────────────────────
    fig.suptitle(
        f"IDX Sector Momentum — Last {days} Trading Days  (Cumulative Return)",
        color=_TEXT, fontsize=13, fontweight="bold", y=0.97,
    )
    ax.set_title(
        "_Note: equal-weighted avg of top 3 stocks per sector · yfinance (15-min delay) · Not financial advice_",
        color=_MUTED, fontsize=7.5, pad=4,
    )

    # Summary box
    b_sign = "+" if finals[best]  >= 0 else ""
    w_sign = "+" if finals[worst] >= 0 else ""
    i_sign = "+" if last_day_rets[improving]   >= 0 else ""
    d_sign = "+" if last_day_rets[deteriorating] >= 0 else ""

    summary = (
        f"🔥 Best: {SECTOR_ICONS.get(best,'')}{best} {b_sign}{finals[best]:.2f}%   "
        f"📉 Worst: {SECTOR_ICONS.get(worst,'')}{worst} {w_sign}{finals[worst]:.2f}%   "
        f"📈 Today↑: {SECTOR_ICONS.get(improving,'')}{improving} {i_sign}{last_day_rets[improving]:.2f}%   "
        f"📉 Today↓: {SECTOR_ICONS.get(deteriorating,'')}{deteriorating} {d_sign}{last_day_rets[deteriorating]:.2f}%"
    )
    fig.text(0.5, 0.005, summary,
             ha="center", va="bottom",
             color=_TEXT, fontsize=8.5,
             bbox=dict(boxstyle="round,pad=0.3", facecolor="#161b22", edgecolor=_GRID))

    # ── Legend (compact, top-left) ───────────────────────────────────────────
    legend_handles = []
    for name in plotted_sectors:
        color = _SECTOR_COLORS[sector_names.index(name) % len(_SECTOR_COLORS)]
        legend_handles.append(Line2D([0], [0], color=color, linewidth=1.6,
                                     label=f"{SECTOR_ICONS.get(name,'')}{name}"))
    ax.legend(
        handles=legend_handles,
        loc="upper left",
        fontsize=6.8,
        ncol=2,
        facecolor="#161b22",
        edgecolor=_GRID,
        labelcolor=_TEXT,
        framealpha=0.9,
    )

    # ── Render ───────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                    facecolor=_BG, edgecolor="none")
        plt.close(fig)
    except Exception as e:
        logger.error(f"[TREND] Render error: {e}")
        plt.close("all")
        return None

    buf.seek(0)
    logger.info(f"[TREND] Momentum chart generated: {len(sector_data)} sectors, {days} days")
    return buf
