# -*- coding: utf-8 -*-
"""
🔐 هسته — دسترسی و اشتراک (واحد در Bot / API / MiniApp) — W8

تنها پیاده‌سازی قانون has_access کل محصول این‌جاست.
subscription.py و api/auth.py فقط thin-wrapper هستند و به همین ماژول تفویض می‌کنند.
ترتیب دقیق عین ربات سابق: enforce خاموش → allowed، ADMIN_ID → allowed، وگرنه sub_is_active.
"""
from dataclasses import dataclass
from typing import Optional
import os
from database import db
from .errors import Code, DEFAULT_MESSAGE

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
except Exception:
    ADMIN_ID = 0

@dataclass
class AccessResult:
    allowed: bool
    code: Optional[str] = None
    message: str = ""
    is_owner: bool = False

async def has_access(uid: int) -> AccessResult:
    """قرارداد واحد has_access با code ماشین‌خوان."""
    uid = int(uid)
    try:
        enforced = await db.get_setting('subscription_enforced', False)
    except Exception:
        enforced = False
    if not enforced:
        return AccessResult(allowed=True)
    if uid == ADMIN_ID:
        return AccessResult(allowed=True, is_owner=True)
    try:
        if await db.sub_is_active(uid):
            return AccessResult(allowed=True)
    except Exception:
        pass
    # دلیل نداشتن دسترسی
    try:
        sub = await db.sub_get(uid)
        if sub:
            status = (sub.get('status') or '').lower()
            if status == 'pending':
                return AccessResult(allowed=False, code=Code.SUB_PENDING, message=DEFAULT_MESSAGE[Code.SUB_PENDING])
            if status in ('expired', 'cancelled', 'revoked'):
                return AccessResult(allowed=False, code=Code.SUB_EXPIRED, message=DEFAULT_MESSAGE[Code.SUB_EXPIRED])
    except Exception:
        pass
    return AccessResult(allowed=False, code=Code.SUB_REQUIRED, message=DEFAULT_MESSAGE[Code.SUB_REQUIRED])

# سازگار با کد قدیم که bool انتظار داشت
async def has_access_bool(uid: int) -> bool:
    return (await has_access(uid)).allowed

async def require_access(uid: int):
    res = await has_access(int(uid))
    if not res.allowed:
        from fastapi import HTTPException
        raise HTTPException(status_code=402, detail={"code": res.code, "message": res.message})
    return res
