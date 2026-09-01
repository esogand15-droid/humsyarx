"""💍 Ring Street — انتخاب کاندید و امتیازدهی (§۸، §۱۰)

فیلترهای «سخت» (compatibility) قبل از رزرو اعمال می‌شوند؛ فیلترهای
نرم (topic، سابقه‌ی تعامل) فقط امتیاز می‌دهند تا در صف‌های کوچک
کاربر مجازاً ساعت‌ها معطل نشود (§۵۳: topic hard filter نکن).

fairness: اول هر که بیشتر منتظر کشیده — queue با sort روی queued_at
انتخاب می‌شود و این ماژول فقط «امتیاز» را برای tie-break می‌دهد.
"""
from __future__ import annotations

from ring import models as M


def hard_ok(me: dict, cand: dict, *, mode: str, cfg: dict) -> tuple[bool, str]:
    """بررسی دوطرفه‌ی سازگاری. دلیل اولِ نقض را برمی‌گرداند."""
    if int(cand.get("user_id", 0)) == int(me.get("user_id", -1)):
        return False, "self"
    if cand.get("mode") != mode or me.get("mode") != mode:
        return False, "mode"
    # ← preference من
    if not M.gender_matches(cand.get("gender"), me.get("pref_gender")):
        return False, "gender_of_me"
    if not M.age_range_matches(cand.get("age_range"), me.get("pref_age_ranges")):
        return False, "age_of_me"
    # ← preference او (دوطرفه — §۶)
    if not M.gender_matches(me.get("gender"), cand.get("pref_gender")):
        return False, "gender_of_cand"
    if not M.age_range_matches(me.get("age_range"), cand.get("pref_age_ranges")):
        return False, "age_of_cand"
    if int(cfg.get("min_age", 18)) and not M.age_ok(cand.get("age"), int(cfg["min_age"])):
        return False, "min_age"
    return True, ""


def score(me: dict, cand: dict, *, waited_s: float = 0.0) -> float:
    """امتیاز نرم. هرچه بالاتر، انتخاب شدن محتمل‌تر (tie-break)."""
    s = 0.0
    mine = set(_tokens(me.get("interests")))
    theirs = set(_tokens(cand.get("interests")))
    if mine and theirs:
        s += 3.0 * len(mine & theirs) / max(1, min(len(mine), len(theirs)))
    if me.get("city") and cand.get("city") and me["city"] == cand["city"]:
        s += 2.0
    if me.get("university") and cand.get("university") and \
            me["university"] == cand["university"]:
        s += 2.5
    if me.get("major") and cand.get("major") and me["major"] == cand["major"]:
        s += 1.5
    tme, tc = set(me.get("topics") or []), set(cand.get("topics") or [])
    if tme and tc:
        s += 1.5 * len(tme & tc)
    # پروفایل کامل‌تر در حالت جدی تجربه‌ی بهتری می‌دهد
    if (me.get("mode") == "serious" or cand.get("mode") == "serious"):
        filled = sum(1 for k in ("bio", "interests", "city", "university", "major")
                     if (cand.get(k) or "").strip())
        s += 0.4 * filled
    # recent interaction ⇒ افت امتیاز (soft) تا آدم‌ها تکراری نشوند
    s += 0.05 * min(60, waited_s / 60.0)          # صبر طولانی ⇒ کمی شانس بیشتر
    return s


def rank(cands: list[dict], me: dict, *, waited_of=None) -> list[dict]:
    """مرتب‌سازی نهایی: fairness (منتظرمانده) بعد از compatibility،
    بعد random tie-breaker (§۱۰ مرحله ۱۰)."""
    import random
    waited_of = waited_of or (lambda d: 0.0)
    keyed = []
    for c in cands:
        keyed.append((score(me, c, waited_s=waited_of(c)), random.random(), c))
    keyed.sort(key=lambda x: (-x[0], -x[1]))
    return [k[2] for k in keyed]


def _tokens(text) -> list[str]:
    if not text:
        return []
    parts = str(text).replace("،", ",").replace("؛", ",").replace("\n", ",").split(",")
    out = []
    for p in parts:
        p = p.strip().lower()
        p = p.replace("‌", " ").strip()
        if len(p) >= 2:
            out.append(p[:32])
    return out[:12]
