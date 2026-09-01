"""💍 Ring Street — کیبوردها (§۷، §۱۱، §۱۶، §۲۰)

همه‌ی callback‌ها با پیشوند `ring:` و حداکثر ۶۴ بایت. هیچ callback داده‌ای
حاوی اطلاعات هویتی نیست (فقط uid در callback نیست که مشکلی ایجاد کند —
شناسه‌ها همگی در سرور نگه داشته می‌شوند).
"""
from __future__ import annotations

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as KB

from ring import models as M

CB = "ring:"


def _row(*btns, w: int = 2):
    return list(btns)[:w] if w else list(btns)


def kb_age() -> KB:
    rows = [[B(lbl, callback_data=f"{CB}age:{k}")] for k, lbl, _, _ in M.AGE_RANGES]
    rows.append([B("🔞 زیر ۱۸ سال", callback_data=f"{CB}age:under")])
    return KB(rows)


def kb_gender() -> KB:
    return KB([[B(v, callback_data=f"{CB}g:{k}") for k, v in M.GENDERS.items()],
               [B("↩️ قبلی", callback_data=f"{CB}back:age")]])


def kb_mode(cfg: dict) -> KB:
    rows = []
    if cfg.get("serious_enabled"):
        rows.append([B(M.MODES["serious"], callback_data=f"{CB}m:serious")])
    if cfg.get("fun_enabled"):
        rows.append([B(M.MODES["fun"], callback_data=f"{CB}m:fun")])
    rows.append([B("↩️ قبلی", callback_data=f"{CB}back:gender")])
    return KB(rows)


def kb_terms() -> KB:
    return KB([[B("✅ می‌پذیرم", callback_data=f"{CB}t:yes"),
                B("✋ نمی‌پذیرم", callback_data=f"{CB}t:no")]])


def kb_profile_menu(p: dict, cfg: dict) -> KB:
    def mark(k):
        return "✅ " if (p or {}).get(k) else "▫️ "
    rows = [[B(mark("bio") + "📝 درباره من", callback_data=f"{CB}p:bio"),
             B(mark("interests") + "🌱 علایق", callback_data=f"{CB}p:interests")],
            [B(mark("city") + "🏙 شهر", callback_data=f"{CB}p:city"),
             B(mark("university") + "🎓 دانشگاه", callback_data=f"{CB}p:university")],
            [B(mark("major") + "📚 رشته", callback_data=f"{CB}p:major"),
             B("🎯 هدف", callback_data=f"{CB}p:intent")],
            [B("🏷 موضوع‌ها", callback_data=f"{CB}p:topics"),
             B("⚙️ ترجیحات", callback_data=f"{CB}p:prefs")]]
    if cfg.get("allow_rating"):
        rows.append([B("🌟 امتیازهای اخیر", callback_data=f"{CB}p:ratings")])
    rows.append([B("💾 ذخیره و بازگشت", callback_data=f"{CB}p:done"),
                 B("🔎 پیدا کردن نفر", callback_data=f"{CB}go")])
    return KB(rows)


def kb_intent() -> KB:
    rows = [[B(v, callback_data=f"{CB}i:{k}")] for k, v in M.INTENTS.items()]
    rows.append([B("↩️ بازگشت", callback_data=f"{CB}p:done")])
    return KB(rows)


def kb_topics(sel: list[str] | None = None, *, done: bool = True) -> KB:
    sel = set(sel or [])
    rows, line = [], []
    for k, lbl in M.TOPICS.items():
        line.append(B(("✅ " if k in sel else "") + lbl, callback_data=f"{CB}tp:{k}"))
        if len(line) == 2:
            rows.append(line)
            line = []
    if line:
        rows.append(line)
    if done:
        rows.append([B("💾 ثبت", callback_data=f"{CB}tp:done")])
    return KB(rows)


def kb_prefs(p: dict) -> KB:
    pref = (p or {}).get("pref_gender") or "any"
    rows = [[B("👥 همه", callback_data=f"{CB}pg:any"),
             B("👨 پسر", callback_data=f"{CB}pg:male"),
             B("👩 دختر", callback_data=f"{CB}pg:female")]]
    rows[0] = [B(("✅ " if pref == k else "") + v, callback_data=f"{CB}pg:{k}")
               for k, v in [("any", "👥 همه"), ("male", "👨 پسر"), ("female", "👩 دختر")]]
    raw = set(str((p or {}).get("pref_age_ranges") or "").split(","))
    rows.append([B("🎂 بازه‌ی سنی مورد نظر" if not (raw - {""}) else
                   "🎂 " + "، ".join(M.AGE_LABELS.get(x, x) for x in sorted(raw - {""}))[:34],
                   callback_data=f"{CB}pa:open")])
    rows.append([B("↩️ بازگشت", callback_data=f"{CB}p:done")])
    return KB(rows)


def kb_pref_age(pick: list[str] | None = None) -> KB:
    cur = set(pick or [])
    rows, line = [], []
    for k, lbl, _, _ in M.AGE_RANGES:
        line.append(B(("✅ " if k in cur else "") + lbl, callback_data=f"{CB}pa:{k}"))
        if len(line) == 3:
            rows.append(line)
            line = []
    if line:
        rows.append(line)
    rows.append([B("🌐 بدون محدودیت", callback_data=f"{CB}pa:any"),
                 B("💾 ثبت", callback_data=f"{CB}pa:done")])
    return KB(rows)


def kb_queue(mode: str, cfg: dict, status: str = "waiting") -> KB:
    """صف (§۱۶): نفر بعدی / پایان / قوانین — در حالت waiting هم در دسترس."""
    rows = [[B("🔎 " + ("جست‌وجوی دوباره" if status == "empty" else "نفر بعدی"),
               callback_data=f"{CB}next"),
             B("⛔ پایان", callback_data=f"{CB}stop")],
            [B("👤 پروفایل", callback_data=f"{CB}profile"),
             B("ℹ️ قوانین", callback_data=f"{CB}rules")]]
    return KB(rows)


def kb_chat(mode: str, cfg: dict) -> KB:
    """گفت‌وگوی فعال (§۱۶). بدون دکمه‌ی «معرفی» اگر پنل بسته باشد."""
    rows = [[B("🔄 نفر بعدی", callback_data=f"{CB}next"),
             B("⛔ پایان", callback_data=f"{CB}stop")],
            [B("🚫 بلاک", callback_data=f"{CB}block"),
             B("⚠️ گزارش", callback_data=f"{CB}report")],
            [B("ℹ️ قوانین", callback_data=f"{CB}rules"),
             B("👤 پروفایل", callback_data=f"{CB}profile")]]
    if (mode == "serious") and cfg.get("allow_reveal"):
        rows.append([B("🤝 معرفی دوطرفه", callback_data=f"{CB}reveal:ask")])
    return KB(rows)


def kb_confirm_block() -> KB:
    return KB([[B("✅ بله، بلاکش کن", callback_data=f"{CB}block:yes"),
                B("↩️ بی‌خیال", callback_data=f"{CB}chat")]])


def kb_report_reasons() -> KB:
    rows, line = [], []
    for k, (lbl, _sev) in M.REPORT_REASONS.items():
        line.append(B(lbl, callback_data=f"{CB}r:{k}"))
        if len(line) == 2:
            rows.append(line)
            line = []
    if line:
        rows.append(line)
    rows.append([B("↩️ بازگشت", callback_data=f"{CB}chat")])
    return KB(rows)


def kb_report_send() -> KB:
    return KB([[B("📨 ثبت گزارش", callback_data=f"{CB}r:send"),
                B("🚫 گزارش + بلاک", callback_data=f"{CB}r:send_block")],
               [B("↩️ انصراف", callback_data=f"{CB}chat")]])


def kb_rating() -> KB:
    return KB([[B("😍 عالی", callback_data=f"{CB}rt:great"),
                B("🙂 خوب", callback_data=f"{CB}rt:good"),
                B("😐 متوسط", callback_data=f"{CB}rt:mid")],
               [B("🙁 بد", callback_data=f"{CB}rt:bad"),
                 B("😖 خیلی بد", callback_data=f"{CB}rt:worst")],
               [B("↩️ بعداً", callback_data=f"{CB}chat")]])


def kb_reveal_ask() -> KB:
    return KB([[B("✅ بله، معرفی کنم", callback_data=f"{CB}reveal:yes"),
                B("🙏 نه", callback_data=f"{CB}reveal:no")]])


def kb_safety(blocks: list[dict]) -> KB:
    rows = [[B("🚫 بلاکِ پارتنر فعلی", callback_data=f"{CB}block_now")],
            [B("⚠️ گزارش بدون چت (با ناشناس‌آی‌دی)", callback_data=f"{CB}report_anon")]]
    for b in (blocks or [])[:10]:
        rows.append([B(f"🧷 {b.get('label') or b['anon'] or b['uid']} — بردارم",
                       callback_data=f"{CB}unblock:{b['uid']}")])
    rows.append([B("ℹ️ قوانین", callback_data=f"{CB}rules"),
                 B("↩️ منوی رینگ", callback_data=f"{CB}menu")])
    return KB(rows)


def kb_menu(view: dict) -> KB:
    """منوی /ring (§۴۱) — فقط گزینه‌هایی که برای این کاربر معنا دارند."""
    rows = []
    if view.get("in_chat"):
        rows.append([B("💬 ادامه‌ی گفت‌وگو", callback_data=f"{CB}chat")])
    if view.get("in_queue"):
        rows.append([B("🔄 نفر بعدی", callback_data=f"{CB}next"),
                     B("⛔ پایان صف", callback_data=f"{CB}stop")])
    if not view.get("in_chat"):
        rows.append([B("🔎 پیدا کردن نفر", callback_data=f"{CB}go")])
    rows.append([B("👤 پروفایل", callback_data=f"{CB}profile"),
                 B("🛡 امنیت", callback_data=f"{CB}safety")])
    rows.append([B("⏸ مکث", callback_data=f"{CB}pause"),
                 B("▶️ ادامه", callback_data=f"{CB}resume")])
    rows.append([B("ℹ️ قوانین", callback_data=f"{CB}rules"),
                 B("🗑 حذف پروفایل", callback_data=f"{CB}del")])
    rows.append([B("↩️ منوی اصلی ربات", callback_data="main")])
    return KB(rows)
