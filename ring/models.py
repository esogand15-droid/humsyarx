"""💍 Ring Street — مدل داده، اعتبارسنجی و ماشین حالت (§۲، §۳، §۱۱، §۲۶)

هیچ‌جا «احراز هویت سن» نمی‌کنیم؛ خوداظهاری است و در متن هم صریح
نوشته می‌شود (§۲). سن دقیق فقط در DB می‌ماند و در UI حلقه‌ی سنی نشان
داده می‌شود — مگر در حالت reveal دوطرفه (§۲۷).
"""
from __future__ import annotations

import re

# ── حلقه‌های سنی (کلید، برچسب، min، max) ──────────────────────
AGE_RANGES = [
    ("18-20", "۱۸–۲۰", 18, 20),
    ("21-23", "۲۱–۲۳", 21, 23),
    ("24-26", "۲۴–۲۶", 24, 26),
    ("27-30", "۲۷–۳۰", 27, 30),
    ("31-35", "۳۱–۳۵", 31, 35),
    ("36+",  "۳۶+",    36, 99),
]
AGE_INDEX = {k: (lo, hi) for k, _, lo, hi in AGE_RANGES}
AGE_LABELS = {k: lbl for k, lbl, _, _ in AGE_RANGES}

GENDERS = {"male": "👨 پسر", "female": "👩 دختر"}
MODES = {"serious": "💍 آشنایی جدی", "fun": "🎭 رینگ فان"}
INTENTS = {"marriage": "💍 ازدواج", "serious": "❤️ رابطه جدی", "first": "🤝 آشنایی اولیه"}
TOPICS = {
    "university": "🎓 دانشگاه", "game": "🎮 بازی", "movie": "🎬 فیلم",
    "music": "🎵 موسیقی", "fun": "😂 فان", "free": "🧠 بحث آزاد", "random": "🎲 رندوم",
}
PROFILE_FIELDS = {
    "bio":        ("درباره من", 300),
    "interests":  ("علایق", 160),
    "city":       ("شهر", 60),
    "university": ("دانشگاه", 80),
    "major":      ("رشته", 80),
}
REPORT_REASONS = {                      # کلید → (برچسب، severity §۲۳)
    "insult":         ("🚫 توهین و ناسزا", 1),
    "sexual_content": ("🔞 محتوای جنسی", 3),
    "spam":           ("📢 تبلیغات / اسپم", 1),
    "harassment":     ("😡 آزار و اذیت", 2),
    "scam":           ("🎣 کلاهبرداری / سوءاستفاده", 4),
    "suspicious":     ("⚠️ رفتار مشکوک", 2),
    "other":          ("📝 سایر", 1),
}
RATINGS = {"great": 5, "good": 4, "mid": 3, "bad": 2, "worst": 1}
ICEBREAKERS = [
    "🎓 رشته‌ات چیه؟", "🎵 آخرین آهنگی که گوش دادی؟", "🎬 فیلم محبوبت؟",
    "☕ قهوه یا چای؟", "😂 عجیب‌ترین اتفاق دانشگاه؟", "💭 یک سوال تصادفی",
]

# ── ماشین حالت (§۱۱) ──────────────────────────────────────────
(IDLE, AGE_GATE, GENDER_PICK, MODE_PICK, TERMS, PROFILE,
 CHATTING, REPORT_WHY, BLOCK_CONFIRM, PAUSED, BANNED) = (
    "IDLE", "AGE_GATE", "GENDER_PICK", "MODE_PICK", "TERMS", "PROFILE",
    "CHATTING", "REPORT_WHY", "BLOCK_CONFIRM", "PAUSED", "BANNED")

TRANSITIONS: dict[str, set[str]] = {
    IDLE: {AGE_GATE, PROFILE, PAUSED},
    AGE_GATE: {GENDER_PICK, IDLE, BANNED},
    GENDER_PICK: {MODE_PICK, IDLE, BANNED},
    MODE_PICK: {TERMS, PROFILE, IDLE, BANNED},
    TERMS: {PROFILE, IDLE, BANNED},
    PROFILE: {IDLE, MODE_PICK, BANNED},
    CHATTING: {IDLE, PAUSED, BANNED, REPORT_WHY, BLOCK_CONFIRM},
    REPORT_WHY: {CHATTING, IDLE, BLOCK_CONFIRM},
    BLOCK_CONFIRM: {IDLE, CHATTING},
    PAUSED: {IDLE, PROFILE},
    BANNED: {IDLE},
}


def can_move(frm: str | None, to: str) -> bool:
    """ترنزیشن مجاز است؟ حالت ناشناخته ⇒ فقط به IDLE برگردیم (fail-safe)."""
    if not frm or frm == to:
        return True
    return to in TRANSITIONS.get(frm, {IDLE})


def age_ok(age, min_age: int = 18) -> bool:
    try:
        a = int(age)
    except (TypeError, ValueError):
        return False
    return min_age <= a <= 99


def range_of(age: int) -> str:
    for key, _, lo, hi in AGE_RANGES:
        if lo <= int(age) <= hi:
            return key
    return AGE_RANGES[0][0]


def ranges_overlap(a: str | None, b: str | None) -> bool:
    """تداخل دو حلقه (هیچکدام = محدودیتی نیست)."""
    if not a or not b or a == "any" or b == "any":
        return True
    alo, ahi = AGE_INDEX.get(a, (0, 0))
    blo, bhi = AGE_INDEX.get(b, (0, 0))
    return not (ahi < blo or bhi < alo)


def age_range_matches(cand_range: str | None, pref_key: str | None) -> bool:
    """preference طرف مقابل: `pref_key` یکی از کلیدهای AGE_RANGES یا
    ترکیبی ('18-20,21-23') یا None است."""
    if not pref_key or pref_key == "any":
        return True
    keys = [k.strip() for k in str(pref_key).split(",") if k.strip()]
    if not keys:
        return True
    return any(ranges_overlap(cand_range, k) for k in keys)


def gender_matches(cand_gender: str | None, pref: str | None) -> bool:
    if not pref or pref in ("any", "", None):
        return True
    return cand_gender == pref


def norm_choice(v, allowed: dict | list | tuple, default=None):
    if isinstance(allowed, dict):
        allowed = list(allowed.keys())
    else:
        allowed = list(allowed)
    if v in allowed:
        return v
    low = str(v or "").strip().lower()
    for a in allowed:
        if str(a).lower() == low:
            return a
    return default


_TEXT_CLEAN = re.compile(r"[\u200b-\u200f\u202a-\u202e<>]")


def clean_text(v, limit: int = 300) -> str:
    """حذف کاراکترهای بی‌نام/RTL-override و تگ — جلوگیری از جعل ظاهری
    و از کارافتادن HTML تلگرام."""
    s = _TEXT_CLEAN.sub("", str(v or ""))
    s = " ".join(s.split())
    return s[:limit]


def has_leak(text: str) -> str | None:
    """§۲۸ — تشخیص ساده‌ی اطلاعات هویتی. هشدار می‌دهد، جلو نمی‌گیرد
    (هیچ فیلتری ۱۰۰٪ نیست و نباید توهم امنیت ایجاد کنیم)."""
    t = str(text or "")
    if re.search(r"(?<!\d)0?9\d{9}(?!\d)", t):
        return "شماره تلفن"
    if re.search(r"@[A-Za-z][A-Za-z0-9_]{4,31}", t):
        return "آیدی تلگرام"
    if re.search(r"\b\d{10,11}\b", t):
        return "شمارهٔ عددی"
    if re.search(r"https?://\S+", t, re.I) or re.search(r"(tg://|t\.me/)", t, re.I):
        return "لینک"
    if re.search(r"\b\d{10}\b|\b\d{3}-?\d{2}-?\d{2}-?\d{6}\b", t):
        return "کد ملی"
    return None
