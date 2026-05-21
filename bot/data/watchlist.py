import json
import os

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlists.json")

def _load() -> dict:
    if not os.path.exists(WATCHLIST_FILE):
        return {}
    try:
        with open(WATCHLIST_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(data: dict):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_watchlist(user_id: int) -> list:
    data = _load()
    return data.get(str(user_id), [])

def add_to_watchlist(user_id: int, ticker: str) -> bool:
    data = _load()
    key = str(user_id)
    if key not in data:
        data[key] = []
    ticker = ticker.upper()
    if ticker in data[key]:
        return False
    data[key].append(ticker)
    _save(data)
    return True

def remove_from_watchlist(user_id: int, ticker: str) -> bool:
    data = _load()
    key = str(user_id)
    ticker = ticker.upper()
    if key not in data or ticker not in data[key]:
        return False
    data[key].remove(ticker)
    _save(data)
    return True

def get_all_watched_tickers() -> list:
    data = _load()
    tickers = set()
    for lst in data.values():
        tickers.update(lst)
    return list(tickers)
