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

# ── قوانین (§۲۶) — نسخه‌دار (§۲۷) ──────────────────────────────
# متن پیش‌فرض همین‌جاست؛ ادمین می‌تواند از پنل متن جایگزین بگذارد
# (کلید تنظیمات `rules_text_override`) و با `rules_version` همه را مجبور
# به پذیرش دوباره کند.
RULES_BODY = (
    "🛡 <b>قوانین رینگ استریت</b>\n\n"
    "رینگ استریت فضای گفت‌وگوی <b>ناشناس</b> برای افراد {min_age} سال به بالاست. "
    "برای اینکه این فضا برای همه امن بماند، رعایت این بندها الزامی است.\n\n"
    "<b>۱. 👤 ناشناس بودن</b>\n"
    "هویت کسی نباید افشا یا درخواست شود. ارسال یا درخواست شمارهٔ تلفن، آیدی و "
    "یوزرنیم شخصی، لینک پروفایل، آدرس خانه یا محل کار، لوکیشن دقیق، اطلاعات "
    "بانکی، رمز عبور و هر دادهٔ هویتی حساس ممنوع است.\n\n"
    "<b>۲. 🤝 احترام</b>\n"
    "توهین، تحقیر، تهدید، آزار، زورگویی و مزاحمت ممنوع است. ناشناس بودن به معنی "
    "بی‌قانون بودن نیست.\n\n"
    "<b>۳. 🔞 محتوای جنسی و نامناسب</b>\n"
    "ارسال یا درخواست محتوای جنسی یا صریح ممنوع؛ اصرار برای فرستادن عکس خصوصی، "
    "تماس تصویری یا هر محتوای خصوصی هم ممنوع.\n\n"
    "<b>۴. 💰 پول و کلاهبرداری</b>\n"
    "درخواست پول، قرض، انتقال وجه، سرمایه‌گذاری، خریدوفروش یا هر پیشنهاد مالی "
    "مشکوک ممنوع. اگر کسی از تو پول خواست، گزارشش کن.\n\n"
    "<b>۵. 📞 بردن گفت‌وگو به بیرون از رینگ</b>\n"
    "هیچ‌کس نباید تو را تحت فشار بگذارد که شماره بدهی، تماس بگیری، تماس تصویری "
    "برقرار کنی یا به شبکهٔ اجتماعی دیگری بروی. اگر نمی‌خواهی، «نه» کافی است.\n\n"
    "<b>۶. 🕵️ تلاش برای شناسایی</b>\n"
    "تلاش برای پیدا کردن هویت واقعی طرف مقابل، استخراج اطلاعات شخصی، تعقیب، "
    "doxxing یا تهدید به افشا ممنوع.\n\n"
    "<b>۷. 📢 تبلیغات و اسپم</b>\n"
    "تبلیغ، ارسال مکرر لینک، دعوت به کانال‌ها، فروش خدمات و اسپم ممنوع.\n\n"
    "<b>۸. 🚫 دور زدن محدودیت‌ها</b>\n"
    "استفاده از حساب‌های متعدد یا هر روش دیگر برای دور زدن محدودیت‌های رینگ "
    "استریت ممنوع.\n\n"
    "<b>۹. 👋 پایان گفت‌وگو</b>\n"
    "اگر طرف مقابل «🔄 نفر بعدی» را زد یا گفت‌وگو را تمام کرد، به تصمیمش احترام "
    "بگذار؛ اصرار، تعقیب و ایجاد مزاحمت ممنوع.\n\n"
    "<b>۱۰. 🚨 گزارش</b>\n"
    "هر رفتار ناراحت‌کننده، تهدیدآمیز یا خلاف قوانین را با «🚨 گزارش» ثبت کن؛ "
    "گزارش‌ها بررسی می‌شوند.\n\n"
    "<b>۱۱. ⚠️ قرار حضوری</b>\n"
    "تصمیم برای ملاقات حضوری کاملاً با خودت است: جای عمومی انتخاب کن، اطلاعات "
    "غیرضروری نده، یک نفر قابل‌اعتماد را در جریان بگذار و در صورت احساس خطر "
    "لغوش کن.\n\n"
    "<b>۱۲. 🔐 مسئولیت</b>\n"
    "رینگ استریت فقط بستری برای گفت‌وگو و آشنایی است؛ اطلاعات حساس خودت را به "
    "افراد ناشناس نده.\n\n"
    "<b>احترام + احتیاط = رینگ بهتر برای همه 💍</b>"
)
RULES_FOOT = {
    "serious": "\n\n💍 در حالت <b>آشنایی جدی</b> اطلاعات پروفایل (رشته، دانشگاه، "
               "شهر و «دربارهٔ من») فقط در حدی نمایش داده می‌شود که خودت در "
               "«👤 پروفایل من → چه چیزهایی دیده شود» اجازه داده باشی. معرفی "
               "هویت فقط با موافقت <b>دوطرفه</b> ممکن است.",
    "fun": "\n\n🎭 در حالت <b>فان</b> فقط حلقهٔ سنی و جنسیت نمایش داده می‌شود؛ "
           "پروفایل سنگین لازم نیست.",
}


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


def _fa(v) -> str:
    """عدد لاتین → فارسی (متن‌های فارسی نباید عدد لاتین وسطشان داشته باشند)."""
    return "".join("۰۱۲۳۴۵۶۷۸۹"[int(c)] if c.isdigit() else c for c in str(v))


def age_gate(min_age: int = 18) -> str:
    return (
        "💍 <b>رینگ استریت</b>\n\n"
        "قبل از ورود، چند اطلاعات کوتاه ازت می‌گیریم.\n"
        "اول بگو چند سالته؟\n\n"
        f"• سن <b>خوداظهاری</b> است و احراز هویت نمی‌شود؛ سن مجاز فقط {_fa(min_age)}+ است.\n"
        f"• سن دقیقت هیچ‌جا نمایش داده نمی‌شود — فقط حلقهٔ سنی.\n\n"
        f"اگر زیر {_fa(min_age)} هستی، گزینهٔ «🔞 زیر ۱۸ سال» را بزن."
    )


def too_young() -> str:
    return ("⛔ رینگ استریت فقط برای افراد ۱۸ سال به بالا فعال است.\n"
            "پروفایلی برایت ساخته نمی‌شود. بقیهٔ بخش‌های همیار مثل قبل در "
            "دسترس است: /start")


def gender_ask() -> str:
    return ("👤 حالا خودت رو چطور معرفی می‌کنی؟\n\n"
            "این انتخاب فقط برای تطبیق استفاده می‌شود و جای دیگری "
            "نشان داده نمی‌شود.")


def mode_ask(cfg: dict) -> str:
    lines = ["🎯 کدام حالت را می‌خواهی؟", "",
             "💍 <b>آشنایی جدی</b> — گفت‌وگوی عمیق‌تر، پروفایل کامل‌تر، "
             "امکان معرفی دوطرفه.",
             "🎭 <b>رینگ فان</b> — گپ سبک، موضوع‌محور، کوتاه."]
    if not cfg.get("serious_enabled"):
        lines[2] = "💍 آشنایی جدی — فعلاً غیرفعال است"
    if not cfg.get("fun_enabled"):
        lines[3] = "🎭 رینگ فان — فعلاً غیرفعال است"
    lines.append("\n• این دو صف هیچ‌وقت با هم مخلوط نمی‌شوند.\n"
                 "• هر لحظه می‌توانی حالت را عوض کنی.\n"
                 "• با «ℹ️ تفاوت این دو حالت» می‌توانی اول بخوانی.")
    return "\n".join(lines)


def terms(mode: str, cfg: dict) -> str:
    return TERMS_TEXT.format(mode="جدی" if mode == "serious" else "فان",
                             min_age=cfg.get("min_age", 18),
                             ttl=cfg.get("evidence_ttl_days", 7))


def rules(mode: str, cfg: dict) -> str:
    """متن قوانین — اگر ادمین از پنل متن جایگزین گذاشته، همان (و در غیر
    این صورت RULES_BODY). `mode` فقط به پاورقی اضافه می‌شود."""
    over = (cfg or {}).get("rules_text_override") or ""
    body = over.strip() or RULES_BODY
    try:
        body = body.format(min_age=int((cfg or {}).get("min_age", 18)))
    except (KeyError, IndexError, ValueError):
        pass                                  # متن ادمین نباید crash بدهد
    return body + RULES_FOOT.get(mode, RULES_FOOT["fun"])


def rules_version_line(cfg: dict) -> str:
    return f"نسخهٔ قوانین: {int((cfg or {}).get('rules_version', 1))}"


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
        # «پیش‌نمایش آنچه طرف مقابل می‌بیند» — فقط با اجازهٔ خود کاربر (§۳۵)
        bits = [x for x, on in ((g, M.view_on(p, "show_gender")),
                                (age, M.view_on(p, "show_age"))) if on and x != "—"]
        if bits:
            out.append("   " + " · ".join(bits))
        for k, flag in (("city", "show_city"), ("university", "show_university"),
                        ("major", "show_field")):
            v = (p.get(k) or "").strip()
            if v and M.view_on(p, flag):
                out.append(f"   • {M.PROFILE_FIELDS[k][0]}: {_e(v)}")
        if M.view_on(p, "show_bio"):
            bio = (p.get("bio") or "").strip()
            if bio:
                out.append(f"\n📝 {_e(bio)}")
            it = (p.get("interests") or "").strip()
            if it:
                out.append(f"🌱 {_e(it)}")
            tp = p.get("topics") or []
            if tp:
                out.append("🏷 " + "، ".join(M.TOPICS.get(x, x) for x in tp))
        hidden = [lbl for key, lbl in M.PROFILE_VIEW.items() if not M.view_on(p, key)]
        if hidden:
            out.append("🙈 مخفی: " + "، ".join(h.split(" ", 1)[-1] for h in hidden))
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


def queue_empty(mode: str, cfg: dict, *, why: str | None = None,
                waited_s: int = 0, p: dict | None = None) -> str:
    if why == "recent_only":
        return ("🙂 فعلاً فرد سازگارِ تازه‌ای پیدا نشد.\n\n"
                "• همه‌ی کسانی که الان در این صف‌اند را اخیراً دیدی؛ برای اینکه "
                "تکراری نشود، فعلاً کنارشان گذاشته‌ایم.\n"
                f"• بعد از {hm_wait(int(cfg.get('rematch_after_s') or 90))} صبر، "
                "همان‌ها هم دوباره قابل انتخاب می‌شوند.\n"
                "• می‌توانی معیارهایت را بازتر کنی: «👤 پروفایل من → ⚙️ معیارها».")
    return (
        "🙂 فعلاً فرد سازگارِ دیگری در صف نیست.\n\n"
        f"⏱ {mmss(waited_s)} جست‌وجو کردیم.\n"
        "• چند دقیقه بعد دوباره امتحان کن؛\n"
        "• یا حلقه‌ی سنی/ترجیحاتت را در «👤 پروفایل من → ⚙️ معیارها» بازتر کن.\n"
        f"• سقف انتظار {max(1, int(cfg['queue_timeout_s']) // 60)} دقیقه است و "
        "صف خودبه‌خود بسته می‌شود."
        + (("\n\n🎯 معیارهای تو:\n" + prefs_line(p)) if p is not None else "")
    )


def match_card(sess: dict, peer: dict, cfg: dict, *, session_no: int = 1) -> str:
    mode = sess.get("mode") or "fun"
    lines = [f"✨ <b>یک همراه پیدا شد!</b> ({'آشنایی جدی' if mode == 'serious' else 'رینگ فان'})", ""]
    peer = peer or {}
    code = str(peer.get("anon_id") or "").lstrip("#")
    lines.append(f"👤 <b>ناشناس #{code}</b>" if code else "👤 <b>ناشناس</b>")
    body = []
    if M.view_on(peer, "show_age"):
        body.append(M.AGE_LABELS.get(peer.get("age_range"), "—"))
    if M.view_on(peer, "show_gender"):
        body.append(M.GENDERS.get(peer.get("gender"), "—").split(" ")[-1])
    if mode == "serious":
        if M.view_on(peer, "show_field") and (peer.get("major") or "").strip():
            body.append(f"📚 {_e(peer['major'].strip()[:40])}")
        if M.view_on(peer, "show_university") and (peer.get("university") or "").strip():
            body.append(f"🎓 {_e(peer['university'].strip()[:40])}")
        if M.view_on(peer, "show_city") and (peer.get("city") or "").strip():
            body.append(f"🏙 {_e(peer['city'].strip()[:30])}")
    if body:
        lines.append("   " + " · ".join(str(x) for x in body))
    if mode == "serious" and M.view_on(peer, "show_bio"):
        bio = (peer.get("bio") or "").strip()
        if bio:
            lines.append(f"\n{_e(bio[:200])}")
        it = (peer.get("interests") or "").strip()
        if it:
            lines.append(f"🌱 {_e(it[:120])}")
    lines.append("\n💬 گفت‌وگو از همین‌جا شروع می‌شود؛ هر پیامی بفرستی برای او می‌رود.")
    lines.append("🔄 نفر بعدی = پایان این گفت‌وگو و ورود دوباره به صف · "
                 "⏹ پایان گفتگو = فقط بستن گفت‌وگو")
    every = int(cfg.get("safety_note_every", 3)) or 3
    if every <= 0 or session_no % every == 0:
        lines.append("\n" + SAFETY_NOTES[(session_no - 1) % len(SAFETY_NOTES)])
    return "\n".join(lines)


def controls_note() -> str:
    return ("\n🎛 کنترل‌ها: نفر بعدی · پایان · بلاک · گزارش · قوانین · پروفایل")


def peer_ended() -> str:
    return ("👋 طرف مقابل گفتگو را به پایان رساند.\n\n"
            "می‌توانی دوباره وارد جست‌وجو شوی.")


def chat_closed_by_you() -> str:
    return ("⏹ گفت‌وگو بسته شد و به منوی رینگ برگشتی.\n"
            "هر وقت خواستی «🔎 پیدا کردن نفر» را بزن.")


QUEUE_COUNT_CAP = 200      # هم‌راستا با db.ring.QUEUE_COUNT_CAP


def hm_wait(seconds: int) -> str:
    """«۹۰ ثانیه» / «۲ دقیقه» — برای متن‌های زمان‌دارِ تقریبی."""
    seconds = max(1, int(seconds))
    return f"{seconds // 60} دقیقه" if seconds >= 60 else f"{seconds} ثانیه"


def being_picked(mode: str = "fun") -> str:
    """کاربر همین لحظه توسط جست‌وجویِ دیگری رزرو شده — باید بداند چه خبر است."""
    return ("💍 <b>رینگ استریت</b>\n\n"
            "⏳ یک نفر همین حالا دارد شما را انتخاب می‌کند؛ اگر انتخاب شد، "
            "کارت گفت‌وگو خودبه‌خود می‌آید.\n\n"
            "   لازم نیست دکمه را دوباره بزنی — اگر این انتخاب به نتیجه نرسید، "
            f"همین‌جا در صف می‌مانی (حالت: {M.MODES.get(mode, '—')}).")


def mmss(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def prefs_line(p: dict) -> str:
    """خلاصهٔ معیارهای جاری — تا بداند «چرا» کسی پیدا نشد (§۱۳)."""
    bits = []
    g = (p or {}).get("pref_gender")
    bits.append("👥 همه" if not g or g == "any" else M.GENDERS.get(g, g))
    pr = (p or {}).get("pref_age_ranges")
    if not pr or pr == "any":
        bits.append("🎂 بدون محدودیت سنی")
    else:
        bits.append("🎂 " + "، ".join(M.AGE_LABELS.get(x.strip(), x.strip())
                                     for x in str(pr).split(",") if x.strip()))
    return "\n".join("   " + b for b in bits)


def searching(mode: str, p: dict | None = None, waited_s: int = 0) -> str:
    lines = [f"💍 <b>رینگ استریت</b>", "", "🔎 در حال پیدا کردن یک نفر...",
             f"⏱ مدت انتظار: {mmss(waited_s)}", "", "🎯 معیارهای تو:"]
    lines.append(prefs_line(p or {}) if p is not None else
                 f"   حالت: {M.MODES.get(mode, '—')}")
    lines.append("\nهر وقت فرد مناسب پیدا شود، خودکار به او متصل می‌شوی.")
    return "\n".join(lines)


def still_waiting(position: int, mode: str, *, waited_s: int = 0,
                  p: dict | None = None) -> str:
    if position > QUEUE_COUNT_CAP:
        tail = f"🎯 حداقل {QUEUE_COUNT_CAP} نفر قبل از تو در صف‌اند."
    elif position > 0:
        tail = f"🎯 {position} نفر قبل از تو در صف‌اند."
    else:
        tail = "🎯 تنها نفرِ این صف هستی."
    lines = ["💍 <b>رینگ استریت</b>", "",
             "🔎 هنوز فرد سازگاری پیدا نشده؛ جست‌وجو ادامه دارد.",
             f"⏱ مدت انتظار: {mmss(waited_s)}",
             f"   {tail}",
             f"   حالت: {M.MODES.get(mode, '—')}"]
    if p is not None:
        lines += ["", "🎯 معیارهای تو:"]
        lines.append(prefs_line(p))
    lines += ["", "هر وقت فرد مناسب پیدا شود، خودکار متصل می‌شوی — لازم نیست "
                  "دوباره دکمه را بزنی."]
    return "\n".join(lines)


def chat_opened(mode: str) -> str:
    return ("💍 <b>گفت‌وگوی جدید شروع شد.</b>\n\n"
            "هویت هر دو نفر ناشناس است.\n"
            "لطفاً محترمانه گفت‌وگو کنید و اطلاعات شخصی ارسال نکنید.\n\n"
            "⏹ پایان گفتگو · 🚨 گزارش · 🚫 مسدود کردن")


def search_paused() -> str:
    return ("⏸ جست‌وجو متوقف شد و از صف خارج شدی.\n"
            "پروفایلت دست‌نخورده مانده؛ با «🔎 ادامه جست‌وجو» برمی‌گردی.")


def idle_prompt(mins: int) -> str:
    return (f"⏳ هنوز اینجایی؟\n\nاگر تا {mins} دقیقه چیزی نفرستی، این گفت‌وگو "
            "بسته می‌شود.")


def delete_confirm() -> str:
    return ("⚠️ با حذف پروفایل رینگ استریت:\n\n"
            "• اطلاعات پروفایل، سابقهٔ match و تنظیمات این بخش حذف می‌شود\n"
            "• اگر در صف یا گفت‌وگو باشی، همان لحظه بسته می‌شود\n"
            "• گزارش‌های ثبت‌شده برای سوابق نظارت می‌مانند\n\n"
            "مطمئنی؟")


def mode_diff() -> str:
    return ("ℹ️ <b>تفاوت این دو حالت</b>\n\n"
            "💍 <b>آشنایی جدی</b> — برای کسانی که قصد آشنایی جدی/ازدواج دارند:\n"
            "   پروفایل کامل‌تر (رشته، دانشگاه، هدف، «دربارهٔ من»)، فیلتر سنی\n"
            "   و امکان معرفی دوطرفه با موافقت هر دو نفر.\n\n"
            "🎭 <b>گفت‌وگوی فان</b> — گپ سبک و کاملاً ناشناس:\n"
            "   فقط حلقهٔ سنی و جنسیت نمایش داده می‌شود؛ بدون معرفی.\n\n"
            "دو صف هیچ‌وقت با هم مخلوط نمی‌شوند.")


def maintenance() -> str:
    return ("💍 رینگ استریت موقتاً در دسترس نیست.\n"
            "به‌زودی دوباره برمی‌گردیم.\n\n"
            "اگر همین الان در گفت‌وگویی، می‌توانی تمامش کنی؛ اما match تازه "
            "ساخته نمی‌شود.")



def peer_next() -> str:
    return ("🔄 طرف مقابل به نفر بعدی رفت.\n"
            "تو هم می‌توانی «🔎 پیدا کردن نفر» بزنی یا /ring را ببندی.")


def admin_ended() -> str:
    return "🛠 گفت‌وگو توسط تیم نظارت بسته شد. برای ادامه: /ring"



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
        "🔎 «پیدا کردن نفر» تا آدم مناسب را پیدا کنی · 🔄 «نفر بعدی» وسط گفت‌وگو\n"
        "🚨 گزارش و 🚫 مسدود کردن در هر لحظه\n\n"
        "🔒 هویت تو (آیدی، نام، عکس، شماره) به طرف مقابل نشان داده نمی‌شود و "
        "متن گفت‌وگو ذخیره نمی‌شود.\n\n"
        "برای شروع: /ring")
