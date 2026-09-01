"""💍 Ring Street — کیبوردها (§۷، §۱۱، §۱۶، §۲۰)

همه‌ی callback‌ها با پیشوند `ring:` و حداکثر ۶۴ بایت. هیچ callback داده‌ای
حاوی اطلاعات هویتی نیست (فقط uid در callback نیست که مشکلی ایجاد کند —
شناسه‌ها همگی در سرور نگه داشته می‌شوند).
"""
from __future__ import annotations

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as KB

from ring import models as M

CB = "ring:"

# ══════════════════════════════════════════════════════════════
#  §۲۰/§۲۱/§۴۶/§۴۷/§۵۸ (V4) — کیبوردِ گفت‌وگو فقط Inline است، و *هیچ*
#  برچسبِ دکمه‌ای نباید به‌عنوان پیام به پارتنر رله شود.
#
#  دو خانواده برچسب داریم:
#   • CONTROL_LABELS — دکمه‌های کنترلیِ خودِ رینگ. اگر کسی این متن‌ها را
#     تایپ هم کرد، رله نمی‌شوند (§۲۱: کنترل = کاربر→بات، نه کاربر→پارتنر).
#   • main_menu_labels() — برچسب‌های کیبوردِ اصلیِ ربات (ReplyKeyboard).
#     این‌ها وقتی در چت زده می‌شوند که کاربر دکمهٔ منوی اصلی را زده باشد؛
#     باید از رله خارج و به هندلرهای خودِ ربات برسند (§۱۲/§۴۷).
# ══════════════════════════════════════════════════════════════

L_NEXT = "⏭ نفر بعدی"
L_END = "❌ پایان گفتگو"
L_REPORT = "🛡 گزارش"
L_BLOCK = "🚫 بلاک"
L_SAFETY = "🛡 امنیت و قوانین"
L_PROFILE = "👤 پروفایل من"
L_REVEAL = "🤝 معرفی دوطرفه"
L_STOPQ = "⏸ توقف جست‌وجو"
L_RESQ = "▶️ ادامه جست‌وجو"
L_YES = "✅ بله، نفر بعدی"
L_NO = "↩️ نه، ادامه بده"

CONTROL_LABELS = frozenset({
    L_NEXT, L_END, L_REPORT, L_BLOCK, L_SAFETY, L_PROFILE, L_REVEAL,
    L_STOPQ, L_RESQ, L_YES, L_NO,
    "🔄 نفر بعدی", "⏹ پایان گفتگو", "🚨 گزارش", "🚫 مسدود کردن",
    "🔎 ادامه جست‌وجو", "⏸ توقف جست‌وجو", "💬 ادامه‌ی گفت‌وگو",
    "🔎 پیدا کردن نفر", "🔎 جست‌وجوی دوباره", "▶️ ادامه گفتگو",
    "🚫 بله، مسدودش کن", "↩️ بی‌خیال", "✅ می‌پذیرم", "↩️ بازگشت به رینگ",
    "👤 پروفایل", "⚙️ معیارها", "📜 قوانین", "↩️ منوی رینگ", "↩️ منوی اصلی ربات",
    "🗑 حذف پروفایل", "🚫 مسدودشده‌ها", "🌟 امتیاز دادن", "💍 انتخاب حالت",
    "💍 رینگ استریت", "🗂 موضوع جلسه",
})

# اگر `import utils` جایی بترکد (تست/محیط ناقص) همین فهرستِ دستی مانع نشت
# دکمه‌ها به گفت‌وگو می‌شود — همان کاری که §۴۷明确要求: هیچ برچسبِ منویی رله نشود.
_MAIN_FALLBACK = (
    "🩺 داشبورد", "📚 منابع", "🧪 بانک سوال", "❓ سوالات متداول", "🤖 هوشیار",
    "📅 برنامه", "👤 پروفایل", "💎 اشتراک ویژه", "💙 حمایت مالی", "🔔 اعلان‌ها",
    "🎫 پشتیبانی", "🎓 پنل محتوا", "👨\u200d⚕️ پنل ادمین", "💍 رینگ استریت",
)

_MAIN_LABELS: frozenset | None = None


def main_menu_labels() -> frozenset:
    """برچسب‌های همهٔ کیبوردهای اصلیِ ربات (ReplyKeyboard) — یک‌بار ساخته و
    کش می‌شود. `import utils` داخل تابع است تا circular import نشود."""
    global _MAIN_LABELS
    if _MAIN_LABELS is not None:
        return _MAIN_LABELS
    out: set[str] = set()
    try:
        import utils
        for name in ("main_keyboard", "content_admin_keyboard", "admin_keyboard",
                     "sub_admin_keyboard"):
            fn = getattr(utils, name, None)
            if not fn:
                continue
            try:
                kb = fn()
            except Exception:
                continue
            for row in (getattr(kb, "keyboard", None) or []):
                for bt in row:
                    t = str(getattr(bt, "text", "") or "").strip()
                    if t:
                        out.add(t)
    except Exception:
        pass
    out |= {"💍 رینگ استریت"}
    if len(out) < 5:                       # utils در دسترس نبود ⇒ فهرست دستی
        out |= set(_MAIN_FALLBACK)
    _MAIN_LABELS = frozenset(out)
    return _MAIN_LABELS


def _norm(text) -> str:
    # ZWJ/ZWSP/BOM و فاصله‌های اضافه: کاربر ممکن است برچسب را تایپ کند
    return (str(text or "").replace("\u200c", "").replace("\u200b", "")
            .replace("\ufeff", "").replace("\u200e", "").strip())


_CONTROL_NORM: frozenset | None = None
_MAIN_NORM: frozenset | None = None


def is_control_label(text) -> bool:
    global _CONTROL_NORM
    if _CONTROL_NORM is None:
        _CONTROL_NORM = frozenset(_norm(x) for x in CONTROL_LABELS)
    return _norm(text) in _CONTROL_NORM


def is_main_menu_label(text) -> bool:
    """دکمهٔ منوی اصلی که وسط چت زده شده (§۴۷) — نباید رله شود."""
    global _MAIN_NORM
    if _MAIN_NORM is None:
        _MAIN_NORM = frozenset(_norm(x) for x in main_menu_labels())
    return _norm(text) in _MAIN_NORM


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
    rows.append([B("ℹ️ تفاوت این دو حالت", callback_data=f"{CB}mdiff")])
    rows.append([B("↩️ بازگشت به رینگ", callback_data=f"{CB}menu")])
    return KB(rows)


def kb_terms(version: int = 1) -> KB:
    return KB([[B("✅ می‌پذیرم", callback_data=f"{CB}t:yes"),
                B("✋ نمی‌پذیرم", callback_data=f"{CB}t:no")],
               [B(f"📜 متن کامل قوانین (نسخه {version})", callback_data=f"{CB}rules")]])


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
    # §۴۲/§۴۳ — لیبل می‌گوید «اینجا هم پیش‌نمایش می‌بینی هم اجازهٔ دیدن را
    # تعیین می‌کنی»؛ کاربر قبل از زدن دکمه می‌داند چه اتفاقی می‌افتد.
    rows.append([B("👁 پیش‌نمایش و «چه چیزی دیده شود»", callback_data=f"{CB}view")])
    rows.append([B("💾 ذخیره و بازگشت", callback_data=f"{CB}p:done"),
                 B("🔎 پیدا کردن نفر", callback_data=f"{CB}go")])
    rows.append([B("↩️ بازگشت به رینگ", callback_data=f"{CB}menu")])
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


def kb_queue(mode: str, cfg: dict, status: str = "waiting", position: int = 0) -> KB:
    """دکمه‌های جست‌وجو (§۱۳..§۱۵).

    ⚠️ «مکث/ادامه» عمداً نیامده: «⏸ توقف جست‌وجو» (=خروج از صف، پروفایل
    می‌ماند) و «🔎 ادامه جست‌وجو» (=ورود دوباره به صف) هر دو کنشِ روشن‌اند و
    هیچ‌کدام جلسه نمی‌سازند یا تمام نمی‌کنند.
    """
    if status == "paused":
        # §۲۳ — لیبل همین ردیف با متن «جست‌وجو متوقف شد» یکی است: ▶️ ادامه
        rows = [[B(L_RESQ, callback_data=f"{CB}resq")],
                [B("↩️ بازگشت به رینگ", callback_data=f"{CB}menu")]]
    elif status == "empty":
        # NO_MATCH: سه راهِ روشن — جست‌وجوی دوباره، بازترکردن معیارها، بازگشت
        rows = [[B("🔎 جست‌وجوی دوباره", callback_data=f"{CB}go")],
                [B("👤 ویرایش پروفایل", callback_data=f"{CB}profile"),
                 B("⚙️ معیارها", callback_data=f"{CB}p:prefs")],
                [B("📜 قوانین", callback_data=f"{CB}rules"),
                 B("↩️ بازگشت به رینگ", callback_data=f"{CB}menu")]]
    else:  # SEARCHING: «ادامه» = همین حالا دوباره تلاش کن (بیرون نمی‌زندش)
        rows = [[B("🔎 ادامه جست‌وجو", callback_data=f"{CB}go"),
                 B("⏸ توقف جست‌وجو", callback_data=f"{CB}stopq")],
                [B("⚙️ معیارها", callback_data=f"{CB}p:prefs"),
                 B("👤 پروفایل", callback_data=f"{CB}profile"),
                 B("↩️ بازگشت به رینگ", callback_data=f"{CB}menu")]]
    if cfg.get("allow_topics"):
        rows.insert(0, [B("🗂 موضوع جلسه", callback_data=f"{CB}tp:0")])
    return KB(rows)


def kb_searching() -> KB:
    """صفحهٔ «در حال پیدا کردن…» (§۱۳) — یک راه فرارِ واقعی، نه دکمهٔ مرده."""
    return KB([[B("⏸ توقف جست‌وجو", callback_data=f"{CB}stopq")]])


def kb_idle_prompt() -> KB:
    """«⏳ هنوز اینجایی؟» (§۵۰) — ادامهٔ همان گفت‌وگو، نه ورود به صف."""
    return KB([[B("▶️ ادامه گفتگو", callback_data=f"{CB}extend"),
                B("⏹ پایان گفتگو", callback_data=f"{CB}end")],
               [B("🚨 گزارش", callback_data=f"{CB}report")]])


def kb_chat(mode: str, cfg: dict) -> KB:
    """کیبورد چت (§۱۲/§۵۷).

    عمداً «مکث/ادامه» ندارد — وسط گفت‌وگو معنا ندارد. دو کنشِ مجزا:
    «🔄 نفر بعدی» = پایان این گفت‌وگو + ورود فوری به صف · «⏹ پایان گفتگو» =
    فقط پایان و بازگشت به منوی رینگ. گزارش/مسدودسازی همیشه در دسترس (§۵۷).
    """
    rows = [[B(L_NEXT, callback_data=f"{CB}next"),
             B(L_END, callback_data=f"{CB}end")],
            [B(L_REPORT, callback_data=f"{CB}report"),
             B(L_BLOCK, callback_data=f"{CB}block")],
            [B(L_SAFETY, callback_data=f"{CB}safety"),
             B(L_PROFILE, callback_data=f"{CB}profile")]]
    if (mode == "serious") and cfg.get("allow_reveal"):
        rows.append([B(L_REVEAL, callback_data=f"{CB}reveal:ask")])
    return KB(rows)


def kb_next_confirm() -> KB:
    """§۲۴ — «نفر بعدی» یک‌بار تأیید می‌خواهد، چون گفت‌وگو را می‌بندد."""
    return KB([[B(L_YES, callback_data=f"{CB}next:yes")],
               [B(L_NO, callback_data=f"{CB}chat")]])


def kb_after_end() -> KB:
    """پس از پایان گفت‌وگو (§۱۷/§۷۱)."""
    return KB([[B("🔎 پیدا کردن نفر جدید", callback_data=f"{CB}go")],
               [B("💍 پروفایل من", callback_data=f"{CB}profile"),
                B("🛡 امنیت و گزارش", callback_data=f"{CB}safety")],
               [B("↩️ منوی رینگ", callback_data=f"{CB}menu")]])


def kb_rules_back() -> KB:
    """صفحهٔ قوانین: پذیرش + بازگشت (§۲۶/§۲۷)."""
    return KB([[B("✅ می‌پذیرم", callback_data=f"{CB}t:yes"),
                B("↩️ بازگشت به رینگ", callback_data=f"{CB}menu")]])


def kb_confirm_block() -> KB:
    """تأیید صریح پیش از مسدود کردن (§۲۰)."""
    return KB([[B("🚫 بله، مسدودش کن", callback_data=f"{CB}block:yes"),
                B("↩️ بی‌خیال", callback_data=f"{CB}chat")]])


def kb_report_reasons() -> KB:
    """۸ دلیل گزارش (§۲۲) — دو تا در هر ردیف تا صفحه کوتاه بماند."""
    rows, line = [], []
    for k, (lbl, _sev) in M.REPORT_REASONS.items():
        line.append(B(lbl, callback_data=f"{CB}r:{k}"))
        if len(line) == 2:
            rows.append(line)
            line = []
    if line:
        rows.append(line)
    rows.append([B("↩️ بازگشت به گفتگو", callback_data=f"{CB}chat"),
                 B("🛡 امنیت", callback_data=f"{CB}safety")])
    return KB(rows)


def kb_report_send() -> KB:
    return KB([[B("📨 ثبت گزارش", callback_data=f"{CB}r:send"),
                B("🚫 گزارش + مسدودسازی", callback_data=f"{CB}r:send_block")],
               [B("↩️ انصراف", callback_data=f"{CB}chat")]])


def kb_rating() -> KB:
    """امتیاز پس از پایان گفت‌وگو (§۳۴).

    callback فقط کلیدِ امتیاز را می‌برد (نه برچسب فارسی) تا با `M.RATINGS`
    جور باشد. هیچ امتیازی هویت را افشا نمی‌کند و امتیاز منفی هرگز به‌طور
    خودکار بن نمی‌سازد — فقط به تیم نظارت می‌رود.
    """
    rows = [[B(M.RATING_LABELS["great"], callback_data=f"{CB}rt:great"),
             B(M.RATING_LABELS["good"], callback_data=f"{CB}rt:good")],
            [B(M.RATING_LABELS["mid"], callback_data=f"{CB}rt:mid"),
             B(M.RATING_LABELS["bad"], callback_data=f"{CB}rt:bad")],
            [B("🚨 مشکل داشت (گزارش)", callback_data=f"{CB}report")],
            [B("↩️ بعداً", callback_data=f"{CB}menu")]]
    return KB(rows)


def kb_reveal_ask() -> KB:
    return KB([[B("✅ بله، معرفی کنم", callback_data=f"{CB}reveal:yes"),
                B("🙏 نه", callback_data=f"{CB}reveal:no")]])


def kb_safety(blocks: list[dict]) -> KB:
    """مرکز امنیت (§۲۱/§۵۷): گزارش، مسدودسازی، قوانین — لیست مسدودشده‌ها
    صفحهٔ جدا دارد (`kb_blocked`) تا این صفحه شلوغ نشود."""
    rows = [[B("🚨 گزارش از گفت‌وگوی فعلی", callback_data=f"{CB}report"),
             B("🚨 گزارش بدون چت", callback_data=f"{CB}report_anon")],
            [B("🚫 مسدود کردن پارتنر فعلی", callback_data=f"{CB}block_now"),
             B("🚫 مسدودشده‌ها", callback_data=f"{CB}blocked")]]
    rows.append([B("📜 قوانین", callback_data=f"{CB}rules"),
                 B("👤 پروفایل من", callback_data=f"{CB}profile")])
    rows.append([B("↩️ بازگشت به رینگ", callback_data=f"{CB}menu")])
    return KB(rows)


def kb_blocked(rows: list[dict]) -> KB:
    kb = []
    for r in (rows or [])[:10]:
        code = str(r.get("anon") or "").lstrip("#")
        kb.append([B(f"🧷 #{code or 'ناشناس'} — آزاد کردن",
                     callback_data=f"{CB}unblock:{r.get('uid')}")])
    if not kb:
        kb.append([B("🙂 کسی را مسدود نکرده‌ای", callback_data=f"{CB}blocked")])
    kb.append([B("↩️ بازگشت به رینگ", callback_data=f"{CB}menu")])
    return KB(kb)


def kb_view(cur: dict) -> KB:
    """«چه چیزهایی از پروفایلم دیده شود» (§۳۵) — هر بخش جدا، پیش‌فرض روشن."""
    rows = []
    for k, label in M.PROFILE_VIEW.items():
        rows.append([B(("✅ " if M.view_on(cur, k) else "⬜ ") + label,
                       callback_data=f"{CB}view:{k}")])
    rows.append([B("↩️ بازگشت به پروفایل من", callback_data=f"{CB}profile")])
    return KB(rows)


def kb_delete_confirm() -> KB:
    """حذف پروفایل فقط با تأیید صریح (§۳۶)."""
    return KB([[B("⚠️ بله، پروفایل رینگ حذف شود", callback_data=f"{CB}del:yes"),
                B("↩️ بی‌خیال", callback_data=f"{CB}menu")]])


def kb_menu(view: dict) -> KB:
    """منوی /ring = داشبورد کوچک (§۲۸/§۴۱/§۶۹).

    «مکث/ادامه/برگشتی» حذف شده (§۵۸)؛ ردیف بالا با وضعیت کاربر عوض می‌شود و
    بقیه جای ثابت دارند تا کاربر هر بار دکمه را پیدا کند.
    """
    rows = []
    if view.get("in_chat"):
        rows.append([B("💬 ادامه‌ی گفت‌وگو", callback_data=f"{CB}chat"),
                     B("⏹ پایان گفتگو", callback_data=f"{CB}end")])
    elif view.get("paused"):
        rows.append([B(L_RESQ, callback_data=f"{CB}resq")])
    elif view.get("in_queue"):
        rows.append([B(L_RESQ, callback_data=f"{CB}resq"),
                     B("⏸ توقف جست‌وجو", callback_data=f"{CB}stopq")])
    elif view.get("mode_missing"):
        rows.append([B("💍 انتخاب حالت", callback_data=f"{CB}m:fun")])
    else:
        rows.append([B("🔎 پیدا کردن نفر", callback_data=f"{CB}go")])
    rows.append([B("👤 پروفایل من", callback_data=f"{CB}profile"),
                 B("🛡 امنیت و قوانین", callback_data=f"{CB}safety")])
    rows.append([B("🚫 مسدودشده‌ها", callback_data=f"{CB}blocked"),
                 B("🗑 حذف پروفایل", callback_data=f"{CB}del")])
    rows.append([B("📜 قوانین", callback_data=f"{CB}rules"),
                 B("🌟 امتیاز دادن", callback_data=f"{CB}rate")])
    rows.append([B("↩️ منوی اصلی ربات", callback_data="main")])
    return KB(rows)
