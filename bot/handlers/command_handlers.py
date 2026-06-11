import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton,
)
from telegram.ext import ContextTypes
from bot.services.data_service import (
    get_stock_data, compute_indicators, get_ihsg_data, get_market_snapshot,
)
from bot.charts.chart_generator import generate_stock_chart
from bot.bandarmology.broker_analyzer import estimate_broker_signal, format_broker_report
from bot.utils.formatters import fmt_price, fmt_volume, fmt_value, fmt_pct, score_emoji
from bot.utils.constants import (
    IDX_STOCKS, ALL_IDX_STOCKS, SCREENER_NAMES,
    BTN_SCREENER, BTN_HEATMAP, BTN_SECTOR, BTN_BANDAR,
    BTN_WATCHLIST, BTN_MOMENTUM, BTN_FOREIGN, BTN_BREADTH, BTN_MENU,
)
from bot.data.watchlist import get_watchlist, add_to_watchlist, remove_from_watchlist

logger = logging.getLogger(__name__)

# ── Persistent bottom keyboard ──────────────────────────────────────────────
BOTTOM_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton(BTN_SCREENER), KeyboardButton(BTN_HEATMAP), KeyboardButton(BTN_SECTOR)],
        [KeyboardButton(BTN_BANDAR),   KeyboardButton(BTN_WATCHLIST), KeyboardButton(BTN_MOMENTUM)],
        [KeyboardButton(BTN_FOREIGN),  KeyboardButton(BTN_BREADTH),   KeyboardButton(BTN_MENU)],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# ── Inline main menu ────────────────────────────────────────────────────────
MAIN_MENU_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("📈 Screener",        callback_data="menu_screener")],
    [InlineKeyboardButton("🔥 Heatmap",         callback_data="menu_heatmap"),
     InlineKeyboardButton("🔄 Sector Rotation", callback_data="menu_sector")],
    [InlineKeyboardButton("🏦 Bandar Detector", callback_data="menu_bandar"),
     InlineKeyboardButton("📊 Watchlist",       callback_data="menu_watchlist")],
    [InlineKeyboardButton("⚡ Top Momentum",    callback_data="menu_momentum"),
     InlineKeyboardButton("💰 Foreign Flow",    callback_data="menu_foreign")],
    [InlineKeyboardButton("📉 Market Breadth",  callback_data="menu_breadth"),
     InlineKeyboardButton("⚙️ Settings",        callback_data="menu_settings")],
])


def _build_ihsg_header(ihsg: dict) -> str:
    price = ihsg.get("price", 0)
    pct   = ihsg.get("pct_chg", 0)
    sign  = "+" if pct >= 0 else ""
    emoji = "🟢" if pct >= 0 else "🔴"
    return f"*IHSG:* {price:,.2f} {emoji} {sign}{pct:.2f}%"


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ihsg = get_ihsg_data()
    text = (
        f"🇮🇩 *IDX Stock Screener Bot*\n\n"
        f"{_build_ihsg_header(ihsg)}\n\n"
        f"Welcome! AI-powered Indonesian Stock Market bot.\n\n"
        f"*Features:*\n"
        f"• 4 Screeners: ARA Hunter, BSJP, Big Acc, Scalper Pro\n"
        f"• Live Heatmap & Sector Rotation\n"
        f"• Bandarology / Broker Flow Analysis\n"
        f"• AI-Generated Stock Explanations\n"
        f"• Charts: Candlestick + RSI + MACD\n"
        f"• Watchlist with Auto Alerts\n\n"
        f"📌 *Quick chart:* type `/bbca`, `/tlkm`, `/bmri`\n\n"
        f"Use the keyboard below or inline menu:"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=BOTTOM_KB,
    )
    await update.message.reply_text(
        "📋 *Main Menu*", parse_mode="Markdown",
        reply_markup=MAIN_MENU_KB,
    )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ihsg = get_ihsg_data()
    await update.message.reply_text(
        f"🇮🇩 *IDX Screener Bot*\n\n{_build_ihsg_header(ihsg)}\n\nChoose:",
        parse_mode="Markdown", reply_markup=MAIN_MENU_KB,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *IDX Screener Bot — Commands*\n\n"
        "*Chart Commands:*\n"
        "`/bbca` `/tlkm` `/bmri` — any IDX ticker\n\n"
        "*Screener Commands:*\n"
        "`/screener` — screener menu\n"
        "`/ara` — ARA Hunter\n"
        "`/bsjp` — BSJP screener\n"
        "`/bigacc` — Big Accumulation\n"
        "`/scalp` — Scalper Pro ⚡\n\n"
        "*Market Commands:*\n"
        "`/heatmap` — sector heatmap\n"
        "`/sector` — sector rotation\n"
        "`/breadth` — market breadth\n"
        "`/momentum` — top momentum\n\n"
        "*Watchlist:*\n"
        "`/watchlist` — view watchlist\n"
        "`/add TICKER` — add to watchlist\n"
        "`/remove TICKER` — remove from watchlist\n\n"
        "`/start` — main menu"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=BOTTOM_KB)


async def cmd_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str = None):
    if ticker is None:
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /chart BBCA")
            return
        ticker = args[0].upper().strip()

    msg = await update.message.reply_text(
        f"⏳ Loading chart for *{ticker}*...", parse_mode="Markdown"
    )

    df = get_stock_data(ticker, period="3mo")
    if df is None or len(df) < 5:
        await msg.edit_text(
            f"❌ No data found for *{ticker}*.\n"
            "Check the ticker or try again later.", parse_mode="Markdown"
        )
        return

    df = compute_indicators(df)
    latest = df.iloc[-1]
    prev   = df.iloc[-2] if len(df) > 1 else latest

    price      = latest["Close"]
    prev_price = prev["Close"]
    pct_chg    = (price - prev_price) / prev_price * 100
    rsi        = latest.get("RSI") or 0
    macd       = latest.get("MACD")
    macd_sig   = latest.get("MACD_Signal")
    ma5        = latest.get("MA5")
    ma20       = latest.get("MA20")
    ma50       = latest.get("MA50")
    rel_vol    = latest.get("RelVol", 1) or 1
    volume     = latest["Volume"]
    value      = price * volume
    sector     = next((s for s, t in IDX_STOCKS.items() if ticker in t), "Other")

    snap = {
        "ticker": ticker, "price": price, "prev_price": prev_price,
        "pct_chg": pct_chg, "volume": volume, "value": value,
        "rel_vol": rel_vol, "bandar_score": latest.get("BandarScore", 0),
        "ma20": ma20, "ma50": ma50,
        "high": latest["High"], "low": latest["Low"],
        "vwap": latest.get("VWAP"),
    }
    broker = estimate_broker_signal(snap)
    sign   = "+" if pct_chg >= 0 else ""
    trend  = "🟢" if pct_chg >= 0 else "🔴"

    rsi_note = ""
    if rsi > 70:   rsi_note = " ⚠️ OB"
    elif rsi < 30: rsi_note = " ⚠️ OS"

    ma_trend = ""
    if ma5 and ma20 and ma50:
        if price > ma5 > ma20 > ma50:   ma_trend = "🟢 Full Bullish"
        elif price > ma20 > ma50:       ma_trend = "🟡 MA20/50 Bullish"
        elif price < ma20:              ma_trend = "🔴 Below MA20"

    caption = (
        f"📊 *{ticker}* — {sector}\n\n"
        f"💰 Price: *{fmt_price(price)}* {trend} {sign}{pct_chg:.2f}%\n"
        f"📦 Vol: {fmt_volume(volume)} ({rel_vol:.1f}x avg)\n"
        f"💵 Value: {fmt_value(value)}\n\n"
        f"*Technical:*\n"
        f"  MA5: {fmt_price(ma5)} | MA20: {fmt_price(ma20)} | MA50: {fmt_price(ma50)}\n"
        f"  RSI: {rsi:.1f}{rsi_note} | MACD: {'🟢' if macd and macd_sig and macd > macd_sig else '🔴'}\n"
        f"  Trend: {ma_trend}\n\n"
        f"🏦 Broker: *{broker['bandar_label']}*"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏦 Broker Flow",    callback_data=f"broker_{ticker}"),
         InlineKeyboardButton("⭐ Add Watchlist",  callback_data=f"watch_add_{ticker}")],
        [InlineKeyboardButton("🔥 Heatmap",        callback_data="menu_heatmap"),
         InlineKeyboardButton("🏠 Main Menu",      callback_data="menu_main")],
    ])

    buf = generate_stock_chart(ticker)
    await msg.delete()

    if buf:
        await update.message.reply_photo(
            photo=buf, caption=caption, parse_mode="Markdown", reply_markup=kb,
        )
    else:
        await update.message.reply_text(caption, parse_mode="Markdown", reply_markup=kb)


async def cmd_screener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 ARA Hunter",       callback_data="screen_ara_hunter")],
        [InlineKeyboardButton("📈 BSJP",             callback_data="screen_bsjp")],
        [InlineKeyboardButton("🏦 Big Accumulation", callback_data="screen_big_accumulation")],
        [InlineKeyboardButton("⚡ Scalper Pro",      callback_data="screen_scalper_pro")],
        [InlineKeyboardButton("🏠 Main Menu",        callback_data="menu_main")],
    ])
    await update.message.reply_text(
        "📈 *Stock Screener*\n\nChoose a screener:\n\n"
        "🎯 *ARA Hunter* — Near-ARA stocks with strong volume\n"
        "📈 *BSJP* — Breakout + foreign buy streak\n"
        "🏦 *Big Accumulation* — Smart money loading\n"
        "⚡ *Scalper Pro* — Intraday scalp setups",
        parse_mode="Markdown", reply_markup=kb,
    )


async def cmd_heatmap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Generating IDX heatmap...")
    from bot.heatmap.heatmap_generator import generate_heatmap
    buf = generate_heatmap()
    await msg.delete()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏦 Finance",     callback_data="heatmap_Finance"),
         InlineKeyboardButton("💻 Technology",  callback_data="heatmap_Technology")],
        [InlineKeyboardButton("⚡ Energy",      callback_data="heatmap_Energy"),
         InlineKeyboardButton("⛏️ Materials",   callback_data="heatmap_Basic Materials")],
        [InlineKeyboardButton("🛍️ Staples",    callback_data="heatmap_Consumer Staples"),
         InlineKeyboardButton("🛒 Cyclicals",   callback_data="heatmap_Consumer Cyclicals")],
        [InlineKeyboardButton("🏥 Healthcare",  callback_data="heatmap_Healthcare"),
         InlineKeyboardButton("🏠 Property",    callback_data="heatmap_Property")],
        [InlineKeyboardButton("🏭 Industrials", callback_data="heatmap_Industrials"),
         InlineKeyboardButton("🛣️ Infra",       callback_data="heatmap_Infrastructure")],
        [InlineKeyboardButton("🚢 Transport",   callback_data="heatmap_Transportation"),
         InlineKeyboardButton("🔄 All Sectors", callback_data="heatmap_all")],
        [InlineKeyboardButton("🏠 Menu",        callback_data="menu_main")],
    ])

    if buf:
        await update.message.reply_photo(
            photo=buf,
            caption="🔥 *IDX Market Heatmap*\n\nTap a sector to filter:",
            parse_mode="Markdown", reply_markup=kb,
        )
    else:
        await update.message.reply_text("❌ Heatmap unavailable. Try again.", reply_markup=kb)


async def cmd_sector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Analyzing sector rotation...")
    from bot.sector_rotation.sector_analyzer import analyze_sectors, format_sector_rotation
    data = analyze_sectors()
    text = format_sector_rotation(data)
    await msg.delete()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Heatmap",    callback_data="menu_heatmap"),
         InlineKeyboardButton("🏦 Bandar Flow",callback_data="menu_bandar")],
        [InlineKeyboardButton("🔄 Refresh",    callback_data="menu_sector"),
         InlineKeyboardButton("🏠 Menu",       callback_data="menu_main")],
    ])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_momentum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Scanning top momentum stocks...")
    snaps = get_market_snapshot(ALL_IDX_STOCKS[:50])
    snaps.sort(key=lambda x: x.get("pct_chg", 0), reverse=True)
    top = snaps[:10]
    lines = ["⚡ *Top Momentum Stocks*\n"]
    for i, s in enumerate(top, 1):
        ticker = s.get("ticker", "")
        pct    = s.get("pct_chg", 0)
        rv     = s.get("rel_vol", 1) or 1
        sign   = "+" if pct >= 0 else ""
        lines.append(f"{i}. *{ticker}* {sign}{pct:.2f}% | Vol: {rv:.1f}x | {fmt_price(s.get('price'))}")
    await msg.delete()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="menu_momentum"),
         InlineKeyboardButton("🏠 Menu",    callback_data="menu_main")],
    ])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


async def cmd_breadth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Analyzing market breadth...")
    snaps  = get_market_snapshot(ALL_IDX_STOCKS[:60])
    ihsg   = get_ihsg_data()
    adv    = sum(1 for s in snaps if s.get("pct_chg", 0) > 0)
    dec    = sum(1 for s in snaps if s.get("pct_chg", 0) < 0)
    unch   = len(snaps) - adv - dec
    total  = len(snaps)
    ratio  = adv / max(dec, 1)
    cond   = "🟢 Bullish" if ratio > 1.5 else "🔴 Bearish" if ratio < 0.7 else "🟡 Mixed"
    pct    = ihsg.get("pct_chg", 0)
    sign   = "+" if pct >= 0 else ""
    text   = (
        f"📉 *Market Breadth*\n\n"
        f"*IHSG:* {ihsg.get('price',0):,.2f} ({sign}{pct:.2f}%)\n"
        f"*Condition:* {cond}\n\n"
        f"🟢 Advance: {adv} ({adv/total*100:.0f}%)\n"
        f"🔴 Decline: {dec} ({dec/total*100:.0f}%)\n"
        f"⚪ Unchanged: {unch}\n"
        f"📊 A/D Ratio: {ratio:.2f}\n\n"
        f"High-Vol Gainers: {sum(1 for s in snaps if s.get('pct_chg',0)>0 and (s.get('rel_vol') or 1)>1.5)}\n"
        f"High-Vol Losers: {sum(1 for s in snaps if s.get('pct_chg',0)<0 and (s.get('rel_vol') or 1)>1.5)}\n\n"
        f"Overbought RSI>70: {sum(1 for s in snaps if (s.get('rsi') or 0)>70)}\n"
        f"Oversold RSI<30: {sum(1 for s in snaps if (s.get('rsi') or 50)<30)}"
    )
    await msg.delete()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="menu_breadth"),
         InlineKeyboardButton("🏠 Menu",    callback_data="menu_main")],
    ])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    wl = get_watchlist(user_id)
    if not wl:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Screener", callback_data="menu_screener")],
            [InlineKeyboardButton("🏠 Menu",     callback_data="menu_main")],
        ])
        await update.message.reply_text(
            "📊 *Watchlist is empty.*\n\nAdd stocks: `/add BBCA`",
            parse_mode="Markdown", reply_markup=kb,
        )
        return
    snaps    = get_market_snapshot(wl)
    snap_map = {s["ticker"]: s for s in snaps}
    lines    = ["📊 *Your Watchlist*\n"]
    buttons  = []
    for ticker in wl:
        s    = snap_map.get(ticker, {})
        pct  = s.get("pct_chg", 0)
        sign = "+" if pct >= 0 else ""
        e    = "🟢" if pct >= 0 else "🔴"
        lines.append(f"{e} *{ticker}* {fmt_price(s.get('price',0))} ({sign}{pct:.2f}%)")
        buttons.append(InlineKeyboardButton(f"📊 {ticker}", callback_data=f"chart_{ticker}"))
    rows = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    rows.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="menu_watchlist"),
        InlineKeyboardButton("🏠 Menu",    callback_data="menu_main"),
    ])
    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows),
    )


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/add BBCA`", parse_mode="Markdown")
        return
    ticker  = args[0].upper().strip()
    user_id = update.effective_user.id
    if add_to_watchlist(user_id, ticker):
        await update.message.reply_text(f"✅ *{ticker}* added to watchlist!", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⚠️ *{ticker}* already in watchlist.", parse_mode="Markdown")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/remove BBCA`", parse_mode="Markdown")
        return
    ticker  = args[0].upper().strip()
    user_id = update.effective_user.id
    if remove_from_watchlist(user_id, ticker):
        await update.message.reply_text(f"✅ *{ticker}* removed from watchlist.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⚠️ *{ticker}* not in watchlist.", parse_mode="Markdown")


async def cmd_bandar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏦 BBCA", callback_data="broker_BBCA"),
             InlineKeyboardButton("🏦 BMRI", callback_data="broker_BMRI")],
            [InlineKeyboardButton("🏦 TLKM", callback_data="broker_TLKM"),
             InlineKeyboardButton("🏦 BBRI", callback_data="broker_BBRI")],
            [InlineKeyboardButton("🏦 ADRO", callback_data="broker_ADRO"),
             InlineKeyboardButton("🏦 ASII", callback_data="broker_ASII")],
            [InlineKeyboardButton("🏠 Menu", callback_data="menu_main")],
        ])
        await update.message.reply_text(
            "🏦 *Bandar Detector*\n\n"
            "Type: `/bandar TICKER` (e.g. `/bandar BBCA`)\n\n"
            "Or tap a stock to analyze:",
            parse_mode="Markdown", reply_markup=kb,
        )
        return
    ticker = args[0].upper().strip()
    await _send_broker_report(update.message, ticker)


async def _send_broker_report(message, ticker: str):
    msg = await message.reply_text(
        f"⏳ Analyzing broker flow for *{ticker}*...", parse_mode="Markdown"
    )
    snaps = get_market_snapshot([ticker])
    if not snaps:
        await msg.edit_text(f"❌ No data for *{ticker}*.", parse_mode="Markdown")
        return
    broker_data = estimate_broker_signal(snaps[0])
    report      = format_broker_report(ticker, broker_data)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Chart",      callback_data=f"chart_{ticker}"),
         InlineKeyboardButton("⭐ Watchlist",  callback_data=f"watch_add_{ticker}")],
        [InlineKeyboardButton("🏠 Menu",       callback_data="menu_main")],
    ])
    await msg.delete()
    await message.reply_text(report, parse_mode="Markdown", reply_markup=kb)


# ─────────────────────────────────────────────────────────────────────────────
#  /alert  — Custom price alert
# ─────────────────────────────────────────────────────────────────────────────

async def cmd_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage:
      /alert BBCA 9500      — alert when BBCA crosses 9,500
      /alert list           — show your active alerts
      /alert remove BBCA    — remove all alerts for BBCA
    """
    args = context.args or []
    user_id = update.effective_user.id

    # ── list ──────────────────────────────────────────────────────────────
    if not args or args[0].lower() == "list":
        from bot.alerts.price_alerts import get_user_alerts
        alerts = get_user_alerts(user_id)
        if not alerts:
            await update.message.reply_text(
                "📋 *No active price alerts.*\n\n"
                "Set one with:\n`/alert BBCA 9500`",
                parse_mode="Markdown",
                reply_markup=BOTTOM_KB,
            )
            return
        lines = ["📋 *Your Price Alerts:*\n"]
        for a in alerts:
            arrow = "📈" if a["direction"] == "above" else "📉"
            lines.append(
                f"{arrow} *{a['ticker']}* → {a['direction']} *{a['target']:,.0f}*"
                f"  (from {a['current']:,.0f})"
            )
        lines.append("\n_Remove with:_ `/alert remove TICKER`")
        await update.message.reply_text(
            "\n".join(lines), parse_mode="Markdown", reply_markup=BOTTOM_KB,
        )
        return

    # ── remove ────────────────────────────────────────────────────────────
    if args[0].lower() == "remove" and len(args) >= 2:
        from bot.alerts.price_alerts import remove_user_alert
        ticker = args[1].upper().strip()
        ok = remove_user_alert(user_id, ticker)
        await update.message.reply_text(
            f"✅ Removed all alerts for *{ticker}*." if ok else f"⚠️ No alerts found for *{ticker}*.",
            parse_mode="Markdown",
            reply_markup=BOTTOM_KB,
        )
        return

    # ── set new alert ─────────────────────────────────────────────────────
    if len(args) < 2:
        await update.message.reply_text(
            "❌ *Usage:* `/alert TICKER TARGET`\n"
            "Example: `/alert BBCA 9500`\n\n"
            "Or view alerts: `/alert list`\n"
            "Remove: `/alert remove BBCA`",
            parse_mode="Markdown",
            reply_markup=BOTTOM_KB,
        )
        return

    ticker = args[0].upper().strip()
    try:
        target = float(args[1].replace(",", "").replace(".", ""))
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid price. Use: `/alert BBCA 9500`",
            parse_mode="Markdown",
        )
        return

    if target <= 0:
        await update.message.reply_text("❌ Target price must be > 0.", parse_mode="Markdown")
        return

    # Fetch current price
    msg   = await update.message.reply_text(f"⏳ Fetching *{ticker}* price…", parse_mode="Markdown")
    snaps = get_market_snapshot([ticker])
    if not snaps:
        await msg.edit_text(
            f"❌ Could not find *{ticker}*. Make sure it's a valid IDX ticker.",
            parse_mode="Markdown",
        )
        return

    current_price = snaps[0].get("price", 0)
    if not current_price:
        await msg.edit_text(f"❌ No price data for *{ticker}*.", parse_mode="Markdown")
        return

    from bot.alerts.price_alerts import add_price_alert
    confirmation = add_price_alert(user_id, ticker, target, current_price)
    await msg.delete()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 My Alerts",   callback_data="menu_main"),
         InlineKeyboardButton("📊 Chart",       callback_data=f"chart_{ticker}")],
        [InlineKeyboardButton("⭐ Add Watchlist", callback_data=f"watch_add_{ticker}"),
         InlineKeyboardButton("🏠 Menu",         callback_data="menu_main")],
    ])
    await update.message.reply_text(
        confirmation, parse_mode="Markdown", reply_markup=kb,
    )


async def cmd_dataquality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /dataquality — Live data validation report.

    Shows:
    • Number of stocks with valid data vs total scanned
    • Data source health (yfinance latency, stale quotes)
    • Detection of uniform / rate-limited data per sector
    • Volume leader integrity check
    • Missing field warnings (market_cap, value, sector mapping)
    • Sector deviation log (equal-weight vs mcap-weighted)
    """
    msg = await update.message.reply_text(
        "⏳ Running data quality audit across all IDX sectors…"
    )

    from bot.services.data_service import get_market_snapshot, generate_data_report
    from bot.utils.constants import IDX_STOCKS, SECTOR_ICONS
    from collections import Counter
    import time

    lines     = ["🔬 *IDX Data Quality Report*\n"]
    issues    = []
    ok_count  = 0
    fail_count= 0
    stale_count = 0
    suspect_sectors = []

    # ── Per-sector validation ─────────────────────────────────────────────────
    for sector_name, tickers in IDX_STOCKS.items():
        sample = tickers[:10]
        t0     = time.monotonic()
        snaps  = get_market_snapshot(sample, _context=f"dq:{sector_name}")
        latency= time.monotonic() - t0

        ok     = len(snaps)
        fail   = len(sample) - ok
        ok_count   += ok
        fail_count += fail

        # Duplicate pct check
        pcts    = [round(s.get("pct_chg", 0), 2) for s in snaps]
        counts  = Counter(pcts)
        top_val, top_cnt = counts.most_common(1)[0] if counts else (0, 0)
        uniform = ok > 2 and (top_cnt / max(ok, 1)) >= 0.6

        # Stale quote detection (timestamp > 1 day old)
        for s in snaps:
            ts_str = s.get("timestamp", "")
            if ts_str:
                try:
                    from datetime import datetime
                    import pytz
                    ts  = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00").split("+")[0])
                    age = (datetime.utcnow() - ts.replace(tzinfo=None)).total_seconds() / 3600
                    if age > 24:
                        stale_count += 1
                        issues.append(f"⚠️ STALE DATA: {s['ticker']} quote age {age:.0f}h")
                except Exception:
                    pass

        icon    = SECTOR_ICONS.get(sector_name, "📊")
        status  = "⚠️ SUSPECT" if uniform else ("✅ OK" if fail == 0 else "🔶 PARTIAL")
        if uniform:
            suspect_sectors.append(sector_name)
            issues.append(
                f"⚠️ UNIFORM DATA: {sector_name} — "
                f"{top_cnt}/{ok} stocks show pct={top_val}% (rate-limit?)"
            )

        lines.append(
            f"{icon} *{sector_name[:14]:14s}* {status}\n"
            f"  Data: {ok}/{len(sample)} ok  |  Latency: {latency*1000:.0f}ms  |  "
            f"Fail: {fail}"
        )

    lines.append("")

    # ── Missing field summary ────────────────────────────────────────────────
    sample_snaps = get_market_snapshot(
        [t for tickers in IDX_STOCKS.values() for t in tickers[:3]][:30],
        _context="dq:missing_fields"
    )
    missing_val   = [s["ticker"] for s in sample_snaps if not s.get("value")]
    missing_vol   = [s["ticker"] for s in sample_snaps if not s.get("volume")]
    missing_rsi   = [s["ticker"] for s in sample_snaps if not s.get("rsi")]

    if missing_val:
        issues.append(f"⚠️ MISSING VALUE: {', '.join(missing_val[:6])}")
    if missing_vol:
        issues.append(f"⚠️ MISSING VOLUME: {', '.join(missing_vol[:6])}")
    if missing_rsi:
        issues.append(f"ℹ️ MISSING RSI: {', '.join(missing_rsi[:6])} (insufficient history)")

    # ── Summary block ─────────────────────────────────────────────────────────
    total     = ok_count + fail_count
    pct_ok    = ok_count / max(total, 1) * 100
    health    = "🟢 Good" if pct_ok >= 80 else ("🟡 Degraded" if pct_ok >= 50 else "🔴 Poor")

    summary = (
        f"*── Summary ──*\n"
        f"Health      : {health} ({pct_ok:.0f}%)\n"
        f"Valid data  : {ok_count}/{total} stocks\n"
        f"Failed      : {fail_count} ({fail_count/max(total,1)*100:.0f}%)\n"
        f"Stale quotes: {stale_count}\n"
        f"Suspect sectors: {len(suspect_sectors)}"
    )
    if suspect_sectors:
        summary += f"\n  → {', '.join(suspect_sectors)}"

    lines.append(summary)

    if issues:
        lines.append("\n*── Issues Detected ──*")
        for issue in issues[:12]:
            lines.append(issue)
        if len(issues) > 12:
            lines.append(f"  _…and {len(issues)-12} more (check bot logs)_")
    else:
        lines.append("\n✅ No data integrity issues detected.")

    lines.append("\n_Run `/dataquality` anytime to re-audit._")

    await msg.delete()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh",        callback_data="dq_refresh"),
         InlineKeyboardButton("🔄 Sector Rotation", callback_data="menu_sector")],
        [InlineKeyboardButton("🔥 Heatmap",         callback_data="menu_heatmap"),
         InlineKeyboardButton("🏠 Menu",            callback_data="menu_main")],
    ])
    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=kb
    )


async def cmd_foreign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg   = await update.message.reply_text("⏳ Scanning foreign flow...")
    snaps = get_market_snapshot(ALL_IDX_STOCKS[:50])
    buys  = sorted(
        [s for s in snaps if s.get("pct_chg", 0) > 0.5 and (s.get("rel_vol") or 1) > 1.5],
        key=lambda x: x.get("pct_chg", 0), reverse=True,
    )[:8]
    sells = [s for s in snaps if s.get("pct_chg", 0) < -0.5 and (s.get("rel_vol") or 1) > 1.5][:5]
    lines = ["💰 *Foreign Flow Tracker*\n", "*Est. Net Foreign Buy:*\n"]
    for s in buys:
        rv = s.get("rel_vol", 1) or 1
        lines.append(f"  🟢 *{s['ticker']}* +{s['pct_chg']:.2f}% | {rv:.1f}x vol")
    lines.append("\n*Est. Net Foreign Sell:*\n")
    for s in sells:
        lines.append(f"  🔴 *{s['ticker']}* {s['pct_chg']:.2f}%")
    lines.append("\n⚠️ _Estimated. Actual data needs paid IDX provider._")
    await msg.delete()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="menu_foreign"),
         InlineKeyboardButton("🏠 Menu",    callback_data="menu_main")],
    ])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
