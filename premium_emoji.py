# -*- coding: utf-8 -*-
"""
🎨 premium_emoji — Custom / Premium emoji for Humsyar Telegram bot

Source pack: data/khoshgelasion-emojis.json
  unicode_emoji → custom_emoji_id (highest priority wins)

Sending (Bot API):
  HTML: <tg-emoji emoji-id="ID">😀</tg-emoji>
  The placeholder MUST be the matching unicode (or a valid emoji char);
  offset/length are handled by Telegram when using HTML parse_mode.

Fallback:
  If pack has no exact unicode, ALIASES map common bot icons to nearest pack emoji.
  If still missing, original unicode stays (no crash).

Buttons (ReplyKeyboard / InlineKeyboard):
  Telegram often does not render custom emoji inside button labels the same way;
  we keep unicode on buttons and premiumize message bodies.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

_PACK_PATHS = (
    Path(__file__).resolve().parent / "data" / "khoshgelasion-emojis.json",
    Path(__file__).resolve().parent / "khoshgelasion-emojis.json",
)

# Bot icons not in pack → nearest pack unicode (visual/role match)
ALIASES: dict[str, str] = {
    # calendar / time
    "📅": "⏰",
    "📆": "⏰",
    "🗓": "⏰",
    # back / navigation
    "🔙": "⬅️",
    "↩️": "⬅️",
    "↩": "⬅️",
    "◀️": "⬅️",
    "◀": "⬅️",
    "▶": "➡️",
    "▶️": "➡️",
    "⏭": "➡️",
    "⏩": "➡️",
    "⇒": "➡️",
    "→": "➡️",
    "←": "⬅️",
    # power / star / warn
    "⚡": "⚡️",
    "⭐": "⭐️",
    "★": "⭐️",
    "⚠": "⚠️",
    # hearts / brand
    "💙": "🩵",
    "❤": "❤️",
    # files / books
    "📘": "📚",
    "📖": "📚",
    "📂": "🗂",
    "📁": "🗂",
    "📋": "📝",
    "📄": "📝",
    "🧾": "📝",
    # search / lock / link / gear
    "🔍": "👀",
    "🔎": "👀",
    "🔒": "🔑",
    "🔐": "🔑",
    "🔗": "📎",
    "⚙️": "🔑",
    "⚙": "🔑",
    # lab / bank
    "🧪": "🩺",
    "🧬": "🩺",
    # notify / rocket / red-yellow
    "🔔": "‼️",
    "🚀": "✨",
    "🔴": "🔻",
    "🟡": "🔸",
    "📢": "📣" if False else "‼️",  # no megaphone in pack
    "▫️": "🔹",
    "•": "🔹",
    # misc UI
    "🏠": "🏠",
    "📥": "📩",
    "📤": "📩",
    "💾": "💎",
    "🗑": "❌",
    "➕": "✨",
    "➖": "➖",
    "🔄": "🔄",
    "🌐": "🧭",
    "💰": "💰",
    "🎁": "🎁",
    "🎉": "🎉",
    "💡": "💡",
    "📈": "📊",
    "🎫": "🔖",
    "🎟": "🔖",
    "👑": "🏆",
    "💍": "💎",
    "📦": "🎁",
    "🏫": "🏫",
    "👨": "👤",
    "⌨": "📱",
    "✂": "🔪",
    "👁": "👁",
    "💬": "💬",
    "🌊": "💫" if False else "✨",
    "🛡": "🛡️" if False else "🔐",  # will alias lock→key
    "⛔": "🚫",
    "🚫": "🚫",
}

# Fix aliases that pointed to missing
ALIASES["🛡"] = "🔑"
ALIASES["📢"] = "‼️"
ALIASES["🔐"] = "🔑"
ALIASES["🔒"] = "🔑"

_TG_EMOJI_RE = re.compile(
    r"<tg-emoji\b[^>]*>.*?</tg-emoji>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


@lru_cache(maxsize=1)
def load_pack_map() -> dict[str, str]:
    """unicode_emoji → custom_emoji_id (best priority)."""
    path = next((p for p in _PACK_PATHS if p.exists()), None)
    if not path:
        logger.warning("premium_emoji pack not found under data/")
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("failed to load premium emoji pack")
        return {}
    buckets: dict[str, list[tuple[int, str]]] = {}
    for row in rows:
        if not row.get("enabled"):
            continue
        u = row.get("unicode_emoji") or ""
        cid = str(row.get("custom_emoji_id") or "").strip()
        if not u or not cid:
            continue
        pr = int(row.get("priority") or 0)
        buckets.setdefault(u, []).append((pr, cid))
    out: dict[str, str] = {}
    for u, items in buckets.items():
        items.sort(key=lambda t: (-t[0], t[1]))
        out[u] = items[0][1]
    logger.info("premium_emoji pack loaded: %s unique unicode from %s", len(out), path.name)
    return out


def resolve_custom_id(unicode_emoji: str) -> str | None:
    """Map a unicode emoji (or alias) to custom_emoji_id."""
    if not unicode_emoji:
        return None
    pack = load_pack_map()
    if unicode_emoji in pack:
        return pack[unicode_emoji]
    # strip VS16
    bare = unicode_emoji.replace("\ufe0f", "")
    if bare in pack:
        return pack[bare]
    # try with VS16
    if bare + "\ufe0f" in pack:
        return pack[bare + "\ufe0f"]
    alias = ALIASES.get(unicode_emoji) or ALIASES.get(bare)
    if alias:
        if alias in pack:
            return pack[alias]
        a2 = alias.replace("\ufe0f", "")
        if a2 in pack:
            return pack[a2]
        if a2 + "\ufe0f" in pack:
            return pack[a2 + "\ufe0f"]
    return None


def _iter_emoji_spans(text: str) -> Iterable[tuple[int, int, str]]:
    """Yield (start, end, emoji) for emoji-like spans outside HTML tags.

    Uses a practical regex covering BMP symbols + astral emoji + ZWJ sequences.
    """
    # Skip regions inside HTML tags and existing tg-emoji
    blocked = []
    for m in _HTML_TAG_RE.finditer(text):
        blocked.append((m.start(), m.end()))

    def is_blocked(i: int) -> bool:
        for a, b in blocked:
            if a <= i < b:
                return True
        return False

    # Emoji presentation sequences (simplified but robust for our codebase)
    pattern = re.compile(
        "(?:"
        "[\U0001F1E6-\U0001F1FF]{2}"  # flags
        "|[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF]"
        "[\U0000FE0F\U0000200D\U0001F3FB-\U0001F3FF\U0001F000-\U0001FAFF]*"
        "|[\U00002190-\U000021FF\U00002300-\U000023FF\U000025A0-\U000025FF\U00002B00-\U00002BFF]"
        "\U0000FE0F?"
        ")"
    )
    for m in pattern.finditer(text):
        if is_blocked(m.start()):
            continue
        yield m.start(), m.end(), m.group(0)


def premium_html(text: str | None, *, enabled: bool = True) -> str:
    """Inject <tg-emoji> for known pack emojis inside an HTML message body.

    Safe to call repeatedly (already-wrapped tags left alone).
    Non-mapped emojis unchanged. Empty/None → original.
    """
    if not enabled or not text:
        return text or ""
    pack = load_pack_map()
    if not pack:
        return text

    # Fast path: nothing emoji-like
    if not any(ord(ch) > 127 for ch in text):
        return text

    # Protect existing <tg-emoji>...</tg-emoji> so re-entry is idempotent
    placeholders: list[str] = []

    def _stash(m: re.Match) -> str:
        placeholders.append(m.group(0))
        return f"\x00PE{len(placeholders)-1}\x00"

    work = _TG_EMOJI_RE.sub(_stash, text)

    out = []
    last = 0
    for start, end, emo in _iter_emoji_spans(work):
        out.append(work[last:start])
        cid = resolve_custom_id(emo)
        if cid:
            out.append(f'<tg-emoji emoji-id="{cid}">{emo}</tg-emoji>')
        else:
            out.append(emo)
        last = end
    out.append(work[last:])
    result = "".join(out)
    for i, original in enumerate(placeholders):
        result = result.replace(f"\x00PE{i}\x00", original)
    return result


def install_telegram_hooks() -> None:
    """Monkey-patch PTB send/edit paths so HTML messages get premium emojis.

    Call once at bot startup (post_init or module import of bot).
    """
    try:
        from telegram import Message
        from telegram._callbackquery import CallbackQuery
        from telegram import Bot
    except Exception:
        logger.exception("premium_emoji hooks: telegram import failed")
        return

    if getattr(install_telegram_hooks, "_done", False):
        return

    def _wrap_html_text(text, kwargs: dict):
        if text is None:
            return text, kwargs
        pm = kwargs.get("parse_mode")
        # Common in this codebase: explicit HTML
        if pm is None:
            return text, kwargs
        pm_s = str(pm).upper() if not isinstance(pm, str) else pm.upper()
        if "HTML" not in pm_s:
            return text, kwargs
        return premium_html(str(text)), kwargs

    # Message.reply_text
    if not getattr(Message.reply_text, "_humsyar_premium", False):
        _orig_reply = Message.reply_text

        async def reply_text(self, text, *args, **kwargs):
            text, kwargs = _wrap_html_text(text, kwargs)
            return await _orig_reply(self, text, *args, **kwargs)

        reply_text._humsyar_premium = True  # type: ignore[attr-defined]
        Message.reply_text = reply_text  # type: ignore[method-assign]

    # Message.edit_text
    if hasattr(Message, "edit_text") and not getattr(Message.edit_text, "_humsyar_premium", False):
        _orig_edit = Message.edit_text

        async def edit_text(self, text, *args, **kwargs):
            text, kwargs = _wrap_html_text(text, kwargs)
            return await _orig_edit(self, text, *args, **kwargs)

        edit_text._humsyar_premium = True  # type: ignore[attr-defined]
        Message.edit_text = edit_text  # type: ignore[method-assign]

    # CallbackQuery.edit_message_text
    if not getattr(CallbackQuery.edit_message_text, "_humsyar_premium", False):
        _orig_cq = CallbackQuery.edit_message_text

        async def edit_message_text(self, text, *args, **kwargs):
            text, kwargs = _wrap_html_text(text, kwargs)
            return await _orig_cq(self, text, *args, **kwargs)

        edit_message_text._humsyar_premium = True  # type: ignore[attr-defined]
        CallbackQuery.edit_message_text = edit_message_text  # type: ignore[method-assign]

    # Bot.send_message
    if not getattr(Bot.send_message, "_humsyar_premium", False):
        _orig_send = Bot.send_message

        async def send_message(self, chat_id, text, *args, **kwargs):
            text, kwargs = _wrap_html_text(text, kwargs)
            return await _orig_send(self, chat_id, text, *args, **kwargs)

        send_message._humsyar_premium = True  # type: ignore[attr-defined]
        Bot.send_message = send_message  # type: ignore[method-assign]

    install_telegram_hooks._done = True  # type: ignore[attr-defined]
    logger.info("premium_emoji telegram hooks installed")


# semantic registry for future explicit use (optional)
def E(name: str, default_unicode: str) -> str:
    """Return unicode placeholder for semantic name (message still needs premium_html)."""
    return default_unicode
