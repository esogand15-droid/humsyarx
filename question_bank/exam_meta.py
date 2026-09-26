"""Data-driven exam metadata for multi-year / multi-session QBank imports.

No year or session is hard-coded in call sites. Callers pass values; this
module only normalizes and labels them. Future exams (Esfand 1403, Shahrivar
1405, …) reuse the same helpers without Core changes.
"""
from __future__ import annotations

import re
from typing import Any

from .contracts import (
    EXAM_SESSION_DEFAULT,
    EXAM_SESSIONS,
    EXAM_TRACK_DEFAULT,
    QuestionDomainError,
    canonical_exam_session,
    canonical_exam_track,
    canonical_exam_year,
    clean_text,
)

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_YEAR_RE = re.compile(r"(1[3-4]\d{2})")

# Filename / path keywords → canonical session key. Order matters: longer
# Persian stems first so «شهریور» wins over bare «شهر».
_SESSION_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("shahrivar", "shahrivar"),
    ("september", "shahrivar"),
    ("شهریور", "shahrivar"),
    ("esfand", "esfand"),
    ("february", "esfand"),
    ("اسفند", "esfand"),
    ("ordibehesht", "ordibehesht"),
    ("اردیبهشت", "ordibehesht"),
    ("mehr", "mehr"),
    ("مهر", "mehr"),
    ("mordad", "mordad"),
    ("مرداد", "mordad"),
    ("azarm", "azar"),  # avoid matching random 'azar' inside words via boundary-ish
    ("azar", "azar"),
    ("آذر", "azar"),
    ("dey", "dey"),
    ("دی", "dey"),
    ("farvardin", "farvardin"),
    ("فروردین", "farvardin"),
)


def infer_exam_session_from_filename(file_name: str) -> str | None:
    """Return canonical session key from a path/filename, or None."""
    text = clean_text(file_name).translate(_FA_DIGITS).casefold()
    # Also keep original for Persian matching (casefold breaks nothing useful in FA).
    raw = clean_text(file_name).translate(_FA_DIGITS)
    lowered_raw = raw.lower()
    for needle, key in _SESSION_KEYWORDS:
        if needle in text or needle in lowered_raw or needle in raw:
            return key
    return None


def infer_exam_year_from_text(value: str) -> str | None:
    text = clean_text(value).translate(_FA_DIGITS)
    candidates = [m for m in _YEAR_RE.findall(text) if True]
    from .contracts import EXAM_YEAR_MAX, EXAM_YEAR_MIN
    valid = [m for m in candidates if EXAM_YEAR_MIN <= m <= EXAM_YEAR_MAX]
    return valid[-1] if valid else None


def session_label(session: str | None, year: str | None) -> str | None:
    """Human-readable label like «شهریور ۱۴۰۴» — never invents a session."""
    if not session:
        return None
    key = canonical_exam_session(session, strict=False)
    if not key or key not in EXAM_SESSIONS:
        return None
    fa = EXAM_SESSIONS[key]
    if year:
        y = clean_text(year).translate(_FA_DIGITS)
        # Display year with Persian digits for UI consistency.
        y_fa = y.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
        return f"{fa} {y_fa}"
    return fa


def build_exam_metadata(
    *,
    title: str | None = None,
    exam_type: str = "basic_sciences",
    year: str | None = None,
    session: str | None = None,
    field: str | None = None,
    source_file: str | None = None,
    description: str | None = None,
    exam_track: str | None = None,
) -> dict:
    """Normalize a reusable exam metadata document (not a DB schema lock-in)."""
    year_n = canonical_exam_year(year, strict=False) if year not in (None, "") else None
    if year not in (None, "") and year_n is None:
        # strict path for explicit bad input from CLI
        year_n = canonical_exam_year(year, strict=True)
    session_n = None
    if session not in (None, ""):
        session_n = canonical_exam_session(session, strict=True)
    elif source_file:
        session_n = infer_exam_session_from_filename(source_file)
    if year_n is None and source_file:
        year_n = infer_exam_year_from_text(source_file)
    track = canonical_exam_track(exam_track or field)
    label = session_label(session_n, year_n)
    auto_title = title or None
    if not auto_title and (year_n or session_n):
        bits = ["آزمون علوم پایه پزشکی"]
        if label:
            bits.append("—")
            bits.append(label)
        auto_title = " ".join(bits)
    exam_id_parts = [
        clean_text(exam_type) or "basic_sciences",
        track,
        year_n or "unknown",
        session_n or "unknown",
    ]
    return {
        "exam_id": "_".join(exam_id_parts),
        "title": clean_text(auto_title) or "آزمون علوم پایه",
        "exam_type": clean_text(exam_type) or "basic_sciences",
        "year": year_n,
        "jalali_year": year_n,
        "session": session_n,
        "session_label": label,
        "field": track,
        "exam_track": track,
        "category": "basic_sciences",
        "description": clean_text(description) or None,
        "source": "archive_import",
        "source_file": clean_text(source_file, 240) or None,
    }


def apply_exam_metadata_to_question_row(row: dict, meta: dict) -> dict:
    """Stamp exam metadata onto one import-schema question row (non-destructive)."""
    out = dict(row)
    if meta.get("year") and not out.get("exam_year"):
        out["exam_year"] = meta["year"]
        out["exam_year_source"] = out.get("exam_year_source") or "inferred_from_filename"
    if meta.get("session") and not out.get("exam_session"):
        out["exam_session"] = meta["session"]
        out["exam_session_label"] = meta.get("session_label")
    if meta.get("exam_track") and not out.get("exam_track"):
        out["exam_track"] = meta["exam_track"]
    return out
