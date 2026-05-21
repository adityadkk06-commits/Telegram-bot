import os
import logging
import re
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from bot.handlers.command_handlers import (
    cmd_start, cmd_help, cmd_chart, cmd_screener,
    cmd_heatmap, cmd_sector, cmd_momentum, cmd_breadth,
    cmd_watchlist, cmd_add, cmd_remove, cmd_bandar, cmd_foreign,
)
from bot.handlers.callback_handlers import handle_callback, handle_screener_detail

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

IDX_TICKERS = [
    "BBCA", "BBRI", "BMRI", "BBNI", "TLKM", "ASII", "UNVR", "ADRO",
    "PTBA", "KLBF", "BSDE", "SMRA", "CTRA", "EMTK", "BUKA", "GOTO",
    "ANTM", "INCO", "MDKA", "AALI", "LSIP", "ICBP", "INDF", "MYOR",
    "GGRM", "HMSP", "JSMR", "WIKA", "PTPP", "TBIG", "TOWR",
    "BRIS", "BNGA", "BTPS", "HRUM", "BYAN", "GEMS", "MEDC",
    "PGAS", "AKRA", "AMRT", "ACES", "MAPI", "SIDO",
]


async def handle_ticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /TICKER commands like /bbca, /tlkm, etc."""
    command = update.message.text.lstrip("/").split("@")[0].upper()
    if command in IDX_TICKERS or len(command) <= 6:
        await cmd_chart(update, context, ticker=command)


async def handle_screener_detail_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    # screen_detail_{screener_type}_{ticker}
    parts = data.split("_", 3)
    if len(parts) == 4:
        screener_type = parts[2]
        ticker = parts[3]
        await handle_screener_detail(query, screener_type, ticker)


async def handle_all_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    if data.startswith("screen_detail_"):
        await handle_screener_detail_cb(update, context)
    else:
        await handle_callback(update, context)


async def watchlist_alert_job(context: ContextTypes.DEFAULT_TYPE):
    """Periodic job: send breakout alerts for all watched tickers."""
    from bot.data.watchlist import get_all_watched_tickers
    from bot.services.data_service import get_market_snapshot

    tickers = get_all_watched_tickers()
    if not tickers:
        return

    snaps = get_market_snapshot(tickers)
    alerts = [s for s in snaps if (s.get("rel_vol") or 1) > 2.5 or abs(s.get("pct_chg", 0)) > 3]

    if not alerts:
        return

    import json, os
    wl_file = os.path.join(os.path.dirname(__file__), "data", "watchlists.json")
    if not os.path.exists(wl_file):
        return

    with open(wl_file) as f:
        data = json.load(f)

    for user_id_str, user_tickers in data.items():
        user_alerts = [a for a in alerts if a["ticker"] in user_tickers]
        if not user_alerts:
            continue
        lines = ["🔔 *Watchlist Alert!*\n"]
        for s in user_alerts:
            ticker = s["ticker"]
            pct = s.get("pct_chg", 0)
            rv = s.get("rel_vol", 1) or 1
            price = s.get("price", 0)
            sign = "+" if pct >= 0 else ""
            if abs(pct) > 3:
                reason = f"🚨 Unusual price move: {sign}{pct:.2f}%"
            else:
                reason = f"⚡ Volume spike: {rv:.1f}x average"
            lines.append(f"• *{ticker}* {price:,.0f} — {reason}")

        try:
            await context.bot.send_message(
                chat_id=int(user_id_str),
                text="\n".join(lines),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Alert failed for user {user_id_str}: {e}")


async def market_open_job(context: ContextTypes.DEFAULT_TYPE):
    """Market open morning summary."""
    from bot.services.data_service import get_ihsg_data
    pass  # Extend as needed


def build_app() -> Application:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set!")

    app = Application.builder().token(token).build()

    # Core commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("menu", cmd_start))
    app.add_handler(CommandHandler("screener", cmd_screener))
    app.add_handler(CommandHandler("ara", lambda u, c: _run_screener_cmd(u, c, "ara_hunter")))
    app.add_handler(CommandHandler("bsjp", lambda u, c: _run_screener_cmd(u, c, "bsjp")))
    app.add_handler(CommandHandler("bigacc", lambda u, c: _run_screener_cmd(u, c, "big_accumulation")))
    app.add_handler(CommandHandler("heatmap", cmd_heatmap))
    app.add_handler(CommandHandler("sector", cmd_sector))
    app.add_handler(CommandHandler("momentum", cmd_momentum))
    app.add_handler(CommandHandler("breadth", cmd_breadth))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("bandar", cmd_bandar))
    app.add_handler(CommandHandler("foreign", cmd_foreign))
    app.add_handler(CommandHandler("chart", cmd_chart))

    # Dynamic ticker commands like /bbca /tlkm etc.
    ticker_pattern = re.compile(r"^/[A-Za-z]{2,6}(@\w+)?$")
    app.add_handler(MessageHandler(filters.Regex(ticker_pattern), handle_ticker_command))

    # Callback handler
    app.add_handler(CallbackQueryHandler(handle_all_callbacks))

    # Periodic jobs
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(watchlist_alert_job, interval=300, first=60)

    return app


async def _run_screener_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, screener_type: str):
    from bot.utils.constants import SCREENER_NAMES
    from bot.screener.screener_engine import run_screener

    name = SCREENER_NAMES.get(screener_type, screener_type.upper())
    msg = await update.message.reply_text(f"⏳ Running *{name}* screener...", parse_mode="Markdown")

    results = run_screener(screener_type, max_results=8)

    if not results:
        from bot.utils.constants import SCREENER_NAMES
        kb_back = __import__("telegram", fromlist=["InlineKeyboardMarkup", "InlineKeyboardButton"])
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="menu_screener")],
        ])
        await msg.edit_text(
            f"📭 *{name}* — No matches today.\nTry during market hours (09:00–16:00 WIB).",
            parse_mode="Markdown", reply_markup=kb,
        )
        return

    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from bot.utils.formatters import fmt_price, score_emoji

    lines = [f"📈 *{name} Results*\n", f"Found *{len(results)}* stocks:\n"]
    for i, s in enumerate(results[:8], 1):
        ticker = s.get("ticker", "")
        price = s.get("price", 0)
        pct = s.get("pct_chg", 0)
        mom = s.get("momentum_score", 50)
        sector = s.get("sector", "")
        broker = s.get("broker_signal", "")
        sign = "+" if pct >= 0 else ""
        lines.append(
            f"{i}. *{ticker}* {fmt_price(price)} {sign}{pct:.2f}%\n"
            f"   {score_emoji(mom)} Score:{mom:.0f} | {sector} | {broker}"
        )

    detail_buttons = [
        InlineKeyboardButton(f"📊 {s['ticker']}", callback_data=f"screen_detail_{screener_type}_{s['ticker']}")
        for s in results[:5]
    ]
    rows = [detail_buttons[i:i+3] for i in range(0, len(detail_buttons), 3)]
    rows.append([InlineKeyboardButton("🔙 Menu", callback_data="menu_screener")])

    await msg.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

    # Send top pick chart
    if results:
        ticker = results[0]["ticker"]
        try:
            from bot.charts.chart_generator import generate_mini_chart
            buf = generate_mini_chart(ticker)
            ai = results[0].get("ai_analysis", "")
            if buf:
                await update.message.reply_photo(
                    photo=buf,
                    caption=f"🥇 *Top Pick: {ticker}*\n\n{ai[:600]}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📊 Full Chart", callback_data=f"chart_{ticker}"),
                         InlineKeyboardButton("🏦 Broker", callback_data=f"broker_{ticker}")],
                        [InlineKeyboardButton("⭐ Watchlist", callback_data=f"watch_add_{ticker}")],
                    ]),
                )
        except Exception as e:
            logger.warning(f"Top pick chart error: {e}")


def main():
    logger.info("Starting IDX Stock Screener Bot...")
    app = build_app()
    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
