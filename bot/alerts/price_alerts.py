"""
Custom price alerts — stores per-user alerts and checks them against live data.

Storage: bot/data/price_alerts.json
Format:  { "user_id": [ {ticker, target, direction, created, note}, ... ] }
"""
import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

ALERTS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "price_alerts.json")


# ── Persistence ──────────────────────────────────────────────────────────────

def _load() -> dict:
    if not os.path.exists(ALERTS_FILE):
        return {}
    try:
        with open(ALERTS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict):
    os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
    with open(ALERTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Public API ────────────────────────────────────────────────────────────────

def add_price_alert(user_id: int, ticker: str, target: float, current_price: float) -> str:
    """
    Add a price alert. Direction is determined automatically:
      current < target → alert when price RISES above target
      current > target → alert when price FALLS below target
    Returns a confirmation message.
    """
    data      = _load()
    uid       = str(user_id)
    direction = "above" if current_price < target else "below"

    entry = {
        "ticker":    ticker.upper(),
        "target":    target,
        "direction": direction,
        "created":   datetime.now().isoformat(),
        "current":   current_price,
    }

    if uid not in data:
        data[uid] = []

    # Prevent duplicates
    for existing in data[uid]:
        if existing["ticker"] == ticker.upper() and abs(existing["target"] - target) < 1:
            return f"⚠️ Alert for *{ticker}* at {target:,.0f} already exists."

    data[uid].append(entry)
    _save(data)

    arrow = "📈" if direction == "above" else "📉"
    return (
        f"✅ Alert set for *{ticker}*\n"
        f"{arrow} Notify when price goes *{direction}* {target:,.0f}\n"
        f"Current: {current_price:,.0f}"
    )


def get_user_alerts(user_id: int) -> list:
    data = _load()
    return data.get(str(user_id), [])


def remove_user_alert(user_id: int, ticker: str) -> bool:
    data = _load()
    uid  = str(user_id)
    if uid not in data:
        return False
    before = len(data[uid])
    data[uid] = [a for a in data[uid] if a["ticker"] != ticker.upper()]
    _save(data)
    return len(data[uid]) < before


def get_all_alert_tickers() -> list:
    data = _load()
    tickers = set()
    for alerts in data.values():
        for a in alerts:
            tickers.add(a["ticker"])
    return list(tickers)


def check_and_fire_alerts(snapshots: list) -> list:
    """
    Check all price alerts against current snapshots.
    Returns list of fired alerts: [{user_id, ticker, target, direction, price}]
    """
    data    = _load()
    snap_map= {s["ticker"]: s for s in snapshots}
    fired   = []
    changed = False

    for uid, alerts in data.items():
        remaining = []
        for alert in alerts:
            ticker = alert["ticker"]
            snap   = snap_map.get(ticker)
            if not snap:
                remaining.append(alert)
                continue
            price  = snap.get("price", 0)
            target = alert["target"]
            direct = alert["direction"]

            triggered = (
                (direct == "above" and price >= target) or
                (direct == "below" and price <= target)
            )
            if triggered:
                fired.append({
                    "user_id":   int(uid),
                    "ticker":    ticker,
                    "target":    target,
                    "direction": direct,
                    "price":     price,
                    "pct_chg":   snap.get("pct_chg", 0),
                    "rel_vol":   snap.get("rel_vol", 1) or 1,
                })
                changed = True
            else:
                remaining.append(alert)
        data[uid] = remaining

    if changed:
        _save(data)

    return fired
