import os
import re
import json
import logging
from datetime import time as dt_time
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from bot.handlers.command_handlers import (
    cmd_start, cmd_menu, cmd_help, cmd_chart, cmd_screener,
    cmd_heatmap, cmd_sector, cmd_momentum, cmd_breadth,
    cmd_watchlist, cmd_add, cmd_remove, cmd_bandar, cmd_foreign,
    cmd_alert,
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

WIB = pytz.timezone("Asia/Jakarta")
KNOWN_TICKERS = set(ALL_IDX_STOCKS)

# File for registered users (anyone who /start-ed or interacted)
USERS_FILE = os.path.join(os.path.dirname(__file__), "data", "users.json")
DATA_DIR   = os.path.join(os.path.dirname(__file__), "data")


# ─────────────────────────────────────────────────────────────────────────────
#  User registry  (persistent across restarts)
# ─────────────────────────────────────────────────────────────────────────────

def _load_users() -> set:
    if not os.path.exists(USERS_FILE):
        return set()
    try:
        with open(USERS_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_users(users: set):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)


def _register_user(user_id: int):
    """Add user to persistent registry. No-op if already registered."""
    if not user_id:
        return
    users = _load_users()
    if user_id not in users:
        users.add(user_id)
        _save_users(users)
        logger.info(f"Registered new user: {user_id} (total: {len(users)})")


def _seed_users_from_all_sources():
    """
    At startup: recover all known user IDs from watchlists.json and
    price_alerts.json so that users.json is never empty after a restart,
    even if nobody re-sends /start.
    """
    recovered = set()

    # From watchlists.json
    wl_path = os.path.join(DATA_DIR, "watchlists.json")
    if os.path.exists(wl_path):
        try:
            with open(wl_path) as f:
                data = json.load(f)
            for uid_str in data.keys():
                try:
                    recovered.add(int(uid_str))
                except ValueError:
                    pass
        except Exception:
            pass

    # From price_alerts.json
    pa_path = os.path.join(DATA_DIR, "price_alerts.json")
    if os.path.exists(pa_path):
        try:
            with open(pa_path) as f:
                data = json.load(f)
            for uid_str in data.keys():
                try:
                    recovered.add(int(uid_str))
                except ValueError:
                    pass
        except Exception:
            pass

    if recovered:
        existing = _load_users()
        combined = existing | recovered
        if len(combined) > len(existing):
            _save_users(combined)
            logger.info(f"Seeded {len(combined - existing)} user(s) from existing data "
                        f"— total registered: {len(combined)}")


# ─────────────────────────────────────────────────────────────────────────────
#  Auto-register on EVERY interaction (message or callback)
# ─────────────────────────────────────────────────────────────────────────────

async def auto_register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Fires on every incoming message/callback (group=-1, before all other handlers).
    Silently registers the user so alerts always have a target audience.
    """
    if update.effective_user:
        _register_user(update.effective_user.id)


# ─────────────────────────────────────────────────────────────────────────────
#  Patched /start that also registers users
# ─────────────────────────────────────────────────────────────────────────────

async def cmd_start_patched(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _register_user(update.effective_user.id)
    await cmd_start(update, context)


# ─────────────────────────────────────────────────────────────────────────────
#  Dynamic /TICKER handler
# ─────────────────────────────────────────────────────────────────────────────

async def handle_ticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw     = update.message.text or ""
    command = raw.lstrip("/").split("@")[0].upper().strip()
    if command in KNOWN_TICKERS or (2 <= len(command) <= 6 and command.isalpha()):
        await cmd_chart(update, context, ticker=command)


# ─────────────────────────────────────────────────────────────────────────────
#  Screener shortcut commands
# ─────────────────────────────────────────────────────────────────────────────

async def cmd_scalp(update, context):   await _run_screener_cmd(update, context, "scalper_pro")
async def cmd_ara(update, context):     await _run_screener_cmd(update, context, "ara_hunter")
async def cmd_bsjp_cmd(update, context):await _run_screener_cmd(update, context, "bsjp")
async def cmd_bigacc(update, context):  await _run_screener_cmd(update, context, "big_accumulation")


async def _run_screener_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, screener_type: str):
    from bot.screener.screener_engine import run_screener
    from bot.utils.constants import SCREENER_NAMES
    from bot.handlers.callback_handlers import format_screener_results
    from bot.charts.chart_generator import generate_mini_chart

    name = SCREENER_NAMES.get(screener_type, screener_type.upper())
    msg  = await update.message.reply_text(
        f"⏳ Running *{name}* screener…", parse_mode="Markdown"
    )

    results = run_screener(screener_type)
    text, rows = format_screener_results(results, name, screener_type)

    if text is None:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Screener Menu", callback_data="menu_screener")],
        ])
        await msg.edit_text(
            f"📭 *{name}*\n\nNo matches today.\nTry during market hours: 09:00–16:00 WIB.",
            parse_mode="Markdown", reply_markup=kb,
        )
        return

    await msg.edit_text(text[:4096], parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

    # Top pick mini-chart
    top_list = results.get("pass") or results.get("near") or []
    if top_list:
        top    = top_list[0]
        ticker = top["ticker"]
        status = top.get("status", "pass")
        try:
            buf = generate_mini_chart(ticker)
            if buf:
                label = "🥇 Top Full Match" if status == "pass" else "🔶 Top Near Miss"
                ai    = top.get("ai_analysis", "")
                kb2 = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 Full Chart",    callback_data=f"chart_{ticker}"),
                     InlineKeyboardButton("🏦 Broker",        callback_data=f"broker_{ticker}")],
                    [InlineKeyboardButton("⭐ Add Watchlist", callback_data=f"watch_add_{ticker}"),
                     InlineKeyboardButton("🏠 Menu",          callback_data="menu_main")],
                ])
                await update.message.reply_photo(
                    photo=buf,
                    caption=f"{label}: *{ticker}*\n\n{ai[:900]}",
                    parse_mode="Markdown",
                    reply_markup=kb2,
                )
        except Exception as e:
            logger.warning(f"Top-pick chart error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  Bottom keyboard text handler
# ─────────────────────────────────────────────────────────────────────────────

async def handle_kb_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if   text == BTN_SCREENER:  await cmd_screener(update, context)
    elif text == BTN_HEATMAP:   await cmd_heatmap(update, context)
    elif text == BTN_SECTOR:    await cmd_sector(update, context)
    elif text == BTN_BANDAR:    await cmd_bandar(update, context)
    elif text == BTN_WATCHLIST: await cmd_watchlist(update, context)
    elif text == BTN_MOMENTUM:  await cmd_momentum(update, context)
    elif text == BTN_FOREIGN:   await cmd_foreign(update, context)
    elif text == BTN_BREADTH:   await cmd_breadth(update, context)
    elif text == BTN_MENU:      await cmd_menu(update, context)


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
#  Watchlist alert job (every 5 min)
# ─────────────────────────────────────────────────────────────────────────────

async def watchlist_alert_job(context: ContextTypes.DEFAULT_TYPE):
    from bot.data.watchlist import get_all_watched_tickers
    from bot.services.data_service import get_market_snapshot

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
        wl_data = json.load(f)

    for uid_str, user_tickers in wl_data.items():
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
            reason = f"🚨 Move: {sign}{pct:.2f}%" if abs(pct) > 3 else f"⚡ Vol: {rv:.1f}x"
            lines.append(f"• *{ticker}* {price:,.0f} — {reason}")
        try:
            btns = [
                InlineKeyboardButton(f"📊 {a['ticker']}", callback_data=f"chart_{a['ticker']}")
                for a in user_alerts[:3]
            ]
            await context.bot.send_message(
                chat_id=int(uid_str),
                text="\n".join(lines),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([btns]),
            )
        except Exception as e:
            logger.warning(f"Alert failed for {uid_str}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  Market open broadcast (09:05 WIB = 02:05 UTC)
# ─────────────────────────────────────────────────────────────────────────────

async def market_open_broadcast(context: ContextTypes.DEFAULT_TYPE):
    from bot.services.data_service import get_market_snapshot, get_ihsg_data
    from bot.screener.screener_engine import run_screener

    logger.info("Running market open broadcast…")
    users = _load_users()
    if not users:
        return

    ihsg  = get_ihsg_data()
    price = ihsg.get("price", 0)
    pct   = ihsg.get("pct_chg", 0)
    sign  = "+" if pct >= 0 else ""
    emoji = "🟢" if pct >= 0 else "🔴"

    # Quick momentum scan
    snaps = get_market_snapshot(ALL_IDX_STOCKS[:40])
    top5  = sorted(snaps, key=lambda x: x.get("pct_chg", 0), reverse=True)[:5]

    lines = [
        "🌅 *IDX Market Open — 09:05 WIB*\n",
        f"*IHSG:* {price:,.2f} {emoji} {sign}{pct:.2f}%\n",
        "*Top Movers at Open:*",
    ]
    for s in top5:
        t    = s.get("ticker", "")
        p    = s.get("pct_chg", 0)
        rv   = s.get("rel_vol", 1) or 1
        sg   = "+" if p >= 0 else ""
        lines.append(f"  {'🟢' if p>=0 else '🔴'} *{t}* {sg}{p:.2f}% | Vol:{rv:.1f}x")

    # Quick ARA scan
    ara = run_screener("ara_hunter", max_pass=3, max_near=2)
    ara_all = ara.get("pass", []) + ara.get("near", [])
    if ara_all:
        lines.append("\n🎯 *ARA Candidates:*")
        for s in ara_all[:3]:
            t   = s["ticker"]
            p   = s.get("pct_chg", 0)
            tag = "✅" if s.get("status") == "pass" else "🔶"
            lines.append(f"  {tag} *{t}* +{p:.2f}%")

    lines.append("\n_Good luck trading today! Use /screener for full scan._")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 Run Screener", callback_data="menu_screener"),
         InlineKeyboardButton("🔥 Heatmap",      callback_data="menu_heatmap")],
    ])
    text = "\n".join(lines)
    for uid in users:
        try:
            await context.bot.send_message(
                chat_id=uid, text=text, parse_mode="Markdown", reply_markup=kb,
            )
        except Exception as e:
            logger.debug(f"Open broadcast failed for {uid}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  Market close broadcast (16:05 WIB = 09:05 UTC)
# ─────────────────────────────────────────────────────────────────────────────

async def market_close_broadcast(context: ContextTypes.DEFAULT_TYPE):
    from bot.services.data_service import get_market_snapshot, get_ihsg_data
    from bot.sector_rotation.sector_analyzer import analyze_sectors

    logger.info("Running market close broadcast…")
    users = _load_users()
    if not users:
        return

    ihsg  = get_ihsg_data()
    price = ihsg.get("price", 0)
    pct   = ihsg.get("pct_chg", 0)
    sign  = "+" if pct >= 0 else ""
    emoji = "🟢" if pct >= 0 else "🔴"

    snaps   = get_market_snapshot(ALL_IDX_STOCKS[:60])
    gainers = sorted(snaps, key=lambda x: x.get("pct_chg", 0), reverse=True)[:5]
    losers  = sorted(snaps, key=lambda x: x.get("pct_chg", 0))[:3]
    adv     = sum(1 for s in snaps if s.get("pct_chg", 0) > 0)
    dec     = sum(1 for s in snaps if s.get("pct_chg", 0) < 0)

    sector_data = analyze_sectors()
    sectors     = sector_data.get("sectors", [])
    top_sector  = sectors[0]["name"] if sectors else "N/A"
    top_sec_pct = sectors[0]["pct_chg"] if sectors else 0

    lines = [
        "🌆 *IDX Market Close — 16:05 WIB*\n",
        f"*IHSG:* {price:,.2f} {emoji} {sign}{pct:.2f}%",
        f"*Advance/Decline:* {adv}/{dec}\n",
        "*Top Gainers:*",
    ]
    for s in gainers:
        t  = s.get("ticker", "")
        p  = s.get("pct_chg", 0)
        rv = s.get("rel_vol", 1) or 1
        lines.append(f"  🟢 *{t}* +{p:.2f}% | Vol:{rv:.1f}x")

    lines.append("\n*Top Losers:*")
    for s in losers:
        t = s.get("ticker", "")
        p = s.get("pct_chg", 0)
        lines.append(f"  🔴 *{t}* {p:.2f}%")

    top_s_sign = "+" if top_sec_pct >= 0 else ""
    lines.append(f"\n🔥 *Best Sector:* {top_sector} {top_s_sign}{top_sec_pct:.2f}%")
    lines.append("\n_Market closed. See you tomorrow! 🇮🇩_")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📉 Market Breadth",  callback_data="menu_breadth"),
         InlineKeyboardButton("🔄 Sector Rotation", callback_data="menu_sector")],
    ])
    text = "\n".join(lines)
    for uid in users:
        try:
            await context.bot.send_message(
                chat_id=uid, text=text, parse_mode="Markdown", reply_markup=kb,
            )
        except Exception as e:
            logger.debug(f"Close broadcast failed for {uid}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  Build app
# ─────────────────────────────────────────────────────────────────────────────

def build_app() -> Application:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set!")

    # Recover users from watchlists/price_alerts on every restart
    _seed_users_from_all_sources()

    app = Application.builder().token(token).build()

    # Auto-register every user who interacts (group=-1 fires before all others)
    app.add_handler(MessageHandler(filters.ALL, auto_register_handler), group=-1)
    app.add_handler(CallbackQueryHandler(auto_register_handler),        group=-1)

    # Standard commands
    app.add_handler(CommandHandler("start",     cmd_start_patched))
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

    # Screener shortcuts
    app.add_handler(CommandHandler("ara",    cmd_ara))
    app.add_handler(CommandHandler("bsjp",   cmd_bsjp_cmd))
    app.add_handler(CommandHandler("bigacc", cmd_bigacc))
    app.add_handler(CommandHandler("scalp",  cmd_scalp))

    # Price alerts
    app.add_handler(CommandHandler("alert",  cmd_alert))

    # Bottom keyboard text buttons (must come BEFORE ticker handler)
    kb_labels = [
        BTN_SCREENER, BTN_HEATMAP, BTN_SECTOR, BTN_BANDAR,
        BTN_WATCHLIST, BTN_MOMENTUM, BTN_FOREIGN, BTN_BREADTH, BTN_MENU,
    ]
    kb_pattern = "^(" + "|".join(re.escape(l) for l in kb_labels) + ")$"
    app.add_handler(MessageHandler(filters.Regex(kb_pattern), handle_kb_text))

    # Dynamic /TICKER commands
    ticker_re = re.compile(r"^/[A-Za-z]{2,6}(@\w+)?$")
    app.add_handler(MessageHandler(filters.Regex(ticker_re), handle_ticker_command))

    # Inline keyboard callbacks
    from bot.handlers.callback_handlers import handle_callback
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Jobs
    jq = app.job_queue
    if jq:
        # Watchlist alerts every 5 min
        jq.run_repeating(watchlist_alert_job, interval=300, first=60)

        # Market open: 09:05 WIB = 02:05 UTC Mon-Fri
        jq.run_daily(
            market_open_broadcast,
            time=dt_time(2, 5, tzinfo=pytz.utc),
            days=(0, 1, 2, 3, 4),   # Mon–Fri
        )
        # Market close: 16:05 WIB = 09:05 UTC Mon-Fri
        jq.run_daily(
            market_close_broadcast,
            time=dt_time(9, 5, tzinfo=pytz.utc),
            days=(0, 1, 2, 3, 4),
        )

        # ── Alert engine jobs ────────────────────────────────────────────
        from bot.alerts.scanner import (
            top_gainer_scan, golden_cross_scan, price_alert_check,
            top_scalping_scan,
        )
        from bot.alerts.self_check import periodic_self_check

        # Top 5 Gainer scan — every 5 min during market hours
        jq.run_repeating(top_gainer_scan,   interval=300, first=120)

        # Golden Cross scan — every 5 min during market hours
        jq.run_repeating(golden_cross_scan, interval=300, first=180)

        # Custom price alert check — every 2 min
        jq.run_repeating(price_alert_check, interval=120, first=30)

        # Top Scalping scan — every 5 min during market hours
        # (additional trigger source; all existing alert logic unchanged)
        jq.run_repeating(top_scalping_scan, interval=300, first=240)

        # Auto self-check — every 30 min
        jq.run_repeating(periodic_self_check, interval=1800, first=10)

    app.add_error_handler(global_error_handler)
    return app


def main():
    logger.info("🇮🇩 Starting IDX Stock Screener Bot…")
    app = build_app()
    logger.info("✅ Bot running. Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
