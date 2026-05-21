import os
import re
import logging
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
    cmd_start, cmd_menu, cmd_help, cmd_chart, cmd_screener,
    cmd_heatmap, cmd_sector, cmd_momentum, cmd_breadth,
    cmd_watchlist, cmd_add, cmd_remove, cmd_bandar, cmd_foreign,
    BOTTOM_KB,
)
from bot.utils.constants import (
    ALL_IDX_STOCKS,
    BTN_SCREENER, BTN_HEATMAP, BTN_SECTOR, BTN_BANDAR,
    BTN_WATCHLIST, BTN_MOMENTUM, BTN_FOREIGN, BTN_BREADTH, BTN_MENU,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# All valid IDX tickers for dynamic /TICKER commands
KNOWN_TICKERS = set(ALL_IDX_STOCKS)


# ─────────────────────────────────────────────────────────────────────────────
#  Dynamic /TICKER handler  (e.g.  /bbca  /tlkm  /bmri)
# ─────────────────────────────────────────────────────────────────────────────

async def handle_ticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw     = update.message.text or ""
    command = raw.lstrip("/").split("@")[0].upper().strip()
    # Accept any 2-6 letter ticker that is either known or looks like an IDX code
    if command in KNOWN_TICKERS or (2 <= len(command) <= 6 and command.isalpha()):
        await cmd_chart(update, context, ticker=command)


# ─────────────────────────────────────────────────────────────────────────────
#  Scalper Pro command
# ─────────────────────────────────────────────────────────────────────────────

async def cmd_scalp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_screener_cmd(update, context, "scalper_pro")


# ─────────────────────────────────────────────────────────────────────────────
#  Shortcut commands  /ara  /bsjp  /bigacc
# ─────────────────────────────────────────────────────────────────────────────

async def cmd_ara(update, context):
    await _run_screener_cmd(update, context, "ara_hunter")

async def cmd_bsjp_cmd(update, context):
    await _run_screener_cmd(update, context, "bsjp")

async def cmd_bigacc(update, context):
    await _run_screener_cmd(update, context, "big_accumulation")


async def _run_screener_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, screener_type: str):
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from bot.screener.screener_engine import run_screener
    from bot.utils.constants import SCREENER_NAMES
    from bot.utils.formatters import fmt_price, score_emoji
    from bot.charts.chart_generator import generate_mini_chart

    name = SCREENER_NAMES.get(screener_type, screener_type.upper())
    msg  = await update.message.reply_text(
        f"⏳ Running *{name}* screener…", parse_mode="Markdown"
    )

    results = run_screener(screener_type, max_results=8)

    if not results:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Screener Menu", callback_data="menu_screener")],
            [InlineKeyboardButton("🏠 Menu",          callback_data="menu_main")],
        ])
        await msg.edit_text(
            f"📭 *{name}*\n\nNo matches today.\n"
            "Try during market hours: 09:00–16:00 WIB.",
            parse_mode="Markdown", reply_markup=kb,
        )
        return

    lines = [f"📈 *{name}*\n", f"Found *{len(results)}* stocks:\n"]
    for i, s in enumerate(results[:8], 1):
        ticker = s.get("ticker", "")
        pct    = s.get("pct_chg", 0)
        mom    = s.get("momentum_score", 50)
        sector = s.get("sector", "")
        broker = s.get("broker_signal", "")
        sign   = "+" if pct >= 0 else ""
        lines.append(
            f"{i}. *{ticker}* {fmt_price(s.get('price'))} {sign}{pct:.2f}%\n"
            f"   {score_emoji(mom)} Score:{mom:.0f} | {sector} | {broker}"
        )

    detail_btns = [
        InlineKeyboardButton(
            f"📊 {s['ticker']}",
            callback_data=f"screen_detail_{screener_type}_{s['ticker']}"
        )
        for s in results[:5]
    ]
    rows = [detail_btns[i:i+3] for i in range(0, len(detail_btns), 3)]
    rows.append([
        InlineKeyboardButton("🔄 Refresh", callback_data=f"screen_{screener_type}"),
        InlineKeyboardButton("🏠 Menu",    callback_data="menu_main"),
    ])
    await msg.edit_text(
        "\n".join(lines), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )

    # Send top pick mini-chart
    top    = results[0]
    ticker = top["ticker"]
    try:
        buf = generate_mini_chart(ticker)
        ai  = top.get("ai_analysis", "")
        if buf:
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            kb2 = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Full Chart",    callback_data=f"chart_{ticker}"),
                 InlineKeyboardButton("🏦 Broker Flow",   callback_data=f"broker_{ticker}")],
                [InlineKeyboardButton("⭐ Add Watchlist", callback_data=f"watch_add_{ticker}"),
                 InlineKeyboardButton("🏠 Menu",          callback_data="menu_main")],
            ])
            await update.message.reply_photo(
                photo=buf,
                caption=f"🥇 *Top Pick: {ticker}*\n\n{ai[:900]}",
                parse_mode="Markdown",
                reply_markup=kb2,
            )
    except Exception as e:
        logger.warning(f"Top-pick chart error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  Persistent bottom-keyboard text handler
# ─────────────────────────────────────────────────────────────────────────────

async def handle_kb_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text == BTN_SCREENER:
        await cmd_screener(update, context)
    elif text == BTN_HEATMAP:
        await cmd_heatmap(update, context)
    elif text == BTN_SECTOR:
        await cmd_sector(update, context)
    elif text == BTN_BANDAR:
        await cmd_bandar(update, context)
    elif text == BTN_WATCHLIST:
        await cmd_watchlist(update, context)
    elif text == BTN_MOMENTUM:
        await cmd_momentum(update, context)
    elif text == BTN_FOREIGN:
        await cmd_foreign(update, context)
    elif text == BTN_BREADTH:
        await cmd_breadth(update, context)
    elif text == BTN_MENU:
        await cmd_menu(update, context)


# ─────────────────────────────────────────────────────────────────────────────
#  Global error handler
# ─────────────────────────────────────────────────────────────────────────────

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ An unexpected error occurred. Please try again.",
                reply_markup=BOTTOM_KB,
            )
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  Watchlist alert job
# ─────────────────────────────────────────────────────────────────────────────

async def watchlist_alert_job(context: ContextTypes.DEFAULT_TYPE):
    from bot.data.watchlist import get_all_watched_tickers
    from bot.services.data_service import get_market_snapshot
    import json

    tickers = get_all_watched_tickers()
    if not tickers:
        return

    snaps  = get_market_snapshot(tickers)
    alerts = [
        s for s in snaps
        if (s.get("rel_vol") or 1) > 2.5 or abs(s.get("pct_chg", 0)) > 3
    ]
    if not alerts:
        return

    wl_file = os.path.join(os.path.dirname(__file__), "data", "watchlists.json")
    if not os.path.exists(wl_file):
        return

    with open(wl_file) as f:
        data = json.load(f)

    for uid_str, user_tickers in data.items():
        user_alerts = [a for a in alerts if a["ticker"] in user_tickers]
        if not user_alerts:
            continue
        lines = ["🔔 *Watchlist Alert!*\n"]
        for s in user_alerts:
            ticker = s["ticker"]
            pct    = s.get("pct_chg", 0)
            rv     = s.get("rel_vol", 1) or 1
            price  = s.get("price", 0)
            sign   = "+" if pct >= 0 else ""
            reason = (
                f"🚨 Price move: {sign}{pct:.2f}%"
                if abs(pct) > 3
                else f"⚡ Volume: {rv:.1f}x avg"
            )
            lines.append(f"• *{ticker}* {price:,.0f} — {reason}")
        try:
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"📊 {a['ticker']}", callback_data=f"chart_{a['ticker']}")
                 for a in user_alerts[:3]],
            ])
            await context.bot.send_message(
                chat_id=int(uid_str),
                text="\n".join(lines),
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception as e:
            logger.warning(f"Alert failed for {uid_str}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  Build + run
# ─────────────────────────────────────────────────────────────────────────────

def build_app() -> Application:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set!")

    app = Application.builder().token(token).build()

    # ── Standard commands ─────────────────────────────────────
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("menu",      cmd_menu))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("screener",  cmd_screener))
    app.add_handler(CommandHandler("heatmap",   cmd_heatmap))
    app.add_handler(CommandHandler("sector",    cmd_sector))
    app.add_handler(CommandHandler("momentum",  cmd_momentum))
    app.add_handler(CommandHandler("breadth",   cmd_breadth))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("add",       cmd_add))
    app.add_handler(CommandHandler("remove",    cmd_remove))
    app.add_handler(CommandHandler("bandar",    cmd_bandar))
    app.add_handler(CommandHandler("foreign",   cmd_foreign))
    app.add_handler(CommandHandler("chart",     cmd_chart))

    # ── Screener shortcut commands ─────────────────────────────
    app.add_handler(CommandHandler("ara",    cmd_ara))
    app.add_handler(CommandHandler("bsjp",   cmd_bsjp_cmd))
    app.add_handler(CommandHandler("bigacc", cmd_bigacc))
    app.add_handler(CommandHandler("scalp",  cmd_scalp))

    # ── Bottom keyboard text buttons ──────────────────────────
    kb_labels = [
        BTN_SCREENER, BTN_HEATMAP, BTN_SECTOR, BTN_BANDAR,
        BTN_WATCHLIST, BTN_MOMENTUM, BTN_FOREIGN, BTN_BREADTH, BTN_MENU,
    ]
    kb_pattern = "^(" + "|".join(re.escape(l) for l in kb_labels) + ")$"
    app.add_handler(MessageHandler(filters.Regex(kb_pattern), handle_kb_text))

    # ── Dynamic /TICKER commands ───────────────────────────────
    ticker_pattern = re.compile(r"^/[A-Za-z]{2,6}(@\w+)?$")
    app.add_handler(MessageHandler(filters.Regex(ticker_pattern), handle_ticker_command))

    # ── Inline keyboard callbacks ──────────────────────────────
    from bot.handlers.callback_handlers import handle_callback
    app.add_handler(CallbackQueryHandler(handle_callback))

    # ── Periodic jobs ──────────────────────────────────────────
    if app.job_queue:
        app.job_queue.run_repeating(watchlist_alert_job, interval=300, first=60)

    # ── Global error handler ───────────────────────────────────
    app.add_error_handler(global_error_handler)

    return app


def main():
    logger.info("🇮🇩 Starting IDX Stock Screener Bot…")
    app = build_app()
    logger.info("✅ Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
