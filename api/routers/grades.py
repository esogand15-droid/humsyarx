"""Student grade endpoints for the Telegram Mini App."""

from fastapi import APIRouter, Depends

from api.auth import get_current_user
from database import db
from grade_utils import summarize_grades_by_term


router = APIRouter()


@router.get("")
async def get_grades(
    user=Depends(get_current_user),
):
    records = await db.grade_list_for_student(
        user["id"]
    )

    if not isinstance(records, list):
        records = []

    # 🛡 AUDIT-§۸۲ — تفکیک ترم هم در همین بدنه می‌آید (کلیدهای قبلی دست‌نخورده)
    return summarize_grades_by_term(records)
