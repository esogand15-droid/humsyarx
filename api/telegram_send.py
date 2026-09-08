"""📤 ارسال فایل به کاربر از طریق ربات — دقیقاً مطابق فرمتی که خود ربات
(basic_science.py و references.py) استفاده می‌کنه: کپشن رسمی، دکمه‌ی
گزارش ایراد/بازگشت، و انتخاب نوع پیام بر اساس نوع فایل."""
import logging
import os
import httpx
from database import db

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

CONTENT_ICONS = {
    "video": "🎥 ویدیو کلاس",
    "ppt":   "📊 پاورپوینت",
    "pdf":   "📄 جزوه PDF",
    "note":  "📝 نکات",
    "test":  "🧪 تست",
    "voice": "🎙 ویس استاد",
}


async def upload_and_get_file_id(chat_id: int, filename: str, file_bytes: bytes,
                                  mime_type: str = "application/octet-stream") -> str | None:
    """
    آپلود فایل خام (که از مرورگر اومده) به تلگرام تا یه file_id قابل‌استفاده
    برگرده — چون تلگرام فقط فایلی که از طریق خود ربات فرستاده بشه رو
    file_id میده؛ آپلود مستقیم HTTP از مرورگر همچین چیزی تولید نمی‌کنه.
    فایل به‌صورت بی‌صدا برای خود ادمینی که آپلود کرده فرستاده می‌شه.

    🐛 FIX آپلود ویدیو — دو تغییر ریشه‌ای:
    ۱) timeout ساخت‌یافته: عدد ثابت ۶۰ برای ویدیوهای چندده‌مگابایتی
       کم بود (هم آپلود write و هم انتظار پاسخ تلگرام read). حالا هر
       مرحله کرانه‌ی مستقل و متناسب با فایل بزرگ دارد.
    ۲) علت واقعی شکست دیگر بلعیده نمی‌شود: status/description تلگرام و
       نوع خطای شبکه لاگ می‌شود (بدون token/URL — هرگز secret لاگ
       نمی‌شود) تا «آپلود ناموفق» در لاگ سرور قابل تشخیص باشد.
    """
    if not BOT_TOKEN:
        logger.warning("UPLOAD_FAILED stage=storage reason=missing_bot_token")
        return None
    size = len(file_bytes)
    try:
        timeout = httpx.Timeout(connect=15.0, read=180.0, write=300.0,
                                pool=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{API_BASE}/sendDocument",
                data={"chat_id": chat_id, "disable_notification": True},
                files={"document": (filename, file_bytes, mime_type)},
            )
    except httpx.HTTPError as e:
        # نوع خطا کافی است — URL حاوی token است و هرگز لاگ نمی‌شود
        logger.warning(
            "UPLOAD_FAILED stage=storage reason=telegram_http_error "
            "err=%s size=%s mime=%s", type(e).__name__, size, mime_type)
        return None
    if resp.status_code != 200:
        try:
            desc = str(resp.json().get("description") or "")[:200]
        except Exception:
            desc = ""
        logger.warning(
            "UPLOAD_FAILED stage=storage reason=telegram_status "
            "status=%s desc=%s size=%s mime=%s",
            resp.status_code, desc, size, mime_type)
        return None
    data = resp.json()
    if not data.get("ok"):
        logger.warning(
            "UPLOAD_FAILED stage=storage reason=telegram_not_ok size=%s",
            size)
        return None
    logger.info("STORAGE_UPLOAD_COMPLETED size=%s mime=%s", size, mime_type)
    return data["result"]["document"]["file_id"]


async def _send(method: str, payload: dict) -> bool:
    if not BOT_TOKEN:
        return False
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{API_BASE}/{method}", json=payload)
    if resp.status_code != 200:
        return False
    return bool(resp.json().get("ok"))


async def send_bs_content(chat_id: int, content_id: str, item: dict) -> bool:
    """محتوای علوم پایه — دقیقاً مثل _download_content توی basic_science.py"""
    ctype = item.get("type", "pdf")
    parts = [CONTENT_ICONS.get(ctype, "📎")]
    if item.get("description"):
        parts.append(f"📝 {item['description']}")
    if item.get("extra_info"):
        parts.append(item["extra_info"])
    parts.append(f"📥 {item.get('downloads', 0)} دانلود")
    caption = "\n".join(parts)

    protect = await db.get_setting("protect_content_enabled", True)
    reply_markup = {"inline_keyboard": [[
        {"text": "⚠️ گزارش ایراد", "callback_data": f"report:resource:{content_id}"}
    ]]}
    file_id = item.get("file_id", "")

    base = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML",
            "reply_markup": reply_markup, "protect_content": protect}

    if ctype == "video":
        return await _send("sendVideo", {**base, "video": file_id})
    if ctype == "voice":
        return await _send("sendVoice", {**base, "voice": file_id})
    return await _send("sendDocument", {**base, "document": file_id})


async def send_ref_file(chat_id: int, item: dict) -> bool:
    """رفرنس/منبع — دقیقاً مثل _download_ref توی references.py"""
    lang = item.get("lang", "fa")
    vol  = item.get("volume", 1)
    desc = item.get("description", "")
    dl   = item.get("downloads", 0)

    lang_icon  = "🇮🇷" if lang == "fa" else "🌐"
    lang_label = "ترجمه فارسی" if lang == "fa" else "نسخه لاتین (اصلی)"

    caption_parts = [f"📘 {lang_icon} {lang_label} — جلد {vol}"]
    if desc:
        caption_parts.append(f"📝 {desc}")
    caption_parts.append(f"📥 {dl} دانلود")
    caption = "\n".join(caption_parts)

    protect = await db.get_setting("protect_content_enabled", True)
    book_id = str(item.get("book_id", ""))
    reply_markup = None
    if book_id:
        reply_markup = {"inline_keyboard": [[
            {"text": "🔙 بازگشت به کتاب", "callback_data": f"ref:book:{book_id}"}
        ]]}

    payload = {"chat_id": chat_id, "document": item.get("file_id", ""),
               "caption": caption, "parse_mode": "HTML", "protect_content": protect}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return await _send("sendDocument", payload)
