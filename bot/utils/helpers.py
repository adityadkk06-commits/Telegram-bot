"""
Safe Telegram message helpers.
Telegram does not allow editing a photo message as text or vice-versa.
All callbacks must use these helpers to avoid BadRequest crashes.
"""
import logging
from telegram import InlineKeyboardMarkup, Message
from telegram.error import BadRequest

logger = logging.getLogger(__name__)


async def safe_edit(query, text: str, reply_markup=None, parse_mode="Markdown") -> bool:
    """
    Try to edit the current message.
    - Text messages: edit_message_text
    - Photo messages: edit_message_caption
    - If both fail: delete old and reply with new text
    Returns True if successful.
    """
    kwargs = {"parse_mode": parse_mode}
    if reply_markup:
        kwargs["reply_markup"] = reply_markup

    # Try editing as text
    try:
        await query.edit_message_text(text, **kwargs)
        return True
    except BadRequest as e:
        if "There is no text in the message" not in str(e) and "Message is not modified" not in str(e):
            logger.debug(f"edit_message_text non-photo error: {e}")

    # Try editing as caption (photo message)
    try:
        await query.edit_message_caption(caption=text[:1024], **kwargs)
        return True
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return True
        logger.debug(f"edit_message_caption error: {e}")

    # Fallback: delete old message, send new one
    try:
        await query.message.delete()
    except Exception:
        pass

    try:
        await query.message.reply_text(text, **kwargs)
        return True
    except Exception as e:
        logger.error(f"safe_edit total failure: {e}")
        return False


async def safe_send_photo(query, buf, caption: str, reply_markup=None, parse_mode="Markdown"):
    """Send a photo from a callback query context. Deletes old message first."""
    try:
        await query.message.delete()
    except Exception:
        pass
    kwargs = {"caption": caption[:1024], "parse_mode": parse_mode}
    if reply_markup:
        kwargs["reply_markup"] = reply_markup
    await query.message.reply_photo(photo=buf, **kwargs)
