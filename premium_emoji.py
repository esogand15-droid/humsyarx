# -*- coding: utf-8 -*-
"""
🎨 premium_emoji — Custom / Premium animated emoji for Humsyar bot

Pack: data/khoshgelasion-emojis.json
  fields: unicode_emoji, custom_emoji_id, priority, enabled

Telegram rules (Bot API ≥ 9.4 / Feb 2026):
  • Bot may send custom emoji in private/group/supergroup if the **bot owner
    has Telegram Premium** (or older Fragment username path).
  • Each custom_emoji entity must cover exactly one ordinary emoji placeholder.
  • offset/length are in **UTF-16 code units**.
  • HTML form: <tg-emoji emoji-id="ID">😀</tg-emoji>
  • entities form: MessageEntity(type=custom_emoji, offset, length, custom_emoji_id)

If Telegram rejects custom emoji (owner not Premium / restricted pack), we
automatically retry once with plain unicode so the bot never breaks.

Buttons: labels stay unicode (client support for custom emoji on buttons is weak).
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

_PACK_PATHS = (
    Path(__file__).resolve().parent / "data" / "khoshgelasion-emojis.json",
    Path(__file__).resolve().parent / "khoshgelasion-emojis.json",
)

# UI glyphs missing from pack → nearest pack unicode
ALIASES: dict[str, str] = {
    "📅": "⏰", "📆": "⏰", "🗓": "⏰",
    "🔙": "⬅️", "↩️": "⬅️", "↩": "⬅️", "◀️": "⬅️", "◀": "⬅️",
    "▶": "➡️", "▶️": "➡️", "⏭": "➡️", "⏩": "➡️", "⇒": "➡️", "→": "➡️", "←": "⬅️",
    "⚡": "⚡️", "⭐": "⭐️", "★": "⭐️", "⚠": "⚠️",
    "💙": "🩵", "❤": "❤️",
    "📘": "📚", "📖": "📚", "📂": "🗂", "📁": "🗂", "📋": "📝", "📄": "📝", "🧾": "📝",
    "🔍": "👀", "🔎": "👀", "🔒": "🔑", "🔐": "🔑", "🔗": "📎", "⚙️": "🔑", "⚙": "🔑",
    "🧪": "🩺", "🧬": "🩺",
    "🔔": "‼️", "🚀": "✨", "🔴": "🔻", "🟡": "🔸", "📢": "‼️", "▫️": "🔹", "•": "🔹",
    "📥": "📩", "📤": "📩", "💾": "💎", "🗑": "❌", "➕": "✨",
    "🌐": "🧭", "🎫": "🔖", "🎟": "🔖", "👑": "🏆", "💍": "💎", "📦": "🎁",
    "👨": "👤", "⌨": "📱", "✂": "🔪", "📈": "📊",
    "🌊": "✨", "🛡": "🔑", "⛔": "🚫",
}

_TG_EMOJI_RE = re.compile(r"<tg-emoji\b[^>]*>.*?</tg-emoji>", re.I | re.S)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_PREMIUM_FAIL_MARKERS = (
    "custom_emoji",
    "custom emoji",
    "ENTITY_CUSTOM_EMOJI",
    "can't parse entities",
    "cant parse entities",
    "BUTTON_USER_PRIVACY",
    "premium",
    "restricted",
)


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


@lru_cache(maxsize=1)
def load_pack_map() -> dict[str, str]:
    path = next((p for p in _PACK_PATHS if p.exists()), None)
    if not path:
        logger.warning("premium_emoji: pack JSON not found")
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("premium_emoji: failed to read pack")
        return {}
    buckets: dict[str, list[tuple[int, str]]] = {}
    for row in rows:
        if not row.get("enabled"):
            continue
        u = row.get("unicode_emoji") or ""
        cid = str(row.get("custom_emoji_id") or "").strip()
        if not u or not cid:
            continue
        buckets.setdefault(u, []).append((int(row.get("priority") or 0), cid))
    out = {}
    for u, items in buckets.items():
        items.sort(key=lambda t: (-t[0], t[1]))
        out[u] = items[0][1]
    logger.info("premium_emoji: loaded %s glyphs from %s", len(out), path.name)
    return out


def resolve_custom_id(unicode_emoji: str) -> str | None:
    if not unicode_emoji:
        return None
    pack = load_pack_map()

    def hit(u: str) -> str | None:
        if u in pack:
            return pack[u]
        bare = u.replace("\ufe0f", "")
        if bare in pack:
            return pack[bare]
        if bare + "\ufe0f" in pack:
            return pack[bare + "\ufe0f"]
        return None

    got = hit(unicode_emoji)
    if got:
        return got
    alias = ALIASES.get(unicode_emoji) or ALIASES.get(unicode_emoji.replace("\ufe0f", ""))
    if alias:
        return hit(alias)
    return None


def _iter_emoji_spans(text: str) -> Iterable[tuple[int, int, str]]:
    blocked = [(m.start(), m.end()) for m in _HTML_TAG_RE.finditer(text)]

    def is_blocked(i: int) -> bool:
        return any(a <= i < b for a, b in blocked)

    pattern = re.compile(
        "(?:"
        "[\U0001F1E6-\U0001F1FF]{2}"
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


def strip_tg_emoji_tags(text: str) -> str:
    """Remove <tg-emoji> wrappers, keep inner placeholder emoji."""
    if not text or "tg-emoji" not in text:
        return text or ""
    return re.sub(
        r'<tg-emoji\b[^>]*>(.*?)</tg-emoji>',
        r"\1",
        text,
        flags=re.I | re.S,
    )


def premium_html(text: str | None, *, enabled: bool = True) -> str:
    """Wrap known emojis with <tg-emoji emoji-id> for HTML parse_mode."""
    if not enabled or not text:
        return text or ""
    if not load_pack_map():
        return text
    if not any(ord(ch) > 127 for ch in text):
        return text

    placeholders: list[str] = []

    def _stash(m: re.Match) -> str:
        placeholders.append(m.group(0))
        return f"\x00PE{len(placeholders)-1}\x00"

    work = _TG_EMOJI_RE.sub(_stash, text)
    out: list[str] = []
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


def build_custom_emoji_entities(plain_text: str) -> list[Any]:
    """Build PTB MessageEntity list for plain (non-HTML) text.

    plain_text must contain ordinary emoji characters (no HTML tags).
    """
    if not plain_text or not load_pack_map():
        return []
    try:
        from telegram import MessageEntity
    except Exception:
        return []

    entities = []
    # Walk emoji spans; compute UTF-16 offsets
    utf16_pos = 0
    i = 0
    # Rebuild by scanning original with same regex but track utf16
    pattern = re.compile(
        "(?:"
        "[\U0001F1E6-\U0001F1FF]{2}"
        "|[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF]"
        "[\U0000FE0F\U0000200D\U0001F3FB-\U0001F3FF\U0001F000-\U0001FAFF]*"
        "|[\U00002190-\U000021FF\U00002300-\U000023FF\U000025A0-\U000025FF\U00002B00-\U00002BFF]"
        "\U0000FE0F?"
        ")"
    )
    last = 0
    for m in pattern.finditer(plain_text):
        # utf16 of gap
        gap = plain_text[last:m.start()]
        utf16_pos += _utf16_len(gap)
        emo = m.group(0)
        ln = _utf16_len(emo)
        cid = resolve_custom_id(emo)
        if cid and ln > 0:
            try:
                entities.append(
                    MessageEntity(
                        type=MessageEntity.CUSTOM_EMOJI,
                        offset=utf16_pos,
                        length=ln,
                        custom_emoji_id=str(cid),
                    )
                )
            except Exception:
                # older PTB without CUSTOM_EMOJI constant
                try:
                    entities.append(
                        MessageEntity(
                            type="custom_emoji",
                            offset=utf16_pos,
                            length=ln,
                            custom_emoji_id=str(cid),
                        )
                    )
                except Exception:
                    pass
        utf16_pos += ln
        last = m.end()
    return entities


def plain_text_from_html(html: str) -> str:
    """Rough HTML→plain for entity mode (tags stripped, entities unescaped lightly)."""
    if not html:
        return ""
    t = strip_tg_emoji_tags(html)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</p\s*>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = (
        t.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
    )
    return t


def _is_premium_rejection(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(m.lower() in msg for m in _PREMIUM_FAIL_MARKERS)


def _prepare_kwargs_for_send(text, kwargs: dict) -> tuple[Any, dict, str | None]:
    """Return (text, kwargs, mode) mode in {html_premium, entities, plain, None}."""
    if text is None:
        return text, kwargs, None
    kwargs = dict(kwargs)
    pm = kwargs.get("parse_mode")
    pm_s = str(pm).upper() if pm is not None else ""

    if "HTML" in pm_s:
        # Prefer HTML tg-emoji (keeps bold/links)
        return premium_html(str(text)), kwargs, "html_premium"

    if pm is None and kwargs.get("entities") is None:
        # plain text path — attach entities if any emoji maps
        plain = str(text)
        ents = build_custom_emoji_entities(plain)
        if ents:
            kwargs["entities"] = ents
            kwargs.pop("parse_mode", None)
            return plain, kwargs, "entities"
        return text, kwargs, None

    return text, kwargs, None


async def _call_with_fallback(orig_coro_factory, text, kwargs, mode: str | None):
    """Run send/edit; on custom-emoji rejection, retry without premium markup."""
    try:
        return await orig_coro_factory(text, kwargs)
    except Exception as e:
        if mode in {"html_premium", "entities"} and _is_premium_rejection(e):
            logger.warning(
                "premium_emoji rejected by Telegram (%s) — falling back to unicode",
                e,
            )
            kw2 = dict(kwargs)
            kw2.pop("entities", None)
            if mode == "html_premium":
                text2 = strip_tg_emoji_tags(str(text))
                # keep parse_mode HTML
            else:
                text2 = text
                kw2.pop("parse_mode", None)
            try:
                return await orig_coro_factory(text2, kw2)
            except Exception:
                raise e
        raise


def install_telegram_hooks() -> None:
    """Patch PTB send/edit so HTML (and plain) messages carry custom emoji ids."""
    try:
        from telegram import Bot, Message
        from telegram._callbackquery import CallbackQuery
    except Exception:
        logger.exception("premium_emoji: telegram not importable")
        return

    if getattr(install_telegram_hooks, "_done", False):
        return

    # —— Message.reply_text ——
    if not getattr(Message.reply_text, "_humsyar_premium", False):
        _orig = Message.reply_text

        async def reply_text(self, text=None, *args, **kwargs):
            text2, kw2, mode = _prepare_kwargs_for_send(text, kwargs)

            async def factory(t, k):
                return await _orig(self, t, *args, **k)

            return await _call_with_fallback(factory, text2, kw2, mode)

        reply_text._humsyar_premium = True  # type: ignore
        Message.reply_text = reply_text  # type: ignore

    # —— Message.edit_text ——
    if hasattr(Message, "edit_text") and not getattr(Message.edit_text, "_humsyar_premium", False):
        _orig = Message.edit_text

        async def edit_text(self, text=None, *args, **kwargs):
            text2, kw2, mode = _prepare_kwargs_for_send(text, kwargs)

            async def factory(t, k):
                return await _orig(self, t, *args, **k)

            return await _call_with_fallback(factory, text2, kw2, mode)

        edit_text._humsyar_premium = True  # type: ignore
        Message.edit_text = edit_text  # type: ignore

    # —— CallbackQuery.edit_message_text ——
    if not getattr(CallbackQuery.edit_message_text, "_humsyar_premium", False):
        _orig = CallbackQuery.edit_message_text

        async def edit_message_text(self, text=None, *args, **kwargs):
            text2, kw2, mode = _prepare_kwargs_for_send(text, kwargs)

            async def factory(t, k):
                return await _orig(self, t, *args, **k)

            return await _call_with_fallback(factory, text2, kw2, mode)

        edit_message_text._humsyar_premium = True  # type: ignore
        CallbackQuery.edit_message_text = edit_message_text  # type: ignore

    # —— Bot.send_message ——
    if not getattr(Bot.send_message, "_humsyar_premium", False):
        _orig = Bot.send_message

        async def send_message(self, chat_id, text=None, *args, **kwargs):
            text2, kw2, mode = _prepare_kwargs_for_send(text, kwargs)

            async def factory(t, k):
                return await _orig(self, chat_id, t, *args, **k)

            return await _call_with_fallback(factory, text2, kw2, mode)

        send_message._humsyar_premium = True  # type: ignore
        Bot.send_message = send_message  # type: ignore

    # —— captions (photos/docs) ——
    for meth_name in ("send_photo", "send_document", "send_animation", "send_video"):
        if not hasattr(Bot, meth_name):
            continue
        meth = getattr(Bot, meth_name)
        if getattr(meth, "_humsyar_premium", False):
            continue
        _orig_m = meth

        async def _make(orig):
            async def wrapped(self, *args, **kwargs):
                if kwargs.get("caption") is not None and kwargs.get("parse_mode"):
                    cap, kw2, mode = _prepare_kwargs_for_send(kwargs.get("caption"), kwargs)
                    kw2 = dict(kw2)
                    kw2["caption"] = cap

                    async def factory(_t, k):
                        return await orig(self, *args, **k)

                    # factory ignores text; pass kwargs only
                    try:
                        return await orig(self, *args, **kw2)
                    except Exception as e:
                        if mode == "html_premium" and _is_premium_rejection(e):
                            kw3 = dict(kw2)
                            kw3["caption"] = strip_tg_emoji_tags(str(kw2.get("caption")))
                            return await orig(self, *args, **kw3)
                        raise
                return await orig(self, *args, **kwargs)

            return wrapped

        # bind carefully
        import asyncio as _aio

        async def wrapped(self, *args, _orig=meth, **kwargs):
            if kwargs.get("caption") is not None:
                pm = kwargs.get("parse_mode")
                if pm and "HTML" in str(pm).upper():
                    kwargs = dict(kwargs)
                    kwargs["caption"] = premium_html(str(kwargs.get("caption")))
                    try:
                        return await _orig(self, *args, **kwargs)
                    except Exception as e:
                        if _is_premium_rejection(e):
                            kwargs["caption"] = strip_tg_emoji_tags(str(kwargs.get("caption")))
                            return await _orig(self, *args, **kwargs)
                        raise
            return await _orig(self, *args, **kwargs)

        wrapped._humsyar_premium = True  # type: ignore
        setattr(Bot, meth_name, wrapped)

    install_telegram_hooks._done = True  # type: ignore
    n = len(load_pack_map())
    logger.info("premium_emoji hooks installed (pack=%s)", n)


async def send_emoji_diagnostic(bot, chat_id: int) -> str:
    """Send a short premium-emoji test message; return status text for logs."""
    pack = load_pack_map()
    samples = ["🧠", "📚", "🤖", "✅", "🔥", "🎓", "💎"]
    lines = ["🧪 <b>تست ایموجی پریموم هامزیار</b>", ""]
    mapped = 0
    for u in samples:
        cid = resolve_custom_id(u)
        if cid:
            mapped += 1
            lines.append(f'{u} → <code>{cid}</code>')
        else:
            lines.append(f"{u} → map نشده")
    lines.append("")
    lines.append(f"پک: <b>{len(pack)}</b> glyph · map نمونه: <b>{mapped}/{len(samples)}</b>")
    lines.append("")
    lines.append("اگر زیر این خط ایموجی‌ها <b>متحرک</b> نیستند:")
    lines.append("۱) اکانت <b>صاحب ربات</b> باید Telegram Premium داشته باشد")
    lines.append("۲) یا ربات username فرگمنت داشته باشد")
    lines.append("۳) IDهای RestrictedEmoji فقط وقتی API قبول کند دیده می‌شوند")
    html = "\n".join(lines)
    # force premium wrap
    html = premium_html(html)
    try:
        await bot.send_message(chat_id, html, parse_mode="HTML")
        return "sent_html_ok"
    except Exception as e:
        try:
            await bot.send_message(chat_id, strip_tg_emoji_tags(html), parse_mode="HTML")
            return f"sent_fallback: {e}"
        except Exception as e2:
            return f"failed: {e} / {e2}"
