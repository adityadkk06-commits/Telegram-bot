"""
Auto Self-Check System.

Validates all bot modules at startup and every 30 minutes.
Logs a health report: any failure is logged as ERROR but does NOT crash the bot.

Checks:
  1. All critical imports resolve
  2. Data service returns IHSG data
  3. Screener modules load and return FilterResult
  4. Heatmap module importable
  5. Sector rotation module importable
  6. Bandar/broker module importable
  7. Watchlist storage accessible
  8. Alert storage accessible
  9. All registered users file readable
 10. Job queue is running (delegated to caller)
"""
import logging
import os
import traceback

logger = logging.getLogger(__name__)

_SEP = "─" * 40


def _check(name: str, fn) -> tuple[bool, str]:
    """Run a single check. Returns (passed, note)."""
    try:
        result = fn()
        msg    = str(result)[:80] if result is not None else "OK"
        return True, msg
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def run_self_check() -> dict:
    """
    Run all health checks synchronously.
    Returns dict: { "passed": int, "failed": int, "checks": [(name, ok, note)] }
    """
    results = []

    # 1. Data service — IHSG
    def chk_data_service():
        from bot.services.data_service import get_ihsg_data
        d = get_ihsg_data()
        if not d:
            raise RuntimeError("get_ihsg_data() returned empty")
        return f"IHSG {d.get('price',0):,.0f} ({d.get('pct_chg',0):+.2f}%)"
    results.append(("data_service / IHSG", *_check("data_service", chk_data_service)))

    # 2. Market snapshot (single stock)
    def chk_snapshot():
        from bot.services.data_service import get_market_snapshot
        snaps = get_market_snapshot(["BBCA"])
        if not snaps:
            raise RuntimeError("No snapshot returned for BBCA")
        return f"BBCA price={snaps[0].get('price',0):,.0f}"
    results.append(("data_service / snapshot", *_check("snapshot", chk_snapshot)))

    # 3. ARA Hunter screener
    def chk_ara():
        from bot.screener.ara_hunter import ara_hunter_score
        from bot.screener.filter_engine import FilterResult
        dummy = {"ticker": "TEST", "price": 500, "prev_price": 450, "open": 460,
                 "volume": 1_000_000, "prev_volume": 800_000, "value": 5_000_000_000,
                 "ma5": 480}
        r = ara_hunter_score(dummy)
        return f"status={r.status} score={r.score}/{r.max_score}"
    results.append(("screener / ara_hunter", *_check("ara_hunter", chk_ara)))

    # 4. BSJP screener
    def chk_bsjp():
        from bot.screener.bsjp import bsjp_score
        dummy = {"ticker": "TEST", "price": 1000, "prev_price": 990, "volume": 2_000_000,
                 "prev_volume": 1_500_000, "value": 10_000_000_000, "ma5": 990,
                 "ma20": 980, "ma50": 950, "vol_ma20": 1_000_000, "rel_vol": 2.1}
        r = bsjp_score(dummy)
        return f"status={r.status}"
    results.append(("screener / bsjp", *_check("bsjp", chk_bsjp)))

    # 5. Big Accumulation screener
    def chk_bigacc():
        from bot.screener.big_accumulation import big_accumulation_score
        dummy = {"ticker": "TEST", "price": 400, "prev_price": 390,
                 "value": 3_000_000_000, "ma20": 390, "ma50": 380,
                 "vol_ma5": 1_500_000, "vol_ma20": 1_000_000, "bandar_score": 30}
        r = big_accumulation_score(dummy)
        return f"status={r.status}"
    results.append(("screener / big_accumulation", *_check("bigacc", chk_bigacc)))

    # 6. Scalper Pro screener
    def chk_scalper():
        from bot.screener.scalper_pro import scalper_pro_score
        dummy = {"ticker": "TEST", "price": 800, "prev_price": 790, "value": 3_000_000_000,
                 "volume": 5_000_000, "ma5": 795, "ma20": 788, "rel_vol": 2.2,
                 "rsi": 55, "macd": 0.5, "macd_signal": 0.3, "vwap": 798,
                 "bandar_score": 20, "high": 810, "low": 788}
        r = scalper_pro_score(dummy)
        return f"status={r.status}"
    results.append(("screener / scalper_pro", *_check("scalper_pro", chk_scalper)))

    # 7. Heatmap
    def chk_heatmap():
        from bot.heatmap import heatmap_generator
        return "importable"
    results.append(("heatmap", *_check("heatmap", chk_heatmap)))

    # 8. Sector rotation
    def chk_sector():
        from bot.sector_rotation import sector_analyzer
        return "importable"
    results.append(("sector_rotation", *_check("sector_rotation", chk_sector)))

    # 9. Broker / bandar
    def chk_broker():
        from bot.bandarmology.broker_analyzer import estimate_broker_signal
        dummy = {"ticker": "BBCA", "price": 9000, "prev_price": 8900,
                 "pct_chg": 1.1, "volume": 1_000_000, "value": 9_000_000_000,
                 "rel_vol": 1.8, "bandar_score": 25, "ma20": 8800, "ma50": 8600}
        r = estimate_broker_signal(dummy)
        return f"signal={r.get('signal')}"
    results.append(("broker_analyzer", *_check("broker", chk_broker)))

    # 10. Signal engine
    def chk_signal():
        from bot.alerts.signal_engine import _basic_signal
        r = _basic_signal({"ticker": "BBCA", "price": 9000, "pct_chg": 1.5,
                            "value": 5e9, "rel_vol": 2.0})
        return f"signal={r['signal_type']} conf={r['confidence_pct']}%"
    results.append(("signal_engine", *_check("signal_engine", chk_signal)))

    # 11. Bid/Offer engine
    def chk_bid_offer():
        from bot.alerts.bid_offer import scalping_probability
        r = scalping_probability({"rel_vol": 2.1, "pct_chg": 1.5}, {
            "bid_dominance": "moderate", "scalp_spread_ok": True, "absorption": True,
            "clv": 0.4
        }, True, 55)
        return f"scalp_prob={r}"
    results.append(("bid_offer", *_check("bid_offer", chk_bid_offer)))

    # 12. Watchlist storage
    def chk_watchlist():
        from bot.data.watchlist import get_all_watched_tickers
        t = get_all_watched_tickers()
        return f"{len(t)} tickers watched"
    results.append(("watchlist_storage", *_check("watchlist", chk_watchlist)))

    # 13. Price alert storage
    def chk_price_alerts():
        from bot.alerts.price_alerts import get_all_alert_tickers
        t = get_all_alert_tickers()
        return f"{len(t)} alert tickers"
    results.append(("price_alerts_storage", *_check("price_alerts", chk_price_alerts)))

    # 14. Users file
    def chk_users():
        path = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")
        if not os.path.exists(path):
            return "users.json not yet created (OK — will be created on first /start)"
        import json
        with open(path) as f:
            u = json.load(f)
        return f"{len(u)} registered users"
    results.append(("users_registry", *_check("users", chk_users)))

    # 15. Alert chart
    def chk_alert_chart():
        from bot.alerts.alert_chart import generate_alert_chart
        return "importable"
    results.append(("alert_chart", *_check("alert_chart", chk_alert_chart)))

    # ── Report ────────────────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed

    logger.info(_SEP)
    logger.info(f"🤖 BOT SELF-CHECK  — {passed}/{len(results)} passed")
    logger.info(_SEP)
    for name, ok, note in results:
        status = "✅ OK  " if ok else "❌ FAIL"
        logger.info(f"  {status} │ {name:<30} │ {note}")
    logger.info(_SEP)

    if failed:
        logger.error(f"⚠️  {failed} check(s) FAILED — see above for details")
    else:
        logger.info("🟢 All systems operational")

    return {"passed": passed, "failed": failed, "checks": results}


async def periodic_self_check(context) -> None:
    """APScheduler job — runs self-check every 30 minutes."""
    result = run_self_check()
    if result["failed"] > 0:
        # Log a compact failure summary
        fails = [name for name, ok, _ in result["checks"] if not ok]
        logger.error(f"Self-check: {result['failed']} failures — {fails}")
