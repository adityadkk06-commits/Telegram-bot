import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils.constants import IDX_STOCKS, ALL_IDX_STOCKS, SCREENER_NAMES
from bot.utils.formatters import (
    fmt_price, fmt_volume, fmt_value,
    score_emoji, broker_signal_emoji,
)
from bot.utils.helpers import safe_edit, safe_send_photo
from bot.data.watchlist import add_to_watchlist, get_watchlist
from bot.services.data_service import get_market_snapshot, get_ihsg_data

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Central dispatcher
# ─────────────────────────────────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data or ""

    try:
        if data == "menu_main":
            await _cb_main_menu(query)
        elif data == "menu_screener":
            await _cb_screener_menu(query)
        elif data.startswith("screen_detail_"):
            parts = data.split("_", 3)
            if len(parts) == 4:
                await _cb_screener_detail(query, parts[2], parts[3])
        elif data.startswith("screen_"):
            stype = data.replace("screen_", "", 1)
            name  = SCREENER_NAMES.get(stype, stype.upper())
            await safe_edit(query, f"⏳ Running *{name}* screener…")
            await _cb_run_screener(query, stype, name)
        elif data.startswith("chart_"):
            ticker = data.replace("chart_", "", 1)
            await safe_edit(query, f"⏳ Loading chart for *{ticker}*…")
            await _cb_chart(query, ticker)
        elif data.startswith("broker_"):
            ticker = data.replace("broker_", "", 1)
            await safe_edit(query, f"⏳ Analyzing broker flow for *{ticker}*…")
            await _cb_broker(query, ticker)
        elif data == "menu_heatmap" or data.startswith("heatmap_"):
            sector = None if data == "menu_heatmap" else data.replace("heatmap_", "", 1)
            if sector == "all":
                sector = None
            await safe_edit(query, "⏳ Generating heatmap…")
            await _cb_heatmap(query, sector)
        elif data == "menu_sector":
            await safe_edit(query, "⏳ Analyzing sectors…")
            await _cb_sector(query)
        elif data == "menu_momentum":
            await safe_edit(query, "⏳ Scanning momentum…")
            await _cb_momentum(query)
        elif data == "menu_breadth":
            await safe_edit(query, "⏳ Analyzing breadth…")
            await _cb_breadth(query)
        elif data == "menu_foreign":
            await safe_edit(query, "⏳ Scanning foreign flow…")
            await _cb_foreign(query)
        elif data == "menu_bandar":
            await _cb_bandar_menu(query)
        elif data == "menu_watchlist":
            await _cb_watchlist(query, update.effective_user.id)
        elif data.startswith("watch_add_"):
            ticker = data.replace("watch_add_", "", 1)
            added  = add_to_watchlist(update.effective_user.id, ticker)
            msg    = f"✅ {ticker} added to watchlist!" if added else f"⚠️ {ticker} already in watchlist."
            await query.answer(msg, show_alert=True)
        elif data == "menu_settings":
            await _cb_settings(query)
    except Exception as e:
        logger.error(f"Callback error [{data}]: {e}", exc_info=True)
        try:
            await safe_edit(query, "❌ Something went wrong. Please try again.")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  Screener result formatter (shared by cb and cmd handlers)
# ─────────────────────────────────────────────────────────────────────────────

def format_screener_results(results: dict, name: str, screener_type: str) -> tuple[str, list]:
    """Returns (text, inline_button_rows)."""
    passes = results.get("pass", [])
    nears  = results.get("near", [])

    if not passes and not nears:
        return None, None

    lines = [f"📈 *{name}*\n"]

    # ── Full matches ──────────────────────────────────────────
    if passes:
        lines.append(f"✅ *FULL MATCH — {len(passes)} stock(s):*\n")
        for i, s in enumerate(passes, 1):
            ticker = s.get("ticker", "")
            pct    = s.get("pct_chg", 0)
            mom    = s.get("momentum_score", 50)
            sector = s.get("sector", "")
            broker = s.get("broker_signal", "")
            fpct   = s.get("filter_pct", 100)
            sign   = "+" if pct >= 0 else ""
            lines.append(
                f"{i}. *{ticker}* {fmt_price(s.get('price'))} {sign}{pct:.2f}%\n"
                f"   {score_emoji(mom)} Score:{mom:.0f} | {fpct:.0f}% match | {sector}"
            )
    else:
        lines.append("✅ *No full matches today.*")

    # ── Near misses ───────────────────────────────────────────
    if nears:
        lines.append(f"\n🔶 *NEAR MISS — {len(nears)} stock(s) almost qualified:*\n")
        for s in nears:
            ticker  = s.get("ticker", "")
            pct     = s.get("pct_chg", 0)
            fpct    = s.get("filter_pct", 0)
            sign    = "+" if pct >= 0 else ""
            near_d  = s.get("near_summary", "")
            lines.append(f"🔸 *{ticker}* {fmt_price(s.get('price'))} {sign}{pct:.2f}% — *{fpct:.0f}%* match")
            if near_d:
                for ln in near_d.split("\n")[:2]:
                    lines.append(f"   {ln}")

    # ── Buttons: detail for top 5 (pass first, then near) ────
    top_stocks = (passes + nears)[:5]
    detail_btns = [
        InlineKeyboardButton(
            f"{'✅' if s['status']=='pass' else '🔶'} {s['ticker']}",
            callback_data=f"screen_detail_{screener_type}_{s['ticker']}"
        )
        for s in top_stocks
    ]
    rows = [detail_btns[i:i+3] for i in range(0, len(detail_btns), 3)]
    rows.append([
        InlineKeyboardButton("🔄 Refresh", callback_data=f"screen_{screener_type}"),
        InlineKeyboardButton("🏠 Menu",    callback_data="menu_screener"),
    ])

    return "\n".join(lines), rows


# ─────────────────────────────────────────────────────────────────────────────
#  Individual handlers
# ─────────────────────────────────────────────────────────────────────────────

async def _cb_main_menu(query):
    from bot.handlers.command_handlers import MAIN_MENU_KB
    ihsg  = get_ihsg_data()
    price = ihsg.get("price", 0)
    pct   = ihsg.get("pct_chg", 0)
    sign  = "+" if pct >= 0 else ""
    emoji = "🟢" if pct >= 0 else "🔴"
    await safe_edit(
        query,
        f"🇮🇩 *IDX Stock Screener Bot*\n\n"
        f"*IHSG:* {price:,.2f} {emoji} {sign}{pct:.2f}%\n\n"
        f"Choose from the menu below:",
        reply_markup=MAIN_MENU_KB,
    )


async def _cb_screener_menu(query):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 ARA Hunter",        callback_data="screen_ara_hunter")],
        [InlineKeyboardButton("📈 BSJP",              callback_data="screen_bsjp")],
        [InlineKeyboardButton("🏦 Big Accumulation",  callback_data="screen_big_accumulation")],
        [InlineKeyboardButton("⚡ Scalper Pro",        callback_data="screen_scalper_pro")],
        [InlineKeyboardButton("🏠 Main Menu",          callback_data="menu_main")],
    ])
    await safe_edit(
        query,
        "📈 *Stock Screener*\n\n"
        "Shows ✅ *Full Match* AND 🔶 *Near Miss* stocks.\n\n"
        "🎯 *ARA Hunter* — Near-ARA stocks\n"
        "📈 *BSJP* — Breakout + foreign buy\n"
        "🏦 *Big Accumulation* — Smart money loading\n"
        "⚡ *Scalper Pro* — Intraday setups",
        reply_markup=kb,
    )


async def _cb_run_screener(query, screener_type: str, name: str):
    from bot.screener.screener_engine import run_screener

    results = run_screener(screener_type)
    text, rows = format_screener_results(results, name, screener_type)

    if text is None:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Try Again", callback_data=f"screen_{screener_type}")],
            [InlineKeyboardButton("🏠 Back",      callback_data="menu_screener")],
        ])
        await safe_edit(
            query,
            f"📭 *{name}*\n\nNo stocks found today.\n"
            "Try during market hours: 09:00–16:00 WIB.",
            reply_markup=kb,
        )
        return

    await safe_edit(query, text[:4096], reply_markup=InlineKeyboardMarkup(rows))

    # Send mini chart for top pick (pass first, else near)
    top_list = results.get("pass") or results.get("near") or []
    if top_list:
        top    = top_list[0]
        ticker = top["ticker"]
        status = top.get("status", "pass")
        try:
            from bot.charts.chart_generator import generate_mini_chart
            buf = generate_mini_chart(ticker)
            ai  = top.get("ai_analysis", "")
            if buf:
                label = "🥇 Top Full Match" if status == "pass" else "🔶 Top Near Miss"
                kb2 = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 Full Chart",    callback_data=f"chart_{ticker}"),
                     InlineKeyboardButton("🏦 Broker",        callback_data=f"broker_{ticker}")],
                    [InlineKeyboardButton("⭐ Add Watchlist", callback_data=f"watch_add_{ticker}"),
                     InlineKeyboardButton("🏠 Menu",          callback_data="menu_main")],
                ])
                await query.message.reply_photo(
                    photo=buf,
                    caption=f"{label}: *{ticker}*\n\n{ai[:900]}",
                    parse_mode="Markdown",
                    reply_markup=kb2,
                )
        except Exception as e:
            logger.warning(f"Mini chart error: {e}")


async def _cb_screener_detail(query, screener_type: str, ticker: str):
    from bot.bandarmology.broker_analyzer import estimate_broker_signal
    from bot.services.ai_service import generate_full_analysis
    from bot.screener.screener_engine import _get_score_fn

    snaps = get_market_snapshot([ticker])
    if not snaps:
        await safe_edit(query, f"❌ No data for *{ticker}*.")
        return

    stock = snaps[0]

    # Run filter to get near summary
    score_fn = _get_score_fn(screener_type)
    filter_result = score_fn(stock) if score_fn else None
    near_d = filter_result.near_summary(4) if filter_result else ""
    filter_pct = filter_result.pct if filter_result else 0
    status = filter_result.status if filter_result else "near"

    broker_data = estimate_broker_signal(stock)
    sector      = next((s for s, t in IDX_STOCKS.items() if ticker in t), "Other")
    pct         = stock.get("pct_chg", 0)
    rel_vol     = stock.get("rel_vol", 1) or 1
    mom         = min(100, max(0, 50 + pct * 4 + (rel_vol - 1) * 8))

    stock["sector"]         = sector
    stock["broker_signal"]  = broker_data["signal"]
    stock["foreign_flow"]   = "Positive" if pct > 1 else "Neutral"
    stock["momentum_score"] = mom

    ai   = generate_full_analysis(stock, screener_type)
    sign = "+" if pct >= 0 else ""
    tag  = "✅ Full Match" if status == "pass" else f"🔶 Near Miss ({filter_pct:.0f}%)"

    text = (
        f"📌 *{ticker}* — {sector} | {tag}\n"
        f"Price: *{fmt_price(stock.get('price'))}* ({sign}{pct:.2f}%)\n"
        f"Volume: {fmt_volume(stock.get('volume',0))} ({rel_vol:.1f}x)\n"
        f"Value: {fmt_value(stock.get('value',0))}\n"
        f"Broker: {broker_signal_emoji(broker_data['signal'])} {broker_data['bandar_label']}\n"
    )
    if near_d and status == "near":
        text += f"\n*What's missing:*\n{near_d}\n"

    text += f"\n{ai}"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Chart",          callback_data=f"chart_{ticker}"),
         InlineKeyboardButton("🏦 Broker Flow",    callback_data=f"broker_{ticker}")],
        [InlineKeyboardButton("⭐ Add Watchlist",  callback_data=f"watch_add_{ticker}"),
         InlineKeyboardButton("🔥 Heatmap",        callback_data="menu_heatmap")],
        [InlineKeyboardButton("🔙 Back",           callback_data=f"screen_{screener_type}"),
         InlineKeyboardButton("🏠 Menu",           callback_data="menu_main")],
    ])
    await safe_edit(query, text[:4096], reply_markup=kb)


async def _cb_chart(query, ticker: str):
    from bot.services.data_service import get_stock_data, compute_indicators
    from bot.bandarmology.broker_analyzer import estimate_broker_signal
    from bot.charts.chart_generator import generate_stock_chart

    df = get_stock_data(ticker, period="3mo")
    if df is None or len(df) < 5:
        await safe_edit(query, f"❌ No data for *{ticker}*.")
        return

    df       = compute_indicators(df)
    latest   = df.iloc[-1]
    prev     = df.iloc[-2] if len(df) > 1 else latest
    price    = latest["Close"]
    pct_chg  = (price - prev["Close"]) / prev["Close"] * 100
    rsi      = latest.get("RSI") or 0
    macd     = latest.get("MACD")
    macd_sig = latest.get("MACD_Signal")
    ma5      = latest.get("MA5")
    ma20     = latest.get("MA20")
    ma50     = latest.get("MA50")
    rel_vol  = latest.get("RelVol", 1) or 1
    volume   = latest["Volume"]
    value    = price * volume
    sector   = next((s for s, t in IDX_STOCKS.items() if ticker in t), "Other")

    snap = {
        "ticker": ticker, "price": price, "prev_price": prev["Close"],
        "pct_chg": pct_chg, "volume": volume, "value": value,
        "rel_vol": rel_vol, "bandar_score": latest.get("BandarScore", 0),
        "ma20": ma20, "ma50": ma50,
        "high": latest["High"], "low": latest["Low"],
        "vwap": latest.get("VWAP"),
    }
    broker = estimate_broker_signal(snap)
    sign   = "+" if pct_chg >= 0 else ""
    trend  = "🟢" if pct_chg >= 0 else "🔴"
    rsi_n  = " ⚠️ OB" if rsi > 70 else " ⚠️ OS" if rsi < 30 else ""
    macd_b = macd is not None and macd_sig is not None and macd > macd_sig

    caption = (
        f"📊 *{ticker}* — {sector}\n\n"
        f"💰 Price: *{fmt_price(price)}* {trend} {sign}{pct_chg:.2f}%\n"
        f"📦 Vol: {fmt_volume(volume)} ({rel_vol:.1f}x avg)\n"
        f"💵 Value: {fmt_value(value)}\n\n"
        f"*Technical:*\n"
        f"  MA5:{fmt_price(ma5)} | MA20:{fmt_price(ma20)} | MA50:{fmt_price(ma50)}\n"
        f"  RSI:{rsi:.1f}{rsi_n} | MACD:{'🟢 Bull' if macd_b else '🔴 Bear'}\n\n"
        f"🏦 Broker: *{broker['bandar_label']}*"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏦 Broker Flow",   callback_data=f"broker_{ticker}"),
         InlineKeyboardButton("⭐ Add Watchlist", callback_data=f"watch_add_{ticker}")],
        [InlineKeyboardButton("🔥 Heatmap",       callback_data="menu_heatmap"),
         InlineKeyboardButton("🏠 Menu",          callback_data="menu_main")],
    ])

    buf = generate_stock_chart(ticker)
    if buf:
        await safe_send_photo(query, buf, caption, reply_markup=kb)
    else:
        await safe_edit(query, caption, reply_markup=kb)


async def _cb_broker(query, ticker: str):
    from bot.bandarmology.broker_analyzer import estimate_broker_signal, format_broker_report
    snaps = get_market_snapshot([ticker])
    if not snaps:
        await safe_edit(query, f"❌ No data for *{ticker}*.")
        return
    broker_data = estimate_broker_signal(snaps[0])
    report      = format_broker_report(ticker, broker_data)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Chart",          callback_data=f"chart_{ticker}"),
         InlineKeyboardButton("⭐ Add Watchlist",  callback_data=f"watch_add_{ticker}")],
        [InlineKeyboardButton("🔄 Refresh",        callback_data=f"broker_{ticker}"),
         InlineKeyboardButton("🏠 Menu",           callback_data="menu_main")],
    ])
    await safe_edit(query, report, reply_markup=kb)


async def _cb_heatmap(query, sector):
    from bot.heatmap.heatmap_generator import generate_heatmap
    buf = generate_heatmap(sector)
    kb  = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏦 Banking",     callback_data="heatmap_Banking"),
         InlineKeyboardButton("💻 Tech",        callback_data="heatmap_Technology")],
        [InlineKeyboardButton("⚡ Energy",      callback_data="heatmap_Energy"),
         InlineKeyboardButton("🛒 Consumer",    callback_data="heatmap_Consumer")],
        [InlineKeyboardButton("🏥 Healthcare",  callback_data="heatmap_Healthcare"),
         InlineKeyboardButton("🏠 Property",    callback_data="heatmap_Property")],
        [InlineKeyboardButton("🏭 Industrial",  callback_data="heatmap_Industrial"),
         InlineKeyboardButton("🌴 Plantation",  callback_data="heatmap_Plantation")],
        [InlineKeyboardButton("🔄 All Sectors", callback_data="heatmap_all"),
         InlineKeyboardButton("🏠 Menu",        callback_data="menu_main")],
    ])
    label = sector if sector else "All Sectors"
    if buf:
        await safe_send_photo(query, buf, f"🔥 *IDX Heatmap — {label}*\n\nTap a sector to filter:", reply_markup=kb)
    else:
        await safe_edit(query, "❌ Heatmap unavailable. Try again.", reply_markup=kb)


async def _cb_sector(query):
    from bot.sector_rotation.sector_analyzer import analyze_sectors, format_sector_rotation
    data = analyze_sectors()
    text = format_sector_rotation(data)
    kb   = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Heatmap",  callback_data="menu_heatmap"),
         InlineKeyboardButton("🏦 Bandar",   callback_data="menu_bandar")],
        [InlineKeyboardButton("🔄 Refresh",  callback_data="menu_sector"),
         InlineKeyboardButton("🏠 Menu",     callback_data="menu_main")],
    ])
    await safe_edit(query, text, reply_markup=kb)


async def _cb_momentum(query):
    snaps = get_market_snapshot(ALL_IDX_STOCKS[:50])
    snaps.sort(key=lambda x: x.get("pct_chg", 0), reverse=True)
    lines = ["⚡ *Top Momentum Stocks*\n"]
    for i, s in enumerate(snaps[:10], 1):
        t    = s.get("ticker", "")
        pct  = s.get("pct_chg", 0)
        rv   = s.get("rel_vol", 1) or 1
        sign = "+" if pct >= 0 else ""
        lines.append(f"{i}. *{t}* {sign}{pct:.2f}% | Vol:{rv:.1f}x | {fmt_price(s.get('price'))}")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="menu_momentum"),
         InlineKeyboardButton("🏠 Menu",    callback_data="menu_main")],
    ])
    await safe_edit(query, "\n".join(lines), reply_markup=kb)


async def _cb_breadth(query):
    snaps = get_market_snapshot(ALL_IDX_STOCKS[:60])
    ihsg  = get_ihsg_data()
    adv   = sum(1 for s in snaps if s.get("pct_chg", 0) > 0)
    dec   = sum(1 for s in snaps if s.get("pct_chg", 0) < 0)
    total = len(snaps)
    ratio = adv / max(dec, 1)
    cond  = "🟢 Bullish" if ratio > 1.5 else "🔴 Bearish" if ratio < 0.7 else "🟡 Mixed"
    pct   = ihsg.get("pct_chg", 0)
    sign  = "+" if pct >= 0 else ""
    text  = (
        f"📉 *Market Breadth*\n\n"
        f"*IHSG:* {ihsg.get('price',0):,.2f} ({sign}{pct:.2f}%)\n"
        f"*Condition:* {cond}\n\n"
        f"🟢 Advance: {adv} ({adv/total*100:.0f}%)\n"
        f"🔴 Decline: {dec} ({dec/total*100:.0f}%)\n"
        f"⚪ Unchanged: {total-adv-dec}\n"
        f"📊 A/D Ratio: {ratio:.2f}\n\n"
        f"High-Vol Gainers: {sum(1 for s in snaps if s.get('pct_chg',0)>0 and (s.get('rel_vol') or 1)>1.5)}\n"
        f"High-Vol Losers:  {sum(1 for s in snaps if s.get('pct_chg',0)<0 and (s.get('rel_vol') or 1)>1.5)}\n\n"
        f"Overbought RSI>70: {sum(1 for s in snaps if (s.get('rsi') or 0)>70)}\n"
        f"Oversold  RSI<30:  {sum(1 for s in snaps if (s.get('rsi') or 50)<30)}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="menu_breadth"),
         InlineKeyboardButton("🏠 Menu",    callback_data="menu_main")],
    ])
    await safe_edit(query, text, reply_markup=kb)


async def _cb_foreign(query):
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
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="menu_foreign"),
         InlineKeyboardButton("🏠 Menu",    callback_data="menu_main")],
    ])
    await safe_edit(query, "\n".join(lines), reply_markup=kb)


async def _cb_bandar_menu(query):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏦 BBCA", callback_data="broker_BBCA"),
         InlineKeyboardButton("🏦 BMRI", callback_data="broker_BMRI"),
         InlineKeyboardButton("🏦 BBRI", callback_data="broker_BBRI")],
        [InlineKeyboardButton("🏦 TLKM", callback_data="broker_TLKM"),
         InlineKeyboardButton("🏦 ADRO", callback_data="broker_ADRO"),
         InlineKeyboardButton("🏦 ASII", callback_data="broker_ASII")],
        [InlineKeyboardButton("🏦 ANTM", callback_data="broker_ANTM"),
         InlineKeyboardButton("🏦 MDKA", callback_data="broker_MDKA"),
         InlineKeyboardButton("🏦 PTBA", callback_data="broker_PTBA")],
        [InlineKeyboardButton("🏠 Menu", callback_data="menu_main")],
    ])
    await safe_edit(
        query,
        "🏦 *Bandar Detector*\n\n"
        "Tap a stock or type `/bandar TICKER`\n\n"
        "Analyzes: AK · BK · YP · CC · PD · XL broker flow\n"
        "Focus: accumulation vs distribution patterns",
        reply_markup=kb,
    )


async def _cb_watchlist(query, user_id: int):
    wl = get_watchlist(user_id)
    if not wl:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Screener", callback_data="menu_screener")],
            [InlineKeyboardButton("🏠 Menu",     callback_data="menu_main")],
        ])
        await safe_edit(query, "📊 *Watchlist empty.*\n\nAdd with `/add TICKER`", reply_markup=kb)
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
    await safe_edit(query, "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))


async def _cb_settings(query):
    text = (
        "⚙️ *Settings*\n\n"
        "*Data:* Yahoo Finance (.JK)\n"
        "*Charts:* Dark theme, mplfinance\n"
        "*Alerts:* Watchlist every 5 min\n"
        "*Broadcasts:* Market open (09:05) + close (16:05) WIB\n"
        "*Focus Brokers:* AK · BK · YP · CC · PD · XL\n\n"
        "*Screeners:*\n"
        "• 🎯 ARA Hunter — near-ARA stocks\n"
        "• 📈 BSJP — breakout momentum\n"
        "• 🏦 Big Accumulation — smart money\n"
        "• ⚡ Scalper Pro — intraday setups\n\n"
        "All screeners show ✅ Full Match + 🔶 Near Miss.\n\n"
        "⚠️ Real IDX broker flow requires paid data provider."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Back", callback_data="menu_main")]])
    await safe_edit(query, text, reply_markup=kb)
