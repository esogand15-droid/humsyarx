# -*- coding: utf-8 -*-
"""🔌 پروب مشترک MongoDB برای تست‌ها.

چرا این فایل وجود دارد
──────────────────────
۱۶ فایل تست یک تابع `_mongo_available()` تکراری داشتند که URI را با
`uri[len("mongodb://"):].partition(":")` پارس می‌کرد. این پارس ساده با
URI استانداردِ دارای نام دیتابیس (`mongodb://127.0.0.1:27017/humsyar`)
می‌شکست:

    ValueError: invalid literal for int() with base 10: '27017/humsyar'

و چون فراخوانی در زمان **import** و روی دکوریتور `skipUnless` است،
کل فایل تست در مرحلهٔ بارگذاری خطا می‌داد (`unittest.loader._FailedTest`)
— یعنی ۱۲ فایل و ~۱۶۰ تست به‌جای «skip» به «error» تبدیل می‌شدند.
این همان چیزی بود که در ممیزی، تعداد تست‌ها را از ۵۵۳ به ۳۹۰ کاهش
می‌داد. پارس درست، هم تست‌ها را برمی‌گرداند و هم سیگنال CI را صادق
می‌کند.

قاعدهٔ ایمنی
────────────
فقط میزبان‌های محلی (127.0.0.1 / localhost / ::1) پروب می‌شوند؛ هر URI
دیگری — به‌ویژه Production — بدون هیچ تلاشی `False` می‌شود.
"""
from __future__ import annotations

import os
import socket
from urllib.parse import parse_qs, urlsplit

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _parse(uri: str) -> tuple[str, int] | None:
    """(host, port) را از URI مونگو درمی‌آورد؛ در هر حالت دیگری None."""
    if not uri:
        return None
    try:
        parts = urlsplit(uri if "://" in uri else "mongodb://" + uri)
    except ValueError:
        return None
    if parts.scheme not in ("mongodb", "mongodb+srv"):
        return None

    host = (parts.hostname or "").strip()
    if not host:
        return None
    # mongodb+srv رکورد SRV دارد و با سوکت ساده پروب نمی‌شود
    if parts.scheme == "mongodb+srv":
        return None

    port: int | None = None
    try:
        port = parts.port
    except ValueError:            # پورت غیرعددی در URI
        return None
    if port is None:
        q = parse_qs(parts.query)
        raw = (q.get("port") or [""])[0]
        try:
            port = int(raw) if raw else 27017
        except (TypeError, ValueError):
            port = 27017
    return host, int(port)


def mongo_available(timeout: float = 1.0) -> bool:
    """آیا یک MongoDB محلی واقعاً در دسترس است؟ (هرگز raise نمی‌کند)"""
    try:
        parsed = _parse(os.getenv("MONGODB_URI", "").strip())
        if not parsed:
            return False
        host, port = parsed
        if host not in _LOCAL_HOSTS:
            return False          # عمداً Production پروب نمی‌شود
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
    except Exception:             # هر خطای غیرمنتظره = «در دسترس نیست»
        return False
