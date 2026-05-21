import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.services.data_service import get_stock_data, compute_indicators, get_ihsg_data, get_market_snapshot
from bot.charts.chart_generator import generate_stock_chart
from bot.bandarmology.broker_analyzer import estimate_broker_signal, format_broker_report
from bot.utils.formatters import fmt_price, fmt_volume, fmt_value, fmt_pct, fmt_score, score_emoji
from bot.utils.constants import IDX_STOCKS, ALL_IDX_STOCKS, SCREENER_NAMES
from bot.data.watchlist import get_watchlist, add_to_watchlist, remove_from_watchlist

logger = logging.getLogger(__name__)

MAIN_MENU_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("📈 Screener", callback_data="menu_screener")],
    [InlineKeyboardButton("🔥 Heatmap", callback_data="menu_heatmap"),
     InlineKeyboardButton("🔄 Sector Rotation", callback_data="menu_sector")],
    [InlineKeyboardButton("🏦 Bandar Detector", callback_data="menu_bandar"),
     InlineKeyboardButton("📊 Watchlist", callback_data="menu_watchlist")],
    [InlineKeyboardButton("⚡ Top Momentum", callback_data="menu_momentum"),
     InlineKeyboardButton("💰 Foreign Flow", callback_data="menu_foreign")],
    [InlineKeyboardButton("📉 Market Breadth", callback_data="menu_breadth"),
     InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")],
])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ihsg = get_ihsg_data()
    price = ihsg.get("price", 0)
    pct = ihsg.get("pct_chg", 0)
    sign = "+" if pct >= 0 else ""
    emoji = "🟢" if pct >= 0 else "🔴"

    text = (
        f"🇮🇩 *IDX Stock Screener Bot*\n\n"
        f"*IHSG:* {price:,.2f} {emoji} {sign}{pct:.2f}%\n\n"
        f"Welcome! I'm your AI-powered Indonesian Stock Market bot.\n\n"
        f"*Features:*\n"
        f"• 3 Built-in Screeners (ARA Hunter, BSJP, Big Accumulation)\n"
        f"• Live Heatmap & Sector Rotation\n"
        f"• Bandarology / Broker Flow Analysis\n"
        f"• AI-Generated Stock Explanations\n"
        f"• Candlestick Charts with Technical Indicators\n"
        f"• Watchlist with Alerts\n\n"
        f"📌 *Quick commands:*\n"
        f"`/bbca` — chart + analysis for BBCA\n"
        f"`/screener` — run screeners\n"
        f"`/heatmap` — sector heatmap\n"
        f"`/watchlist` — your watchlist\n\n"
        f"Choose from the menu below:"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_MENU_KB)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *IDX Screener Bot — Commands*\n\n"
        "*Chart Commands:*\n"
        "`/TICKER` — e.g. `/bbca`, `/tlkm`, `/bmri`\n"
        "Shows candlestick chart + full analysis\n\n"
        "*Screener Commands:*\n"
        "`/screener` — open screener menu\n"
        "`/ara` — run ARA Hunter screener\n"
        "`/bsjp` — run BSJP screener\n"
        "`/bigacc` — run Big Accumulation screener\n\n"
        "*Market Commands:*\n"
        "`/heatmap` — IDX sector heatmap\n"
        "`/sector` — sector rotation analysis\n"
        "`/breadth` — market breadth\n"
        "`/momentum` — top momentum stocks\n\n"
        "*Watchlist:*\n"
        "`/watchlist` — view your watchlist\n"
        "`/add TICKER` — add to watchlist\n"
        "`/remove TICKER` — remove from watchlist\n\n"
        "`/start` — main menu"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str = None):
    if ticker is None:
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /chart TICKER (e.g. /chart BBCA)")
            return
        ticker = args[0].upper()

    msg = await update.message.reply_text(f"⏳ Generating chart for *{ticker}*...", parse_mode="Markdown")

    df = get_stock_data(ticker, period="3mo")
    if df is None or len(df) < 5:
        await msg.edit_text(f"❌ No data found for *{ticker}*. Check the ticker symbol.", parse_mode="Markdown")
        return

    df = compute_indicators(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    price = latest["Close"]
    prev_price = prev["Close"]
    pct_chg = (price - prev_price) / prev_price * 100
    rsi = latest.get("RSI")
    macd = latest.get("MACD")
    ma5 = latest.get("MA5")
    ma20 = latest.get("MA20")
    ma50 = latest.get("MA50")
    rel_vol = latest.get("RelVol", 1) or 1
    volume = latest["Volume"]
    value = price * volume

    sector = next((s for s, tickers in IDX_STOCKS.items() if ticker in tickers), "Other")

    snap = {
        "ticker": ticker,
        "price": price,
        "prev_price": prev_price,
        "pct_chg": pct_chg,
        "volume": volume,
        "value": value,
        "rel_vol": rel_vol,
        "bandar_score": latest.get("BandarScore", 0),
        "ma20": ma20,
        "ma50": ma50,
    }
    broker = estimate_broker_signal(snap)

    sign = "+" if pct_chg >= 0 else ""
    trend_emoji = "🟢" if pct_chg >= 0 else "🔴"
    rsi_note = ""
    if rsi:
        if rsi > 70:
            rsi_note = " ⚠️ Overbought"
        elif rsi < 30:
            rsi_note = " ⚠️ Oversold"

    ma_trend = ""
    if ma5 and ma20 and ma50:
        if price > ma5 > ma20 > ma50:
            ma_trend = "🟢 All MAs Bullish"
        elif price > ma20 > ma50:
            ma_trend = "🟡 MA20/50 Bullish"
        elif price < ma20:
            ma_trend = "🔴 Below MA20"

    caption = (
        f"📊 *{ticker}* — {sector}\n\n"
        f"💰 Price: *{fmt_price(price)}* {trend_emoji} {sign}{pct_chg:.2f}%\n"
        f"📦 Volume: {fmt_volume(volume)} ({rel_vol:.1f}x avg)\n"
        f"💵 Value: {fmt_value(value)}\n\n"
        f"📐 *Technical:*\n"
        f"  MA5: {fmt_price(ma5)} | MA20: {fmt_price(ma20)} | MA50: {fmt_price(ma50)}\n"
        f"  RSI: {rsi:.1f}{rsi_note}\n"
        f"  MACD: {'🟢 Bullish' if macd and macd > latest.get('MACD_Signal', 0) else '🔴 Bearish'}\n"
        f"  Trend: {ma_trend}\n\n"
        f"🏦 *Broker:* {broker['bandar_label']}\n"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Full Chart", callback_data=f"chart_{ticker}"),
         InlineKeyboardButton("🏦 Broker Flow", callback_data=f"broker_{ticker}")],
        [InlineKeyboardButton("🔥 Heatmap", callback_data="menu_heatmap"),
         InlineKeyboardButton("⭐ Add Watchlist", callback_data=f"watch_add_{ticker}")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")],
    ])

    buf = generate_stock_chart(ticker)
    await msg.delete()

    if buf:
        await update.message.reply_photo(
            photo=buf,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=kb,
        )
    else:
        await update.message.reply_text(caption, parse_mode="Markdown", reply_markup=kb)


async def cmd_screener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 ARA Hunter", callback_data="screen_ara_hunter")],
        [InlineKeyboardButton("📈 BSJP", callback_data="screen_bsjp")],
        [InlineKeyboardButton("🏦 Big Accumulation", callback_data="screen_big_accumulation")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")],
    ])
    await update.message.reply_text(
        "📈 *Stock Screener*\n\nChoose a screener to run:\n\n"
        "🎯 *ARA Hunter* — Stocks nearing ARA limit\n"
        "📈 *BSJP* — BSJP momentum filter\n"
        "🏦 *Big Accumulation* — Bandar accumulation targets",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def cmd_heatmap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Generating IDX heatmap...")
    from bot.heatmap.heatmap_generator import generate_heatmap
    buf = generate_heatmap()
    await msg.delete()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏦 Banking", callback_data="heatmap_Banking"),
         InlineKeyboardButton("💻 Technology", callback_data="heatmap_Technology")],
        [InlineKeyboardButton("⚡ Energy", callback_data="heatmap_Energy"),
         InlineKeyboardButton("🛒 Consumer", callback_data="heatmap_Consumer")],
        [InlineKeyboardButton("🏥 Healthcare", callback_data="heatmap_Healthcare"),
         InlineKeyboardButton("🏠 Property", callback_data="heatmap_Property")],
        [InlineKeyboardButton("🏭 Industrial", callback_data="heatmap_Industrial"),
         InlineKeyboardButton("🌴 Plantation", callback_data="heatmap_Plantation")],
        [InlineKeyboardButton("🔄 Refresh All", callback_data="heatmap_all"),
         InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
    ])

    if buf:
        await update.message.reply_photo(
            photo=buf, caption="🔥 *IDX Market Heatmap*\n\nFilter by sector using buttons below.",
            parse_mode="Markdown", reply_markup=kb,
        )
    else:
        await update.message.reply_text("❌ Could not generate heatmap. Try again shortly.", reply_markup=kb)


async def cmd_sector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Analyzing sector rotation...")
    from bot.sector_rotation.sector_analyzer import analyze_sectors, format_sector_rotation
    data = analyze_sectors()
    text = format_sector_rotation(data)
    await msg.delete()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 View Charts", callback_data="menu_heatmap"),
         InlineKeyboardButton("🏦 Bandar Flow", callback_data="menu_bandar")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="menu_sector"),
         InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
    ])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_momentum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Scanning top momentum stocks...")
    snaps = get_market_snapshot(ALL_IDX_STOCKS[:40])
    snaps.sort(key=lambda x: x.get("pct_chg", 0), reverse=True)
    top = snaps[:10]

    lines = ["⚡ *Top Momentum Stocks*\n"]
    for i, s in enumerate(top, 1):
        ticker = s.get("ticker", "")
        pct = s.get("pct_chg", 0)
        rel_vol = s.get("rel_vol", 1) or 1
        price = s.get("price", 0)
        sign = "+" if pct >= 0 else ""
        lines.append(
            f"{i}. *{ticker}* {sign}{pct:.2f}% | Vol: {rel_vol:.1f}x | {fmt_price(price)}"
        )

    await msg.delete()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="menu_momentum"),
         InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
    ])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


async def cmd_breadth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Analyzing market breadth...")
    snaps = get_market_snapshot(ALL_IDX_STOCKS[:60])
    ihsg = get_ihsg_data()

    advance = sum(1 for s in snaps if s.get("pct_chg", 0) > 0)
    decline = sum(1 for s in snaps if s.get("pct_chg", 0) < 0)
    unchanged = len(snaps) - advance - decline
    total = len(snaps)
    ratio = advance / max(decline, 1)

    market_condition = (
        "🟢 Bullish" if ratio > 1.5
        else "🔴 Bearish" if ratio < 0.7
        else "🟡 Mixed"
    )

    ihsg_pct = ihsg.get("pct_chg", 0)
    ihsg_price = ihsg.get("price", 0)
    ihsg_sign = "+" if ihsg_pct >= 0 else ""

    text = (
        f"📉 *Market Breadth Analysis*\n\n"
        f"*IHSG:* {ihsg_price:,.2f} ({ihsg_sign}{ihsg_pct:.2f}%)\n"
        f"*Condition:* {market_condition}\n\n"
        f"*Advance/Decline ({total} stocks):*\n"
        f"  🟢 Advance: {advance} ({advance/total*100:.0f}%)\n"
        f"  🔴 Decline: {decline} ({decline/total*100:.0f}%)\n"
        f"  ⚪ Unchanged: {unchanged}\n"
        f"  📊 A/D Ratio: {ratio:.2f}\n\n"
        f"*Volume Breadth:*\n"
        f"  High Volume Gainers: {sum(1 for s in snaps if s.get('pct_chg',0)>0 and (s.get('rel_vol') or 1)>1.5)}\n"
        f"  High Volume Losers: {sum(1 for s in snaps if s.get('pct_chg',0)<0 and (s.get('rel_vol') or 1)>1.5)}\n\n"
        f"*Overbought (RSI>70):* {sum(1 for s in snaps if (s.get('rsi') or 0)>70)}\n"
        f"*Oversold (RSI<30):* {sum(1 for s in snaps if (s.get('rsi') or 50)<30)}"
    )

    await msg.delete()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="menu_breadth"),
         InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
    ])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    wl = get_watchlist(user_id)

    if not wl:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Run Screener", callback_data="menu_screener")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
        ])
        await update.message.reply_text(
            "📊 *Your Watchlist is empty.*\n\nAdd stocks with `/add TICKER`",
            parse_mode="Markdown", reply_markup=kb,
        )
        return

    snaps = get_market_snapshot(wl)
    snap_map = {s["ticker"]: s for s in snaps}

    lines = ["📊 *Your Watchlist*\n"]
    buttons = []
    for ticker in wl:
        s = snap_map.get(ticker, {})
        price = s.get("price", 0)
        pct = s.get("pct_chg", 0)
        sign = "+" if pct >= 0 else ""
        emoji = "🟢" if pct >= 0 else "🔴"
        lines.append(f"{emoji} *{ticker}* {fmt_price(price)} ({sign}{pct:.2f}%)")
        buttons.append(InlineKeyboardButton(f"📊 {ticker}", callback_data=f"chart_{ticker}"))

    rows = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton("🔄 Refresh", callback_data="menu_watchlist"),
                 InlineKeyboardButton("🔙 Menu", callback_data="menu_main")])
    kb = InlineKeyboardMarkup(rows)
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /add TICKER (e.g. /add BBCA)")
        return
    ticker = args[0].upper()
    user_id = update.effective_user.id
    if add_to_watchlist(user_id, ticker):
        await update.message.reply_text(f"✅ *{ticker}* added to your watchlist!", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⚠️ *{ticker}* is already in your watchlist.", parse_mode="Markdown")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /remove TICKER (e.g. /remove BBCA)")
        return
    ticker = args[0].upper()
    user_id = update.effective_user.id
    if remove_from_watchlist(user_id, ticker):
        await update.message.reply_text(f"✅ *{ticker}* removed from your watchlist.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⚠️ *{ticker}* was not in your watchlist.", parse_mode="Markdown")


async def cmd_bandar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏦 BBCA", callback_data="broker_BBCA"),
             InlineKeyboardButton("🏦 BMRI", callback_data="broker_BMRI")],
            [InlineKeyboardButton("🏦 TLKM", callback_data="broker_TLKM"),
             InlineKeyboardButton("🏦 BBRI", callback_data="broker_BBRI")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
        ])
        await update.message.reply_text(
            "🏦 *Bandar Detector*\n\nEnter: `/bandar TICKER`\nOr pick a stock:",
            parse_mode="Markdown", reply_markup=kb,
        )
        return

    ticker = args[0].upper()
    msg = await update.message.reply_text(f"⏳ Analyzing broker flow for *{ticker}*...", parse_mode="Markdown")
    snaps = get_market_snapshot([ticker])
    if not snaps:
        await msg.edit_text(f"❌ No data for *{ticker}*.", parse_mode="Markdown")
        return

    stock = snaps[0]
    broker_data = estimate_broker_signal(stock)
    report = format_broker_report(ticker, broker_data)

    await msg.delete()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Chart", callback_data=f"chart_{ticker}"),
         InlineKeyboardButton("⭐ Watchlist", callback_data=f"watch_add_{ticker}")],
        [InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
    ])
    await update.message.reply_text(report, parse_mode="Markdown", reply_markup=kb)


async def cmd_foreign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Scanning foreign flow data...")
    snaps = get_market_snapshot(ALL_IDX_STOCKS[:40])

    # Approximate: stocks with positive price change & volume spike
    potential_foreign_buy = [
        s for s in snaps
        if s.get("pct_chg", 0) > 0.5 and (s.get("rel_vol") or 1) > 1.5
    ]
    potential_foreign_buy.sort(key=lambda x: x.get("pct_chg", 0), reverse=True)

    lines = ["💰 *Foreign Flow Tracker*\n", "*Estimated Net Foreign Buy (Top Picks):*\n"]
    for s in potential_foreign_buy[:8]:
        ticker = s["ticker"]
        pct = s.get("pct_chg", 0)
        rv = s.get("rel_vol", 1) or 1
        lines.append(f"  🟢 *{ticker}* +{pct:.2f}% | Vol {rv:.1f}x")

    lines.append("\n*Estimated Net Foreign Sell:*\n")
    potential_sell = [
        s for s in snaps
        if s.get("pct_chg", 0) < -0.5 and (s.get("rel_vol") or 1) > 1.5
    ]
    for s in potential_sell[:5]:
        ticker = s["ticker"]
        pct = s.get("pct_chg", 0)
        lines.append(f"  🔴 *{ticker}* {pct:.2f}%")

    lines.append("\n⚠️ _Foreign flow is estimated. Actual data requires paid IDX provider._")

    await msg.delete()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="menu_foreign"),
         InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
    ])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
