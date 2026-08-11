"""Unified Mini App search across educational content."""

import asyncio
import re

from fastapi import (
    APIRouter,
    Depends,
    Query,
)

from api.auth import (
    get_current_user,
)

from database import db


router = APIRouter()


def text(
    value,
) -> str:
    return str(
        value or ""
    ).strip()


@router.get("")
async def search(
    q: str = Query(
        ...,
        min_length=2,
        max_length=100,
    ),

    user=Depends(
        get_current_user
    ),
):
    query = " ".join(
        q.split()
    )

    pattern = {
        "$regex":
            re.escape(query),

        "$options":
            "i",
    }


    # 🌊 C1.5 — جستجوی سراسری scope-aware است (همان تعریف واحد scope):
    # دانشجو → [ورودی خودش، سراسری]؛ مدیر محتوا/مالک → بدون فیلتر
    # (پیش‌نمایش). حتی *عنوان* محتوای ورودی دیگر هم نمایش داده نمی‌شود.
    _filt = (
        None
        if await db.is_content_admin(user["id"])
        else db.student_intake_filter(
            (user.get("_db") or {}).get("intake", "")
        )
    )
    _scope_q = (
        {"intake": {"$in": _filt}}
        if _filt is not None
        else {}
    )

    (
        resources,
        questions,
        faqs,
        schedules,
        subjects,
        books,
        qbank,
    ) = await asyncio.gather(
        db.search_resources(
            query,
            intake=_filt,
        ),

        db.questions.find({
            "approved":
                True,

            "$or": [
                {
                    "question":
                        pattern,
                },

                {
                    "lesson":
                        pattern,
                },

                {
                    "topic":
                        pattern,
                },
            ],

            **_scope_q,
        })
        .limit(10)
        .to_list(10),

        db.faq.find({
            "$or": [
                {
                    "question":
                        pattern,
                },

                {
                    "answer":
                        pattern,
                },
            ],
        })
        .limit(10)
        .to_list(10),

        db.schedules.find({
            "$or": [
                {
                    "lesson":
                        pattern,
                },

                {
                    "teacher":
                        pattern,
                },

                {
                    "notes":
                        pattern,
                },
            ],
        })
        .sort(
            "date",
            -1,
        )
        .limit(10)
        .to_list(10),

        db.ref_subjects.find({
            "name":
                pattern,

            **_scope_q,
        })
        .limit(10)
        .to_list(10),

        db.ref_books.find({
            "name":
                pattern,
        })
        .limit(10)
        .to_list(10),

        db.qbank_files.find({
            "$or": [
                {
                    "lesson":
                        pattern,
                },

                {
                    "topic":
                        pattern,
                },

                {
                    "description":
                        pattern,
                },
            ],

            **_scope_q,
        })
        .limit(10)
        .to_list(10),
    )


    results = []


    for item in (
        resources or []
    )[:10]:
        subtitle = " • ".join(
            filter(
                None,
                [
                    text(
                        item.get(
                            "lesson_name"
                        )
                    ),

                    text(
                        item.get(
                            "session_topic"
                        )
                    ),
                ],
            )
        )

        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "resource",

            "icon":
                "📗",

            "title": (
                text(
                    item.get("name")
                )
                or "منبع آموزشی"
            ),

            "subtitle":
                subtitle,

            "route":
                "/learn/resources",
        })


    for item in questions:
        subtitle = " • ".join(
            filter(
                None,
                [
                    text(
                        item.get(
                            "lesson"
                        )
                    ),

                    text(
                        item.get(
                            "topic"
                        )
                    ),
                ],
            )
        )

        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "question",

            "icon":
                "🧪",

            "title":
                text(
                    item.get(
                        "question"
                    )
                )[:140],

            "subtitle":
                subtitle,

            "route":
                "/learn/questions",
        })


    for item in faqs:
        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "faq",

            "icon":
                "❓",

            "title":
                text(
                    item.get(
                        "question"
                    )
                ),

            "subtitle": (
                text(
                    item.get(
                        "category"
                    )
                )
                or "راهنما"
            ),

            "route":
                "/me/faq",
        })


    for item in schedules:
        subtitle = " • ".join(
            filter(
                None,
                [
                    text(
                        item.get(
                            "date"
                        )
                    ),

                    text(
                        item.get(
                            "time"
                        )
                    ),

                    text(
                        item.get(
                            "teacher"
                        )
                    ),
                ],
            )
        )

        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "schedule",

            "icon":
                "📅",

            "title": (
                text(
                    item.get(
                        "lesson"
                    )
                )
                or "برنامه درسی"
            ),

            "subtitle":
                subtitle,

            "route":
                "/schedule",
        })


    for item in subjects:
        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "reference",

            "icon":
                "📘",

            "title":
                text(
                    item.get("name")
                ),

            "subtitle":
                "موضوع رفرنس",

            "route":
                "/learn/references",
        })


    for item in books:
        # 🌊 C1.5 — کتاب فرزند موضوع است؛ scope از resolver والد می‌آید
        if _filt is not None and (
            await db.ref_book_intake(text(item.get("_id")))
        ) not in _filt:
            continue

        # 🍴 Q1 — baseای که برای ورودیِ بیننده fork دارد سرکوب می‌شود
        # (جستجو نباید نسخه‌ی سراسری+اختصاصی را با هم تکراری نشان دهد)
        if _filt is not None:
            _viewer = next((v for v in _filt if v), "")
            if _viewer and await db.book_superseded_by_fork(
                text(item.get("_id")), _viewer
            ):
                continue

        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "reference",

            "icon":
                "📕",

            "title":
                text(
                    item.get("name")
                ),

            "subtitle":
                "کتاب مرجع",

            "route":
                "/learn/references",
        })


    for item in qbank:
        title = " • ".join(
            filter(
                None,
                [
                    text(
                        item.get(
                            "lesson"
                        )
                    ),

                    text(
                        item.get(
                            "topic"
                        )
                    ),
                ],
            )
        )

        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "qbank",

            "icon":
                "📦",

            "title": (
                title
                or "بانک فایل سؤال"
            ),

            "subtitle":
                text(
                    item.get(
                        "description"
                    )
                ),

            "route":
                "/learn/resources",
        })


    order = {
        "question": 0,
        "resource": 1,
        "qbank": 2,
        "reference": 3,
        "schedule": 4,
        "faq": 5,
    }


    results.sort(
        key=lambda item:
            order.get(
                item["type"],
                99,
            )
    )


    return {
        "query":
            query,

        "results":
            results[:50],

        "total":
            len(results),
    }
