"""💍 Ring Street — متن‌های کاربر (§۳۹)

لحن: محترمانه، غیرقضاوتی، بدون تهدید. جمله‌های حقوقی کوتاه‌اند و
همیشه «خوداظهاری سن» و «ناشناس‌بودن» صریح گفته می‌شود (§۲، §۱۲).
هیچ‌جا ادعای «امنیت کامل» نمی‌کنیم؛ یادآوری‌ها «توصیه»اند (§۲۸).
"""
from __future__ import annotations

from html import escape as _e

from ring import models as M

BOT_NOTE = "پیام‌ها از طریق ربات و بدون نمایش آیدی/نام شما ارسال می‌شود."

SAFETY_NOTES = [
    "🛡 شماره، آیدی شخصی، لوکیشن و لینک نفرست.",
    "🛡 اگر طرف مقابل اصرار به تماس/ویدیو/پول کرد، گزارش بده.",
    "🛡 قرار حضوری = مسئولیت خودت؛ جای عمومی و به کسی خبر بده.",
    "🛡 هیچ اطلاعات مالی یا رمز عبوری با کسی به اشتراک نگذار.",
    "🛡 هر وقت خواستی با /ring یا دکمه‌ی «پایان» خارج شو.",
]

RULES_SERIOUS = (
    "💍 <b>قوانین آشنایی جدی</b>\n\n"
    "• احترام در اولویت است؛ توهین، تبعیض و آزار = محدودیت.\n"
    "• خبری از عکس پروفایل و نام نیست — اول آدم‌ها را بشناس.\n"
    "• شماره/آیدی/لینک نفرست؛ معرفی فقط با <b>موافقت دوطرفه</b>.\n"
    "• محتوای جنسی، تبلیغات و درخواست پول ممنوع.\n"
    "• سن پایین‌تر از {min_age} وارد نمی‌شود (خوداظهاری).\n"
    "• هر لحظه می‌توانی «نفر بعدی» بزنی، بلاک یا گزارش کنی."
)
RULES_FUN = (
    "🎭 <b>قوانین رینگ فان</b>\n\n"
    "• فقط گپ سبک و محترمانه؛ فحاشی و آزار = محدودیت.\n"
    "• هویتت مخفی می‌ماند؛ شماره/آیدی/لوکیشن نفرست.\n"
    "• محتوای جنسی و تبلیغات ممنوع.\n"
    "• سن پایین‌تر از {min_age} وارد نمی‌شود (خوداظهاری).\n"
    "• «نفر بعدی» یعنی خداحافظی مؤدبانه؛ گیر نده."
)
TERMS_TEXT = (
    "📜 <b>قبل از شروع، این را بخوان</b>\n\n"
    "۱) رینگ استریت فضایی <b>ناشناس</b> برای گفت‌وگوی {mode} است.\n"
    "۲) پیام‌ها <b>از طریق همین ربات</b> رد می‌شود؛ طرف مقابل آیدی، نام، "
    "عکس پروفایل یا شماره‌ی تلگرام تو را نمی‌بیند.\n"
    "۳) ما سن را <b>احراز هویت نمی‌کنیم</b>؛ تو اعلام می‌کنی {min_age}+ هستی "
    "و صحتش مسئولیت خودت است.\n"
    "۴) متن گفت‌وگو ذخیره <b>نمی‌شود</b>. فقط اگر گزارش ثبت کنی، چند پیام "
    "آخر برای بررسی نگه داشته می‌شود ({ttl} روز).\n"
    "۵) توهین، آزار، محتوای جنسی، تبلیغات و درخواست پول ⇒ محدودیت یا بن.\n"
    "۶) هر لحظه می‌توانی خارج شوی، بلاک یا گزارش کنی.\n"
    "۷) رینگ جای پیدا کردن شریک زندگی قطعی نیست؛ تصمیم‌های جدی را با "
    "شناخت بیشتر و در دنیای واقعی بگیر.\n\n"
    f"🔒 {BOT_NOTE}"
)


def _age(min_age: int) -> dict:
    return {"min_age": min_age, "ttl": 7}


def privacy_intro() -> str:
    return (
        "🕶 <b>هویت شما مخفی می‌ماند</b>\n\n"
        "• نام، یوزرنیم، آیدی عددی تلگرام، عکس پروفایل و شماره‌ی شما "
        "هرگز به طرف مقابل نشان داده نمی‌شود.\n"
        "• پیام‌ها با کپی‌کردن داخل ربات ارسال می‌شود؛ هیچ لینکی به پیام "
        "اصلی شما وجود ندارد.\n"
        "• در هر گفت‌وگو با یک برچسب بی‌نام مثل «👤 ناشناس #A7K3» دیده می‌شوید.\n"
        "• معرفی فقط با موافقت دوطرفه و در حالت جدی ممکن است."
    )


def age_gate() -> str:
    return (
        "💍 <b>رینگ استریت</b>\n\n"
        "این فضا فقط برای افراد ۱۸ سال به بالاست.\n"
        "سن شما <b>خوداظهاری</b> است و احراز هویت نمی‌شود، اما درایه‌ی نادرست "
        "همان لحظه دسترسی را می‌بندد و قابل پیگیری است.\n\n"
        "حلقه‌ی سنی‌ات کدام است؟"
    )


def too_young() -> str:
    return ("⛔ متأسفم — رینگ استریت فقط برای ۱۸+ است و پروفایلی برایت "
            "ساخته نمی‌شود.\nبقیه‌ی قابلیت‌های ربات هم مثل قبل در دسترس است: /start")


def gender_ask() -> str:
    return ("👤 با چه جنسیتی در این فضا حضور داری؟\n"
            "(فقط برای تطبیق استفاده می‌شود؛ جای دیگر نشان داده نمی‌شود.)")


def mode_ask(cfg: dict) -> str:
    lines = ["🎯 کدام حالت را می‌خواهی؟", "",
             "💍 <b>آشنایی جدی</b> — گفت‌وگوی عمیق‌تر، پروفایل کامل‌تر، "
             "امکان معرفی دوطرفه.",
             "🎭 <b>رینگ فان</b> — گپ سبک، موضوع‌محور، کوتاه."]
    if not cfg.get("serious_enabled"):
        lines[2] = "💍 آشنایی جدی — فعلاً غیرفعال است"
    if not cfg.get("fun_enabled"):
        lines[3] = "🎭 رینگ فان — فعلاً غیرفعال است"
    lines.append("\nهیچ‌وقت هر دو را هم‌زمان نداشته باشی؛ هر لحظه قابل تغییر است.")
    return "\n".join(lines)


def terms(mode: str, cfg: dict) -> str:
    return TERMS_TEXT.format(mode="جدی" if mode == "serious" else "فان",
                             min_age=cfg.get("min_age", 18),
                             ttl=cfg.get("evidence_ttl_days", 7))


def rules(mode: str, cfg: dict) -> str:
    txt = RULES_SERIOUS if mode == "serious" else RULES_FUN
    return txt.format(min_age=cfg.get("min_age", 18))


def declined_terms() -> str:
    return "🙏 باشه. تا قوانین را نپذیری وارد نمی‌شوی. هر وقت خواستی /ring."


def profile_ask(field: str) -> str:
    label, limit = M.PROFILE_FIELDS[field]
    extra = {
        "bio": "چند خط درباره‌ی خودت؛ بدون نام/شماره/لینک.",
        "interests": "با کاما جدا کن: کتاب، کوهنوردی، فیلم...",
        "city": "شهر (اختیاری).",
        "university": "دانشگاه/محل تحصیل (اختیاری).",
        "major": "رشته (اختیاری).",
    }.get(field, "")
    return f"✏️ {label} — حداکثر {limit} کاراکتر.\n{extra}\n«رد کردن» هم مجاز است."


def profile_saved() -> str:
    return "✅ ذخیره شد."


def profile_summary(p: dict, *, for_whom: str = "self") -> str:
    mode = M.MODES.get(p.get("mode"), "—")
    age = M.AGE_LABELS.get(p.get("age_range"), "—")
    g = M.GENDERS.get(p.get("gender"), "—")
    out = [f"👤 <b>{_e(str(p.get('anon_id') or 'ناشناس'))}</b>"]
    if for_whom == "self":
        out.append(f"   {g} · {age} · {mode}")
    else:
        out.append(f"   {g} · {age}")
    for k in ("city", "university", "major"):
        v = (p.get(k) or "").strip()
        if v:
            out.append(f"   • {M.PROFILE_FIELDS[k][0]}: {_e(v)}")
    bio = (p.get("bio") or "").strip()
    if bio:
        out.append(f"\n📝 {_e(bio)}")
    it = (p.get("interests") or "").strip()
    if it:
        out.append(f"🌱 {_e(it)}")
    tp = p.get("topics") or []
    if tp:
        out.append("🏷 " + "، ".join(M.TOPICS.get(t, t) for t in tp))
    if for_whom == "self":
        st = int(p.get("report_score") or 0)
        if st:
            out.append(f"⚠️ امتیاز گزارش: {st}")
    return "\n".join(out)


def queue_waiting(mode: str, cfg: dict) -> str:
    return (
        f"⏳ {'در صف آشنایی جدی' if mode == 'serious' else 'در صف رینگ فان'} هستی…\n\n"
        f"• معمولاً کمتر از {max(1, int(cfg['queue_timeout_s']) // 60)} دقیقه طول می‌کشد.\n"
        "• اگر کسی پیدا نشد، بهت می‌گویم و هر وقت خواستی دوباره تلاش کن.\n"
        "• صف را با «پایان» ببند؛ نیازی نیست منتظر بمانی."
    )


def queue_empty(mode: str, cfg: dict) -> str:
    return (
        "🙂 الان کسی در صف نیست که با معیارهای تو بخورد.\n\n"
        "• چند دقیقه بعد دوباره امتحان کن؛\n"
        f"• یا حلقه‌ی سنی/ترجیحاتت را در «👤 پروفایل» بازتر کن.\n"
        f"• سقف انتظار {max(1, int(cfg['queue_timeout_s']) // 60)} دقیقه است و "
        "صف خودبه‌خود بسته می‌شود."
    )


def match_card(sess: dict, peer: dict, cfg: dict, *, session_no: int = 1) -> str:
    mode = sess.get("mode") or "fun"
    lines = [f"✨ <b>یک همراه پیدا شد!</b> ({'آشنایی جدی' if mode == 'serious' else 'رینگ فان'})", ""]
    who = f"👤 ناشناس #{str((peer or {}).get('anon_id') or '').lstrip('#')}"
    lines.append(who)
    body = []
    for k in ("age_range", "city", "university", "major"):
        if k == "age_range":
            body.append(M.AGE_LABELS.get((peer or {}).get("age_range"), "—"))
        else:
            v = ((peer or {}).get(k) or "").strip()
            if v:
                body.append(_e(v[:60]))
    if body:
        lines.append("   " + " · ".join(str(b) for b in body))
    bio = ((peer or {}).get("bio") or "").strip()
    if bio:
        lines.append(f"\n{_e(bio[:200])}")
    it = ((peer or {}).get("interests") or "").strip()
    if it:
        lines.append(f"🌱 {_e(it[:120])}")
    lines.append("\n🗣 از همین چت بنویس؛ هر پیامی که بفرستی برای او می‌رود.")
    lines.append("🔎 «نفر بعدی» یعنی تمام؛ «پایان» یعنی بستن گفت‌وگو.")
    every = int(cfg.get("safety_note_every", 3)) or 3
    if every <= 0 or session_no % every == 0:
        lines.append("\n" + SAFETY_NOTES[(session_no - 1) % len(SAFETY_NOTES)])
    return "\n".join(lines)


def controls_note() -> str:
    return ("\n🎛 کنترل‌ها: نفر بعدی · پایان · بلاک · گزارش · قوانین · پروفایل")


def peer_ended() -> str:
    return ("🔚 طرف مقابل گفت‌وگو را بست.\n"
            "اگر دوست داری دوباره وارد شوی: «🔎 پیدا کردن نفر» در /ring.")


def peer_next() -> str:
    return ("🔄 طرف مقابل به نفر بعدی رفت.\n"
            "تو هم می‌توانی «🔎 پیدا کردن نفر» بزنی یا /ring را ببندی.")


def admin_ended() -> str:
    return "🛠 گفت‌وگو توسط تیم نظارت بسته شد. برای ادامه: /ring"


def ending_soon(mins: int) -> str:
    return (f"⌛ اگر تا {mins} دقیقه پاسخی نیاید، گفت‌وگو بسته می‌شود.\n"
            "با «🔎 نفر بعدی» می‌توانی زودتر تمامش کنی.")


def blocked() -> str:
    return ("🚫 او را بلاک کردی.\n• دیگر هیچ‌وقت با تو جفت نمی‌شود\n"
            "• گفت‌وگو بسته شد\n• از «🛡 امنیت» می‌توانی لیست بلاک را ببینی.")


def unblocked() -> str:
    return "✅ بلاک برداشته شد."


def report_ask() -> str:
    return ("⚠️ چه اتفاقی افتاده؟\n"
            "دلیل را انتخاب کن؛ بعد در صورت تمایل چند خط توضیح بنویس.\n"
            "🔒 گزارش فقط برای تیم نظارت است و به طرف مقابل گفته نمی‌شود.")


def report_done(info: dict) -> str:
    extra = "\n🚫 او را بلاک هم کردم." if info.get("blocked") else ""
    status = ("گزارشت به تیم نظارت رسید و در حال بررسی است." if info.get("ok")
              else "گزارش ثبت نشد.")
    return (f"✅ {status}\n• گفت‌وگو بسته شد.\n"
            f"• اگر رفتار خطرناک بود، از تلگرام هم گزارش بده."
            f"{extra}")


def no_session() -> str:
    return "🙂 الان در گفت‌وگو نیستی. با /ring شروع کن."


def disabled() -> str:
    return "🔒 رینگ استریت فعلاً غیرفعال است. بعداً دوباره سر بزن."


def feature_off(feature: str) -> str:
    return f"🔒 {feature} فعلاً از پنل غیرفعال است."


def reveal_ask() -> str:
    return ("🤝 طرف مقابل می‌خواهد هویت شما دوطرفه مشخص شود.\n"
            "اگر موافقی «بله» را بزن؛ با «نه» همه‌چیز مثل قبل می‌ماند.")


def reveal_shared(profile: dict | None) -> str:
    p = profile or {}
    tg = p.get("telegram_username")
    return ("🎉 معرفی دوطرفه انجام شد:\n"
            f"• حلقه‌ی سنی: {M.AGE_LABELS.get(p.get('age_range'), '—')}\n"
            f"• شهر: {_e(p.get('city') or '—')}\n"
            + (f"• نام نمایشی: {_e(p.get('display_name'))}\n" if p.get("display_name") else "")
            + (f"• تلگرام: @{_e(tg)}\n" if tg else "")
            + "\nهر طور راحتی ادامه بده؛ رینگ همچنان ناظر گفت‌وگو نیست.")


def ban_notice() -> str:
    return "🚫 دسترسی شما به رینگ استریت محدود شده است."


def queue_status_line(count: int) -> str:
    if count <= 0:
        return "🎯 تنها نفرِ صف هستی."
    return f"🎯 {count} نفر قبل از تو در صف‌اند."


def rating_ask() -> str:
    return "🌟 این گفت‌وگو چطور بود؟ (اختیاری — فقط برای کیفیت سنجی)"


def bye() -> str:
    return "👋 رینگ استریت بسته شد. هر وقت خواستی /ring."


def help_ring() -> str:
    return (
        "ℹ️ <b>رینگ استریت</b> — گفت‌وگوی ناشناس با افراد هم‌سن‌وسال.\n\n"
        "💍 آشنایی جدی · 🎭 رینگ فان\n"
        "🔎 «نفر بعدی» تا آدم مناسب را پیدا کنی\n"
        "🚫 بلاک و ⚠️ گزارش در هر لحظه\n\n"
        "🔒 هویت تو (آیدی، نام، عکس، شماره) به طرف مقابل نشان داده نمی‌شود و "
        "متن گفت‌وگو ذخیره نمی‌شود.\n\n"
        "برای شروع: /ring")
