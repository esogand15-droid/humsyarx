"""🌊 QBANK-W3 — دامنه تصویر سؤال.

مدل ذخیره‌سازی (§۷.۱): همان الگوی `bs_content` ولی کالکشن جدا
(`question_images`) چون رکورد bs_content به session گره خورده و منطق
نوتیف/ترتیب خودش را دارد؛ قاطی‌کردن تصویر سؤال با منابع درسی، لیست
منابع و نوتیف‌ها را آلوده می‌کند. بایت‌ها در تلگرام‌اند (file_id) و
اینجا فقط ارجاع + متادیتا نگه داشته می‌شود:

- آپلود وب‌ادمین → `upload_and_get_file_id` → `attach`
- ربات → مستقیم با file_id از `send_photo` استفاده می‌کند (بدون دانلود)
- مینی‌اپ/PDF → `resolve_file` + `download_telegram_file` در لایه API
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from bson import ObjectId

from time_utils import utc_now_iso
from .contracts import QuestionDomainError, clean_text

ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
# کپشن تلگرام ~۱۰۲۴ کاراکتر است؛ ۹۰۰ حاشیه امن برای HTML/entity است.
PHOTO_CAPTION_LIMIT = 900

_BULK_RE = re.compile(r"^([0-9a-f]{8,64})[_-](\d{1,5})$", re.IGNORECASE)


def image_state(document: Mapping[str, Any]) -> dict:
    """وضعیت نرمال تصویر؛ tolerant نسبت به شکل legacy (pre-W1)."""
    image = document.get("image")
    if not isinstance(image, dict):
        return {"has_image": False, "pending_upload": False,
                "alt_text": None, "storage_ref": None}
    if image.get("required") or clean_text(image.get("description")):
        return {"has_image": True, "pending_upload": True,
                "alt_text": clean_text(image.get("description")) or None,
                "storage_ref": None}
    return {"has_image": bool(image.get("has_image")),
            "pending_upload": bool(image.get("pending_upload")),
            "alt_text": clean_text(image.get("alt_text")) or None,
            "storage_ref": image.get("storage_ref") or None}


def validate_image_upload(*, mime_type: str, size: int) -> str:
    """اعتبارسنجی آپلود؛ خروجی mime نرمال‌شده است."""
    mime = (mime_type or "").strip().lower().split(";")[0]
    if mime not in ALLOWED_IMAGE_MIMES:
        raise QuestionDomainError("unsupported_image_type",
                                  "فقط تصویر JPEG/PNG/WebP/GIF مجاز است", 415)
    if size <= 0 or size > MAX_IMAGE_BYTES:
        raise QuestionDomainError("image_too_large",
                                  "حجم تصویر باید کمتر از ۱۰ مگابایت باشد", 413)
    return mime


def parse_bulk_filename(file_name: str) -> tuple[str, int] | None:
    """نام‌گذاری bulk (§۷.۲): `{fingerprint}_{page}.png` → (پیشوند fp، صفحه).

    پیشوند حداقل ۸ کاراکتر hex است (fingerprint کامل ۶۴ کاراکتری لازم
    نیست؛ تطبیق با startswith روی job همان batch انجام می‌شود).
    """
    stem = clean_text(file_name).rsplit(".", 1)[0].rsplit("/", 1)[-1]
    match = _BULK_RE.match(stem)
    if not match:
        return None
    return match.group(1).lower(), int(match.group(2))


def split_photo_caption(html_text: str, limit: int = PHOTO_CAPTION_LIMIT) -> tuple[str, bool]:
    """کپشن امن برای send_photo؛ خروجی (caption، آیا پیام دوم لازم است).

    وقتی متن از سقف می‌گذرد، عکس با کپشن کوتاه می‌رود و متن کامل در
    پیام بعدی با دکمه‌ها ارسال می‌شود (§۷.۳).
    """
    text = html_text or ""
    if len(text) <= limit:
        return text, False
    return text[:limit] + "…", True


class QuestionImageService:
    def __init__(self, database):
        self.db = database

    async def attach(self, *, question_id: str, file_id: str, admin_id: int,
                     mime_type: str, size: int, original_name: str = "") -> dict:
        """اتصال/جایگزینی تصویر یک سؤال؛ pending را می‌بندد."""
        if not ObjectId.is_valid(str(question_id)):
            raise QuestionDomainError("invalid_question_id", "شناسه سؤال معتبر نیست")
        mime = validate_image_upload(mime_type=mime_type, size=size)
        question = await self.db.questions.find_one({"_id": ObjectId(str(question_id))})
        if not question:
            raise QuestionDomainError("question_not_found", "سؤال پیدا نشد", 404)
        now = utc_now_iso()
        record = {"question_id": str(question["_id"]), "file_id": file_id,
                  "mime_type": mime, "file_size": int(size),
                  "original_name": clean_text(original_name, 200),
                  "uploaded_by": int(admin_id or 0), "uploaded_at": now}
        existing = await self.db.question_images.find_one({"question_id": str(question["_id"])})
        if existing:
            await self.db.question_images.update_one({"_id": existing["_id"]}, {"$set": record})
            image_id = existing["_id"]
        else:
            image_id = (await self.db.question_images.insert_one(record)).inserted_id
        state = image_state(question)
        await self.db.questions.update_one(
            {"_id": question["_id"]},
            {"$set": {"image": {"has_image": True, "pending_upload": False,
                                "storage_ref": str(image_id),
                                "alt_text": state["alt_text"]},
                      "updated_at": now}})
        return {"ok": True, "question_id": str(question["_id"]),
                "storage_ref": str(image_id), "replaced": bool(existing)}

    async def detach(self, *, question_id: str, admin_id: int) -> dict:
        """برگرداندن سؤال به صف انتظار (تصویر اشتباه)؛ رکورد برای ممیزی می‌ماند."""
        if not ObjectId.is_valid(str(question_id)):
            raise QuestionDomainError("invalid_question_id", "شناسه سؤال معتبر نیست")
        question = await self.db.questions.find_one({"_id": ObjectId(str(question_id))})
        if not question:
            raise QuestionDomainError("question_not_found", "سؤال پیدا نشد", 404)
        state = image_state(question)
        if not state["has_image"]:
            raise QuestionDomainError("no_image_attached", "این سؤال تصویری ندارد", 409)
        await self.db.questions.update_one(
            {"_id": question["_id"]},
            {"$set": {"image.pending_upload": True, "updated_at": utc_now_iso()}})
        await self.db.question_images.update_many(
            {"question_id": str(question["_id"])},
            {"$set": {"detached_at": utc_now_iso(), "detached_by": int(admin_id or 0)}})
        return {"ok": True, "question_id": str(question["_id"])}

    async def resolve_file(self, question_id: str) -> dict | None:
        """file_id تلگرام برای ارسال/دانلود؛ pending یا بدون تصویر → None."""
        if not ObjectId.is_valid(str(question_id)):
            return None
        question = await self.db.questions.find_one(
            {"_id": ObjectId(str(question_id))},
            {"image": 1, "status": 1, "intake": 1})
        if not question:
            return None
        state = image_state(question)
        if not state["has_image"] or state["pending_upload"] or not state["storage_ref"]:
            return None
        record = await self.db.question_images.find_one(
            {"question_id": str(question["_id"])}, {"file_id": 1, "mime_type": 1})
        if not record or not record.get("file_id"):
            return None
        return {"file_id": record["file_id"],
                "mime_type": record.get("mime_type") or "image/jpeg",
                "alt_text": state["alt_text"]}

    async def pending_queue(self, *, job_id: str | None = None,
                            skip: int = 0, limit: int = 50) -> dict:
        """صف تصاویر منتظر (§۷.۲)؛ قدیمی‌ترین اول (FIFO اپراتوری)."""
        query: dict = {"image.pending_upload": True}
        if job_id:
            query["import_job_id"] = job_id
        total = await self.db.questions.count_documents(query)
        docs = await self.db.questions.find(query).sort("created_at", 1).skip(skip).limit(limit).to_list(limit)
        items = [{
            "id": str(d.get("_id")), "question": clean_text(d.get("question"), 200),
            "lesson": d.get("lesson", ""), "topic": d.get("topic", ""),
            "exam_year": d.get("exam_year"), "status": d.get("status", ""),
            "job_id": d.get("import_job_id"), "source_file_name": d.get("source_file_name", ""),
            "source_page": d.get("source_page"), "image_ref": d.get("image_ref"),
            "created_at": d.get("created_at"),
        } for d in docs]
        return {"items": items, "total": total, "skip": skip, "limit": limit}


async def ensure_qbank_w3_indexes(database) -> dict:
    names = []
    names.append(await database.question_images.create_index(
        [("question_id", 1)], name="qbank_w3_image_question", unique=True))
    names.append(await database.question_images.create_index(
        [("uploaded_at", -1)], name="qbank_w3_image_uploaded"))
    return {"indexes": names}
