"""👑 Admin Panel"""
import asyncio
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from api.auth import get_admin_user
from database import db

router = APIRouter()
ADMIN_ID = int(os.getenv("ADMIN_ID","0"))


async def _notify(chat_id: int, text: str, ntype: str = "admin_notice"):
    # 🌊 W-Admin-fix: قبلاً coroutine اینسرت هرگز await نمی‌شد ⇒ همه‌ی اعلان‌های
    # این روتر (تأیید کاربر، پاسخ تیکت، سیگنال‌ها) سکوت-coroutine می‌شدند.
    notif = db.client["medicalbot"]["bot_notifications"]
    return await notif.insert_one({"type":ntype,"chat_id":chat_id,"text":text,
        "sent":False,"created_at":datetime.now().isoformat()})


async def _audit(admin, action: str, module: str, *, severity: str = "INFO",
                 target_id: str = "", target_type: str = "",
                 target_label: str = "", details: str = "",
                 before: dict = None, after: dict = None,
                 tags: list = None):
    """ثبت رویداد در audit_logs برای اقدامات انجام‌شده از پنل وب +
    ارسال همان رویداد به گروه لاگ تلگرام از طریق صف bot_notifications.

    مقادیر به‌صورت موضعی (positional) به db.log_action داده می‌شوند تا
    دقیقاً با امضای موجود در database.py سازگار بمانند.

    FIX سینک: قبلاً لاگ‌های وب فقط در دیتابیس می‌ماندند و گروه لاگ
    تلگرام هرگز اقدامات پنل وب را نمی‌دید (فقط لاگ‌های ربات را).
    حالا متن با همان build_audit_log_text مشترکِ ربات ساخته می‌شود و به
    گروه log_group_admin صف می‌شود — قالب پیام در گروه برای هر دو کانال
    کاملاً یکدست است و لاگ‌های وب با تگ #پنل_وب مشخص می‌شوند.
    هر خطایی در لاگ نباید اقدام اصلی را شکست دهد، پس در try/except است.
    """
    try:
        actor = admin.get("_db") or {}
        uid  = actor.get("user_id", admin.get("id", 0))
        name = actor.get("name", "مدیر ارشد")
        # نقش واقعی با همان منطق ربات (مدیر ارشد/نقش‌های فرعی/...) تا
        # در گروه و دیتابیس دقیقاً مثل لاگ‌های ربات دیده شود
        try:
            role = await db.get_actor_role_label(uid)
        except Exception:
            role = actor.get("role", "admin")
        await db.log_action(
            uid, name, role,
            action, module, "admin", severity,
            str(target_id), target_type, target_label,
            before, after, details, tags,
        )
        # سینک با گروه لاگ تلگرام — همان متنی که send_audit_log می‌سازد
        try:
            from utils import build_audit_log_text
            chat_id = await db.get_setting("log_group_admin", None)
            if chat_id:
                sync_tags = list(dict.fromkeys((tags or []) + ["پنل_وب"]))
                text = build_audit_log_text(
                    "admin", name, uid, action,
                    module=module, severity=severity, actor_role=role,
                    target_id=str(target_id), target_type=target_type,
                    target_label=target_label, before=before, after=after,
                    details=details, tags=sync_tags,
                )
                await _notify(int(chat_id), text, "audit_log_web")
        except Exception:
            pass
    except Exception:
        pass


def _rp_mini(u: dict) -> dict:
    """👑 P3 — مینی-چیپ پرستیژ از فیلدهای ذخیره‌شده (بدون کوئری اضافه)."""
    ranks = {r[0]: r for r in db.PRESTIGE_RANKS}
    r = ranks.get(u.get("prestige_rank") or "rookie", ranks["rookie"])
    try:
        dv = int(u.get("prestige_div", 3) or 3)
    except Exception:
        dv = 3
    return {"icon": r[2], "title": r[1], "color": r[4],
            "div": dv, "roman": db.ROMAN.get(dv, "III"),
            "stars": db.DIV_STARS.get(dv, "⭐")}


@router.get("/stats")
async def stats(admin=Depends(get_admin_user)):
    """نمای فشرده‌ی واقعی داشبورد مالک.

    کلیدهای flat برای Web Admin فعلی نگه داشته می‌شوند و آبجکت‌های nested
    نیز برای مصرف‌کننده‌های قدیمی باقی می‌مانند. هیچ مقدار placeholder یا
    عدد ساختگی در پاسخ وجود ندارد.
    """
    from utils import today_start_utc_str

    today_start = today_start_utc_str()
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    (users_total, users_pending, questions_approved, questions_pending,
     tickets_open, reports_open, subscriptions, active_today, active_week,
     new_today, total_answers) = await asyncio.gather(
        db.users.count_documents({"approved": True}),
        db.users.count_documents({"approved": False}),
        db.questions.count_documents({"approved": True}),
        db.questions.count_documents({"approved": False}),
        db.tickets.count_documents({"status": "open"}),
        db.content_reports.count_documents({"status": "new"}),
        db.sub_stats(),
        db.count_active_users_today(),
        db.users.count_documents({"last_active": {"$gte": week_ago}}),
        db.users.count_documents({"registered_at": {"$gte": today_start}}),
        db.answers.count_documents({}),
    )
    return {
        "active_today": active_today,
        "active_week": active_week,
        "new_today": new_today,
        "total_answers": total_answers,
        "users": {"total": users_total, "pending": users_pending},
        "questions": {"approved": questions_approved, "pending": questions_pending},
        "tickets": {"open": tickets_open},
        "reports": {"open": reports_open},
        "subscriptions": subscriptions or {},
    }

@router.get("/bot-status")
async def bot_status(admin=Depends(get_admin_user)):
    """سلامت واقعی DB/API و حضور process ربات در همان container.

    این endpoint heartbeat تلگرام را جعل نمی‌کند: ``bot_ok`` فقط می‌گوید
    process مربوط به ``bot.py`` زنده دیده شده است. جزئیات خطا نیز جداگانه
    برگردانده می‌شود تا UI حالت نامشخص را با «سالم» اشتباه نگیرد.
    """
    import time

    db_ping = None
    db_error = ""
    db_ok = False
    try:
        t0 = time.monotonic()
        await db.client.admin.command("ping")
        db_ping = int((time.monotonic() - t0) * 1000)
        db_ok = True
    except Exception as e:
        db_error = str(e)[:160]

    bot_ok = False
    bot_pid = None
    bot_error = ""
    sys_info = {}
    try:
        import psutil
        import os as _os

        current_pid = _os.getpid()
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                args = p.info.get("cmdline") or []
                proc_name = (p.info.get("name") or "").lower()
                executable = _os.path.basename(args[0]).lower() if args else ""
                has_bot_arg = any(_os.path.basename(str(arg)) == "bot.py" for arg in args[1:])
                is_python = "python" in proc_name or executable.startswith("python")
                if p.info.get("pid") != current_pid and is_python and has_bot_arg:
                    bot_ok = True
                    bot_pid = p.info.get("pid")
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        proc = psutil.Process(current_pid)
        mem = proc.memory_info().rss / 1024 / 1024
        vm = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)
        up = time.time() - proc.create_time()
        h, r = divmod(int(up), 3600)
        m, s = divmod(r, 60)
        sys_info = {
            "api_ram_mb": round(mem, 1),
            "total_ram_mb": round(vm.total / 1024 / 1024),
            "used_ram_pct": vm.percent,
            "cpu_pct": cpu,
            "uptime": f"{h}h {m}m" if h else f"{m}m {s}s",
        }
    except Exception as e:
        bot_error = str(e)[:160]

    return {
        "api_ok": True,
        "bot_ok": bot_ok,
        "bot_pid": bot_pid,
        "bot_error": bot_error,
        "db_ok": db_ok,
        "db_ping_ms": db_ping,
        "db_error": db_error,
        "checked_at": datetime.now().isoformat(),
        "sys": sys_info,
    }

# ══════════════════════════════════════════════
# 👥 کاربران
# ══════════════════════════════════════════════

@router.get("/users")
async def list_users(admin=Depends(get_admin_user), search: Optional[str]=Query(None),
                      group: Optional[str]=Query(None), intake: Optional[str]=Query(None)):
    # 🔎 قرارداد مشترک جست‌وجو (db.build_user_search_query) — حالا آیدی
    # عددی تلگرام هم دقیق پیدا می‌شود؛ قبلاً فقط name/student_id/username
    # بود و با ربات ناسازگار بود.
    q = db.build_user_search_query(search) if search else {}
    if group: q["group"]=group
    if intake: q["intake"]=intake
    # 🚀 موج ۴.۶۰ — projection: قبلاً سند کامل هر کاربر (شامل
    # notification_settings تو‌در‌تو، weak_topics، آمار و…) روی
    # سیم می‌رفت؛ فقط فیلدهای مصرفی پاسخ fetch می‌شود.
    _projection = {
        "user_id": 1, "name": 1, "student_id": 1,
        "group": 1, "intake": 1, "role": 1,
        "approved": 1, "suspended": 1,
        "registered_at": 1, "total_answers": 1,
        # 👑 P3 — مینی-چیپ پرستیژ برای NameChip در UserManagement
        "prestige_rank": 1, "prestige_div": 1,
    }
    users = await db.users.find(q, _projection).sort("registered_at",-1).to_list(500)
    return {"users":[{"id":u.get("user_id"),"name":u.get("name",""),
        # 🏷 Identity v1 — ادمین همیشه هر دو هویت را می‌بیند (§۳)
        "nickname": u.get("nickname"),
        "display_name": db.display_name_of(u),
        "student_id":u.get("student_id",""),
        "group":u.get("group",""),"intake":u.get("intake",""),"role":u.get("role","student"),
        "approved":u.get("approved",False),"suspended":u.get("suspended",False),
        "registered_at":u.get("registered_at","")[:10],"total_answers":u.get("total_answers",0),
        "prestige": _rp_mini(u)} for u in users]}

@router.get("/users/pending")
async def pending_users(admin=Depends(get_admin_user)):
    users = await db.pending_users()
    return {"users":[{"id":u.get("user_id"),"name":u.get("name",""),"student_id":u.get("student_id",""),
        "group":u.get("group",""),"intake":u.get("intake",""),"registered_at":u.get("registered_at","")[:10]} for u in users]}

@router.get("/users/{uid}")
async def user_detail(uid: int, admin=Depends(get_admin_user)):
    u = await db.get_user(uid)
    if not u: raise HTTPException(404, "کاربر پیدا نشد")
    return {"user":{"id":u.get("user_id"),"name":u.get("name",""),
        "nickname": u.get("nickname"),
        "display_name": db.display_name_of(u),
        "student_id":u.get("student_id",""),
        "group":u.get("group",""),"intake":u.get("intake",""),"role":u.get("role","student"),
        "approved":u.get("approved",False),"suspended":u.get("suspended",False),
        "registered_at":u.get("registered_at","")[:10],"total_answers":u.get("total_answers",0),
        "correct_answers":u.get("correct_answers",0),"downloads":u.get("downloads",0)}}

@router.post("/users/{uid}/approve")
async def approve(uid: int, admin=Depends(get_admin_user)):
    user = await db.get_user(uid)
    if not user: raise HTTPException(404)
    await db.update_user(uid,{"approved":True})
    await _notify(uid, "✅ <b>حساب شما تأیید شد!</b>\n\nاکنون می‌توانید از هامزیار استفاده کنید.\n/start بزنید.", "user_approved")
    # 🔔 موج ۴.۹۰ — اینباکس مینی‌اپ (تأیید حساب)
    await db.inbox_add(uid, 'account', "✅ حسابت تأیید شد!",
        "اکنون به تمام بخش‌های هامزیار دسترسی داری — خوش اومدی! 🎓", link='/')
    await _audit(admin, "تأیید حساب کاربر", "Users", severity="INFO",
        target_id=uid, target_type="user", target_label=user.get("name",""),
        tags=["تأیید_کاربر","پنل_وب"])
    return {"ok":True}

@router.post("/users/{uid}/reject")
async def reject(uid: int, admin=Depends(get_admin_user)):
    user = await db.get_user(uid)
    await db.users.delete_one({"user_id":uid})
    await _audit(admin, "رد درخواست عضویت", "Users", severity="WARNING",
        target_id=uid, target_type="user",
        target_label=(user or {}).get("name",""),
        tags=["رد_کاربر","پنل_وب"])
    return {"ok":True}

@router.post("/users/{uid}/suspend")
async def suspend(uid: int, admin=Depends(get_admin_user)):
    if uid == ADMIN_ID: raise HTTPException(403,"نمی‌توانید ادمین را تعلیق کنید")
    user = await db.get_user(uid)
    if not user: raise HTTPException(404)
    suspended = not user.get("suspended",False)
    await db.update_user(uid,{"suspended":suspended, "approved": not suspended})
    if suspended:
        await _notify(uid, "⚠️ دسترسی شما موقتاً تعلیق شد.", "user_suspended")
    await _audit(admin,
        "تعلیق حساب کاربر" if suspended else "رفع تعلیق حساب کاربر",
        "Users", severity="HIGH" if suspended else "INFO",
        target_id=uid, target_type="user", target_label=user.get("name",""),
        before={"suspended":not suspended}, after={"suspended":suspended},
        tags=["تعلیق_کاربر","پنل_وب"])
    return {"ok":True,"suspended":suspended}


class DmBody(BaseModel):
    """متن پیام مستقیم ادمین به کاربر"""
    text: str


@router.post("/users/{uid}/message")
async def dm_user_ep(uid: int, body: DmBody, admin=Depends(get_admin_user)):
    # ✉️ موج ۴.۸۰ — پیام مستقیم از کارت کاربر مینی‌اپ.
    # ارسال واقعی از طریق صف bot_notifications (همان کانالی که خودِ ربات
    # برای اطلاع‌رسانی‌ها استفاده می‌کند) انجام می‌شود؛ جاب outbox هر ۲۰
    # ثانیه تخلیه می‌کند — پاسخ صادقانه «در صف قرار گرفت» است.
    user = await db.get_user(uid)
    if not user: raise HTTPException(404, "کاربر پیدا نشد")
    text = body.text.strip()
    if len(text) < 2:    raise HTTPException(400, "متن پیام خیلی کوتاه است")
    if len(text) > 3500: raise HTTPException(400, "متن پیام خیلی بلند است (حداکثر ۳۵۰۰ کاراکتر)")
    # بدنه escape می‌شود: نه تزریق HTML، نه شکستن ارسال با «<»
    from html import escape as _esc
    out = (
        "📩 <b>پیام از مدیریت هامزیار</b>\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"{_esc(text)}"
    )
    # _notify سنکرون صدا زده می‌شود و insert را برمی‌گرداند؛ اگر خروجی
    # coroutine باشد (motor) باید await شود تا درج واقعاً اجرا شود —
    # در حالت درایور همگام هم بی‌اثر است. بدون این، پیام گاهی فقط
    # «برنامه‌ریزی» می‌شد و هرگز به outbox نمی‌نشست.
    _res = await _notify(uid, out, "admin_dm")
    if asyncio.iscoroutine(_res):
        await _res
    # 🔔 موج ۴.۹۰ — پیام مستقیم در مرکز اعلان مینی‌اپ هم می‌نشیند؛
    # حتی اگر ربات بلاک باشد، کاربر آنجا می‌خواندش
    await db.inbox_add(uid, 'admin_dm', "📩 پیام از مدیریت هامزیار",
        text[:400], link=None)
    await _audit(admin, "ارسال پیام مستقیم به کاربر", "Users", severity="INFO",
        target_id=uid, target_type="user", target_label=user.get("name",""),
        details=text[:100], tags=["پیام_مستقیم","پنل_وب"])
    return {"ok": True, "queued": True}

@router.post("/users/{uid}/delete")
async def delete_user_ep(uid: int, admin=Depends(get_admin_user)):
    if uid == ADMIN_ID: raise HTTPException(403,"نمی‌توانید ادمین ارشد را حذف کنید")
    user = await db.get_user(uid)
    if not user: raise HTTPException(404)
    await _notify(uid, "❌ حساب شما حذف شد.", "user_deleted")
    await db.delete_user(uid)
    await _audit(admin, "حذف حساب کاربر", "Users", severity="CRITICAL",
        target_id=uid, target_type="user", target_label=user.get("name",""),
        tags=["حذف_کاربر","پنل_وب"])
    return {"ok":True}

@router.post("/users/{uid}/block")
async def block_user_ep(uid: int, admin=Depends(get_admin_user)):
    if uid == ADMIN_ID: raise HTTPException(403,"نمی‌توانید ادمین ارشد را بلاک کنید")
    user = await db.get_user(uid)
    if not user: raise HTTPException(404)
    actor_name = admin["_db"].get("name","مدیر ارشد")
    await db.block_user(uid, blocked_by=admin["id"], blocked_by_name=actor_name)
    await db.blacklist.update_one({"_id":uid},{"$set":{"name":user.get("name","")}})
    await _notify(uid, "🚫 حساب شما مسدود شد و امکان ثبت‌نام مجدد ندارید.", "user_blocked")
    await _audit(admin, "مسدودسازی کاربر (بلک‌لیست)", "Users", severity="CRITICAL",
        target_id=uid, target_type="user", target_label=user.get("name",""),
        tags=["بلاک_کاربر","پنل_وب"])
    return {"ok":True}

@router.post("/users/{uid}/unblock")
async def unblock_user_ep(uid: int, admin=Depends(get_admin_user)):
    ok = await db.unblock_user(uid)
    if not ok: raise HTTPException(404,"این آیدی در بلک‌لیست نبود")
    await _audit(admin, "رفع مسدودیت کاربر", "Users", severity="HIGH",
        target_id=uid, target_type="user", tags=["آنبلاک_کاربر","پنل_وب"])
    return {"ok":True}

@router.get("/blacklist")
async def blacklist(admin=Depends(get_admin_user)):
    items = await db.get_blacklist()
    return {"blacklist":[{"id":b.get("_id"),"name":b.get("name",""),
        "blocked_by_name":b.get("blocked_by_name",""),"blocked_at":str(b.get("blocked_at",""))[:10]} for b in items]}

# ══════════════════════════════════════════════
# 🎓 ادمین‌های محتوا
# ══════════════════════════════════════════════

@router.get("/content-admins")
async def content_admins_list(admin=Depends(get_admin_user)):
    admins = await db.get_content_admins()
    return {"admins":[{"id":a.get("user_id"),"name":a.get("name","")} for a in admins]}

@router.post("/content-admins/{uid}")
async def grant_content_admin(uid: int, admin=Depends(get_admin_user)):
    user = await db.get_user(uid)
    if not user: raise HTTPException(404)
    await db.update_user(uid,{"role":"content_admin"})
    await _notify(uid, "🎓 <b>دسترسی ادمین محتوا به شما داده شد!</b>", "content_admin_granted")
    await _audit(admin, "اعطای دسترسی ادمین ارشد محتوا", "Roles", severity="HIGH",
        target_id=uid, target_type="user", target_label=user.get("name",""),
        tags=["اعطای_نقش","پنل_وب"])
    return {"ok":True}

@router.delete("/content-admins/{uid}")
async def revoke_content_admin(uid: int, admin=Depends(get_admin_user)):
    await db.update_user(uid,{"role":"student"})
    await _notify(uid, "⚠️ دسترسی ادمین محتوای شما لغو شد.", "content_admin_revoked")
    await _audit(admin, "لغو دسترسی ادمین ارشد محتوا", "Roles", severity="HIGH",
        target_id=uid, target_type="user",
        tags=["لغو_نقش","پنل_وب"])
    return {"ok":True}

@router.get("/students")
async def students_list(admin=Depends(get_admin_user), q: Optional[str]=Query(None)):
    users = await db.all_users(approved_only=True)
    students = [u for u in users if u.get("role","student")=="student"]
    if q:
        ql=q.lower()
        students=[u for u in students if ql in u.get("name","").lower() or ql in u.get("student_id","").lower()]
    return {"students":[{"id":u.get("user_id"),"name":u.get("name",""),"group":u.get("group","")} for u in students[:50]]}

# ══════════════════════════════════════════════
# ✏️ ویرایش کاربر
# ══════════════════════════════════════════════

class UserPatch(BaseModel):
    name: Optional[str]=None; group: Optional[str]=None
    intake: Optional[str]=None; student_id: Optional[str]=None
    role: Optional[str]=None
    nickname: Optional[str]=None   # 🏷 Identity v1

@router.patch("/users/{uid}")
async def edit_user(uid: int, body: UserPatch, admin=Depends(get_admin_user)):
    updates={}
    if body.name       is not None: updates["name"]=body.name.strip()
    if body.group      is not None: updates["group"]=db.normalize_group(body.group)
    if body.intake     is not None: updates["intake"]=body.intake
    if body.student_id is not None: updates["student_id"]=body.student_id.strip()
    if body.role       is not None:
        if body.role not in ("student","content_admin","support"): raise HTTPException(422,"نقش نامعتبر")
        updates["role"]=body.role
    # 🏷 Identity v1 — لقب از مسیر IdentityService (اعتبارسنجی
    # کامل + bypass Cooldown برای ادمین + Audit خودکار در db)
    if body.nickname is not None:
        actor_id = admin["id"] if isinstance(admin, dict) else 0
        ok, err, _info = await db.set_nickname(
            uid, body.nickname,
            changed_by=f"admin:{actor_id}",
            reason="پنل مدیریت",
        )
        if not ok:
            raise HTTPException(422, f"لقب نامعتبر: {err}")
    if updates:
        await db.update_user(uid,updates)
        await _audit(admin, "ویرایش اطلاعات کاربر", "Users", severity="WARNING",
            target_id=uid, target_type="user",
            details=" / ".join(f"{k}: {v}" for k, v in updates.items())[:400],
            tags=["ویرایش_کاربر","پنل_وب"])
    return {"ok":True}

# ══════════════════════════════════════════════
# 📅 ورودی‌ها (Intakes)
# ══════════════════════════════════════════════

@router.get("/intakes")
async def intakes_list(admin=Depends(get_admin_user)):
    items = await db.get_all_intakes()
    result=[]
    for i in items:
        st = await db.intake_stats(i.get("code",""))
        result.append({"code":i.get("code",""),"label":i.get("label",""),
            "active":i.get("active",True),"total":st.get("total",0),"groups":st.get("groups",{})})
    return {"intakes":result}

class IntakeCreate(BaseModel):
    code: str; label: str

@router.post("/intakes")
async def add_intake_ep(body: IntakeCreate, admin=Depends(get_admin_user)):
    code=body.code.strip(); label=body.label.strip()
    if not code or not label: raise HTTPException(422,"کد و برچسب الزامی است")
    await db.add_intake(code, label)
    await _audit(admin, "افزودن ورودی جدید", "Users", severity="INFO",
        target_id=code, target_type="intake", target_label=label,
        tags=["ورودی","پنل_وب"])
    return {"ok":True}

@router.post("/intakes/{code}/toggle")
async def toggle_intake_ep(code: str, admin=Depends(get_admin_user)):
    new_state = await db.toggle_intake(code)
    await _audit(admin,
        "فعال‌سازی پذیرش ورودی" if new_state else "توقف پذیرش ورودی",
        "Users", severity="WARNING",
        target_id=code, target_type="intake",
        tags=["ورودی","پنل_وب"])
    return {"ok":True,"active":new_state}

@router.delete("/intakes/{code}")
async def delete_intake_ep(code: str, admin=Depends(get_admin_user)):
    await db.delete_intake(code)
    await _audit(admin, "حذف ورودی", "Users", severity="HIGH",
        target_id=code, target_type="intake", tags=["ورودی","پنل_وب"])
    return {"ok":True}

# ══════════════════════════════════════════════
# 🎫 تیکت‌ها
# ══════════════════════════════════════════════

@router.get("/tickets")
async def all_tickets(admin=Depends(get_admin_user), status: Optional[str]=Query(None)):
    tickets = await db.ticket_get_all(status=status)
    return {"tickets":[{"id":t.get("ticket_id"),"user_name":t.get("user_name",""),"subject":t.get("subject",""),
        "status":t.get("status","open"),"reply_count":len(t.get("replies",[])),"created_at":t.get("created_at","")[:10]} for t in tickets]}

@router.get("/tickets/{tid}")
async def ticket_detail(tid: int, admin=Depends(get_admin_user)):
    t = await db.ticket_get(tid)
    if not t: raise HTTPException(404)
    uid=t.get("user_id"); u=await db.get_user(uid) if uid else None
    replies=[{"text":r.get("text","").removeprefix("[دانشجو]").strip(),
        "sender":"user" if r.get("text","").startswith("[دانشجو]") else "support","at":r.get("at","")[:16]} for r in t.get("replies",[])]
    return {"ticket":{"id":t.get("ticket_id"),"subject":t.get("subject",""),"message":t.get("message",""),
        "status":t.get("status","open"),"created_at":t.get("created_at","")[:10],"replies":replies,
        "user":{"id":uid,"name":t.get("user_name",""),"student_id":u.get("student_id","") if u else "","group":u.get("group","") if u else "","intake":u.get("intake","") if u else ""}}}

class AdminReply(BaseModel):
    message: str

@router.post("/tickets/{tid}/reply")
async def admin_reply(tid: int, body: AdminReply, admin=Depends(get_admin_user)):
    t=await db.ticket_get(tid)
    if not t: raise HTTPException(404)
    if t.get("status")=="closed": raise HTTPException(400)
    msg=body.message.strip()
    if not msg: raise HTTPException(422)
    await db.ticket_add_reply(tid, msg)
    await _notify(t["user_id"], f"💬 <b>پاسخ پشتیبانی #{tid}</b>\n{msg}", "ticket_admin_reply")
    await _audit(admin, "پاسخ به تیکت پشتیبانی", "Tickets", severity="INFO",
        target_id=tid, target_type="ticket", target_label=t.get("subject",""),
        tags=["تیکت","پنل_وب"])
    return {"ok":True}

@router.post("/tickets/{tid}/close")
async def close_ticket(tid: int, admin=Depends(get_admin_user)):
    await db.ticket_close(tid)
    await _audit(admin, "بستن تیکت", "Tickets", severity="INFO",
        target_id=tid, target_type="ticket", tags=["تیکت","پنل_وب"])
    return {"ok":True}

@router.post("/tickets/{tid}/reopen")
async def reopen_ticket(tid: int, admin=Depends(get_admin_user)):
    await db.ticket_reopen(tid)
    await _audit(admin, "بازگشایی تیکت", "Tickets", severity="INFO",
        target_id=tid, target_type="ticket", tags=["تیکت","پنل_وب"])
    return {"ok":True}

# ══════════════════════════════════════════════
# 📢 Broadcast پیشرفته — preview / تأیید / زمان‌دار / هدفمند
# ══════════════════════════════════════════════

class BroadcastTarget(BaseModel):
    scope: str = "all"                    # all | intake | intake_group
    intake: Optional[str] = None
    group: Optional[str] = None           # "1" | "2"

async def _resolve_broadcast_users(target: BroadcastTarget):
    users = await db.all_users(approved_only=True)
    if target.scope == "intake" and target.intake:
        users = [u for u in users if u.get("intake") == target.intake]
    elif target.scope == "intake_group" and target.intake and target.group:
        users = [u for u in users if u.get("intake") == target.intake and u.get("group") == target.group]
    return [u for u in users if u.get("user_id") != ADMIN_ID]

class BroadcastPreview(BaseModel):
    target: BroadcastTarget

@router.post("/broadcast/preview")
async def broadcast_preview(body: BroadcastPreview, admin=Depends(get_admin_user)):
    users = await _resolve_broadcast_users(body.target)
    return {"recipient_count": len(users)}

class BroadcastSend(BaseModel):
    text: str
    target: BroadcastTarget
    send_at: Optional[str] = None   # ISO datetime — اگه خالی باشه فوری ارسال می‌شه

@router.post("/broadcast")
async def broadcast(body: BroadcastSend, admin=Depends(get_admin_user)):
    text = body.text.strip()
    if len(text) < 5: raise HTTPException(422, "متن پیام خیلی کوتاهه")
    if body.send_at:
        try: datetime.fromisoformat(body.send_at)
        except ValueError: raise HTTPException(422, "فرمت زمان نامعتبر است")
    users = await _resolve_broadcast_users(body.target)
    notif = db.client["medicalbot"]["bot_notifications"]
    doc_base = {"type":"broadcast","text":text,"sent":False,"created_at":datetime.now().isoformat()}
    if body.send_at: doc_base["send_at"] = body.send_at
    docs = [{**doc_base, "chat_id": u["user_id"]} for u in users]
    if docs: await notif.insert_many(docs)
    # 🔔 موج ۴.۹۰ — انعکاس اطلاعیه در مرکز اعلان مینی‌اپ (فوری و زمان‌دار)
    import re as _re
    await db.inbox_add_many([
        {'user_id': u["user_id"], 'type': 'announcement',
         'title': "📢 اطلاعیه‌ی مدیریت",
         'body': _re.sub(r'<[^>]+>', '', text).strip() or 'پیام همگانی مدیریت',
         'link': None}
        for u in users if u.get("user_id")
    ])
    await _audit(admin, "ارسال همگانی" + (" (زمان‌دار)" if body.send_at else ""),
        "Notifications", severity="HIGH",
        target_type="broadcast", target_label=f"{len(docs)} گیرنده",
        details=text[:300],
        tags=["ارسال_همگانی","پنل_وب"])
    return {"ok":True, "queued": len(docs), "scheduled": bool(body.send_at)}

@router.get("/broadcast/history")
async def broadcast_history(admin=Depends(get_admin_user), limit: int=Query(20)):
    notif = db.client["medicalbot"]["bot_notifications"]
    pipeline = [
        {"$match": {"type": "broadcast"}},
        {"$group": {"_id": {"text":"$text","created_at":"$created_at"},
            "total": {"$sum": 1}, "sent": {"$sum": {"$cond": ["$sent", 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$failed", True]}, 1, 0]}}}},
        {"$sort": {"_id.created_at": -1}}, {"$limit": limit},
    ]
    rows = await notif.aggregate(pipeline).to_list(limit)
    return {"history":[{"text":r["_id"]["text"][:80],"created_at":r["_id"]["created_at"],
        "total":r["total"],"sent":r["sent"],"failed":r["failed"]} for r in rows]}

# ── 🌊 موج Notif-Scheduled — مدیریت ارسال‌های همگانی زمان‌دارِ در انتظار ──
# پاریت با ربات: تا لحظه‌ی send_at پیام‌ها sent=False می‌مانند؛ لغو = حذف همان
# دسته (کلید یکتای دسته = text + created_at). همه‌ی مسیرها سطح مالک می‌مانند.

@router.get("/broadcast/scheduled")
async def broadcast_scheduled(admin=Depends(get_admin_user), limit: int=Query(10, ge=1, le=50)):
    """فهرست دسته‌های ارسال همگانی زمان‌دار که هنوز موعدشان نرسیده است."""
    notif = db.client["medicalbot"]["bot_notifications"]
    now_iso = datetime.now().isoformat()
    docs = await notif.find(
        {"type": "broadcast", "sent": False, "send_at": {"$gt": now_iso}}
    ).sort("send_at", 1).limit(500).to_list(500)
    groups = {}
    for d in docs:
        key = (d.get("text", ""), d.get("created_at", ""), d.get("send_at", ""))
        g = groups.setdefault(key, {"text": key[0], "created_at": key[1],
                                    "send_at": key[2], "total": 0})
        g["total"] += 1
    items = sorted(groups.values(), key=lambda x: x["send_at"])[:limit]
    for it in items:
        it["text"] = it["text"][:120]
    return {"scheduled": items}

class BroadcastCancel(BaseModel):
    text: str
    created_at: str

@router.post("/broadcast/cancel")
async def broadcast_cancel(body: BroadcastCancel, admin=Depends(get_admin_user)):
    """لغو یک دسته‌ی ارسال زمان‌دار — فقط پیام‌های هنوز ارسال‌نشده‌ی همان دسته."""
    notif = db.client["medicalbot"]["bot_notifications"]
    res = await notif.delete_many({"type": "broadcast", "sent": False,
                                   "text": body.text, "created_at": body.created_at})
    n = getattr(res, "deleted_count", 0)
    if not n:
        raise HTTPException(404, "دسته‌ی ارسالی یافت نشد (شاید قبلاً ارسال شده)")
    await _audit(admin, "لغو ارسال همگانی زمان‌دار", "Notifications", severity="HIGH",
        target_type="broadcast", target_label=f"{n} گیرنده",
        details=body.text[:300],
        tags=["ارسال_همگانی", "لغو", "پنل_وب"])
    return {"ok": True, "cancelled": n}

# ══════════════════════════════════════════════
# 📊 نظرسنجی کانال
# ══════════════════════════════════════════════

@router.get("/poll/status")
async def poll_status(admin=Depends(get_admin_user)):
    channel_id = await db.get_setting("poll_channel_id", None)
    return {"channel_id": channel_id, "configured": bool(channel_id)}

class PollChannelSet(BaseModel):
    channel_id: str

@router.post("/poll/channel")
async def poll_channel_set(body: PollChannelSet, admin=Depends(get_admin_user)):
    await db.set_setting("poll_channel_id", body.channel_id.strip())
    return {"ok":True}

class PollCreate(BaseModel):
    question: str; options: List[str]; anonymous: bool = False

@router.post("/poll")
async def poll_create(body: PollCreate, admin=Depends(get_admin_user)):
    if len(body.options) < 2: raise HTTPException(422, "حداقل ۲ گزینه لازم است")
    channel_id = await db.get_setting("poll_channel_id", None)
    if not channel_id: raise HTTPException(400, "کانال نظرسنجی تنظیم نشده — اول از بخش تنظیمات کانال رو وارد کن")
    from api.telegram_send import BOT_TOKEN, API_BASE
    import httpx
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{API_BASE}/sendPoll", json={
            "chat_id": channel_id, "question": body.question, "options": body.options,
            "is_anonymous": body.anonymous, "allows_multiple_answers": False,
        })
    data = resp.json()
    if not data.get("ok"):
        raise HTTPException(502, f"ارسال ناموفق — مطمئن شو ربات ادمین کانال هست ({data.get('description','')})")
    await _audit(admin, "ایجاد نظرسنجی در کانال", "Notifications", severity="INFO",
        target_type="poll", target_label=body.question[:100],
        tags=["نظرسنجی","پنل_وب"])
    return {"ok":True}

# ══════════════════════════════════════════════
# 🔒 قفل اجباری عضویت کانال — 🌊 موج ChannelLock
# (معادل admin:channel_lock ربات؛ متدهای db موجود بودند
# ولی API وب نداشتند — فقط افزودنی، سطح مالک)
# ══════════════════════════════════════════════

@router.get("/channel-lock")
async def channel_lock_list(admin=Depends(get_admin_user)):
    channels = await db.get_required_channels()
    return {"channels": [
        {"id": c.get("id", ""), "title": c.get("title", ""),
         "invite_link": c.get("invite_link", "")} for c in channels]}

class ChannelLockAdd(BaseModel):
    id: str
    title: str
    invite_link: str = ""

@router.post("/channel-lock")
async def channel_lock_add(body: ChannelLockAdd, admin=Depends(get_admin_user)):
    cid = body.id.strip(); title = body.title.strip()
    if not cid or not title:
        raise HTTPException(422, "آیدی و نام کانال الزامی است")
    ok = await db.add_required_channel(cid, title, body.invite_link.strip())
    if not ok:
        raise HTTPException(409, "این کانال قبلاً اضافه شده است")
    await _audit(admin, "افزودن کانال اجباری", "Settings", severity="WARNING",
        target_id=cid, target_type="channel", target_label=title,
        tags=["قفل_کانال", "پنل_وب"])
    return {"ok": True}

@router.delete("/channel-lock/{channel_id}")
async def channel_lock_remove(channel_id: str, admin=Depends(get_admin_user)):
    current = await db.get_required_channels()
    if not any(c.get("id") == channel_id for c in current):
        raise HTTPException(404, "کانال در لیست نیست")
    await db.remove_required_channel(channel_id)
    await _audit(admin, "حذف کانال اجباری", "Settings", severity="WARNING",
        target_id=channel_id, target_type="channel",
        tags=["قفل_کانال", "پنل_وب"])
    return {"ok": True}

# ══════════════════════════════════════════════
# 🔔 مدیریت اعلان‌ها — فاصله زمانی / تاریخچه / retry
# ══════════════════════════════════════════════

@router.get("/notifications/settings")
async def notif_settings(admin=Depends(get_admin_user)):
    interval = await db.get_setting("resource_notif_interval_hours", 24)
    last_sent = await db.get_setting("resource_notif_last_sent", None)
    last_error = await db.get_setting("resource_notif_last_error", None)
    return {"interval_hours": interval, "last_sent": last_sent, "last_error": last_error}

class NotifSettingsUpdate(BaseModel):
    interval_hours: int

@router.post("/notifications/settings")
async def notif_settings_update(body: NotifSettingsUpdate, admin=Depends(get_admin_user)):
    if body.interval_hours not in (24, 48, 72): raise HTTPException(422, "مقدار مجاز: ۲۴، ۴۸ یا ۷۲")
    old = await db.get_setting("resource_notif_interval_hours", 24)
    await db.set_setting("resource_notif_interval_hours", body.interval_hours)
    await _audit(admin, "تغییر فاصله اعلان منابع", "Settings", severity="WARNING",
        target_type="settings",
        before={"فاصله(ساعت)": old}, after={"فاصله(ساعت)": body.interval_hours},
        tags=["تنظیمات_اعلان","پنل_وب"])
    return {"ok":True}

@router.get("/notifications/history")
async def notif_history(admin=Depends(get_admin_user), job_name: Optional[str]=Query(None), limit: int=Query(15)):
    runs = await db.get_recent_notif_runs(job_name=job_name, limit=limit)
    return {"runs":[{"id":str(r["_id"]),"job_name":r.get("job_name",""),"status":r.get("status",""),
        "sent":r.get("sent",0),"failed":r.get("failed",0),"total":r.get("total",0),
        "started_at":r.get("started_at",""),"finished_at":r.get("finished_at")} for r in runs]}

@router.post("/notifications/history/{run_id}/retry")
async def notif_retry(run_id: str, admin=Depends(get_admin_user)):
    targets = await db.get_failed_notif_details(run_id)
    if not targets: raise HTTPException(404, "موردی برای تلاش مجدد پیدا نشد")
    notif = db.client["medicalbot"]["bot_notifications"]
    docs = [{"type":"notif_retry","chat_id":t["user_id"],"text":t["message"],"sent":False,
        "created_at":datetime.now().isoformat()} for t in targets if t.get("message")]
    if docs: await notif.insert_many(docs)
    return {"ok":True, "requeued": len(docs)}

@router.post("/export/excel")
async def export_excel(admin=Depends(get_admin_user)):
    await _notify(ADMIN_ID, "__EXCEL_EXPORT__", "excel_export_request")
    return {"ok":True,"message":"📊 فایل اکسل از طریق ربات ارسال می‌شود."}


# ── بخش‌های بکاپ — دقیقاً همان‌هایی که منوی backup.py در ربات دارد ──
BACKUP_SECTION_LABELS_FA = {
    "all":          "کامل — همه بخش‌ها",
    "users":        "کاربران",
    "content":      "علوم پایه",
    "refs":         "رفرنس‌ها",
    "qbank":        "بانک سوال",
    "subscription": "اشتراک و پرداخت",
    "grades":       "نمرات",
    "access":       "دسترسی‌ها و تنظیمات",
}

class BackupRequestBody(BaseModel):
    section: str = "all"

@router.post("/backup")
async def request_backup(body: BackupRequestBody, admin=Depends(get_admin_user)):
    """درخواست فایل پشتیبان JSON از پنل وب — با همان الگوی خروجی اکسل:
    سیگنال __BACKUP_REQUEST__ در صف bot_notifications می‌نشیند و
    mini_app_outbox_job در ربات فایل را می‌سازد و به چت ادمین می‌فرستد
    (همان build_full_backup_data / build_section_backup_data مشترک ربات)."""
    if body.section not in BACKUP_SECTION_LABELS_FA:
        raise HTTPException(422, "بخش بکاپ نامعتبر است")
    signal = ("__BACKUP_REQUEST__" if body.section == "all"
              else f"__BACKUP_REQUEST__:{body.section}")
    await _notify(admin.get("id", ADMIN_ID), signal, f"backup_request_{body.section}")
    await _audit(admin, "درخواست فایل پشتیبان از پنل وب", "Backup", severity="HIGH",
        details=f"بخش: {BACKUP_SECTION_LABELS_FA[body.section]}",
        tags=["بکاپ", "پنل_وب"])
    return {"ok": True,
            "message": "💾 فایل پشتیبان از طریق ربات ارسال می‌شود (بسته به حجم دیتابیس ممکن است چند ثانیه طول بکشد)."}

# ══════════════════════════════════════════════
# ⚙️ تنظیمات ربات — همان کلیدهایی که پنل ربات
# استفاده می‌کند تا هر دو کانال سینک بمانند
# ══════════════════════════════════════════════

@router.get("/settings")
async def bot_settings_get(admin=Depends(get_admin_user)):
    """خواندن تنظیمات مشترک ربات/مینی‌اپ."""
    return {
        "maintenance_mode": bool(await db.get_setting("maintenance_mode", False)),
        "maintenance_text": (await db.get_setting("maintenance_text", "")) or "",
        "require_student_id": bool(await db.get_setting("require_student_id", False)),
        # گروه‌های لاگ تلگرام — همان کلیدهای پنل ربات تا وضعیتش از وب هم
        # قابل مشاهده/تغییر باشد (None یعنی تنظیم نشده)
        "log_group_admin": await db.get_setting("log_group_admin", None),
        "log_group_content": await db.get_setting("log_group_content", None),
        # 💙 حمایت مالی — همان کلیدهای پنل ربات (admin:donation_manage)
        "donation_enabled": bool(await db.get_setting("donation_enabled", False)),
        "donation_link": await db.get_setting("donation_link", None),
        # 💾 بکاپ خودکار — همان کلیدهای backup.py (backup:auto_settings)
        "auto_backup_enabled": bool(await db.get_setting("auto_backup_enabled", False)),
        "auto_backup_hour": int(await db.get_setting("auto_backup_hour", 3) or 0),
        "auto_backup_last_run": await db.get_setting("auto_backup_last_run", None),
    }

class BotSettingsPatch(BaseModel):
    maintenance_mode: Optional[bool] = None
    maintenance_text: Optional[str] = None
    require_student_id: Optional[bool] = None
    # None صریح در بدنه = حذف تنظیم گروه (با model_fields_set تشخیص داده می‌شود)
    log_group_admin: Optional[int] = None
    log_group_content: Optional[int] = None
    donation_enabled: Optional[bool] = None
    # '' یا None = حذف لینک
    donation_link: Optional[str] = None
    auto_backup_enabled: Optional[bool] = None
    # ساعت اجرا به‌وقت تهران ۰ تا ۲۳
    auto_backup_hour: Optional[int] = None

@router.patch("/settings")
async def bot_settings_patch(body: BotSettingsPatch, admin=Depends(get_admin_user)):
    """تغییر تنظیمات — دقیقاً با همان سطح حساسیت لاگ پنل ربات:
    حالت تعمیر → CRITICAL، الزام شماره دانشجویی → HIGH."""
    changed = []

    if body.maintenance_mode is not None:
        old = bool(await db.get_setting("maintenance_mode", False))
        if old != body.maintenance_mode:
            await db.set_setting("maintenance_mode", body.maintenance_mode)
            await _audit(admin,
                "فعال‌شدن حالت تعمیر" if body.maintenance_mode else "غیرفعال‌شدن حالت تعمیر",
                "Settings", severity="CRITICAL",
                before={"وضعیت": "غیرفعال" if body.maintenance_mode else "فعال"},
                after={"وضعیت": "فعال" if body.maintenance_mode else "غیرفعال"},
                tags=["حالت_تعمیر", "پنل_وب"])
            changed.append("maintenance_mode")

    if body.maintenance_text is not None:
        text = body.maintenance_text.strip()
        if len(text) > 400:
            raise HTTPException(422, "متن حالت تعمیر نباید بیشتر از ۴۰۰ کاراکتر باشد")
        old = (await db.get_setting("maintenance_text", "")) or ""
        if old != text:
            await db.set_setting("maintenance_text", text)
            await _audit(admin, "تغییر متن حالت تعمیر", "Settings", severity="HIGH",
                before={"متن": old or "(پیش‌فرض)"},
                after={"متن": text or "(پیش‌فرض)"},
                tags=["حالت_تعمیر", "پنل_وب"])
            changed.append("maintenance_text")

    if body.require_student_id is not None:
        old = bool(await db.get_setting("require_student_id", False))
        if old != body.require_student_id:
            await db.set_setting("require_student_id", body.require_student_id)
            await _audit(admin,
                "اجباری‌شدن شماره دانشجویی" if body.require_student_id else "اختیاری‌شدن شماره دانشجویی",
                "Settings", severity="HIGH",
                before={"شماره دانشجویی": "اختیاری" if body.require_student_id else "اجباری"},
                after={"شماره دانشجویی": "اجباری" if body.require_student_id else "اختیاری"},
                tags=["تنظیمات_ثبت_نام", "پنل_وب"])
            changed.append("require_student_id")

    # ── گروه‌های لاگ تلگرام — None صریح یعنی حذف تنظیم ──
    for field, key, label in (
        ("log_group_admin",   "log_group_admin",   "گروه لاگ مدیریت"),
        ("log_group_content", "log_group_content", "گروه لاگ محتوا"),
    ):
        if field in body.model_fields_set:
            val = getattr(body, field)
            if val is not None and val >= 0:
                raise HTTPException(422,
                    "آیدی گروه باید عدد منفی باشد (مثل -1001234567890) — عدد مثبت آیدی کاربر است")
            old = await db.get_setting(key, None)
            if old != val:
                await db.set_setting(key, val)
                await _audit(admin,
                    f"تنظیم {label}" if val is not None else f"حذف {label}",
                    "Settings", severity="HIGH",
                    before={"گروه": str(old) if old else "تنظیم نشده"},
                    after={"گروه": str(val) if val is not None else "حذف شد"},
                    tags=["گروه_لاگ", "پنل_وب"])
                changed.append(key)

    # ── 💙 حمایت مالی — برچسب‌های لاگ دقیقاً مثل پنل ربات ──
    if body.donation_enabled is not None:
        old = bool(await db.get_setting("donation_enabled", False))
        if old != body.donation_enabled:
            await db.set_setting("donation_enabled", body.donation_enabled)
            await _audit(admin,
                "فعال‌شدن بخش حمایت مالی" if body.donation_enabled else "غیرفعال‌شدن بخش حمایت مالی",
                "Settings", severity="HIGH",
                before={"وضعیت": "غیرفعال" if body.donation_enabled else "فعال"},
                after={"وضعیت": "فعال" if body.donation_enabled else "غیرفعال"},
                tags=["حمایت_مالی", "پنل_وب"])
            changed.append("donation_enabled")

    if body.donation_link is not None or "donation_link" in body.model_fields_set:
        link = (body.donation_link or "").strip()
        if link and not (link.startswith("http://") or link.startswith("https://")):
            raise HTTPException(422, "لینک باید با http:// یا https:// شروع شود")
        if len(link) > 300:
            raise HTTPException(422, "لینک نباید بیشتر از ۳۰۰ کاراکتر باشد")
        new_val = link or None
        old = await db.get_setting("donation_link", None)
        if old != new_val:
            await db.set_setting("donation_link", new_val)
            await _audit(admin,
                "تنظیم لینک حمایت مالی" if new_val else "حذف لینک حمایت مالی",
                "Settings", severity="HIGH",
                before={"لینک": old or "تنظیم نشده"},
                after={"لینک": new_val or "حذف شد"},
                tags=["حمایت_مالی", "پنل_وب"])
            changed.append("donation_link")

    # ── 💾 بکاپ خودکار — همان منطق backup:auto_settings در ربات ──
    if body.auto_backup_enabled is not None:
        old = bool(await db.get_setting("auto_backup_enabled", False))
        if old != body.auto_backup_enabled:
            await db.set_setting("auto_backup_enabled", body.auto_backup_enabled)
            await _audit(admin,
                "فعال‌سازی بکاپ خودکار روزانه" if body.auto_backup_enabled else "غیرفعال‌سازی بکاپ خودکار روزانه",
                "Backup", severity="HIGH",
                before={"بکاپ خودکار": "غیرفعال" if body.auto_backup_enabled else "فعال"},
                after={"بکاپ خودکار": "فعال" if body.auto_backup_enabled else "غیرفعال"},
                tags=["بکاپ", "پنل_وب"])
            changed.append("auto_backup_enabled")

    if body.auto_backup_hour is not None:
        if not (0 <= body.auto_backup_hour <= 23):
            raise HTTPException(422, "ساعت بکاپ خودکار باید بین ۰ تا ۲۳ باشد")
        old = int(await db.get_setting("auto_backup_hour", 3) or 0)
        if old != body.auto_backup_hour:
            await db.set_setting("auto_backup_hour", body.auto_backup_hour)
            await _audit(admin, "تغییر ساعت بکاپ خودکار", "Backup", severity="HIGH",
                before={"ساعت": f"{old}:00"},
                after={"ساعت": f"{body.auto_backup_hour}:00"},
                tags=["بکاپ", "پنل_وب"])
            changed.append("auto_backup_hour")

    return {"ok": True, "changed": changed}

class LogGroupTestBody(BaseModel):
    kind: str  # 'admin' | 'content'

@router.post("/settings/test-log-group")
async def test_log_group(body: LogGroupTestBody, admin=Depends(get_admin_user)):
    """ارسال پیام تست به گروه لاگ از مسیر واقعی ربات (صف bot_notifications)
    تا سلامت کل زنجیره‌ی وب→دیتابیس→ربات→گروه با یک دکمه قابل بررسی باشد."""
    if body.kind not in ("admin", "content"):
        raise HTTPException(422, "kind باید admin یا content باشد")
    key   = "log_group_admin" if body.kind == "admin" else "log_group_content"
    label = "🛡 لاگ مدیریت" if body.kind == "admin" else "🎓 لاگ محتوا"
    chat_id = await db.get_setting(key, None)
    if not chat_id:
        raise HTTPException(404, "این گروه هنوز تنظیم نشده است")
    await _notify(int(chat_id),
        f"🧪 <b>پیام تست گروه {label}</b>\n\n"
        "این پیام از پنل وب مینی‌اپ ارسال شد — اگر آن را می‌خوانی، "
        "اتصال کامل وب ← ربات ← گروه لاگ سالم است. ✅",
        "log_group_test")
    await _audit(admin, f"ارسال پیام تست به گروه {label}", "Settings",
        severity="INFO", target_id=str(chat_id), target_type="group",
        tags=["گروه_لاگ", "پنل_وب"])
    return {"ok": True, "message": "پیام تست از طریق ربات ارسال می‌شود (ظرف چند ثانیه در گروه می‌رسد)."}


# ══════════════════════════════════════════════
# 🛠 Fix-Foundation — عملیات نهایی مالک (Parity-Final)
# endpointهای owner موجود آزاد نشده‌اند؛ این routeها صرفاً افزودنی‌اند.
# ══════════════════════════════════════════════

@router.post("/prestige/backfill")
async def prestige_backfill(admin=Depends(get_admin_user)):
    raw = await db.prestige_backfill()
    firsts = raw.get("firsts") or []
    report = {
        "scanned": int(raw.get("scanned") or 0),
        "migrated": int(raw.get("migrated") or 0),
        "founders": int(raw.get("founders") or 0),
        "firsts": len(firsts) if isinstance(firsts, list) else int(firsts or 0),
        "first_items": firsts[:10] if isinstance(firsts, list) else [],
        "errors": int(raw.get("errors") or 0),
        "fatal": raw.get("fatal") or "",
    }
    await _audit(admin, "اجرای Backfill Prestige", "Prestige",
                 severity="HIGH", after=report,
                 tags=["پرستیژ", "backfill", "پنل_وب"])
    return {"ok": not bool(report["fatal"]), "report": report}


@router.post("/notifications/force-send")
async def notifications_force_send(admin=Depends(get_admin_user)):
    """ثبت سیگنال؛ اجرای واقعی با bot instance در outbox job انجام می‌شود."""
    await _notify(admin["id"], "__FORCE_RES_NOTIF__", "force_resources_notification")
    await _audit(admin, "درخواست ارسال فوری اعلان منابع", "Notifications",
                 severity="HIGH", tags=["اعلان_منابع", "ارسال_فوری", "پنل_وب"])
    return {
        "ok": True,
        "message": "📨 درخواست ثبت شد؛ نتیجه‌ی اجرای واقعی در گفت‌وگوی ربات ارسال می‌شود.",
    }


@router.post("/log-groups/test")
async def log_groups_test(admin=Depends(get_admin_user)):
    """تست واقعی هر دو گروه از مسیر Bot API، بدون افشای token به مرورگر."""
    import time
    import httpx
    from api.telegram_send import API_BASE, BOT_TOKEN

    specs = [
        ("admin", "log_group_admin", "🛡 لاگ مدیریت"),
        ("content", "log_group_content", "🎓 لاگ محتوا"),
    ]
    results = []
    for kind, key, label in specs:
        chat_id = await db.get_setting(key, None)
        if not chat_id:
            results.append({"key": kind, "label": label, "status": "unset", "ms": None, "error": ""})
            continue
        if not BOT_TOKEN:
            results.append({"key": kind, "label": label, "status": "error", "ms": None,
                            "error": "TELEGRAM_TOKEN تنظیم نشده است"})
            continue
        started = time.monotonic()
        status = "error"
        error = ""
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(f"{API_BASE}/sendMessage", json={
                    "chat_id": int(chat_id),
                    "text": (f"🧪 <b>تست اتصال {label}</b>\n\n"
                             "ارسال مستقیم از Web Admin با موفقیت انجام شد. ✅"),
                    "parse_mode": "HTML",
                })
            payload = resp.json() if resp.content else {}
            if resp.status_code == 200 and payload.get("ok"):
                status = "sent"
            else:
                error = str(payload.get("description") or f"HTTP {resp.status_code}")[:160]
        except Exception as e:
            error = str(e)[:160]
        results.append({
            "key": kind, "label": label, "status": status,
            "ms": int((time.monotonic() - started) * 1000), "error": error,
        })

    await _audit(admin, "تست اتصال گروه‌های لاگ", "Settings",
                 severity="INFO", after={r["key"]: r["status"] for r in results},
                 tags=["گروه_لاگ", "تست_اتصال", "پنل_وب"])
    return {"ok": all(r["status"] in ("sent", "unset") for r in results),
            "results": results}


# ══════════════════════════════════════════════
# 🛡 لاگ فعالیت مدیران (نمایش در پنل وب)
# ══════════════════════════════════════════════

@router.get("/audit-logs")
async def audit_logs_admin(
    admin=Depends(get_admin_user),
    category: Optional[str] = Query(None),
    min_severity: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
):
    """فهرست لاگ فعالیت با فیلتر دسته/سطح/جست‌وجو + شمارنده سطوح.

    داده همان audit_logs مشترک با بات است؛ اکشن‌های ثبت‌شده از پنل وب
    (تگ «پنل_وب») و اکشن‌های بات هر دو اینجا دیده می‌شوند.
    """
    query = {}
    if category in ("admin", "content"):
        query["category"] = category
    if min_severity:
        order = ["INFO", "WARNING", "HIGH", "CRITICAL"]
        idx = order.index(min_severity) if min_severity in order else 0
        query["severity"] = {"$in": order[idx:]}
    if q:
        import re
        pat = re.compile(re.escape(q), re.IGNORECASE)
        query["$or"] = [
            {"action": pat},
            {"actor.name": pat},
            {"target.label": pat},
            {"details": pat},
            {"module": pat},
        ]

    total = await db.audit_logs.count_documents(query)

    # شمارنده سطوح (با همان فیلترهای دسته/جست‌وجو، بدون فیلتر سطح)
    counter_query = {k: v for k, v in query.items() if k != "severity"}
    sev_counts = await db.audit_logs.aggregate([
        {"$match": counter_query},
        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
    ]).to_list(10)
    counters = {
        r["_id"]: r["count"] for r in sev_counts if r.get("_id")
    }

    rows = await db.audit_logs.find(query).sort(
        "timestamp", -1
    ).skip(skip).limit(limit).to_list(limit)

    logs = [{
        "id": str(r.get("_id")),
        "timestamp": r.get("timestamp", ""),
        "severity": r.get("severity", "INFO"),
        "category": r.get("category", "admin"),
        "module": r.get("module", ""),
        "action": r.get("action", ""),
        "actor": r.get("actor") or {},
        "target": r.get("target") or {},
        "details": r.get("details", ""),
        "changes": r.get("changes") or [],
        "tags": r.get("tags") or [],
    } for r in rows]

    return {"logs": logs, "total": total, "counters": counters}

# ══════════════════════════════════════════════
# 📊 آمار تحلیلی (نمودارهای پنل وب)
# ══════════════════════════════════════════════

@router.get("/analytics")
async def analytics_admin(
    admin=Depends(get_admin_user),
    days: int = Query(14, ge=7, le=90),
):
    """آمار روزانه بازه اخیر + کاربران فعال + توزیع عملیات و ساعات اوج.

    🌊 موج Analytics-Filters — بدنه به db.stats_analytics_bundle منتقل شد
    (تک‌منبع حقیقت: هم این endpoint مالک، هم wa-analytics با گیت stats.deep).
    خروجی دقیقاً همان شکل قبلی است.
    """
    return await db.stats_analytics_bundle(days)


# ══════════════════════════════════════════════════
#  👑 P3 — Prestige: تنظیمات زنده‌ی تعادل + پایش چالش
# ══════════════════════════════════════════════════

# کلیدهای مجاز اورراید (آستانه‌ی رنک‌ها عمداً اینجا نیست — Design Lock)
# key: (برچسب فارسی, حداقل, حداکثر)
PRESTIGE_CFG_KEYS = {
    "xp_easy":               ("XP پاسخ آسان", 0, 200),
    "xp_medium":             ("XP پاسخ متوسط", 0, 300),
    "xp_hard":               ("XP پاسخ سخت", 0, 500),
    "xp_unknown":            ("XP پاسخ بدون سختی", 0, 300),
    "xp_wrong_first":        ("XP تلاش اولین‌بار", 0, 50),
    "xp_streak_day":         ("XP فعالیت روزانه (استریک)", 0, 200),
    "xp_exam_complete":      ("XP تکمیل آزمون", 0, 500),
    "xp_exam_acc80":         ("بونوس دقت ≥۸۰٪ آزمون", 0, 300),
    "xp_exam_perfect":       ("بونوس برگ کامل آزمون", 0, 300),
    "xp_file_download":      ("XP اولین دانلود هر فایل", 0, 100),
    "xp_ai_daily":           ("XP گفت‌وگوی روزانه‌ی هوشیار", 0, 100),
    "xp_question_approved":  ("XP تأیید سؤال طراحی‌شده", 0, 300),
    "xp_report_useful":      ("XP گزارش مفید", 0, 300),
    "xp_challenge_win":      ("جایزه‌ی برد چالش ارتقا", 0, 1000),
    "xp_apex_win":           ("جایزه‌ی برد چالش Apex (یک‌بار)", 0, 2000),
    "xp_weekly_champion":    ("جایزه‌ی قهرمان هفته", 0, 1000),
    "daily_cap":             ("سقف روزانه‌ی XP پاسخ‌محور", 10, 1000),
    "diminish_after":        ("آستانه‌ی diminishing (صحیح/روز)", 5, 400),
    "shield_answers":        ("سپر ارتقا (تعداد پاسخ)", 0, 200),
    "shield_days":           ("سپر ارتقا (روز)", 0, 90),
    "decay_idle_days":       ("پنجره‌ی رکود Decay (روز)", 3, 90),
    "challenge_cooldown_h":  ("کول‌داون شکست چالش (ساعت)", 1, 168),
    "challenge_cooldown_apex_h": ("کول‌داون شکست Apex (ساعت)", 1, 720),
}


def _prestige_cfg_defaults() -> dict:
    return {
        "xp_easy": db.XP_BY_DIFF["easy"], "xp_medium": db.XP_BY_DIFF["medium"],
        "xp_hard": db.XP_BY_DIFF["hard"], "xp_unknown": db.XP_BY_DIFF["unknown"],
        "xp_wrong_first": db.XP_WRONG_FIRST, "xp_streak_day": db.XP_DAILY_STREAK,
        "xp_exam_complete": db.XP_EXAM_COMPLETE,
        "xp_exam_acc80": db.XP_EXAM_ACC_BONUS,
        "xp_exam_perfect": db.XP_EXAM_PERFECT,
        "xp_file_download": db.XP_FILE_DOWNLOAD, "xp_ai_daily": db.XP_AI_DAILY,
        "xp_question_approved": db.XP_Q_APPROVED,
        "xp_report_useful": db.XP_REPORT_USEFUL,
        "xp_challenge_win": db.XP_CHALLENGE_WIN, "xp_apex_win": db.XP_APEX_WIN,
        "xp_weekly_champion": db.XP_WEEKLY_CHAMPION,
        "daily_cap": db.DAILY_ANSWER_CAP, "diminish_after": db.DIMINISH_AFTER,
        "shield_answers": db.SHIELD_ANSWERS, "shield_days": db.SHIELD_DAYS,
        "decay_idle_days": db.DECAY_IDLE_DAYS,
        "challenge_cooldown_h": db.CH_COOLDOWN_H,
        "challenge_cooldown_apex_h": db.CH_APEX_COOLDOWN_H,
    }


@router.get("/prestige-config")
async def prestige_config_get(admin=Depends(get_admin_user)):
    """خواندن تنظیمات زنده‌ی پرستیژ: پیش‌فرض + اورراید + مؤثر + آمار چالش"""
    try:
        doc = await db.settings.find_one({"_id": "prestige_config"}) or {}
    except Exception:
        doc = {}
    values = doc.get("values") or {}
    if not isinstance(values, dict):
        values = {}
    defaults = _prestige_cfg_defaults()
    effective = dict(defaults)
    for k, v in values.items():
        if k in PRESTIGE_CFG_KEYS and isinstance(v, (int, float)):
            effective[k] = int(v)
    stats = {}
    try:
        stats = await db.prestige_challenge_stats()
    except Exception:
        stats = {}
    return {
        "defaults": defaults, "overrides": values, "effective": effective,
        "meta": {k: {"label": v[0], "min": v[1], "max": v[2]}
                 for k, v in PRESTIGE_CFG_KEYS.items()},
        "updated_at": doc.get("updated_at", ""),
        "challenge_stats": stats,
    }


class PrestigeConfigPut(BaseModel):
    values: dict = {}


@router.put("/prestige-config")
async def prestige_config_put(body: PrestigeConfigPut, admin=Depends(get_admin_user)):
    """ذخیره‌ی اوررایدها — بدون ری‌دیپلوی (کش ۶۰ثانیه‌ای فوراً باطل می‌شود).
    مقادیر نامعتبر/کلید ناشناخته ⇒ rejected، بدون ذخیره‌ی آن کلید."""
    if not isinstance(body.values, dict):
        raise HTTPException(422, "ساختار values نامعتبر است")
    clean, rejected = {}, []
    for k, v in (body.values or {}).items():
        if k not in PRESTIGE_CFG_KEYS:
            rejected.append(k)
            continue
        try:
            num = float(v)
        except Exception:
            rejected.append(k)
            continue
        lo, hi = PRESTIGE_CFG_KEYS[k][1], PRESTIGE_CFG_KEYS[k][2]
        if not (lo <= num <= hi):
            rejected.append(k)
            continue
        clean[k] = int(num)
    try:
        old_doc = await db.settings.find_one({"_id": "prestige_config"}) or {}
    except Exception:
        old_doc = {}
    old = old_doc.get("values") or {}
    await db.settings.update_one(
        {"_id": "prestige_config"},
        {"$set": {"values": clean,
                  "updated_at": datetime.now().isoformat()}},
        upsert=True)
    try:
        setattr(db, "_pcfgc", None)      # باطل‌سازی فوری کش ۶۰ثانیه‌ای موتور
    except Exception:
        pass
    await _audit(admin, "به‌روزرسانی تنظیمات زنده‌ی پرستیژ", "Prestige",
                 severity="HIGH", before=old, after=clean,
                 tags=["پرستیژ", "تعادل", "پنل_وب"])
    return {"ok": True, "applied": clean, "rejected": rejected}
