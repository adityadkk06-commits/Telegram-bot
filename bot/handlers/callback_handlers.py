import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils.constants import IDX_STOCKS, ALL_IDX_STOCKS, SCREENER_NAMES
from bot.utils.formatters import fmt_price, fmt_volume, fmt_value, fmt_pct, fmt_score, score_emoji, broker_signal_emoji
from bot.data.watchlist import add_to_watchlist, remove_from_watchlist, get_watchlist
from bot.services.data_service import get_market_snapshot, get_ihsg_data

logger = logging.getLogger(__name__)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── Main menu ──────────────────────────────────────────────
    if data == "menu_main":
        from bot.handlers.command_handlers import MAIN_MENU_KB
        ihsg = get_ihsg_data()
        price = ihsg.get("price", 0)
        pct = ihsg.get("pct_chg", 0)
        sign = "+" if pct >= 0 else ""
        emoji = "🟢" if pct >= 0 else "🔴"
        await query.edit_message_text(
            f"🇮🇩 *IDX Stock Screener Bot*\n\n"
            f"*IHSG:* {price:,.2f} {emoji} {sign}{pct:.2f}%\n\n"
            f"Choose from the menu below:",
            parse_mode="Markdown",
            reply_markup=MAIN_MENU_KB,
        )

    # ── Screener menu ──────────────────────────────────────────
    elif data == "menu_screener":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 ARA Hunter", callback_data="screen_ara_hunter")],
            [InlineKeyboardButton("📈 BSJP", callback_data="screen_bsjp")],
            [InlineKeyboardButton("🏦 Big Accumulation", callback_data="screen_big_accumulation")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu_main")],
        ])
        await query.edit_message_text(
            "📈 *Stock Screener*\n\nChoose a screener:\n\n"
            "🎯 *ARA Hunter* — Stocks nearing ARA with strong volume\n"
            "📈 *BSJP* — Breakout with foreign buy streak\n"
            "🏦 *Big Accumulation* — Bandar loading positions",
            parse_mode="Markdown",
            reply_markup=kb,
        )

    # ── Run screener ──────────────────────────────────────────
    elif data.startswith("screen_"):
        screener_type = data.replace("screen_", "")
        name = SCREENER_NAMES.get(screener_type, screener_type.upper())
        await query.edit_message_text(f"⏳ Running *{name}* screener...", parse_mode="Markdown")
        await _run_screener_cb(query, context, screener_type, name)

    # ── Chart ──────────────────────────────────────────────────
    elif data.startswith("chart_"):
        ticker = data.replace("chart_", "")
        await query.edit_message_text(f"⏳ Loading chart for *{ticker}*...", parse_mode="Markdown")
        from bot.charts.chart_generator import generate_stock_chart
        from bot.bandarmology.broker_analyzer import estimate_broker_signal
        from bot.services.data_service import get_stock_data, compute_indicators

        df = get_stock_data(ticker, period="3mo")
        if df is None or len(df) < 5:
            await query.edit_message_text(f"❌ No data for *{ticker}*.", parse_mode="Markdown")
            return

        df = compute_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        price = latest["Close"]
        prev_price = prev["Close"]
        pct_chg = (price - prev_price) / prev_price * 100
        rsi = latest.get("RSI", 50) or 50
        rel_vol = latest.get("RelVol", 1) or 1
        volume = latest["Volume"]
        value = price * volume
        snap = {"ticker": ticker, "price": price, "prev_price": prev_price,
                "pct_chg": pct_chg, "volume": volume, "value": value,
                "rel_vol": rel_vol, "bandar_score": latest.get("BandarScore", 0),
                "ma20": latest.get("MA20"), "ma50": latest.get("MA50")}
        broker = estimate_broker_signal(snap)
        sign = "+" if pct_chg >= 0 else ""

        caption = (
            f"📊 *{ticker}*\n"
            f"Price: *{fmt_price(price)}* ({sign}{pct_chg:.2f}%)\n"
            f"Vol: {fmt_volume(volume)} ({rel_vol:.1f}x) | RSI: {rsi:.1f}\n"
            f"Broker: {broker['bandar_label']}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏦 Broker Flow", callback_data=f"broker_{ticker}"),
             InlineKeyboardButton("⭐ Watchlist", callback_data=f"watch_add_{ticker}")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu_main")],
        ])

        buf = generate_stock_chart(ticker)
        if buf:
            await query.message.reply_photo(photo=buf, caption=caption, parse_mode="Markdown", reply_markup=kb)
            await query.delete_message()
        else:
            await query.edit_message_text(caption, parse_mode="Markdown", reply_markup=kb)

    # ── Broker flow ────────────────────────────────────────────
    elif data.startswith("broker_"):
        ticker = data.replace("broker_", "")
        from bot.bandarmology.broker_analyzer import estimate_broker_signal, format_broker_report
        snaps = get_market_snapshot([ticker])
        if not snaps:
            await query.edit_message_text(f"❌ No data for *{ticker}*.", parse_mode="Markdown")
            return
        broker_data = estimate_broker_signal(snaps[0])
        report = format_broker_report(ticker, broker_data)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Chart", callback_data=f"chart_{ticker}"),
             InlineKeyboardButton("⭐ Watchlist", callback_data=f"watch_add_{ticker}")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu_main")],
        ])
        await query.edit_message_text(report, parse_mode="Markdown", reply_markup=kb)

    # ── Heatmap ────────────────────────────────────────────────
    elif data == "menu_heatmap" or data.startswith("heatmap_"):
        sector = None if data == "menu_heatmap" else data.replace("heatmap_", "")
        if sector == "all":
            sector = None
        await query.edit_message_text("⏳ Generating heatmap...")
        from bot.heatmap.heatmap_generator import generate_heatmap
        buf = generate_heatmap(sector)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏦 Banking", callback_data="heatmap_Banking"),
             InlineKeyboardButton("💻 Technology", callback_data="heatmap_Technology")],
            [InlineKeyboardButton("⚡ Energy", callback_data="heatmap_Energy"),
             InlineKeyboardButton("🛒 Consumer", callback_data="heatmap_Consumer")],
            [InlineKeyboardButton("🏥 Healthcare", callback_data="heatmap_Healthcare"),
             InlineKeyboardButton("🏠 Property", callback_data="heatmap_Property")],
            [InlineKeyboardButton("🏭 Industrial", callback_data="heatmap_Industrial"),
             InlineKeyboardButton("🌴 Plantation", callback_data="heatmap_Plantation")],
            [InlineKeyboardButton("🔄 All Sectors", callback_data="heatmap_all"),
             InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
        ])
        label = sector if sector else "All Sectors"
        if buf:
            await query.message.reply_photo(
                photo=buf, caption=f"🔥 *IDX Heatmap — {label}*",
                parse_mode="Markdown", reply_markup=kb,
            )
            await query.delete_message()
        else:
            await query.edit_message_text("❌ Heatmap unavailable. Try again.", reply_markup=kb)

    # ── Sector rotation ────────────────────────────────────────
    elif data == "menu_sector":
        await query.edit_message_text("⏳ Analyzing sectors...")
        from bot.sector_rotation.sector_analyzer import analyze_sectors, format_sector_rotation
        result = analyze_sectors()
        text = format_sector_rotation(result)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔥 Heatmap", callback_data="menu_heatmap"),
             InlineKeyboardButton("🔄 Refresh", callback_data="menu_sector")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
        ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

    # ── Momentum ───────────────────────────────────────────────
    elif data == "menu_momentum":
        await query.edit_message_text("⏳ Scanning top momentum stocks...")
        snaps = get_market_snapshot(ALL_IDX_STOCKS[:40])
        snaps.sort(key=lambda x: x.get("pct_chg", 0), reverse=True)
        top = snaps[:10]
        lines = ["⚡ *Top Momentum Stocks*\n"]
        for i, s in enumerate(top, 1):
            t = s.get("ticker", "")
            pct = s.get("pct_chg", 0)
            rv = s.get("rel_vol", 1) or 1
            sign = "+" if pct >= 0 else ""
            lines.append(f"{i}. *{t}* {sign}{pct:.2f}% | Vol: {rv:.1f}x | {fmt_price(s.get('price'))}")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="menu_momentum"),
             InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
        ])
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)

    # ── Market breadth ─────────────────────────────────────────
    elif data == "menu_breadth":
        await query.edit_message_text("⏳ Analyzing market breadth...")
        snaps = get_market_snapshot(ALL_IDX_STOCKS[:60])
        ihsg = get_ihsg_data()
        advance = sum(1 for s in snaps if s.get("pct_chg", 0) > 0)
        decline = sum(1 for s in snaps if s.get("pct_chg", 0) < 0)
        total = len(snaps)
        ratio = advance / max(decline, 1)
        condition = "🟢 Bullish" if ratio > 1.5 else "🔴 Bearish" if ratio < 0.7 else "🟡 Mixed"
        ihsg_pct = ihsg.get("pct_chg", 0)
        ihsg_price = ihsg.get("price", 0)
        sign = "+" if ihsg_pct >= 0 else ""
        text = (
            f"📉 *Market Breadth*\n\n"
            f"*IHSG:* {ihsg_price:,.2f} ({sign}{ihsg_pct:.2f}%)\n"
            f"*Condition:* {condition}\n\n"
            f"🟢 Advance: {advance} | 🔴 Decline: {decline}\n"
            f"A/D Ratio: {ratio:.2f}\n\n"
            f"Overbought (RSI>70): {sum(1 for s in snaps if (s.get('rsi') or 0)>70)}\n"
            f"Oversold (RSI<30): {sum(1 for s in snaps if (s.get('rsi') or 50)<30)}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="menu_breadth"),
             InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
        ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

    # ── Foreign flow ───────────────────────────────────────────
    elif data == "menu_foreign":
        await query.edit_message_text("⏳ Scanning foreign flow...")
        snaps = get_market_snapshot(ALL_IDX_STOCKS[:40])
        buys = sorted([s for s in snaps if s.get("pct_chg", 0) > 0.5 and (s.get("rel_vol") or 1) > 1.5],
                      key=lambda x: x.get("pct_chg", 0), reverse=True)[:7]
        sells = [s for s in snaps if s.get("pct_chg", 0) < -0.5 and (s.get("rel_vol") or 1) > 1.5][:4]
        lines = ["💰 *Foreign Flow Tracker*\n", "*Estimated Net Foreign Buy:*\n"]
        for s in buys:
            lines.append(f"  🟢 *{s['ticker']}* +{s['pct_chg']:.2f}% | {(s.get('rel_vol') or 1):.1f}x vol")
        lines.append("\n*Estimated Net Foreign Sell:*\n")
        for s in sells:
            lines.append(f"  🔴 *{s['ticker']}* {s['pct_chg']:.2f}%")
        lines.append("\n⚠️ _Estimates only. Actual data requires paid IDX provider._")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="menu_foreign"),
             InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
        ])
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)

    # ── Watchlist ──────────────────────────────────────────────
    elif data == "menu_watchlist":
        user_id = update.effective_user.id
        wl = get_watchlist(user_id)
        if not wl:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📈 Screener", callback_data="menu_screener")],
                [InlineKeyboardButton("🔙 Menu", callback_data="menu_main")],
            ])
            await query.edit_message_text(
                "📊 *Watchlist empty.*\n\nUse `/add TICKER` to add stocks.",
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
            e = "🟢" if pct >= 0 else "🔴"
            lines.append(f"{e} *{ticker}* {fmt_price(price)} ({sign}{pct:.2f}%)")
            buttons.append(InlineKeyboardButton(f"📊 {ticker}", callback_data=f"chart_{ticker}"))
        rows = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
        rows.append([InlineKeyboardButton("🔄 Refresh", callback_data="menu_watchlist"),
                     InlineKeyboardButton("🔙 Menu", callback_data="menu_main")])
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

    # ── Watch add ──────────────────────────────────────────────
    elif data.startswith("watch_add_"):
        ticker = data.replace("watch_add_", "")
        user_id = update.effective_user.id
        added = add_to_watchlist(user_id, ticker)
        msg = f"✅ *{ticker}* added to watchlist!" if added else f"⚠️ *{ticker}* already in watchlist."
        await query.answer(msg.replace("*", ""), show_alert=True)

    # ── Settings ───────────────────────────────────────────────
    elif data == "menu_settings":
        text = (
            "⚙️ *Settings*\n\n"
            "*Bot Configuration:*\n"
            "• Data source: Yahoo Finance (IDX .JK)\n"
            "• Chart style: Dark theme\n"
            "• Screener refresh: On demand\n"
            "• Watchlist alerts: Auto\n\n"
            "*Data Note:*\n"
            "Real-time IDX broker flow requires a paid data provider (e.g., Stockbit, RTI Business).\n"
            "Current broker analysis is estimated from price/volume patterns.\n\n"
            "*Focus Brokers:* AK, BK, YP, CC, PD, XL"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_main")]])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def _run_screener_cb(query, context, screener_type: str, name: str):
    from bot.screener.screener_engine import run_screener

    results = run_screener(screener_type, max_results=8)

    if not results:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Try Again", callback_data=f"screen_{screener_type}")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu_screener")],
        ])
        await query.edit_message_text(
            f"📭 *{name} Screener*\n\nNo stocks matched the filter criteria today.\n"
            "Try again during market hours (09:00–16:00 WIB).",
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return

    # Send summary text
    lines = [f"📈 *{name} Screener Results*\n", f"Found *{len(results)}* stocks:\n"]
    for i, s in enumerate(results[:8], 1):
        ticker = s.get("ticker", "")
        price = s.get("price", 0)
        pct = s.get("pct_chg", 0)
        mom = s.get("momentum_score", 50)
        sector = s.get("sector", "")
        broker = s.get("broker_signal", "Neutral")
        sign = "+" if pct >= 0 else ""
        e = score_emoji(mom)
        lines.append(
            f"{i}. *{ticker}* {fmt_price(price)} {sign}{pct:.2f}%\n"
            f"   {e} Score: {mom:.0f} | {sector} | {broker}"
        )

    # Detail buttons for top 5
    detail_buttons = []
    for s in results[:5]:
        ticker = s["ticker"]
        detail_buttons.append(InlineKeyboardButton(f"📊 {ticker}", callback_data=f"screen_detail_{screener_type}_{ticker}"))

    rows = [detail_buttons[i:i+3] for i in range(0, len(detail_buttons), 3)]
    rows.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"screen_{screener_type}"),
                 InlineKeyboardButton("🔙 Back", callback_data="menu_screener")])

    await query.edit_message_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows)
    )

    # Send chart for top result
    if results:
        top = results[0]
        ticker = top["ticker"]
        try:
            from bot.charts.chart_generator import generate_mini_chart
            buf = generate_mini_chart(ticker)
            ai = top.get("ai_analysis", "")
            if buf:
                await query.message.reply_photo(
                    photo=buf,
                    caption=f"🥇 *{ticker}* — Top Pick\n\n{ai[:600]}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📊 Full Chart", callback_data=f"chart_{ticker}"),
                         InlineKeyboardButton("🏦 Broker", callback_data=f"broker_{ticker}")],
                        [InlineKeyboardButton("⭐ Add Watchlist", callback_data=f"watch_add_{ticker}")],
                    ]),
                )
        except Exception as e:
            logger.warning(f"Mini chart send error: {e}")


async def handle_screener_detail(query, screener_type: str, ticker: str):
    from bot.screener.screener_engine import run_screener
    from bot.charts.chart_generator import generate_mini_chart
    from bot.bandarmology.broker_analyzer import format_broker_report, estimate_broker_signal
    from bot.services.data_service import get_market_snapshot

    snaps = get_market_snapshot([ticker])
    if not snaps:
        await query.edit_message_text(f"❌ No data for *{ticker}*.", parse_mode="Markdown")
        return

    stock = snaps[0]
    broker_data = estimate_broker_signal(stock)

    from bot.services.ai_service import generate_full_analysis
    from bot.sector_rotation.sector_analyzer import analyze_sectors

    sector = next((s for s, ts in IDX_STOCKS.items() if ticker in ts), "Other")
    stock["sector"] = sector
    stock["broker_signal"] = broker_data["signal"]
    stock["foreign_flow"] = "Positive" if stock.get("pct_chg", 0) > 1 else "Neutral"

    # Momentum score inline
    pct = stock.get("pct_chg", 0)
    rel_vol = stock.get("rel_vol", 1) or 1
    mom = min(100, max(0, 50 + pct * 4 + (rel_vol - 1) * 8))
    stock["momentum_score"] = mom

    ai = generate_full_analysis(stock, screener_type)

    price = stock.get("price", 0)
    sign = "+" if pct >= 0 else ""

    text = (
        f"📌 *{ticker}* — {sector}\n"
        f"Price: *{fmt_price(price)}* ({sign}{pct:.2f}%)\n"
        f"Volume: {fmt_volume(stock.get('volume',0))} ({rel_vol:.1f}x)\n"
        f"Value: {fmt_value(stock.get('value',0))}\n"
        f"Broker: {broker_signal_emoji(broker_data['signal'])} {broker_data['bandar_label']}\n\n"
        f"{ai}"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Chart", callback_data=f"chart_{ticker}"),
         InlineKeyboardButton("🏦 Broker Flow", callback_data=f"broker_{ticker}")],
        [InlineKeyboardButton("🔥 Heatmap", callback_data="menu_heatmap"),
         InlineKeyboardButton("⭐ Watchlist", callback_data=f"watch_add_{ticker}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"screen_{screener_type}")],
    ])
    await query.edit_message_text(text[:4096], parse_mode="Markdown", reply_markup=kb)
