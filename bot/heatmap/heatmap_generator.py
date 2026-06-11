"""
IDX Market Heatmap — Treemap-style, value-proportional tile sizing.

Architecture:
  • Each tile sized by transaction value (larger value = larger tile)
  • Colors use sector-relative scale: SB > +3%, B > +1%, N ±1%, Br < -1%, SBr < -3%
  • Squarify treemap layout (strip algorithm)
  • Deduplication: each ticker appears exactly once (enforced at render time)
  • Volume leader score: transaction_value × 0.70 + rel_vol × 0.30 (normalized)
  • Per-tile shows: ticker, pct_chg, price, rel_vol indicator
"""

import io
import logging
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

from bot.services.data_service import get_sector_snapshots, get_market_snapshot
from bot.utils.constants import IDX_STOCKS, SECTOR_ICONS

logger = logging.getLogger(__name__)

# ── Color palette (sector-relative, 5 tiers) ─────────────────────────────────
_STRONG_BULL   = "#1b5e20"   # > +3%
_BULL          = "#43a047"   # +1% to +3%
_NEUTRAL_POS   = "#a5d6a7"   # 0% to +1%
_NEUTRAL       = "#546e7a"   # exactly neutral
_NEUTRAL_NEG   = "#ef9a9a"   # -1% to 0%
_BEAR          = "#e53935"   # -3% to -1%
_STRONG_BEAR   = "#b71c1c"   # < -3%

def _pct_color(pct: float) -> str:
    if pct >  3.0:  return _STRONG_BULL
    if pct >  1.0:  return _BULL
    if pct >  0.0:  return _NEUTRAL_POS
    if pct == 0.0:  return _NEUTRAL
    if pct > -1.0:  return _NEUTRAL_NEG
    if pct > -3.0:  return _BEAR
    return _STRONG_BEAR

def _text_color(pct: float) -> str:
    return "white" if abs(pct) > 0.5 else "#c9d1d9"


# ── Squarify (strip algorithm) ────────────────────────────────────────────────

def _worst_aspect(row: list, short_side: float) -> float:
    area = sum(row)
    if area == 0 or short_side == 0:
        return float("inf")
    min_v, max_v = min(row), max(row)
    s2 = short_side ** 2
    return max(s2 * max_v / area ** 2, area ** 2 / (s2 * min_v))


def _squarify(areas: list, x: float, y: float, w: float, h: float) -> list:
    """
    Strip squarify — returns list of (x, y, w, h) rects in same order as areas.
    """
    if not areas:
        return []
    total = sum(areas)
    if total == 0 or w <= 0 or h <= 0:
        # Degenerate — equal tiles
        n = len(areas)
        cols = max(1, int(np.sqrt(n)))
        rows = (n + cols - 1) // cols
        tw, th = w / cols, h / rows
        return [(x + (i % cols) * tw, y + (i // cols) * th, tw, th)
                for i in range(n)]

    # Normalise to fill rectangle
    scale = (w * h) / total
    norm  = [a * scale for a in areas]

    result: list = [None] * len(norm)
    _strip(norm, result, list(range(len(norm))), x, y, w, h)
    return result


def _strip(norm, result, indices, x, y, w, h):
    if not indices:
        return
    if len(indices) == 1:
        result[indices[0]] = (x, y, w, h)
        return

    short = min(w, h)
    row_idx   = []
    best_asp  = float("inf")
    remaining = [norm[i] for i in indices]
    total_rem = sum(remaining)

    for k, val in enumerate(remaining):
        row_idx.append(k)
        row_areas = [norm[indices[j]] for j in row_idx]
        asp = _worst_aspect(row_areas, short)
        if asp <= best_asp:
            best_asp = asp
        else:
            row_idx.pop()
            break

    row_areas  = [norm[indices[j]] for j in row_idx]
    row_total  = sum(row_areas)
    rest_idx   = indices[len(row_idx):]

    if w >= h:
        row_w = row_total / h if h > 0 else w
        row_w = min(row_w, w)
        y_cur = y
        for j, area in zip(row_idx, row_areas):
            item_h = area / row_w if row_w > 0 else h / len(row_areas)
            result[indices[j]] = (x, y_cur, row_w, item_h)
            y_cur += item_h
        if rest_idx:
            _strip(norm, result, rest_idx, x + row_w, y, max(0, w - row_w), h)
    else:
        row_h = row_total / w if w > 0 else h
        row_h = min(row_h, h)
        x_cur = x
        for j, area in zip(row_idx, row_areas):
            item_w = area / row_h if row_h > 0 else w / len(row_areas)
            result[indices[j]] = (x_cur, y, item_w, row_h)
            x_cur += item_w
        if rest_idx:
            _strip(norm, result, rest_idx, x, y + row_h, w, max(0, h - row_h))


# ── Volume leader score ───────────────────────────────────────────────────────

def _vol_score(stock: dict) -> float:
    """Volume leader score = transaction_value×0.70 + normalized_rel_vol×0.30."""
    val  = stock.get("value",   0) or 0
    rv   = stock.get("rel_vol", 1) or 1
    # Normalize rv to [0, 1] assuming max useful rel_vol = 5
    rv_n = min(rv / 5.0, 1.0)
    return val * 0.70 + (val * rv_n) * 0.30


# ── Main generator ───────────────────────────────────────────────────────────

def generate_heatmap(sector_filter: str = None) -> io.BytesIO | None:
    """
    Generate a treemap heatmap PNG.

    Args:
        sector_filter: exact IDX sector name (e.g. "Finance", "Technology")
                       None / "all" → full market heatmap
    """
    # ── Determine scope ──────────────────────────────────────────────────────
    if sector_filter and sector_filter in IDX_STOCKS:
        sectors_to_show = {sector_filter: IDX_STOCKS[sector_filter]}
        title_label     = f"{SECTOR_ICONS.get(sector_filter, '📊')} {sector_filter}"
    else:
        sectors_to_show = IDX_STOCKS
        title_label     = "All Sectors"
        if sector_filter and sector_filter not in IDX_STOCKS:
            logger.warning(
                f"[HEATMAP] Unknown sector filter '{sector_filter}'. "
                f"Valid: {list(IDX_STOCKS.keys())}"
            )

    # ── Fetch data — enforce deduplication globally ──────────────────────────
    all_data     = []
    seen_tickers = set()

    for sector_name, tickers in sectors_to_show.items():
        # Cap per-sector at 12 stocks for all-sectors view to keep layout readable
        limit  = 12 if len(sectors_to_show) > 1 else len(tickers)
        snaps  = get_sector_snapshots(sector_name, tickers[:limit])

        added  = 0
        for s in snaps:
            t = s.get("ticker", "")
            if not t:
                continue
            if t in seen_tickers:
                logger.warning(f"[HEATMAP] DUPLICATE TICKER: {t} already added — skipping "
                               f"(second occurrence in sector {sector_name})")
                continue
            seen_tickers.add(t)
            s["sector"] = sector_name
            # Validate key fields
            if not s.get("price"):
                logger.warning(f"[HEATMAP] MISSING PRICE: {t} — excluded")
                continue
            if s.get("value", 0) == 0:
                logger.warning(f"[HEATMAP] MISSING VALUE: {t} transaction value = 0")
            all_data.append(s)
            added += 1

        logger.info(f"[HEATMAP] sector={sector_name}: {added}/{len(tickers[:limit])} stocks added")

    if not all_data:
        logger.error("[HEATMAP] No data available after deduplication")
        return None

    # ── Sort by transaction value descending (largest tile = most liquid) ────
    all_data.sort(key=lambda x: x.get("value", 0) or 0, reverse=True)

    # Avoid zero-value tiles (use a floor so every stock appears)
    values = [max(s.get("value", 0) or 0, 1) for s in all_data]

    # ── Figure setup ─────────────────────────────────────────────────────────
    margin_top    = 0.08   # for title
    margin_bottom = 0.14   # for legend + summary
    fig_w, fig_h  = 16, 12

    fig = plt.figure(figsize=(fig_w, fig_h), facecolor="#0d1117")
    ax  = fig.add_axes([0, margin_bottom, 1, 1 - margin_top - margin_bottom])
    ax.set_facecolor("#0d1117")
    ax.axis("off")

    canvas_w = 1.0
    canvas_h = 1.0

    # ── Treemap layout ───────────────────────────────────────────────────────
    rects = _squarify(values, 0, 0, canvas_w, canvas_h)

    PAD = 0.003   # gap between tiles

    for stock, (rx, ry, rw, rh) in zip(all_data, rects):
        if rw < 0.01 or rh < 0.01:
            continue   # too small to render

        pct    = stock.get("pct_chg", 0)
        ticker = stock.get("ticker",  "")
        price  = stock.get("price",   0)
        rv     = stock.get("rel_vol", 1) or 1
        sector = stock.get("sector",  "")

        color    = _pct_color(pct)
        txt_clr  = _text_color(pct)
        sign     = "+" if pct >= 0 else ""

        # Draw tile with padding
        tile = patches.FancyBboxPatch(
            (rx + PAD, ry + PAD),
            max(0, rw - 2 * PAD),
            max(0, rh - 2 * PAD),
            boxstyle="round,pad=0.005",
            linewidth=0.3,
            edgecolor="#21262d",
            facecolor=color,
        )
        ax.add_patch(tile)

        cx, cy = rx + rw / 2, ry + rh / 2

        # Dynamic font size based on tile area
        area_px  = rw * rh * fig_w * fig_h * 100   # rough pixel area
        fs_tick  = min(9.5, max(5.0, area_px ** 0.35))
        fs_pct   = min(8.0, max(4.0, area_px ** 0.30))
        fs_price = min(6.5, max(3.5, area_px ** 0.26))

        # Only show text if tile is large enough
        if rw > 0.03 and rh > 0.03:
            ax.text(cx, cy + rh * 0.14, ticker,
                    ha="center", va="center",
                    color=txt_clr, fontsize=fs_tick, fontweight="bold",
                    clip_on=True)
            ax.text(cx, cy,            f"{sign}{pct:.1f}%",
                    ha="center", va="center",
                    color=txt_clr, fontsize=fs_pct,
                    clip_on=True)
        if rw > 0.06 and rh > 0.06:
            price_str = f"{price:,.0f}" if price < 10_000 else f"{price/1_000:.1f}K"
            ax.text(cx, cy - rh * 0.16, price_str,
                    ha="center", va="center",
                    color=txt_clr, fontsize=fs_price, alpha=0.8,
                    clip_on=True)
        if rv > 1.5 and rw > 0.04 and rh > 0.04:
            ax.text(rx + rw - PAD * 6, ry + rh - PAD * 6,
                    f"{rv:.1f}×",
                    ha="right", va="top",
                    color=txt_clr, fontsize=max(3.5, fs_price - 1), alpha=0.7,
                    clip_on=True)

    # ── Title ────────────────────────────────────────────────────────────────
    fig.text(0.5, 0.975, f"IDX Heatmap — {title_label}",
             ha="center", va="top",
             color="#c9d1d9", fontsize=15, fontweight="bold")

    # ── Color legend ─────────────────────────────────────────────────────────
    legend_ax = fig.add_axes([0.05, margin_bottom * 0.35, 0.35, 0.025])
    legend_ax.set_facecolor("#0d1117")
    legend_ax.axis("off")

    tiers = [
        (_STRONG_BEAR, "< -3%"),
        (_BEAR,        "-3% to -1%"),
        (_NEUTRAL_NEG, "-1% to 0%"),
        (_NEUTRAL,     "0%"),
        (_NEUTRAL_POS, "0% to +1%"),
        (_BULL,        "+1% to +3%"),
        (_STRONG_BULL, "> +3%"),
    ]
    for i, (col, lbl) in enumerate(tiers):
        legend_ax.add_patch(patches.Rectangle(
            (i / len(tiers), 0), 1 / len(tiers), 1,
            facecolor=col, edgecolor="none"))
    legend_ax.set_xlim(0, 1); legend_ax.set_ylim(0, 1)
    fig.text(0.225, margin_bottom * 0.12, "% Change",
             ha="center", color="#8b949e", fontsize=8)

    # ── Summary stats ────────────────────────────────────────────────────────
    gainers     = sorted(all_data, key=lambda x: x.get("pct_chg", 0), reverse=True)[:3]
    losers      = sorted(all_data, key=lambda x: x.get("pct_chg", 0))[:3]
    vol_leaders = sorted(all_data, key=_vol_score, reverse=True)[:3]

    g_str = " | ".join(f"{s['ticker']} +{s['pct_chg']:.1f}%" for s in gainers)
    l_str = " | ".join(f"{s['ticker']} {s['pct_chg']:.1f}%"  for s in losers)
    v_str = " | ".join(f"{s['ticker']} {(s.get('rel_vol') or 1):.1f}× val:{s.get('value',0)/1e9:.1f}B"
                       for s in vol_leaders)

    sy = margin_bottom * 0.92
    fig.text(0.5, sy,            f"🟢 Top Gainers: {g_str}",
             ha="center", color="#43a047", fontsize=8)
    fig.text(0.5, sy - 0.03,     f"🔴 Top Losers: {l_str}",
             ha="center", color="#e53935", fontsize=8)
    fig.text(0.5, sy - 0.06,     f"⚡ Vol Leaders (value×70%+vol×30%): {v_str}",
             ha="center", color="#f9a825", fontsize=7.5)

    # Sector summary row (when showing all sectors)
    if len(sectors_to_show) > 1:
        by_sector = {}
        for s in all_data:
            sec = s.get("sector", "")
            by_sector.setdefault(sec, []).append(s.get("pct_chg", 0))
        sec_avgs = {k: sum(v)/len(v) for k, v in by_sector.items() if v}
        top_sec  = max(sec_avgs, key=sec_avgs.get) if sec_avgs else ""
        bot_sec  = min(sec_avgs, key=sec_avgs.get) if sec_avgs else ""
        if top_sec and bot_sec:
            fig.text(
                0.5, sy - 0.09,
                f"🔥 Best: {SECTOR_ICONS.get(top_sec,'')}{top_sec} {sec_avgs[top_sec]:+.2f}%  "
                f"  📉 Worst: {SECTOR_ICONS.get(bot_sec,'')}{bot_sec} {sec_avgs[bot_sec]:+.2f}%",
                ha="center", color="#c9d1d9", fontsize=7.5)

    # ── Render ───────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                    facecolor="#0d1117", edgecolor="none")
        plt.close(fig)
    except Exception as e:
        logger.error(f"[HEATMAP] Render error: {e}")
        plt.close("all")
        return None

    buf.seek(0)
    logger.info(
        f"[HEATMAP] Generated '{title_label}' — {len(all_data)} stocks, "
        f"sectors={len(sectors_to_show)}"
    )
    return buf
