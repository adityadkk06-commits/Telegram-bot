"""
Alert-specific chart generator.

Produces a professional dark-theme candlestick chart with:
  • MA10 (yellow-green) and MA20 (blue)
  • Volume bars (color-coded)
  • Horizontal lines: Entry, TP1, TP2, SL
  • Shaded entry zone
  • Golden cross marker (if applicable)
  • Trade zone labels
"""
import io
import logging
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import mplfinance as mpf

from bot.services.data_service import get_stock_data, compute_indicators

logger = logging.getLogger(__name__)

# Re-use the same dark style as the main chart generator
_DARK_RC = {
    "axes.facecolor":   "#0d1117",
    "figure.facecolor": "#0d1117",
    "axes.edgecolor":   "#30363d",
    "axes.labelcolor":  "#c9d1d9",
    "xtick.color":      "#8b949e",
    "ytick.color":      "#8b949e",
    "grid.color":       "#21262d",
    "grid.linewidth":   0.5,
    "font.family":      "DejaVu Sans",
}
_DARK_MC = mpf.make_marketcolors(
    up="#00e676", down="#ff1744",
    edge="inherit",
    wick={"up": "#00e676", "down": "#ff1744"},
    volume={"up": "#00e676", "down": "#ff1744"},
)
_STYLE = mpf.make_mpf_style(
    base_mpl_style="dark_background",
    marketcolors=_DARK_MC,
    rc=_DARK_RC,
)


def generate_alert_chart(ticker: str, sig: dict) -> io.BytesIO | None:
    """
    Generate an alert chart for ticker with trade levels from sig.

    sig keys used: entry, tp1, tp2, sl, confidence, ma10, ma20
    If sig is empty or levels are 0, a plain MA10/MA20 chart is generated.
    """
    try:
        df = get_stock_data(ticker, period="2mo")
        if df is None or len(df) < 15:
            return None
        df = compute_indicators(df)
        df["MA10"] = df["Close"].rolling(10).mean()

        df_plot = df.tail(30).copy()

        # MA lines
        add_plots = []

        if df_plot["MA10"].notna().any():
            add_plots.append(mpf.make_addplot(
                df_plot["MA10"], color="#aeea00", width=1.4, label="MA10"
            ))
        if df_plot["MA20"].notna().any():
            add_plots.append(mpf.make_addplot(
                df_plot["MA20"], color="#29b6f6", width=1.4, label="MA20"
            ))

        # Volume in panel 1 is handled by mplfinance natively

        entry = sig.get("entry", 0)
        tp1   = sig.get("tp1", 0)
        tp2   = sig.get("tp2", 0)
        sl    = sig.get("sl", 0)
        conf  = sig.get("confidence", 0)
        has_levels = entry > 0 and tp1 > 0 and sl > 0

        # Horizontal level lines via hlines
        hlines_vals   = []
        hlines_colors = []
        if has_levels:
            hlines_vals   = [entry, tp1, tp2, sl]
            hlines_colors = ["#ffeb3b", "#00e676", "#69f0ae", "#ff5252"]

        price_now = float(df_plot["Close"].iloc[-1])
        pct       = (price_now - float(df_plot["Close"].iloc[-2])) / float(df_plot["Close"].iloc[-2]) * 100
        sign      = "+" if pct >= 0 else ""

        title_parts = [f"{ticker}  Price:{price_now:,.0f}  ({sign}{pct:.1f}%)"]
        if has_levels:
            title_parts.append(f"Entry:{entry:,.0f}  TP1:{tp1:,.0f}  SL:{sl:,.0f}  Conf:{conf}/10")
        title = "  |  ".join(title_parts)

        buf = io.BytesIO()
        fig, axlist = mpf.plot(
            df_plot,
            type="candle",
            style=_STYLE,
            title=f"\n{title}",
            volume=True,
            addplot=add_plots if add_plots else [],
            hlines=dict(hlines=hlines_vals, colors=hlines_colors,
                        linewidths=[1.5] * len(hlines_vals),
                        linestyle=["--"] * len(hlines_vals)) if has_levels else {},
            panel_ratios=(4, 1),
            figsize=(12, 7),
            returnfig=True,
            tight_layout=True,
        )

        ax = axlist[0]

        # Shade entry zone (entry to tp1)
        if has_levels:
            ax.axhspan(entry, tp1, alpha=0.07, color="#00e676", zorder=0)  # green: profit zone
            ax.axhspan(sl, entry, alpha=0.06, color="#ff1744", zorder=0)   # red: risk zone

            # Level text annotations
            xmax = ax.get_xlim()[1]
            ax.annotate(f"TP2 {tp2:,.0f}", xy=(xmax, tp2), xycoords="data",
                        color="#69f0ae", fontsize=7, ha="right")
            ax.annotate(f"TP1 {tp1:,.0f}", xy=(xmax, tp1), xycoords="data",
                        color="#00e676", fontsize=7, ha="right")
            ax.annotate(f"Entry {entry:,.0f}", xy=(xmax, entry), xycoords="data",
                        color="#ffeb3b", fontsize=7, ha="right")
            ax.annotate(f"SL {sl:,.0f}", xy=(xmax, sl), xycoords="data",
                        color="#ff5252", fontsize=7, ha="right")

        # Legend
        legend_patches = [
            mpatches.Patch(color="#aeea00", label="MA10"),
            mpatches.Patch(color="#29b6f6", label="MA20"),
        ]
        if has_levels:
            legend_patches += [
                mpatches.Patch(color="#ffeb3b", label="Entry"),
                mpatches.Patch(color="#00e676", label="TP"),
                mpatches.Patch(color="#ff5252", label="SL"),
            ]
        ax.legend(handles=legend_patches, loc="upper left", fontsize=7,
                  framealpha=0.3, facecolor="#0d1117", edgecolor="#30363d")

        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                    facecolor="#0d1117", edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return buf

    except Exception as e:
        logger.error(f"Alert chart error for {ticker}: {e}")
        plt.close("all")
        return None
