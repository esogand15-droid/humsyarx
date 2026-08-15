"""🎓 Content Admin — 🌊 موج C1: enforce اسکوپ ورودی در سطح endpoint"""
import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Optional, List
from api.auth import get_content_admin_user, get_content_global_user, resolve_content_intake
from api.telegram_send import upload_and_get_file_id
from api.routers.admin_panel import _audit
from database import db

router = APIRouter()
TERMS = ['ترم ۱', 'ترم ۲', 'ترم ۳', 'ترم ۴', 'ترم ۵']
CONTENT_TYPES = ['video', 'ppt', 'pdf', 'note', 'test', 'voice']
GLOBAL_USER = get_content_global_user  # بخش‌های بدون scope (schedule/grades/reports) — رفتار دقیق قبلی


async def _deny_intake(item_intake: str, admin: dict):
    """۴۰۳ اگر آیتم خارج از scope کاربر باشد.

    wrapperهای permission-based می‌توانند scope حل‌شده را روی admin بگذارند؛
    مسیرهای قدیمی بدون آن همچنان از منبع واحد db استفاده می‌کنند.
    """
    scope = admin.get("_scope")
    if scope:
        if scope.get("kind") == "global":
            return
        if (item_intake or "") == (scope.get("intake") or ""):
            return
        raise HTTPException(403, "intake_out_of_scope")
    if not await db.can_access_intake(admin["id"], item_intake or ''):
        raise HTTPException(403, "intake_out_of_scope")


async def _read_intake(item_intake: str, admin: dict) -> bool:
    """🌊 C1.5 — گیت مشاهده؛ سراسری برای scoped فقط‌خواندنی است."""
    scope = admin.get("_scope")
    if scope:
        if scope.get("kind") == "global":
            return False
        own = scope.get("intake") or ""
        if (item_intake or "") == own:
            return False
        if (item_intake or "") == "":
            return True
        raise HTTPException(403, "intake_out_of_scope")
    if await db.can_access_intake(admin["id"], item_intake or ''):
        return False
    scope = admin.get("_scope") or {}
    if scope.get("kind") == "scoped" and (item_intake or '') == '':
        return True
    raise HTTPException(403, "intake_out_of_scope")


@router.get("/intakes")
async def content_intakes(admin=Depends(get_content_admin_user)):
    """🌊 C1 — لیست ورودی‌های فعال برای picker مینی‌اپ + scope فعلی کاربر.
    ادمین ورودی خاص: فقط scope خودش را می‌بیند (گزینه‌ای برای انتخاب ندارد)."""
    scope = admin.get("_scope") or {"kind": "global", "intake": None}
    items = await db.get_all_intakes()
    active = [{"code": i["code"], "label": i["label"]}
              for i in items if i.get("active", True)]
    own = scope.get("intake") or ""
    own_label = next((i["label"] for i in items if i["code"] == own), own)
    return {
        "scope_kind": scope.get("kind"),
        "scope_intake": own if scope.get("kind") == "scoped" else None,
        "scope_label": own_label if scope.get("kind") == "scoped" else None,
        "intakes": active if scope.get("kind") == "global"
                   else [{"code": own, "label": own_label}],
    }


@router.get("/overview")
async def overview(admin=Depends(get_content_admin_user),
                   intake: Optional[str] = Query(None),
                   effective: Optional[bool] = Query(False)):
    iv = resolve_content_intake(admin, intake)
    # آمار هم‌scope با ورودی انتخاب‌شده (§۱۷ spec) — بدون نشت cross-intake
    s = await db.content_admin_stats(intake=iv)
    out = {"intake": iv,
        "pending_questions":s["q_pending"],
        "approved_questions":s["q_total"],
        "total_resources":s["bs_total"],
        "upcoming_exams":0,"total_faq":0}
    # 🌊 C1.5 — زیرساخت «آمار مؤثر» (§۲۳ spec): اختصاصی + سراسری —
    # فقط وقتی صراحتاً درخواست شود (رفتار پیش‌فرض دست‌نخورده)
    if effective:
        e = await db.content_admin_stats(intake=iv, effective=True)
        out["effective"] = {
            "pending_questions": e["q_pending"],
            "approved_questions": e["q_total"],
            "total_resources": e["bs_total"],
        }
    return out

@router.get("/questions/pending")
async def pending_questions(admin=Depends(get_content_admin_user),
                            intake: Optional[str] = Query(None)):
    iv = resolve_content_intake(admin, intake)
    docs=await db.questions.find({"approved":False,"intake":iv}).sort("created_at",-1).to_list(100)
    return {"intake": iv,
        "questions":[{"id":str(d["_id"]),"lesson":d.get("lesson",""),"topic":d.get("topic",""),
        "difficulty":d.get("difficulty",""),"question":d.get("question",""),"options":d.get("options",[]),
        "correct":d.get("correct_answer",0),"explanation":d.get("explanation",""),
        "creator_name":d.get("creator_name",""),"created_at":d.get("created_at","")[:10],
        "intake":d.get("intake",""),
        "source":d.get("source","bot")} for d in docs]}

@router.post("/questions/{qid}/approve")
async def approve_question(qid: str, admin=Depends(get_content_admin_user)):
    q=await db.get_question_by_id(qid)
    if not q: raise HTTPException(404)
    await _deny_intake(q.get("intake",""), admin)
    await db.approve_question(qid)
    await _audit(
        admin, "تأیید سؤال پیشنهادی", "Questions", severity="INFO",
        target_id=qid, target_type="question",
        target_label=f"{q.get('lesson','')} — {q.get('topic','')}"[:300],
        before={"approved": False}, after={"approved": True},
        tags=["سؤال", "تأیید", "پنل_وب"],
    )
    # db.approve_question منبع واحد پاداش + Inbox + DM طراح است.
    return {"ok":True}

@router.post("/questions/{qid}/reject")
async def reject_question(qid: str, admin=Depends(get_content_admin_user)):
    q=await db.get_question_by_id(qid)
    if not q: raise HTTPException(404)
    await _deny_intake(q.get("intake",""), admin)
    await db.delete_question(qid)
    await _audit(
        admin, "رد و حذف سؤال پیشنهادی", "Questions", severity="WARNING",
        target_id=qid, target_type="question",
        target_label=f"{q.get('lesson','')} — {q.get('topic','')}"[:300],
        before={"approved": False, "question": q.get("question", "")[:300]},
        after={"deleted": True}, tags=["سؤال", "رد", "پنل_وب"],
    )
    if q.get("source")=="webapp" and q.get("creator_id"):
        await db.notify_user(
            q["creator_id"], "question_rejected", title="❌ سؤالت رد شد",
            body=f"📚 {q.get('lesson','')} — {q.get('topic','')}",
            link="/learn/my-questions", dm=(
                f"❌ <b>سؤالت رد شد</b>\n\n"
                f"📚 {q.get('lesson','')} — {q.get('topic','')}"),
        )
    return {"ok":True}

# ── 🌊 موج Q-Editor — ویرایش سؤال پیش از تأیید (scope-aware + audit) ──
class QuestionPatch(BaseModel):
    question: Optional[str] = None
    options: Optional[List[str]] = None
    correct: Optional[int] = None                    # ایندکس گزینه‌ی صحیح (۰-مبنا)
    explanation: Optional[str] = None
    difficulty: Optional[str] = None                 # easy | medium | hard
    lesson: Optional[str] = None
    topic: Optional[str] = None

@router.patch("/questions/{qid}")
async def patch_question(qid: str, body: QuestionPatch,
                         admin=Depends(get_content_admin_user)):
    """ویرایش سؤالِ در انتظار بازبینی — دقیقاً همان scope گیت approve/reject."""
    q = await db.get_question_by_id(qid)
    if not q: raise HTTPException(404)
    await _deny_intake(q.get("intake",""), admin)
    if q.get("approved"):
        raise HTTPException(422, "فقط سؤال‌های در انتظار بازبینی قابل ویرایش‌اند")

    updates = {}
    if body.question is not None:
        t = body.question.strip()
        if len(t) < 5: raise HTTPException(422, "متن سؤال خیلی کوتاه است")
        updates["question"] = t[:1000]
    if body.lesson is not None: updates["lesson"] = body.lesson.strip()[:80]
    if body.topic is not None: updates["topic"] = body.topic.strip()[:80]
    if body.explanation is not None:
        updates["explanation"] = body.explanation.strip()[:2000]
    if body.difficulty is not None:
        if body.difficulty not in ("easy","medium","hard"):
            raise HTTPException(422, "سختی نامعتبر است")
        updates["difficulty"] = body.difficulty
    if body.options is not None:
        ops = [str(o).strip()[:300] for o in body.options]
        ops = [o for o in ops if o]
        if not (2 <= len(ops) <= 6): raise HTTPException(422, "گزینه‌ها باید بین ۲ تا ۶ باشند")
        updates["options"] = ops
        # سازگاری: اگر ایندکس صحیحِ قبلی از محدوده‌ی جدید بیرون افتاد، clamp
        cur = q.get("correct_answer", 0)
        if isinstance(cur, int) and cur >= len(ops) and body.correct is None:
            updates["correct_answer"] = 0
    if body.correct is not None:
        final_ops = updates.get("options", q.get("options", []))
        if not (0 <= body.correct < len(final_ops)):
            raise HTTPException(422, "گزینه‌ی صحیح خارج از محدوده است")
        updates["correct_answer"] = body.correct

    if not updates: raise HTTPException(422, "چیزی برای ویرایش نیست")
    ok = await db.update_question(qid, updates)
    if not ok: raise HTTPException(500, "ویرایش انجام نشد")
    try:
        await db.log_action(
            admin["id"], (admin.get("_db") or {}).get("name", str(admin["id"])),
            await db.get_actor_role_label(admin["id"]),
            "ویرایش سؤال در انتظار بازبینی", "Questions", "admin", "WARNING",
            str(qid), "question", f"{q.get('lesson','')} — {q.get('topic','')}"[:300],
            None, {k: (v if not isinstance(v, list) else f"{len(v)} گزینه")
                     for k, v in updates.items()},
            "", ["ویرایش_سؤال", "پنل_وب"])
    except Exception:
        pass
    return {"ok": True, "changed": list(updates.keys())}

# ── 🌊 موج Q-Import — درون‌ریزی گروهی سؤال (scope-aware + audit) ──
class QuestionImportItem(BaseModel):
    lesson: str = ""
    topic: str = ""
    difficulty: str = ""
    question: str = ""
    options: List[str] = []
    correct: int = 0
    explanation: str = ""

class QuestionImportBody(BaseModel):
    items: List[QuestionImportItem] = Field(default_factory=list, max_length=200)
    approve: bool = False           # درج مستقیمِ تأییدشده؟ (پیش‌فرض: به صف بازبینی)

@router.post("/questions/bulk-import")
async def bulk_import_questions(body: QuestionImportBody, intake: Optional[str] = Query(None),
                                admin=Depends(get_content_admin_user)):
    """درون‌ریزی گروهی — تا ۲۰۰ سؤال؛ همان scope گیت approve/reject. آیتم‌های
    معیوب رد و با متن خطا گزارش می‌شوند؛ بقیه درج می‌شوند."""
    iv = resolve_content_intake(admin, intake)
    if not body.items:
        raise HTTPException(422, "فهرست سؤال‌ها خالی است")
    res = await db.add_questions_bulk(
        [it.model_dump() for it in body.items],
        creator=admin["id"], intake=iv, auto_approve=body.approve)
    try:
        await db.log_action(
            admin["id"], (admin.get("_db") or {}).get("name", str(admin["id"])),
            await db.get_actor_role_label(admin["id"]),
            "درون‌ریزی گروهی سؤال", "Questions", "admin", "WARNING",
            "", "question_bank", f"ورودی {iv or 'سراسری'}",
            None, {"درج": res["inserted"], "ناموفق": len(res["failed"]),
                   "حالت": "تأیید مستقیم" if body.approve else "صف بازبینی"},
            "", ["درون‌ریزی", "پنل_وب"])
    except Exception:
        pass
    return {"ok": True, "inserted": res["inserted"], "failed": res["failed"],
            "approve": body.approve, "intake": iv}

@router.get("/schedule")
async def schedule_list(admin=Depends(GLOBAL_USER), stype: Optional[str]=Query(None)):
    items=await db.get_schedules(stype=stype, upcoming=False)
    return {"schedule":[{"id":str(s["_id"]),"type":s.get("type",""),"lesson":s.get("lesson",""),
        "teacher":s.get("teacher",""),"date":s.get("date",""),"time":s.get("time",""),
        "location":s.get("location",""),"group":db.normalize_group(s.get("group","هر دو")) or "هر دو","note":s.get("notes",""),
        "flex_type":s.get("flex_type","fixed"),"flex_note":s.get("flex_note","")} for s in items]}

class ScheduleCreate(BaseModel):
    type: str; lesson: str; teacher: str=""; date: str; time: str=""; group: str="هر دو"
    location: str=""; note: str=""; flex_type: str="fixed"

@router.post("/schedule")
async def add_schedule(body: ScheduleCreate, admin=Depends(GLOBAL_USER)):
    if body.type not in ("class", "exam", "makeup"):
        raise HTTPException(422, "نوع برنامه نامعتبر است")
    if body.flex_type not in ("fixed", "flexible"):
        raise HTTPException(422, "نوع زمان‌بندی نامعتبر")
    try:
        datetime.strptime(body.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(422, "فرمت تاریخ YYYY-MM-DD")
    group = db.normalize_group(body.group) or "هر دو"
    sid = await db.add_schedule(
        stype=body.type, lesson=body.lesson.strip(), teacher=body.teacher.strip(),
        date=body.date, time=body.time, location=body.location.strip(),
        notes=body.note.strip(), group=group, flex_type=body.flex_type)
    item = await db.get_schedule_by_id(str(sid)) or {
        "_id": sid, "type": body.type, "lesson": body.lesson.strip(),
        "teacher": body.teacher.strip(), "date": body.date, "time": body.time,
        "location": body.location.strip(), "notes": body.note.strip(), "group": group,
    }
    notice = await db.schedule_notify_event(item, "created")
    await _audit(
        admin, "ایجاد برنامه آموزشی", "Schedules", severity="INFO",
        target_id=str(sid), target_type="schedule", target_label=body.lesson.strip(),
        after={"type": body.type, "date": body.date, "time": body.time,
               "group": group, "notified": notice.get("notified", 0)},
        tags=["برنامه", body.type, "پنل_وب"],
    )
    return {"ok": True, "id": str(sid), "notified": notice.get("notified", 0)}


class ScheduleUpdate(BaseModel):
    lesson: str; teacher: str=""; date: str; time: str=""; group: str="هر دو"
    location: str=""; note: str=""; flex_type: str="fixed"

@router.patch("/schedule/{sid}")
async def edit_schedule(sid: str, body: ScheduleUpdate, admin=Depends(GLOBAL_USER)):
    try:
        datetime.strptime(body.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(422, "فرمت تاریخ YYYY-MM-DD")
    old = await db.get_schedule_by_id(sid)
    if not old:
        raise HTTPException(404, "برنامه پیدا نشد")
    group = db.normalize_group(body.group) or "هر دو"
    ok = await db.update_schedule_full(
        sid, body.lesson.strip(), body.teacher.strip(), body.date, body.time,
        body.location.strip(), body.note.strip(), group, body.flex_type)
    if not ok:
        raise HTTPException(404, "برنامه پیدا نشد")
    item = await db.get_schedule_by_id(sid) or {
        **old, "lesson": body.lesson.strip(), "teacher": body.teacher.strip(),
        "date": body.date, "time": body.time, "location": body.location.strip(),
        "notes": body.note.strip(), "group": group, "flex_type": body.flex_type,
    }
    notice = await db.schedule_notify_event(item, "updated")
    await _audit(
        admin, "ویرایش برنامه آموزشی", "Schedules", severity="WARNING",
        target_id=sid, target_type="schedule", target_label=body.lesson.strip(),
        before={"lesson": old.get("lesson"), "date": old.get("date"),
                "time": old.get("time"), "group": old.get("group")},
        after={"lesson": body.lesson.strip(), "date": body.date,
               "time": body.time, "group": group,
               "notified": notice.get("notified", 0)},
        tags=["برنامه", old.get("type", ""), "پنل_وب"],
    )
    return {"ok": True, "notified": notice.get("notified", 0)}


@router.delete("/schedule/{sid}")
async def del_schedule(sid: str, admin=Depends(GLOBAL_USER)):
    old = await db.get_schedule_by_id(sid)
    if not old:
        raise HTTPException(404, "برنامه پیدا نشد")
    await db.delete_schedule(sid)
    notice = await db.schedule_notify_event(old, "cancelled")
    await _audit(
        admin, "حذف و لغو برنامه آموزشی", "Schedules", severity="HIGH",
        target_id=sid, target_type="schedule", target_label=old.get("lesson", ""),
        before={"type": old.get("type"), "date": old.get("date"),
                "time": old.get("time"), "group": old.get("group")},
        after={"deleted": True, "notified": notice.get("notified", 0)},
        tags=["برنامه", "لغو", old.get("type", ""), "پنل_وب"],
    )
    return {"ok": True, "notified": notice.get("notified", 0)}


# ── 🔄 اعلام تغییر زمان کلاس منعطف (flex) ──

@router.get("/schedule/flex")
async def flex_list(admin=Depends(GLOBAL_USER)):
    items = await db.get_schedules(upcoming=True)
    flex = [s for s in items if s.get("flex_type")=="flexible"]
    return {"items":[{"id":str(s["_id"]),"lesson":s.get("lesson",""),"teacher":s.get("teacher",""),
        "date":s.get("date",""),"time":s.get("time",""),"flex_note":s.get("flex_note","")} for s in flex]}

class FlexChange(BaseModel):
    date: str; time: str; note: str=""

@router.post("/schedule/{sid}/flex-change")
async def flex_change(sid: str, body: FlexChange, admin=Depends(GLOBAL_USER)):
    try:
        datetime.strptime(body.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(422, "فرمت تاریخ YYYY-MM-DD")
    sched = await db.get_schedule_by_id(sid)
    if not sched:
        raise HTTPException(404, "برنامه پیدا نشد")
    ok = await db.update_schedule_time(sid, body.date, body.time, body.note)
    if not ok:
        raise HTTPException(500, "تغییر زمان ذخیره نشد")
    item = {**sched, "date": body.date, "time": body.time,
            "flex_note": body.note}
    notice = await db.schedule_notify_event(item, "time_changed")
    await _audit(
        admin, "اعلام تغییر زمان برنامه", "Schedules", severity="WARNING",
        target_id=sid, target_type="schedule", target_label=sched.get("lesson", ""),
        before={"date": sched.get("date"), "time": sched.get("time")},
        after={"date": body.date, "time": body.time,
               "notified": notice.get("notified", 0)},
        tags=["برنامه", "تغییر_زمان", sched.get("type", ""), "پنل_وب"],
    )
    return {"ok": True, "notified": notice.get("notified", 0)}


@router.get("/faq")
async def faq_list(admin=Depends(get_content_admin_user)):
    docs=await db.faq_get_all()
    return {"items":[{"id":str(d["_id"]),"category":d.get("category","عمومی"),
        "question":d.get("question",""),"answer":d.get("answer","")} for d in docs]}

class FaqCreate(BaseModel):
    category: str="عمومی"; question: str=Field(min_length=5); answer: str=Field(min_length=5)

@router.post("/faq")
async def add_faq(body: FaqCreate, admin=Depends(get_content_admin_user)):
    fid = await db.faq_add(body.question, body.answer, body.category)
    await _audit(admin, "ایجاد پرسش متداول", "Content", severity="INFO",
        target_id=str(fid or ""), target_type="faq", target_label=body.question[:300],
        after={"category": body.category}, tags=["FAQ", "ایجاد", "پنل_وب"])
    return {"ok":True}

@router.delete("/faq/{fid}")
async def del_faq(fid: str, admin=Depends(get_content_admin_user)):
    old = await db.faq_get(fid)
    if not old: raise HTTPException(404, "پرسش متداول پیدا نشد")
    await db.faq_delete(fid)
    await _audit(admin, "حذف پرسش متداول", "Content", severity="HIGH",
        target_id=fid, target_type="faq", target_label=old.get("question", "")[:300],
        before={"category": old.get("category")}, after={"deleted": True},
        tags=["FAQ", "حذف", "پنل_وب"])
    return {"ok":True}

class GradeBulk(BaseModel):
    entries: List[dict]; lesson: str; exam_title: str; exam_date: str

@router.post("/grades/bulk")
async def bulk_grades(body: GradeBulk, admin=Depends(GLOBAL_USER)):
    from api.routers import academic_admin as academic_api
    try:
        entries = [academic_api.GradeEntry(
            user_id=e.get("user_id", e.get("student_id")), score=e.get("score"))
            for e in body.entries]
        payload = academic_api.GradeBulkCreate(
            entries=entries, lesson=body.lesson,
            exam_title=body.exam_title, exam_date=body.exam_date)
    except Exception as exc:
        raise HTTPException(422, f"داده نمرات نامعتبر است: {exc}")
    return await academic_api.grades_bulk_create(body=payload, admin=admin)

@router.get("/grades/recent")
async def grades_recent(admin=Depends(GLOBAL_USER), skip: int=Query(0), limit: int=Query(30),
                         intake: Optional[str]=Query(None)):
    items = await db.grade_list_recent(skip=skip, limit=limit, intake=intake)
    total = await db.grade_count_recent(intake=intake)
    # اسم دانشجوها رو batch می‌گیریم تا برای هر نمره کوئری جدا نزنیم
    uids = list({g.get("student_id") for g in items if g.get("student_id")})
    names = {}
    for uid in uids:
        u = await db.get_user(uid)
        names[uid] = u.get("name","") if u else f"#{uid}"
    return {"total": total, "grades":[{"id":str(g["_id"]),"student_id":g.get("student_id"),
        "student_name":names.get(g.get("student_id"),""),"lesson":g.get("lesson",""),
        "exam_title":g.get("exam_title",""),"exam_date":g.get("exam_date",""),
        "score":g.get("score",0)} for g in items]}

@router.get("/grades/find-student")
async def grades_find_student(name: str = Query(...), admin=Depends(GLOBAL_USER)):
    # FIX جدید: به‌جای تطبیق دقیق نام (find_students_by_name که با کوچیک‌ترین
    # اختلاف تایپی یا سرچ جزئی هیچی برنمی‌گردوند)، حالا از search_users
    # استفاده می‌شه — همون تابع جامعی که توی خود ربات (پنل ادمین، جست‌وجوی
    # اشتراک، AI ادمین) استفاده می‌شه: نام (جزئی)، شماره دانشجویی (جزئی)،
    # یوزرنیم تلگرام با/بدون @ (جزئی)، آیدی عددی تلگرام (دقیق) — همه با یک کوئری.
    results = await db.search_users(name)
    students = [s for s in results if s.get("approved")]
    return {"students":[{"id":s.get("user_id"),"name":s.get("name",""),
        "student_id":s.get("student_id",""),"group":s.get("group","")} for s in students]}

class GradeUpdate(BaseModel):
    score: float = Field(ge=0, le=20)

@router.patch("/grades/{gid}")
async def edit_grade(gid: str, body: GradeUpdate, admin=Depends(GLOBAL_USER)):
    # همان business entry point امنی که Web Admin مصرف می‌کند.
    from api.routers import academic_admin as academic_api
    return await academic_api.grade_update(
        grade_id=gid, body=academic_api.GradeUpdate(score=body.score), admin=admin)

@router.delete("/grades/{gid}")
async def del_grade(gid: str, admin=Depends(GLOBAL_USER)):
    from api.routers import academic_admin as academic_api
    return await academic_api.grade_delete(grade_id=gid, admin=admin)

# ══════════════════════════════════════════════
# 🧬 علوم پایه — ترم‌ها / درس‌ها / جلسات / محتوا
# ══════════════════════════════════════════════

@router.get("/basic-science/terms")
async def bs_terms(admin=Depends(get_content_admin_user)):
    return {"terms": TERMS}

@router.get("/basic-science/lessons")
async def bs_lessons(term: str = Query(...), admin=Depends(get_content_admin_user),
                     intake: Optional[str] = Query(None)):
    iv = resolve_content_intake(admin, intake)
    scope = admin.get("_scope") or {}
    # 🌊 C1.5 — ادمین ورودی خاص: درس‌های سراسری هم با فلگ readonly
    # دیده می‌شوند (§۲۲ spec: Global=هسته‌ی پایه، فقط‌خواندنی)
    if scope.get("kind") == "scoped":
        items = await db.bs_get_lessons(term, intake=[iv, ''])
        return {"intake": iv,
            "lessons":[{"id":str(l["_id"]),"name":l.get("name",""),
                        "teacher":l.get("teacher",""),
                        "readonly": (l.get("intake") or '') != iv} for l in items]}
    items = await db.bs_get_lessons(term, intake=iv)
    return {"intake": iv,
        "lessons":[{"id":str(l["_id"]),"name":l.get("name",""),"teacher":l.get("teacher",""),
                    "readonly": False} for l in items]}

class BsLessonCreate(BaseModel):
    term: str; name: str = Field(min_length=1); teacher: str = ""; intake: str = ""


class BsLessonUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    teacher: Optional[str] = Field(default=None, max_length=120)


@router.post("/basic-science/lessons")
async def bs_add_lesson_ep(body: BsLessonCreate, admin=Depends(get_content_admin_user)):
    if body.term not in TERMS: raise HTTPException(422, "ترم نامعتبر")
    iv = resolve_content_intake(admin, body.intake)
    r = await db.bs_add_lesson(body.term, body.name.strip(), body.teacher.strip(), intake=iv)
    if r is None: raise HTTPException(409, "این درس قبلاً در این ترم ثبت شده")
    await _audit(admin, "ایجاد درس علوم پایه", "Content", severity="INFO",
        target_id=str(r), target_type="lesson", target_label=body.name.strip(),
        after={"term": body.term, "teacher": body.teacher.strip(), "intake": iv},
        tags=["محتوا", "ایجاد_درس", "پنل_وب"])
    return {"ok":True, "id":str(r)}


@router.patch("/basic-science/lessons/{lid}")
async def bs_edit_lesson_ep(lid: str, body: BsLessonUpdate,
                            admin=Depends(get_content_admin_user)):
    old = await db.bs_get_lesson(lid)
    if not old:
        raise HTTPException(404, "درس پیدا نشد")
    await _deny_intake(old.get("intake", ""), admin)
    updates = {}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.teacher is not None:
        updates["teacher"] = body.teacher.strip()
    if not updates:
        raise HTTPException(422, "چیزی برای ویرایش نیست")
    ok = await db.bs_update_lesson(lid, updates)
    if not ok:
        raise HTTPException(500, "ویرایش درس انجام نشد")
    await _audit(
        admin, "ویرایش درس علوم پایه", "Content", severity="WARNING",
        target_id=lid, target_type="lesson", target_label=updates.get("name", old.get("name", "")),
        before={k: old.get(k, "") for k in updates}, after=updates,
        tags=["محتوا", "ویرایش_درس", "پنل_وب"],
    )
    return {"ok": True, "changed": list(updates)}


@router.delete("/basic-science/lessons/{lid}")
async def bs_del_lesson_ep(lid: str, admin=Depends(get_content_admin_user)):
    old = await db.bs_get_lesson(lid)
    if not old: raise HTTPException(404, "درس پیدا نشد")
    await _deny_intake(old.get("intake", ""), admin)
    await db.bs_delete_lesson(lid)
    await _audit(admin, "حذف درس علوم پایه", "Content", severity="HIGH",
        target_id=lid, target_type="lesson", target_label=old.get("name", ""),
        before={"term": old.get("term"), "teacher": old.get("teacher"),
                "intake": old.get("intake", "")}, after={"deleted": True},
        tags=["محتوا", "حذف_درس", "پنل_وب"])
    return {"ok":True}

@router.get("/basic-science/lessons/{lid}/sessions")
async def bs_sessions_ep(lid: str, admin=Depends(get_content_admin_user)):
    # 🌊 C1.5 — مشاهده‌ی فقط‌خواندنیِ جلساتِ درسِ سراسری برای scoped
    ro = await _read_intake(await db.lesson_intake(lid), admin)
    scope = admin.get("_scope") or {}
    # 🍴 C2 — نمای مؤثر برای scoped روی درس سراسری: fork خودش جایگزین base
    if ro and scope.get("kind") == "scoped":
        items = await db.bs_get_sessions_effective(
            lid, [scope.get("intake") or '', ''])
    else:
        items = await db.bs_get_sessions(lid)
    return {"readonly": ro,
        "sessions":[{"id":str(s["_id"]),"number":s.get("number",0),"topic":s.get("topic",""),
        "teacher":s.get("teacher",""),
        # 🍴 C2 — متادیتای fork برای رندر دکمه‌های ✂️/↩️ و نشان ⭐ در مینی‌اپ
        "intake":s.get("intake") or "", "is_fork":bool(s.get("fork_of"))} for s in items]}

class BsSessionCreate(BaseModel):
    number: int = Field(ge=1, le=10000)
    topic: str = Field(min_length=1, max_length=200)
    teacher: str = Field(default="", max_length=120)


class BsSessionUpdate(BaseModel):
    number: Optional[int] = Field(default=None, ge=1, le=10000)
    topic: Optional[str] = Field(default=None, min_length=1, max_length=200)
    teacher: Optional[str] = Field(default=None, max_length=120)


@router.post("/basic-science/lessons/{lid}/sessions")
async def bs_add_session_ep(lid: str, body: BsSessionCreate, admin=Depends(get_content_admin_user)):
    await _deny_intake(await db.lesson_intake(lid), admin)
    sid = await db.bs_add_session(lid, body.number, body.topic.strip(), body.teacher.strip())
    await _audit(admin, "ایجاد جلسه علوم پایه", "Content", severity="INFO",
        target_id=str(sid), target_type="session",
        target_label=f"جلسه {body.number} — {body.topic.strip()}",
        after={"lesson_id": lid, "number": body.number, "teacher": body.teacher.strip()},
        tags=["محتوا", "ایجاد_جلسه", "پنل_وب"])
    return {"ok":True, "id":sid}


@router.patch("/basic-science/sessions/{sid}")
async def bs_edit_session_ep(sid: str, body: BsSessionUpdate,
                             admin=Depends(get_content_admin_user)):
    old = await db.bs_get_session(sid)
    if not old:
        raise HTTPException(404, "جلسه پیدا نشد")
    await _deny_intake(await db.session_intake(sid), admin)
    updates = {}
    if body.number is not None:
        updates["number"] = body.number
    if body.topic is not None:
        updates["topic"] = body.topic.strip()
    if body.teacher is not None:
        updates["teacher"] = body.teacher.strip()
    if not updates:
        raise HTTPException(422, "چیزی برای ویرایش نیست")
    ok = await db.bs_update_session(sid, updates)
    if not ok:
        raise HTTPException(500, "ویرایش جلسه انجام نشد")
    await _audit(
        admin, "ویرایش جلسه علوم پایه", "Content", severity="WARNING",
        target_id=sid, target_type="session",
        target_label=f"جلسه {updates.get('number', old.get('number',''))} — {updates.get('topic', old.get('topic',''))}",
        before={k: old.get(k, "") for k in updates}, after=updates,
        tags=["محتوا", "ویرایش_جلسه", "پنل_وب"],
    )
    return {"ok": True, "changed": list(updates)}


@router.delete("/basic-science/sessions/{sid}")
async def bs_del_session_ep(sid: str, admin=Depends(get_content_admin_user)):
    old = await db.bs_get_session(sid)
    if not old: raise HTTPException(404, "جلسه پیدا نشد")
    await _deny_intake(await db.session_intake(sid), admin)
    # 🍴 Q1 — حذف baseای که fork دارد ⇒ orphan؛ با 409 مسدود می‌شود
    if await db.bs_session_has_forks(sid):
        raise HTTPException(409,
            "این جلسه نسخه‌ی اختصاصی (fork) دارد؛ ابتدا نسخه‌ها را بازگردانید")
    await db.bs_delete_session(sid)
    await _audit(admin, "حذف جلسه علوم پایه", "Content", severity="HIGH",
        target_id=sid, target_type="session",
        target_label=f"جلسه {old.get('number','')} — {old.get('topic','')}",
        before={"lesson_id": old.get("lesson_id"), "teacher": old.get("teacher")},
        after={"deleted": True}, tags=["محتوا", "حذف_جلسه", "پنل_وب"])
    return {"ok":True}

@router.get("/basic-science/sessions/{sid}/content")
async def bs_content_ep(sid: str, admin=Depends(get_content_admin_user)):
    # 🌊 C1.5 — مشاهده‌ی فقط‌خواندنیِ محتوای جلسه‌ی سراسری برای scoped
    ro = await _read_intake(await db.session_intake(sid), admin)
    items = await db.bs_get_content(sid)
    # 🍴 C2 — نشان نسخه‌ی اختصاصی برای سربرگ مینی‌اپ
    sdoc = await db.bs_get_session(sid) or {}
    return {"readonly": ro, "is_fork": bool(sdoc.get("fork_of")),
        "content":[{"id":str(c["_id"]),"type":c.get("type",""),"description":c.get("description",""),
        "extra_info":c.get("extra_info",""),"downloads":c.get("downloads",0)} for c in items]}

@router.post("/basic-science/sessions/{sid}/content")
async def bs_add_content_ep(sid: str, ctype: str = Form(...), description: str = Form(""),
                             extra_info: str = Form(""), file: UploadFile = File(...),
                             admin=Depends(get_content_admin_user)):
    if ctype not in CONTENT_TYPES: raise HTTPException(422, "نوع محتوا نامعتبر")
    await _deny_intake(await db.session_intake(sid), admin)
    raw = await file.read()
    if len(raw) > 45 * 1024 * 1024: raise HTTPException(413, "حجم فایل بیش از حد مجاز است (۴۵MB)")
    file_id = await upload_and_get_file_id(admin["id"], file.filename or "file", raw,
        file.content_type or "application/octet-stream")
    if not file_id: raise HTTPException(502, "آپلود فایل به تلگرام ناموفق بود")
    cid = await db.bs_add_content(sid, ctype, file_id, description.strip(), extra_info.strip())
    await _audit(admin, "افزودن فایل جلسه", "Content", severity="INFO",
        target_id=str(cid), target_type="content_item",
        target_label=description.strip() or (file.filename or "file"),
        after={"session_id": sid, "type": ctype, "extra_info": extra_info.strip()},
        tags=["محتوا", "افزودن_فایل", "پنل_وب"])
    return {"ok":True, "id":str(cid)}

@router.delete("/basic-science/content/{cid}")
async def bs_del_content_ep(cid: str, admin=Depends(get_content_admin_user)):
    old = await db.bs_get_content_item(cid)
    if not old: raise HTTPException(404, "فایل پیدا نشد")
    await _deny_intake(await db.content_intake(cid), admin)
    await db.bs_delete_content(cid)
    await _audit(admin, "حذف فایل جلسه", "Content", severity="HIGH",
        target_id=cid, target_type="content_item", target_label=old.get("description", ""),
        before={"session_id": old.get("session_id"), "type": old.get("type")},
        after={"deleted": True}, tags=["محتوا", "حذف_فایل", "پنل_وب"])
    return {"ok":True}

# ══════════════════════════════════════════════
# 📖 رفرنس‌ها — موضوع‌ها / کتاب‌ها / فایل‌ها
# ══════════════════════════════════════════════

@router.get("/references/subjects")
async def ref_subjects_ep(admin=Depends(get_content_admin_user),
                          intake: Optional[str] = Query(None)):
    iv = resolve_content_intake(admin, intake)
    scope = admin.get("_scope") or {}
    # 🌊 C1.5 — ادمین ورودی خاص: موضوعات سراسری هم با فلگ readonly (§۲۲)
    if scope.get("kind") == "scoped":
        items = await db.ref_get_subjects(intake=[iv, ''])
        return {"intake": iv,
            "subjects":[{"id":str(s["_id"]),"name":s.get("name",""),
                         "intake": s.get("intake") or "",
                         "readonly": (s.get("intake") or '') != iv} for s in items]}
    items = await db.ref_get_subjects(intake=iv)
    return {"intake": iv,
        "subjects":[{"id":str(s["_id"]),"name":s.get("name",""),
                     "intake": s.get("intake") or "", "readonly": False} for s in items]}

class RefSubjectCreate(BaseModel):
    name: str = Field(min_length=1); intake: str = ""


class RefNameUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class ReorderBody(BaseModel):
    direction: str = Field(pattern="^(up|down)$")


@router.post("/references/subjects")
async def ref_add_subject_ep(body: RefSubjectCreate, admin=Depends(get_content_admin_user)):
    iv = resolve_content_intake(admin, body.intake)
    r = await db.ref_add_subject(body.name.strip(), intake=iv)
    if r is None: raise HTTPException(409, "این موضوع قبلاً ثبت شده")
    await _audit(admin, "ایجاد موضوع رفرنس", "Content", severity="INFO",
        target_id=str(r), target_type="reference_subject", target_label=body.name.strip(),
        after={"intake": iv}, tags=["رفرنس", "ایجاد", "پنل_وب"])
    return {"ok":True, "id":str(r)}


@router.patch("/references/subjects/{sid}")
async def ref_edit_subject_ep(sid: str, body: RefNameUpdate,
                              admin=Depends(get_content_admin_user)):
    old = await db.ref_get_subject(sid)
    if not old:
        raise HTTPException(404, "موضوع رفرنس پیدا نشد")
    await _deny_intake(old.get("intake", ""), admin)
    name = body.name.strip()
    ok = await db.ref_update_subject(sid, {"name": name})
    if not ok:
        raise HTTPException(500, "ویرایش موضوع انجام نشد")
    await _audit(
        admin, "ویرایش نام موضوع رفرنس", "Content", severity="WARNING",
        target_id=sid, target_type="reference_subject", target_label=name,
        before={"name": old.get("name", "")}, after={"name": name},
        tags=["رفرنس", "ویرایش", "پنل_وب"],
    )
    return {"ok": True}


@router.post("/references/subjects/{sid}/reorder")
async def ref_reorder_subject_ep(sid: str, body: ReorderBody,
                                 admin=Depends(get_content_admin_user)):
    item = await db.ref_get_subject(sid)
    if not item:
        raise HTTPException(404, "موضوع رفرنس پیدا نشد")
    await _deny_intake(item.get("intake", ""), admin)
    fn = db.reorder_up if body.direction == "up" else db.reorder_down
    ok = await fn("ref_subjects", sid, {"intake": item.get("intake") or ""})
    if ok:
        await _audit(
            admin, "تغییر ترتیب موضوع رفرنس", "Content", severity="INFO",
            target_id=sid, target_type="reference_subject",
            target_label=item.get("name", ""), after={"direction": body.direction},
            tags=["رفرنس", "ترتیب", "پنل_وب"],
        )
    return {"ok": bool(ok)}


@router.delete("/references/subjects/{sid}")
async def ref_del_subject_ep(sid: str, admin=Depends(get_content_admin_user)):
    old = await db.ref_get_subject(sid)
    if not old: raise HTTPException(404, "موضوع رفرنس پیدا نشد")
    await _deny_intake(old.get("intake", ""), admin)
    await db.ref_delete_subject(sid)
    await _audit(admin, "حذف موضوع رفرنس", "Content", severity="HIGH",
        target_id=sid, target_type="reference_subject", target_label=old.get("name", ""),
        before={"intake": old.get("intake", "")}, after={"deleted": True},
        tags=["رفرنس", "حذف", "پنل_وب"])
    return {"ok":True}

@router.get("/references/subjects/{sid}/books")
async def ref_books_ep(sid: str, admin=Depends(get_content_admin_user)):
    # 🌊 C1.5 — مشاهده‌ی فقط‌خواندنیِ کتاب‌های موضوع سراسری برای scoped
    ro = await _read_intake(await db.ref_subject_intake(sid), admin)
    scope = admin.get("_scope") or {}
    # 🍴 C2 — نمای مؤثر برای scoped روی موضوع سراسری: fork جایگزین base
    if ro and scope.get("kind") == "scoped":
        items = await db.ref_get_books_effective(
            sid, [scope.get("intake") or '', ''])
    else:
        items = await db.ref_get_books(sid)
    return {"readonly": ro,
        "books":[{"id":str(b["_id"]),"name":b.get("name",""),
        "intake":b.get("intake") or "", "is_fork":bool(b.get("fork_of"))} for b in items]}

class RefBookCreate(BaseModel):
    name: str = Field(min_length=1)

@router.post("/references/subjects/{sid}/books")
async def ref_add_book_ep(sid: str, body: RefBookCreate, admin=Depends(get_content_admin_user)):
    await _deny_intake(await db.ref_subject_intake(sid), admin)
    r = await db.ref_add_book(sid, body.name.strip())
    await _audit(admin, "ایجاد کتاب رفرنس", "Content", severity="INFO",
        target_id=str(r), target_type="reference_book", target_label=body.name.strip(),
        after={"subject_id": sid}, tags=["رفرنس", "ایجاد", "پنل_وب"])
    return {"ok":True, "id":str(r)}


@router.patch("/references/books/{bid}")
async def ref_edit_book_ep(bid: str, body: RefNameUpdate,
                           admin=Depends(get_content_admin_user)):
    old = await db.ref_get_book(bid)
    if not old:
        raise HTTPException(404, "کتاب رفرنس پیدا نشد")
    await _deny_intake(await db.ref_book_intake(bid), admin)
    name = body.name.strip()
    ok = await db.ref_update_book(bid, {"name": name})
    if not ok:
        raise HTTPException(500, "ویرایش کتاب انجام نشد")
    await _audit(
        admin, "ویرایش نام کتاب رفرنس", "Content", severity="WARNING",
        target_id=bid, target_type="reference_book", target_label=name,
        before={"name": old.get("name", "")}, after={"name": name},
        tags=["رفرنس", "ویرایش", "پنل_وب"],
    )
    return {"ok": True}


@router.post("/references/books/{bid}/reorder")
async def ref_reorder_book_ep(bid: str, body: ReorderBody,
                              admin=Depends(get_content_admin_user)):
    item = await db.ref_get_book(bid)
    if not item:
        raise HTTPException(404, "کتاب رفرنس پیدا نشد")
    await _deny_intake(await db.ref_book_intake(bid), admin)
    fn = db.reorder_up if body.direction == "up" else db.reorder_down
    query = {"subject_id": item.get("subject_id", "")}
    if item.get("fork_of") or (item.get("intake") or ""):
        query["intake"] = item.get("intake") or ""
    else:
        # کتاب پایه با fork ورودی دیگر در یک ترتیب مشترک swap نمی‌شود.
        query["fork_of"] = {"$in": [None, ""]}
        query["$or"] = [{"intake": ""}, {"intake": None},
                        {"intake": {"$exists": False}}]
    ok = await fn("ref_books", bid, query)
    if ok:
        await _audit(
            admin, "تغییر ترتیب کتاب رفرنس", "Content", severity="INFO",
            target_id=bid, target_type="reference_book",
            target_label=item.get("name", ""), after={"direction": body.direction},
            tags=["رفرنس", "ترتیب", "پنل_وب"],
        )
    return {"ok": bool(ok)}


@router.delete("/references/books/{bid}")
async def ref_del_book_ep(bid: str, admin=Depends(get_content_admin_user)):
    old = await db.ref_get_book(bid)
    if not old: raise HTTPException(404, "کتاب رفرنس پیدا نشد")
    await _deny_intake(await db.ref_book_intake(bid), admin)
    # 🍴 Q1 — حذف کتابی که fork دارد ⇒ orphan؛ با 409 مسدود می‌شود
    if await db.ref_book_has_forks(bid):
        raise HTTPException(409,
            "این کتاب نسخه‌ی اختصاصی (fork) دارد؛ ابتدا نسخه‌ها را بازگردانید")
    await db.ref_delete_book(bid)
    await _audit(admin, "حذف کتاب رفرنس", "Content", severity="HIGH",
        target_id=bid, target_type="reference_book", target_label=old.get("name", ""),
        before={"subject_id": old.get("subject_id")}, after={"deleted": True},
        tags=["رفرنس", "حذف", "پنل_وب"])
    return {"ok":True}

@router.get("/references/books/{bid}/files")
async def ref_files_ep(bid: str, skip: int = Query(0, ge=0),
                       limit: int = Query(50, ge=1, le=100),
                       admin=Depends(get_content_admin_user)):
    # 🌊 C1.5 — مشاهده‌ی فقط‌خواندنیِ فایل‌های کتاب سراسری برای scoped
    ro = await _read_intake(await db.ref_book_intake(bid), admin)
    items, total = await db.ref_get_files_page(bid, skip=skip, limit=limit)
    # 🍴 C2 — نشان نسخه‌ی اختصاصی برای سربرگ مینی‌اپ
    bdoc = await db.ref_get_book(bid) or {}
    return {"readonly": ro, "is_fork": bool(bdoc.get("fork_of")),
        "total": total, "skip": skip, "limit": limit,
        "has_more": skip + len(items) < total,
        "files":[{"id":str(f["_id"]),"lang":f.get("lang","fa"),"volume":f.get("volume",1),
        "description":f.get("description",""),"downloads":f.get("downloads",0)} for f in items]}

@router.post("/references/books/{bid}/files")
async def ref_add_file_ep(bid: str, lang: str = Form("fa"), volume: int = Form(1),
                           description: str = Form(""), file: UploadFile = File(...),
                           admin=Depends(get_content_admin_user)):
    if lang not in ("fa","en"): raise HTTPException(422, "زبان نامعتبر")
    await _deny_intake(await db.ref_book_intake(bid), admin)
    raw = await file.read()
    if len(raw) > 45 * 1024 * 1024: raise HTTPException(413, "حجم فایل بیش از حد مجاز است (۴۵MB)")
    file_id = await upload_and_get_file_id(admin["id"], file.filename or "file", raw,
        file.content_type or "application/octet-stream")
    if not file_id: raise HTTPException(502, "آپلود فایل به تلگرام ناموفق بود")
    fid = await db.ref_add_file(bid, lang, file_id, volume, description.strip())
    await _audit(admin, "افزودن فایل رفرنس", "Content", severity="INFO",
        target_id=str(fid), target_type="reference_file",
        target_label=description.strip() or (file.filename or "file"),
        after={"book_id": bid, "lang": lang, "volume": volume},
        tags=["رفرنس", "افزودن_فایل", "پنل_وب"])
    return {"ok":True, "id":fid}

@router.delete("/references/files/{fid}")
async def ref_del_file_ep(fid: str, admin=Depends(get_content_admin_user)):
    old = await db.ref_get_file(fid)
    if not old: raise HTTPException(404, "فایل رفرنس پیدا نشد")
    await _deny_intake(await db.ref_file_intake(fid), admin)
    await db.ref_delete_file(fid)
    await _audit(admin, "حذف فایل رفرنس", "Content", severity="HIGH",
        target_id=fid, target_type="reference_file", target_label=old.get("description", ""),
        before={"book_id": old.get("book_id"), "lang": old.get("lang"),
                "volume": old.get("volume")}, after={"deleted": True},
        tags=["رفرنس", "حذف_فایل", "پنل_وب"])
    return {"ok":True}

# ══════════════════════════════════════════════
# 🍴 موج C2 — Fork/Unfork (سفارشی‌سازی سراسری برای یک ورودی)
# قواعد: فقط آیتم «سراسری» fork می‌شود؛ هدف = scope خود ادمینِ
# ورودی‌خاص یا ctx انتخابیِ ادمین ارشد؛ سربار دانلود/اعلان صفر است
# (کپی با downloads=0 و notif_sent=True — بدون دوباره‌اعلانی).
# ══════════════════════════════════════════════

async def _fork_target(admin, requested):
    """هدف fork: ادمین ورودی‌خاص → scope خودش؛ ادمین ارشد → ورودی درخواستی."""
    scope = admin.get("_scope") or {}
    if scope.get("kind") == "scoped":
        return scope.get("intake") or ''
    # فقط رشته‌ی واقعی intake معتبر است (فراخوانی بدون پارامتر ⇒ سطل سراسری)
    if not isinstance(requested, str):
        requested = None
    return resolve_content_intake(admin, requested) or ''

async def _intakes_active_codes() -> list:
    items = await db.get_all_intakes()
    return [i["code"] for i in items if i.get("active", True)]

@router.post("/basic-science/sessions/{sid}/fork")
async def bs_fork_session_ep(sid: str, admin=Depends(get_content_admin_user),
                             intake: Optional[str] = Query(None)):
    target = await _fork_target(admin, intake)
    if not target:
        raise HTTPException(422,
            "سفارشی‌سازی روی سطل سراسری معنا ندارد؛ ابتدا یک ورودی را انتخاب کنید")
    new_sid = await db.bs_fork_session(sid, target)
    if not new_sid:
        raise HTTPException(422, "فقط جلسه‌ی سراسری قابل سفارشی‌سازی است")
    try:
        from api.routers.admin_panel import _audit
        _docs = await db.get_all_intakes()
        _lbl = next((i["label"] for i in _docs if i["code"] == target), target)
        _base = await db.bs_get_session(sid) or {}
        await _audit(admin, "ساخت نسخه‌ی اختصاصی (Fork) جلسه", "Content",
            severity="INFO", target_id=str(sid), target_type="session",
            target_label=_base.get("topic", ""),
            details=f"🍴 Fork Session\n🏷 ورودی: {_lbl}", tags=["فورک_محتوا"])
    except Exception:
        pass
    return {"ok":True, "fork_id":new_sid}

@router.delete("/basic-science/sessions/{sid}/fork")
async def bs_unfork_session_ep(sid: str, admin=Depends(get_content_admin_user)):
    _fi = await db.session_intake(sid)
    await _deny_intake(_fi, admin)
    base_id = await db.bs_unfork_session(sid)
    if not base_id:
        raise HTTPException(422, "این جلسه نسخه‌ی اختصاصی نیست")
    try:
        from api.routers.admin_panel import _audit
        await _audit(admin, "بازگردانی جلسه به نسخه‌ی سراسری (حذف Fork)",
            "Content", severity="INFO", target_id=str(sid),
            target_type="session",
            details=f"↩️ Unfork Session\n🏷 ورودی: {_fi or 'سراسری'}",
            tags=["فورک_محتوا"])
    except Exception:
        pass
    return {"ok":True, "base_id":base_id}

@router.post("/references/books/{bid}/fork")
async def ref_fork_book_ep(bid: str, admin=Depends(get_content_admin_user),
                           intake: Optional[str] = Query(None)):
    target = await _fork_target(admin, intake)
    if not target:
        raise HTTPException(422,
            "سفارشی‌سازی روی سطل سراسری معنا ندارد؛ ابتدا یک ورودی را انتخاب کنید")
    new_bid = await db.ref_fork_book(bid, target)
    if not new_bid:
        raise HTTPException(422, "فقط کتاب سراسری قابل سفارشی‌سازی است")
    try:
        from api.routers.admin_panel import _audit
        _docs = await db.get_all_intakes()
        _lbl = next((i["label"] for i in _docs if i["code"] == target), target)
        _base = await db.ref_get_book(bid) or {}
        await _audit(admin, "ساخت نسخه‌ی اختصاصی (Fork) کتاب", "Content",
            severity="INFO", target_id=str(bid), target_type="book",
            target_label=_base.get("name", ""),
            details=f"🍴 Fork Book\n🏷 ورودی: {_lbl}", tags=["فورک_محتوا"])
    except Exception:
        pass
    return {"ok":True, "fork_id":new_bid}

@router.delete("/references/books/{bid}/fork")
async def ref_unfork_book_ep(bid: str, admin=Depends(get_content_admin_user)):
    _fi = await db.ref_book_intake(bid)
    await _deny_intake(_fi, admin)
    base_id = await db.ref_unfork_book(bid)
    if not base_id:
        raise HTTPException(422, "این کتاب نسخه‌ی اختصاصی نیست")
    try:
        from api.routers.admin_panel import _audit
        await _audit(admin, "بازگردانی کتاب به نسخه‌ی سراسری (حذف Fork)",
            "Content", severity="INFO", target_id=str(bid),
            target_type="book",
            details=f"↩️ Unfork Book\n🏷 ورودی: {_fi or 'سراسری'}",
            tags=["فورک_محتوا"])
    except Exception:
        pass
    return {"ok":True, "base_id":base_id}

# ══════════════════════════════════════════════
# 📦 ابزار Move — بازتخصیص آیتم‌های قدیمیِ سراسری به یک ورودی
# (فقط ادمین ارشد؛ anti-duplicate در لایه‌ی DB: 409 همنام)
# ══════════════════════════════════════════════

class MoveBody(BaseModel):
    intake: str = ""

@router.post("/basic-science/lessons/{lid}/move")
async def bs_move_lesson_ep(lid: str, body: MoveBody, admin=Depends(GLOBAL_USER)):
    iv = body.intake or ''
    if iv and iv not in (await _intakes_active_codes()):
        raise HTTPException(422, "کد ورودی نامعتبر است")
    source = await db.bs_get_lesson(lid)
    status, info = await db.bs_move_lesson_intake(lid, iv)
    if status == 'err':
        if info == 'not_found': raise HTTPException(404, "درس یافت نشد")
        duplicate = await db.bs_lessons.find_one({
            'term': (source or {}).get('term', ''), 'name': (source or {}).get('name', ''),
            'intake': iv, '_id': {'$ne': (source or {}).get('_id')}})
        raise HTTPException(409, {"code": "duplicate_name", "object": (source or {}).get('name', ''),
            "destination": iv or "global", "existing_id": str((duplicate or {}).get('_id', '')),
            "reason": "درسی با همین نام در سطل مقصد موجود است"})
    try:
        await _audit(admin, "انتقال درس به سطل ورودی", "Content",
            severity="HIGH", target_id=str(lid), target_type="lesson",
            details=f"📦 Move Lesson: {info or 'سراسری'} → {iv or 'سراسری'}",
            tags=["فورک_محتوا"])
    except Exception:
        await db.bs_move_lesson_intake(lid, info or '')
        raise HTTPException(503, "ثبت حسابرسی ناموفق بود؛ انتقال بازگردانده شد")
    return {"ok":True, "from":info, "to":iv}

@router.post("/references/subjects/{sid}/move")
async def ref_move_subject_ep(sid: str, body: MoveBody, admin=Depends(GLOBAL_USER)):
    iv = body.intake or ''
    if iv and iv not in (await _intakes_active_codes()):
        raise HTTPException(422, "کد ورودی نامعتبر است")
    source = await db.ref_get_subject(sid)
    status, info = await db.ref_move_subject_intake(sid, iv)
    if status == 'err':
        if info == 'not_found': raise HTTPException(404, "موضوع یافت نشد")
        duplicate = await db.ref_subjects.find_one({
            'name': (source or {}).get('name', ''), 'intake': iv,
            '_id': {'$ne': (source or {}).get('_id')}})
        raise HTTPException(409, {"code": "duplicate_name", "object": (source or {}).get('name', ''),
            "destination": iv or "global", "existing_id": str((duplicate or {}).get('_id', '')),
            "reason": "موضوعی با همین نام در سطل مقصد موجود است"})
    try:
        await _audit(admin, "انتقال موضوع به سطل ورودی", "Content",
            severity="HIGH", target_id=str(sid), target_type="subject",
            details=f"📦 Move Subject: {info or 'سراسری'} → {iv or 'سراسری'}",
            tags=["فورک_محتوا"])
    except Exception:
        await db.ref_move_subject_intake(sid, info or '')
        raise HTTPException(503, "ثبت حسابرسی ناموفق بود؛ انتقال بازگردانده شد")
    return {"ok":True, "from":info, "to":iv}

@router.post("/qbank/files/{fid}/move")
async def qbank_move_file_ep(fid: str, body: MoveBody, admin=Depends(GLOBAL_USER)):
    iv = body.intake or ''
    if iv and iv not in (await _intakes_active_codes()):
        raise HTTPException(422, "کد ورودی نامعتبر است")
    source = await db.get_qbank_file(fid)
    status, info = await db.qbank_move_file_intake(fid, iv)
    if status == 'err':
        if info == 'not_found': raise HTTPException(404, "فایل یافت نشد")
        duplicate = await db.qbank_files.find_one({
            'lesson': (source or {}).get('lesson', ''), 'topic': (source or {}).get('topic', ''),
            'description': (source or {}).get('description', ''), 'intake': iv,
            '_id': {'$ne': (source or {}).get('_id')}})
        raise HTTPException(409, {"code": "duplicate_name",
            "object": (source or {}).get('description') or f"{(source or {}).get('lesson','')} / {(source or {}).get('topic','')}",
            "destination": iv or "global", "existing_id": str((duplicate or {}).get('_id', '')),
            "reason": "فایل همسانی در سطل مقصد موجود است"})
    try:
        await _audit(admin, "انتقال فایل بانک سؤال به سطل ورودی", "Content",
            severity="HIGH", target_id=str(fid), target_type="qbank_file",
            details=f"📦 Move QBank File: {info or 'سراسری'} → {iv or 'سراسری'}",
            tags=["فورک_محتوا"])
    except Exception:
        await db.qbank_move_file_intake(fid, info or '')
        raise HTTPException(503, "ثبت حسابرسی ناموفق بود؛ انتقال بازگردانده شد")
    return {"ok":True, "from":info, "to":iv}

# ══════════════════════════════════════════════
# 🧪 بانک سوال — آپلود و مدیریت فایل
# ══════════════════════════════════════════════

@router.get("/qbank/files")
async def qbank_files_ep(lesson: Optional[str]=Query(None), topic: Optional[str]=Query(None),
                          intake: Optional[str]=Query(None), skip: int = Query(0, ge=0),
                          limit: int = Query(50, ge=1, le=100),
                          admin=Depends(get_content_admin_user)):
    iv = resolve_content_intake(admin, intake)
    scope = admin.get("_scope") or {}
    visible_intakes = [iv, ''] if scope.get("kind") == "scoped" else iv
    items, total = await db.get_qbank_files_page(
        lesson, topic, intake=visible_intakes, skip=skip, limit=limit)
    return {"intake": iv, "total": total, "skip": skip, "limit": limit,
        "has_more": skip + len(items) < total,
        "files":[{"id":str(f["_id"]),"lesson":f.get("lesson",""),"topic":f.get("topic",""),
        "description":f.get("description",""),"file_type":f.get("file_type","document"),
        "intake": f.get("intake") or "",
        "readonly": (f.get("intake") or '') != iv if scope.get("kind") == "scoped" else False,
        "downloads":f.get("downloads",0),"upload_date":f.get("upload_date","")[:10]} for f in items]}

@router.post("/qbank/files")
async def qbank_add_file_ep(lesson: str = Form(...), topic: str = Form(...),
                             description: str = Form(""), intake: str = Form(""),
                             file: UploadFile = File(...),
                             admin=Depends(get_content_admin_user)):
    iv = resolve_content_intake(admin, intake)
    raw = await file.read()
    if len(raw) > 45 * 1024 * 1024: raise HTTPException(413, "حجم فایل بیش از حد مجاز است (۴۵MB)")
    ctype = file.content_type or ""
    ftype = "video" if ctype.startswith("video") else "voice" if ctype.startswith("audio") else "document"
    file_id = await upload_and_get_file_id(admin["id"], file.filename or "file", raw,
        ctype or "application/octet-stream")
    if not file_id: raise HTTPException(502, "آپلود فایل به تلگرام ناموفق بود")
    fid = await db.add_qbank_file(lesson.strip(), topic.strip(), file_id, description.strip(), ftype, intake=iv)
    await _audit(admin, "افزودن فایل بانک سؤال", "Content", severity="INFO",
        target_id=str(fid), target_type="qbank_file",
        target_label=description.strip() or f"{lesson.strip()} — {topic.strip()}",
        after={"lesson": lesson.strip(), "topic": topic.strip(),
               "file_type": ftype, "intake": iv},
        tags=["بانک_سؤال", "افزودن_فایل", "پنل_وب"])
    return {"ok":True, "id":str(fid)}

@router.delete("/qbank/files/{fid}")
async def qbank_del_file_ep(fid: str, admin=Depends(get_content_admin_user)):
    item = await db.get_qbank_file(fid)
    if not item: raise HTTPException(404, "فایل بانک سؤال پیدا نشد")
    await _deny_intake(item.get("intake",""), admin)
    await db.delete_qbank_file(fid)
    await _audit(admin, "حذف فایل بانک سؤال", "Content", severity="HIGH",
        target_id=fid, target_type="qbank_file",
        target_label=item.get("description", "") or f"{item.get('lesson','')} — {item.get('topic','')}",
        before={"file_type": item.get("file_type"), "intake": item.get("intake", "")},
        after={"deleted": True}, tags=["بانک_سؤال", "حذف_فایل", "پنل_وب"])
    return {"ok":True}

# ══════════════════════════════════════════════
# 🚩 گزارش‌های ایراد (سوال/جزوه)
# ══════════════════════════════════════════════

@router.get("/reports/stats")
async def reports_stats_ep(admin=Depends(GLOBAL_USER)):
    return await db.content_reports_stats()

@router.get("/reports")
async def reports_list_ep(
    status: Optional[str] = Query(None), skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100), admin=Depends(GLOBAL_USER),
):
    if status and status not in ("new", "reviewing", "resolved", "rejected"):
        raise HTTPException(422, "وضعیت نامعتبر")
    items = await db.get_content_reports(status=status, skip=skip, limit=limit)
    total = await db.content_reports_count(status=status)
    REASON_FA = {'wrong_answer':'پاسخ اشتباه','unclear':'گنگ/نامفهوم','duplicate':'تکراری',
        'broken_file':'فایل خراب','outdated':'محتوای قدیمی','other':'سایر'}
    return {"total": total, "skip": skip, "limit": limit,
        "reports":[{"id":r.get("report_id"),"target_type":r.get("target_type",""),
        "target_id":r.get("target_id",""),"reporter_name":r.get("reporter_name",""),
        "reason":REASON_FA.get(r.get("reason",""), r.get("reason","")),"note":r.get("note",""),
        "status":r.get("status","new"),"created_at":str(r.get("created_at", ""))[:16],
        "resolved_at":str(r.get("resolved_at", "") or "")[:16]} for r in items]}

class ReportStatusUpdate(BaseModel):
    status: str

@router.post("/reports/{rid}/status")
async def report_status_ep(rid: int, body: ReportStatusUpdate, admin=Depends(GLOBAL_USER)):
    if body.status not in ("new","reviewing","resolved","rejected"): raise HTTPException(422,"وضعیت نامعتبر")
    r = await db.get_content_report(rid)
    if not r: raise HTTPException(404)
    old_status = r.get("status", "new")
    await db.update_report_status(rid, body.status, resolved_by=admin["id"])
    await _audit(
        admin, "تغییر وضعیت گزارش محتوا", "Reports", severity="WARNING",
        target_id=str(rid), target_type="content_report",
        target_label=f"{r.get('target_type','')} · {r.get('reason','')}"[:300],
        before={"status": old_status}, after={"status": body.status},
        tags=["گزارش_محتوا", "بازبینی", "پنل_وب"],
    )
    return {"ok":True}
