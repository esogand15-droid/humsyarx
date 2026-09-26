"""Canonical contracts for the shared Question Bank domain."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

QUESTION_STATUSES = frozenset({"pending", "approved", "rejected", "needs_changes"})
QUESTION_SOURCES = frozenset({
    "student_bot", "student_webapp", "admin_bot", "web_admin",
    "ai_student", "ai_admin_import", "system",
})
CREATOR_TYPES = frozenset({"student", "admin", "ai", "system"})
DIFFICULTY_LABELS = {
    "easy": "آسان 🟢", "medium": "متوسط 🟡", "hard": "سخت 🔴",
}
_DIFFICULTY_ALIASES = {
    "easy": "easy", "آسان": "easy", "آسان 🟢": "easy",
    "medium": "medium", "متوسط": "medium", "متوسط 🟡": "medium",
    "hard": "hard", "سخت": "hard", "سخت 🔴": "hard",
}
_SOURCE_ALIASES = {
    "webapp": "student_webapp", "web_import": "web_admin", "user": "student_bot",
    "bot": "admin_bot",
}


# 🌊 QBANK-W1 — سال آزمون: رشته‌ی ۴رقمی شمسی با بازه‌ی باز (۱۳۹۰–۱۴۳۰) تا
# سال‌های آینده بدون تغییر کد پذیرفته شوند (§۱۵.۳ نقشه‌ی راه بر §۳.۳ اولویت دارد).
EXAM_YEAR_MIN = "1390"
EXAM_YEAR_MAX = "1430"

# 🌊 QBANK-W1 — منبع محتوا (برند سؤال) — مستقل از `source` قدیمی (کانال ساخت).
CONTENT_SOURCES = {
    "hamsyar": "بانک اختصاصی همشیار",
    "konkoor_sarasari": "کنکور سراسری علوم پایه",
    "sib_sabz": "سیب سبز",
    "prognoz": "پروگنوز",
    "other": "سایر",
}
CONTENT_SOURCE_DEFAULT = "hamsyar"

# 🌊 QBANK-W1/§۱۵.۲ — رشته‌ی آزمون منبع؛ فقط ردیابی در provenance، نه فیلتر UI.
EXAM_TRACKS = frozenset({"medicine", "dentistry"})
EXAM_TRACK_DEFAULT = "medicine"

# 🌊 QBANK-W5 — نوبت آزمون (data-driven؛ سال/نوبت hard-code نمی‌شود).
# کلیدها پایدار و لاتین‌اند؛ برچسب فارسی فقط برای نمایش.
EXAM_SESSIONS = {
    "shahrivar": "شهریور",
    "esfand": "اسفند",
    "ordibehesht": "اردیبهشت",
    "mehr": "مهر",
    "azar": "آذر",
    "dey": "دی",
    "farvardin": "فروردین",
    "mordad": "مرداد",
    "other": "سایر",
}
EXAM_SESSION_DEFAULT = None  # نوبت اختیاری است؛ بدون حدس.


@dataclass
class QuestionDomainError(ValueError):
    code: str
    message: str
    status_code: int = 422
    details: dict | None = None

    def __str__(self) -> str:
        return self.message


def clean_text(value: Any, limit: int = 0) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit] if limit else text


def canonical_difficulty(value: Any, *, strict: bool = True) -> str:
    normalized = _DIFFICULTY_ALIASES.get(clean_text(value).lower())
    if normalized:
        return normalized
    if strict:
        raise QuestionDomainError("invalid_difficulty", "سطح سختی معتبر نیست")
    return "medium"


def canonical_status(document_or_value: Mapping | str | None) -> str:
    if isinstance(document_or_value, Mapping):
        status = clean_text(document_or_value.get("status"))
        if status in QUESTION_STATUSES:
            return status
        return "approved" if document_or_value.get("approved") else "pending"
    value = clean_text(document_or_value)
    return value if value in QUESTION_STATUSES else "pending"


def canonical_source(value: Any, creator_type: str = "student") -> str:
    value = clean_text(value)
    if value in QUESTION_SOURCES:
        return value
    if value in _SOURCE_ALIASES:
        return _SOURCE_ALIASES[value]
    return "system" if creator_type == "system" else "student_bot"


def canonical_exam_year(value: Any, *, strict: bool = True) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if len(text) == 4 and text.isdigit() and EXAM_YEAR_MIN <= text <= EXAM_YEAR_MAX:
        return text
    if strict:
        raise QuestionDomainError("invalid_exam_year", f"سال آزمون باید بین {EXAM_YEAR_MIN} تا {EXAM_YEAR_MAX} باشد")
    return None


def canonical_content_source(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return CONTENT_SOURCE_DEFAULT
    if text in CONTENT_SOURCES:
        return text
    raise QuestionDomainError("invalid_content_source", "منبع محتوا معتبر نیست")


def canonical_exam_track(value: Any) -> str:
    text = clean_text(value).lower()
    if text in EXAM_TRACKS:
        return text
    return EXAM_TRACK_DEFAULT


def canonical_exam_session(value: Any, *, strict: bool = True) -> str | None:
    """Normalize exam session key (shahrivar/esfand/…). Empty → None."""
    text = clean_text(value).casefold()
    if not text:
        return None
    # Persian label → key
    for key, label in EXAM_SESSIONS.items():
        if text == key or text == label or text == label.casefold():
            return key
    # Common aliases
    aliases = {
        "sep": "shahrivar", "september": "shahrivar", "شهریورماه": "shahrivar",
        "feb": "esfand", "february": "esfand", "اسفندماه": "esfand",
    }
    if text in aliases:
        return aliases[text]
    if text in EXAM_SESSIONS:
        return text
    if strict:
        raise QuestionDomainError("invalid_exam_session", "نوبت آزمون معتبر نیست")
    return None


def approved_query() -> dict:
    """Read new status and legacy approved=True without a destructive migration."""
    return {"$or": [
        {"status": "approved"},
        {"status": {"$exists": False}, "approved": True},
    ]}


def status_query(status: str) -> dict:
    if status == "approved":
        return approved_query()
    if status == "pending":
        return {"$or": [
            {"status": "pending"},
            {"status": {"$exists": False}, "approved": {"$ne": True}},
        ]}
    return {"status": status}


def and_query(*parts: dict | None) -> dict:
    valid = [part for part in parts if part]
    if not valid:
        return {}
    if len(valid) == 1:
        return valid[0]
    return {"$and": valid}


def normalized_question_text(value: Any) -> str:
    text = clean_text(value).casefold()
    text = text.translate(str.maketrans("يىكۀة", "ییکهه"))
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def question_content_hash(question: Any, options: list[Any]) -> str:
    payload = {
        "question": normalized_question_text(question),
        "options": sorted(normalized_question_text(item) for item in options),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def validate_question_payload(payload: Mapping[str, Any], *, allow_missing_answer: bool = False) -> dict:
    question = clean_text(payload.get("question"), 2000)
    if len(question) < 10:
        raise QuestionDomainError("question_too_short", "متن سؤال باید حداقل ۱۰ کاراکتر باشد")
    raw_options = payload.get("options")
    if not isinstance(raw_options, list) or len(raw_options) != 4:
        raise QuestionDomainError("four_options_required", "سؤال باید دقیقاً چهار گزینه داشته باشد")
    options = [clean_text(item, 500) for item in raw_options]
    if any(not item for item in options) or len({normalized_question_text(x) for x in options}) != 4:
        raise QuestionDomainError("unique_options_required", "چهار گزینه متفاوت و غیرخالی لازم است")
    raw_correct = payload.get("correct_answer", payload.get("correct", payload.get("correct_option")))
    correct: int | None
    if raw_correct is None or raw_correct == "":
        if allow_missing_answer:
            correct = None
        else:
            raise QuestionDomainError("invalid_correct_option", "گزینه صحیح معتبر نیست")
    else:
        try:
            correct = int(raw_correct)
        except (TypeError, ValueError):
            raise QuestionDomainError("invalid_correct_option", "گزینه صحیح معتبر نیست")
        if not 0 <= correct < 4:
            raise QuestionDomainError("invalid_correct_option", "گزینه صحیح باید بین ۱ تا ۴ باشد")
    difficulty = canonical_difficulty(payload.get("difficulty") or "medium")
    exam_year = canonical_exam_year(payload.get("exam_year"))
    content_source = canonical_content_source(payload.get("content_source"))
    confidence = clean_text(payload.get("exam_year_confidence"))
    if confidence not in {"extracted", "inferred_from_filename", "unknown"}:
        confidence = "unknown" if not exam_year else "extracted"
    return {
        "question": question,
        "options": options,
        "correct_answer": correct,
        "difficulty": difficulty,
        "explanation": clean_text(payload.get("explanation"), 4000),
        "content_hash": question_content_hash(question, options),
        "exam_year": exam_year,
        "exam_year_confidence": confidence,
        "content_source": content_source,
        "content_source_label_fa": CONTENT_SOURCES[content_source],
        "answer_missing": correct is None,
    }


def public_question(document: Mapping[str, Any], *, reveal: bool = False) -> dict:
    from .images import image_state as _image_state
    _img = _image_state(document)
    _qid = str(document.get("_id") or document.get("id") or "")
    _cs = clean_text(document.get("content_source"))
    if _cs not in CONTENT_SOURCES:
        _cs = CONTENT_SOURCE_DEFAULT
    _prov = dict(document.get("provenance") or {})
    _session_raw = document.get("exam_session") or _prov.get("exam_session")
    try:
        _session = canonical_exam_session(_session_raw, strict=False) if _session_raw else None
    except QuestionDomainError:
        _session = None
    _session_label = clean_text(document.get("exam_session_label") or _prov.get("exam_session_label")) or None
    if _session and not _session_label:
        _year = clean_text(document.get("exam_year")) or None
        fa = EXAM_SESSIONS.get(_session, _session)
        if _year:
            y_fa = _year.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
            _session_label = f"{fa} {y_fa}"
        else:
            _session_label = fa
    result = {
        "id": str(document.get("_id") or document.get("id") or ""),
        "lesson_id": str(document.get("lesson_id") or ""),
        "topic_id": str(document.get("topic_id") or ""),
        "lesson": clean_text(document.get("lesson")),
        "topic": clean_text(document.get("topic")),
        "difficulty": canonical_difficulty(document.get("difficulty"), strict=False),
        "difficulty_label": DIFFICULTY_LABELS[canonical_difficulty(document.get("difficulty"), strict=False)],
        "question": clean_text(document.get("question")),
        "options": [str(x) for x in (document.get("options") or [])],
        "source": canonical_source(document.get("source"), clean_text(document.get("creator_type"))),
        "creator_type": clean_text(document.get("creator_type")) or "student",
        "provenance": _prov,
        "exam_year": clean_text(document.get("exam_year")) or None,
        "exam_year_confidence": clean_text(document.get("exam_year_confidence")) or "unknown",
        "exam_session": _session,
        "exam_session_label": _session_label,
        "content_source": _cs,
        "content_source_label_fa": CONTENT_SOURCES[_cs],
        "exam_track": canonical_exam_track(_prov.get("exam_track")),
        "image": {"has_image": _img["has_image"], "pending_upload": _img["pending_upload"],
                  "alt_text": _img["alt_text"]},
        "image_url": (f"/api/questions/image/{_qid}"
                      if (_img["has_image"] and not _img["pending_upload"] and _qid) else None),
    }
    if reveal:
        result.update({
            "correct_answer": int(document.get("correct_answer", 0) or 0),
            "explanation": clean_text(document.get("explanation")),
        })
    return result
