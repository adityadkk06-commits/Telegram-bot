"""
Rate-limited notification queue.

Prevents Telegram API flood (max 30 msgs/sec, 1 msg/sec per chat).
Uses a per-chat deque of send timestamps to enforce rate limits.
"""
import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional
import io

logger = logging.getLogger(__name__)

# Per-chat: max 1 alert per COOLDOWN_SECONDS for the same ticker
COOLDOWN_SECONDS = 120   # 2 minutes
_last_sent: dict[tuple, datetime] = {}   # (chat_id, ticker) → last sent time

# Global rate limiter: max 25 messages per 30 seconds
_global_queue: deque = deque()
MAX_PER_30S = 25


def _is_on_cooldown(chat_id: int, ticker: str) -> bool:
    key = (chat_id, ticker)
    last = _last_sent.get(key)
    if last is None:
        return False
    return (datetime.now() - last).total_seconds() < COOLDOWN_SECONDS


def _mark_sent(chat_id: int, ticker: str):
    _last_sent[(chat_id, ticker)] = datetime.now()


def _global_rate_ok() -> bool:
    """Allow if fewer than MAX_PER_30S messages in the last 30 seconds."""
    now = datetime.now()
    cutoff = now - timedelta(seconds=30)
    while _global_queue and _global_queue[0] < cutoff:
        _global_queue.popleft()
    return len(_global_queue) < MAX_PER_30S


def _record_global():
    _global_queue.append(datetime.now())


async def send_alert(
    bot,
    chat_id: int,
    text: str,
    ticker: str = "__generic__",
    photo: Optional[io.BytesIO] = None,
    reply_markup=None,
    parse_mode: str = "Markdown",
) -> bool:
    """
    Send a single alert with rate limiting and cooldown check.
    Returns True if sent, False if suppressed.
    """
    if _is_on_cooldown(chat_id, ticker):
        logger.debug(f"Alert suppressed (cooldown): {ticker} → {chat_id}")
        return False
    if not _global_rate_ok():
        logger.debug("Global rate limit hit — skipping alert")
        return False

    try:
        if photo:
            photo.seek(0)
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=text[:1024],
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=text[:4096],
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        _mark_sent(chat_id, ticker)
        _record_global()
        return True
    except Exception as e:
        logger.warning(f"Alert send failed ({chat_id}, {ticker}): {e}")
        return False


async def broadcast_alert(
    bot,
    user_ids: list[int],
    text: str,
    ticker: str = "__generic__",
    photo: Optional[io.BytesIO] = None,
    reply_markup=None,
    delay_between: float = 0.05,   # seconds between sends
) -> int:
    """
    Broadcast same alert to a list of users.
    Returns count of successfully sent messages.
    """
    sent = 0
    for uid in user_ids:
        # Each user gets their own photo BytesIO read position
        photo_copy = None
        if photo:
            photo.seek(0)
            buf = io.BytesIO(photo.read())
            photo_copy = buf

        ok = await send_alert(
            bot, uid, text, ticker=ticker,
            photo=photo_copy, reply_markup=reply_markup,
        )
        if ok:
            sent += 1
        if delay_between > 0:
            await asyncio.sleep(delay_between)
    return sent
