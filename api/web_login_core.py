# -*- coding: utf-8 -*-
"""🔐 هستهٔ ورود وب (PWA) — منطق خالص، بدون دیتابیس.

چرا جدا از روتر؟
────────────────
همهٔ چیزهایی که «باید درست باشند» (هش کد، مقایسهٔ ثابت‌زمان، انقضای
نشست، نرمال‌سازی شناسه، محدودیت نرخ) در این فایل‌اند تا بدون Mongo و
بدون FastAPI هم قابل تست باشند. روتر فقط ارکستراسیون می‌کند.

قراردادها
─────────
* کد یک‌بارمصرف ۶ رقمی، ذخیره‌شده به‌صورت ``sha256(salt:code)``.
* مقایسه همیشه ``compare_digest`` (ضدِ حملهٔ زمان‌سنجی).
* نشست: توکن تصادفی ۳۲ بایتی؛ در دیتابیس فقط **هش** آن ذخیره می‌شود.
* هیچ پیام خطایی «وجود/عدم‌وجود حساب» را لو نمی‌دهد.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, Optional, Tuple

# ── ثابت‌های قرارداد ──────────────────────────────────────────────
OTP_LENGTH = 6
OTP_TTL_MIN = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SEC = 60
SESSION_COOKIE = "hu_session"
SESSION_TTL_DAYS = 30
SESSION_TTL_DAYS_MAX = 90

#: پیام یکسان برای «ارسال شد» — عمداً دربارهٔ وجود حساب چیزی نمی‌گوید.
GENERIC_REQUEST_MESSAGE = (
    "اگر این حساب در هامزیار ثبت شده و تأیید شده باشد، "
    "کد ورود در تلگرام برایتان ارسال می‌شود."
)
GENERIC_CODE_ERROR = "کد نامعتبر یا منقضی است."

_IDENT_MAX = 64


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_identifier(raw: str) -> str:
    """شناسهٔ ورود را نرمال می‌کند: حذف فاصله، @ ابتدایی، ارقام فارسی."""
    text = str(raw or "").strip()
    if not text:
        return ""
    text = _to_ascii_digits(text)
    text = text.replace("\u200c", "").replace(" ", "")
    text = text.lstrip("@")
    return text[:_IDENT_MAX]


_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def _to_ascii_digits(text: str) -> str:
    out = []
    for ch in text:
        if ch in _FA_DIGITS:
            out.append(str(_FA_DIGITS.index(ch)))
        elif ch in _AR_DIGITS:
            out.append(str(_AR_DIGITS.index(ch)))
        else:
            out.append(ch)
    return "".join(out)


def is_numeric_identifier(value: str) -> bool:
    return bool(value) and value.lstrip("-").isdigit()


def make_code() -> str:
    """کد ۶ رقمی با ``secrets`` (نه ``random``)."""
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


def make_salt() -> str:
    return secrets.token_hex(16)


def hash_code(salt: str, code: str) -> str:
    return hashlib.sha256(f"{salt}:{str(code or '').strip()}".encode("utf-8")).hexdigest()


def code_matches(salt: str, code: str, stored_hash: str) -> bool:
    """مقایسهٔ ثابت‌زمان؛ برای salt خالی هم مقاوم است."""
    if not stored_hash:
        return False
    salt = str(salt or "")
    candidate = hash_code(salt, code) if salt else hashlib.sha256(
        str(code or "").strip().encode("utf-8")).hexdigest()
    return secrets.compare_digest(candidate, str(stored_hash))


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def session_ttl_days() -> int:
    import os
    try:
        days = int(os.getenv("WEB_SESSION_TTL_DAYS", str(SESSION_TTL_DAYS)) or SESSION_TTL_DAYS)
    except (TypeError, ValueError):
        days = SESSION_TTL_DAYS
    return max(1, min(days, SESSION_TTL_DAYS_MAX))


def expiry_from_now(minutes: int = OTP_TTL_MIN) -> datetime:
    return now_utc() + timedelta(minutes=minutes)


def is_past(moment) -> bool:
    """True اگر زمان داده‌شده در گذشته باشد (نوع نامعتبر = منقضی)."""
    if not isinstance(moment, datetime):
        return True
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment <= now_utc()


def seconds_until(moment) -> int:
    if not isinstance(moment, datetime):
        return 0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0, int((moment - now_utc()).total_seconds()))


class SlidingWindowLimiter:
    """محدودکنندهٔ نرخ درون‌فرآیندی (پنجرهٔ لغزان).

    صادقانه: در استقرار چند-ورکری، این محدودیت فقط per-process است.
    برای همین در روتر یک «فاصلهٔ ارسال مجدد» دیتابیسی هم اعمال می‌شود
    که بین همهٔ ورکرها مشترک است.
    """

    def __init__(self, limit: int, window_sec: int) -> None:
        self.limit = max(1, int(limit))
        self.window_sec = max(1, int(window_sec))
        self._hits: Dict[str, Deque[float]] = {}

    def allow(self, key: str, at: Optional[float] = None) -> bool:
        stamp = time.monotonic() if at is None else float(at)
        bucket = self._hits.setdefault(key, deque())
        edge = stamp - self.window_sec
        while bucket and bucket[0] <= edge:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(stamp)
        if len(self._hits) > 4096:  # سقف حافظه — کلیدهای بی‌مصرف
            for stale in [k for k, v in self._hits.items() if not v][:1024]:
                self._hits.pop(stale, None)
        return True

    def reset(self, key: Optional[str] = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)


#: نرخ‌ها: هر شناسه ۵ درخواست/۱۰ دقیقه، هر IP ۱۵ درخواست/۱۰ دقیقه.
IDENT_LIMITER = SlidingWindowLimiter(limit=5, window_sec=600)
IP_LIMITER = SlidingWindowLimiter(limit=15, window_sec=600)


def request_allowed(identifier: str, ip: str) -> bool:
    """ترتیب بررسی: اول IP (جلوگیری از انفجار)، بعد شناسه."""
    if not IP_LIMITER.allow(f"ip:{ip or '-'}"):
        return False
    return IDENT_LIMITER.allow(f"id:{identifier or '-'}")


def mask_identifier(value: str) -> str:
    """برای نمایش در UI/لاگ — هرگز شناسهٔ کامل را برنگردان."""
    text = str(value or "")
    if len(text) <= 3:
        return "*" * len(text)
    return f"{text[0]}{'*' * (len(text) - 2)}{text[-1]}"


_PHONE_RE = re.compile(r"^0?9\d{9}$")


def looks_like_phone(value: str) -> bool:
    return bool(_PHONE_RE.match(_to_ascii_digits(str(value or "")).replace(" ", "")))
