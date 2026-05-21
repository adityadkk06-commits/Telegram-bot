import io
import logging
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import mplfinance as mpf
import pandas as pd
from bot.services.data_service import get_stock_data, compute_indicators
from bot.bandarmology.broker_analyzer import estimate_broker_signal

logger = logging.getLogger(__name__)

DARK_STYLE = {
    "base_mpl_style": "dark_background",
    "marketcolors": mpf.make_marketcolors(
        up="#00e676", down="#ff1744",
        edge="inherit",
        wick={"up": "#00e676", "down": "#ff1744"},
        volume={"up": "#00e676", "down": "#ff1744"},
    ),
    "rc": {
        "axes.facecolor": "#0d1117",
        "figure.facecolor": "#0d1117",
        "axes.edgecolor": "#30363d",
        "axes.labelcolor": "#c9d1d9",
        "xtick.color": "#8b949e",
        "ytick.color": "#8b949e",
        "grid.color": "#21262d",
        "grid.linewidth": 0.5,
        "font.family": "DejaVu Sans",
    },
}

mpf_style = mpf.make_mpf_style(**DARK_STYLE)


def generate_stock_chart(ticker: str) -> io.BytesIO | None:
    df = get_stock_data(ticker, period="3mo")
    if df is None or len(df) < 20:
        return None

    df = compute_indicators(df)
    df_plot = df.tail(60).copy()

    # Keep only last 60 rows for cleaner chart
    close = df_plot["Close"]
    volume = df_plot["Volume"]

    # Buy/Sell signals
    buy_signals = pd.Series(index=df_plot.index, dtype=float)
    sell_signals = pd.Series(index=df_plot.index, dtype=float)

    for i in range(2, len(df_plot)):
        row = df_plot.iloc[i]
        prev = df_plot.iloc[i - 1]
        # Buy: price crosses above MA20 with volume
        if (prev["Close"] < prev["MA20"] and row["Close"] > row["MA20"]
                and row.get("RelVol", 1) > 1.3):
            buy_signals.iloc[i] = row["Low"] * 0.995
        # Sell: RSI > 75 or price crosses below MA20
        if row.get("RSI", 50) > 75:
            sell_signals.iloc[i] = row["High"] * 1.005

    # Additional plots
    ma5 = mpf.make_addplot(df_plot["MA5"], color="#f9a825", width=1.2, label="MA5")
    ma20 = mpf.make_addplot(df_plot["MA20"], color="#29b6f6", width=1.5, label="MA20")
    ma50 = mpf.make_addplot(df_plot["MA50"], color="#ef9a9a", width=1.2, label="MA50")

    # MACD subplot
    macd_hist = df_plot["MACD_Hist"].fillna(0)
    macd_colors = ["#00e676" if v >= 0 else "#ff1744" for v in macd_hist]
    macd_line = mpf.make_addplot(df_plot["MACD"], panel=2, color="#f9a825", width=1, secondary_y=False)
    macd_sig = mpf.make_addplot(df_plot["MACD_Signal"], panel=2, color="#29b6f6", width=1, secondary_y=False)
    macd_bar = mpf.make_addplot(macd_hist, panel=2, type="bar", color=macd_colors, secondary_y=False)

    # RSI subplot
    rsi = mpf.make_addplot(df_plot["RSI"], panel=3, color="#ab47bc", width=1.2, secondary_y=False)
    rsi_ob = mpf.make_addplot(pd.Series(70, index=df_plot.index), panel=3, color="#ff1744",
                               width=0.8, linestyle="--", secondary_y=False)
    rsi_os = mpf.make_addplot(pd.Series(30, index=df_plot.index), panel=3, color="#00e676",
                               width=0.8, linestyle="--", secondary_y=False)

    # Buy/Sell markers
    add_plots = [ma5, ma20, ma50, macd_line, macd_sig, macd_bar, rsi, rsi_ob, rsi_os]

    if buy_signals.notna().any():
        buy_plot = mpf.make_addplot(buy_signals, type="scatter", markersize=80,
                                     marker="^", color="#00e676")
        add_plots.append(buy_plot)

    if sell_signals.notna().any():
        sell_plot = mpf.make_addplot(sell_signals, type="scatter", markersize=80,
                                      marker="v", color="#ff1744")
        add_plots.append(sell_plot)

    # Broker accumulation data
    snap = {
        "ticker": ticker,
        "price": close.iloc[-1],
        "prev_price": close.iloc[-2] if len(close) > 1 else close.iloc[-1],
        "pct_chg": (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100 if len(close) > 1 else 0,
        "volume": volume.iloc[-1],
        "value": close.iloc[-1] * volume.iloc[-1],
        "rel_vol": df_plot["RelVol"].iloc[-1],
        "bandar_score": df_plot["BandarScore"].iloc[-1],
        "ma20": df_plot["MA20"].iloc[-1],
        "ma50": df_plot["MA50"].iloc[-1],
    }
    broker = estimate_broker_signal(snap)
    broker_signal = broker["signal"]
    price_now = close.iloc[-1]
    pct_chg = snap["pct_chg"]
    rsi_now = df_plot["RSI"].iloc[-1]
    rel_vol_now = df_plot["RelVol"].iloc[-1] or 1

    title = (
        f"{ticker}  |  Price: {price_now:,.0f}  ({'+' if pct_chg>=0 else ''}{pct_chg:.2f}%)  "
        f"|  RSI: {rsi_now:.1f}  |  RelVol: {rel_vol_now:.1f}x  |  Broker: {broker_signal}"
    )

    buf = io.BytesIO()
    try:
        fig, axlist = mpf.plot(
            df_plot,
            type="candle",
            style=mpf_style,
            title=f"\n{title}",
            volume=True,
            addplot=add_plots,
            panel_ratios=(4, 1, 1.5, 1.2),
            figsize=(14, 10),
            returnfig=True,
            tight_layout=True,
        )

        # Legend on main panel
        ax = axlist[0]
        legend_handles = [
            mpatches.Patch(color="#f9a825", label="MA5"),
            mpatches.Patch(color="#29b6f6", label="MA20"),
            mpatches.Patch(color="#ef9a9a", label="MA50"),
            mpatches.Patch(color="#00e676", label="Buy Signal"),
            mpatches.Patch(color="#ff1744", label="Sell/OB"),
        ]
        ax.legend(handles=legend_handles, loc="upper left", fontsize=8,
                  framealpha=0.3, facecolor="#0d1117", edgecolor="#30363d")

        # Panel labels
        if len(axlist) > 4:
            axlist[4].set_ylabel("MACD", color="#8b949e", fontsize=8)
        if len(axlist) > 6:
            axlist[6].set_ylabel("RSI", color="#8b949e", fontsize=8)

        fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                    facecolor="#0d1117", edgecolor="none")
        plt.close(fig)
    except Exception as e:
        logger.error(f"Chart error for {ticker}: {e}")
        plt.close("all")
        return None

    buf.seek(0)
    return buf


def generate_mini_chart(ticker: str) -> io.BytesIO | None:
    """Quick small chart for screener result cards."""
    df = get_stock_data(ticker, period="1mo")
    if df is None or len(df) < 5:
        return None
    df = compute_indicators(df)
    df_plot = df.tail(20).copy()

    ma5 = mpf.make_addplot(df_plot["MA5"], color="#f9a825", width=1)
    ma20 = mpf.make_addplot(df_plot["MA20"], color="#29b6f6", width=1)

    buf = io.BytesIO()
    try:
        fig, _ = mpf.plot(
            df_plot,
            type="candle",
            style=mpf_style,
            title=f"\n{ticker} — 20-day",
            volume=True,
            addplot=[ma5, ma20],
            figsize=(10, 6),
            returnfig=True,
            tight_layout=True,
        )
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight",
                    facecolor="#0d1117", edgecolor="none")
        plt.close(fig)
    except Exception as e:
        logger.error(f"Mini chart error for {ticker}: {e}")
        plt.close("all")
        return None

    buf.seek(0)
    return buf
