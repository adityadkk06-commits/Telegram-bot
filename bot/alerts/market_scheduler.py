"""
Market hours utilities for IDX (Indonesia Stock Exchange).

IDX trading hours (WIB = UTC+7):
  Pre-open:  08:45 – 09:00
  Session 1: 09:00 – 12:00
  Break:     12:00 – 13:30
  Session 2: 13:30 – 15:50
  Post:      15:50 – 16:15

We scan during 09:00 – 16:20 WIB (Mon–Fri).
"""
from datetime import datetime, time as dt_time
import pytz

WIB = pytz.timezone("Asia/Jakarta")

MARKET_OPEN  = dt_time(9, 0)
MARKET_CLOSE = dt_time(16, 20)
TRADING_DAYS = {0, 1, 2, 3, 4}   # Monday–Friday


def is_market_open() -> bool:
    """Return True if IDX market is currently in session."""
    now = datetime.now(WIB)
    if now.weekday() not in TRADING_DAYS:
        return False
    t = now.time()
    return MARKET_OPEN <= t <= MARKET_CLOSE


def is_pre_market() -> bool:
    """Return True during pre-open (08:30–09:05 WIB)."""
    now = datetime.now(WIB)
    if now.weekday() not in TRADING_DAYS:
        return False
    t = now.time()
    return dt_time(8, 30) <= t < dt_time(9, 5)


def market_session() -> str:
    """Return current market session label."""
    now = datetime.now(WIB)
    if now.weekday() not in TRADING_DAYS:
        return "closed"
    t = now.time()
    if dt_time(8, 30) <= t < dt_time(9, 0):
        return "pre_open"
    if dt_time(9, 0) <= t < dt_time(12, 0):
        return "session1"
    if dt_time(12, 0) <= t < dt_time(13, 30):
        return "break"
    if dt_time(13, 30) <= t < dt_time(15, 50):
        return "session2"
    if dt_time(15, 50) <= t <= dt_time(16, 20):
        return "closing"
    return "closed"
