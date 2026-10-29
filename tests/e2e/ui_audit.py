#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HumsYarX — ممیزی بصری و دودی مینی‌اپ با مرورگر واقعی (Playwright/Chromium)

چرا این فایل وجود دارد؟
─────────────────────────
قبلاً «تست مرورگر واقعی» انجام نشده بود. این اسکریپت همان را ممکن می‌کند:
یک Chromium واقعی، محیط تلگرام شبیه‌سازی‌شده (initData امضاشده لازم نیست،
فقط برای احراز هویت سمت فرانت)، و یک لایه‌ی Mock برای `/api/*` که از فایل
`fixtures.json` پاسخ می‌دهد.

خروجی‌ها (در پوشه‌ی مقصد):
  1. <route>.png        → اسکرین‌شات هر مسیر در ۳ اندازه (موبایل کوچک/معمولی/تبلت)
  2. console.json       → خطاهای کنسول و pageerror هر مسیر
  3. summary.json       → ارتفاع صفحه، RTL، رنگ‌ها، وجود متن، اسکرول افقی
  4. sheet.png          → کانتکت‌شیت موبایل همه‌ی مسیرها (برای بازبینی چشمی)
  5. report.md          → گزارش قابل‌خواندن

اجرا:
  python3 tests/e2e/ui_audit.py --base http://127.0.0.1:8099/app/ --out /tmp/ui
  (یا با --base به دامنه‌ی Railway برای بررسی بعد از دیپلوی)

⚠️ محدودیت صادقانه: این تست بک‌اند واقعی و MongoDB و درگاه پرداخت را
صدا نمی‌زند. تست *رابط کاربری* است (رندر، ناوبری، RTL، خطاهای JS،
شکست چیدمان) — نه تست یکپارچگی داده.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sys.exit("Playwright نصب نیست: pip install playwright && python -m playwright install chromium")

ROUTES = [
    ("/", "خانه"),
    ("/learn", "یادگیری"),
    ("/schedule", "برنامه"),
    ("/grades", "نمرات"),
    ("/me", "من"),
    ("/ai", "هوشیار"),
    ("/learn/questions", "بانک سؤال"),
    ("/learn/exam", "آزمون"),
    ("/learn/resources", "منابع"),
    ("/learn/references", "جزوات"),
    ("/me/subscription", "اشتراک"),
    ("/leaderboard", "رتبه‌بندی"),
    ("/me/tickets", "تیکت"),
    ("/search", "جست‌وجو"),
    ("/me/profile", "پروفایل"),
]

VIEWPORTS = [
    ("sm", 360, 640, 2),    # گوشی کوچک — تست سرریز
    ("md", 390, 844, 2),    # iPhone 14 / معمول
    ("lg", 768, 1024, 1),   # تبلت — تست واکنش‌گرایی
]

# پاسخ‌های نمونه برای مسیرهایی که شکل داده در UI مهم است.
FIXTURES = {
    "/api/profile": {
        "user": {
            "uid": 100200300,
            "first_name": "علی",
            "firstname": "علی",
            "name": "علی",
            "username": "ali",
            "grade": "علوم پایه",
            "field": "پزشکی",
            "intake": "نیم‌سال دوم ۱۴۰۴–۱۴۰۵",
            "role": "student",
            "is_admin": False,
            "is_subscribed": True,
            "subscription_active": True,
            "subscription_until": "1405-03-01",
            "points": 1280,
            "streak": 7,
            "permissions": [],
        }
    },
    "/api/subscription/wallet": {"balance": 42000, "currency": "IRR"},
    # خانه — شکل واقعی پاسخ /api/dashboard (api/routers/dashboard.py)
    "/api/dashboard": {
        "user": {
            "name": "علی رضایی",
            "display_name": "علی رضایی",
            "nickname": None,
            "group": "پزشکی",
            "intake": "نیم‌سال دوم ۱۴۰۴–۱۴۰۵",
            "role": "student",
        },
        "stats": {
            "percentage": 77,
            "total_answers": 412,
            "correct_answers": 351,
            "downloads": 12,
            "week_activity": 12,
            "level": {"icon": "🥈", "label": "نقره‌ای"},
            "weak_topics": ["فیزیولوژی", "بیوشیمی"],
        },
        "upcoming_exams": [
            {
                "id": "e1",
                "lesson": "میان‌ترم فیزیولوژی",
                "date": "1404-08-12",
                "time": "10:00",
                "days_left": 3,
            }
        ],
        "open_tickets": 1,
    },
    "/api/dashboard/weekly": {
        "weekly": [
            {"date": "2026-10-23", "count": 3},
            {"date": "2026-10-24", "count": 8},
            {"date": "2026-10-25", "count": 5},
            {"date": "2026-10-26", "count": 6},
            {"date": "2026-10-27", "count": 2},
            {"date": "2026-10-28", "count": 9},
            {"date": "2026-10-29", "count": 4},
        ]
    },
    "/api/tickets/unread-count": {"unread": 2},
}


DEFAULT_PAYLOAD = {"ok": True, "items": [], "data": [], "total": 0, "message": ""}


TG_STUB_JS = """
/* onboarding را رد می‌کنیم تا صفحهٔ اصلی دیده شود (نه اسلاید خوش‌آمد) */
try { localStorage.setItem('humsyar_onboarded_v1', '1'); } catch (e) {}
/* استاب تلگرام — جای اسکریپت CDN تلگرام می‌نشیند تا initData
   قابل‌کنترل باشد و تست به شبکه بیرونی وابسته نباشد. */
window.Telegram = { WebApp: {
  initData: 'query_id=AAH&user=%7B%22id%22%3A100200300%2C%22first_name%22%3A%22%D8%B9%D9%84%DB%8C%22%2C%22username%22%3A%22ali%22%7D&auth_date=1700000000&hash=test',
  initDataUnsafe: { user: { id: 100200300, first_name: 'علی', username: 'ali', language_code: 'fa' }, start_param: '' },
  colorScheme: 'dark', themeParams: {}, version: '7.10', platform: 'android',
  ready(){}, expand(){}, setHeaderColor(){}, setBackgroundColor(){},
  enableClosingConfirmation(){}, disableVerticalSwipes(){}, close(){},
  HapticFeedback:{ impactOccurred(){}, notificationOccurred(){} },
  openLink(u){ window.__opened = u; },
  BackButton:{ show(){}, hide(){}, onClick(){}, offClick(){} },
  MainButton:{ show(){}, hide(){}, setText(){}, onClick(){} }
}};
"""


def install_mocks(page, console):
    """تلگرام + API را شبیه‌سازی می‌کند."""

    # اسکریپت CDN تلگرام را با استاب خودمان عوض می‌کنیم (قطعی و آفلاین)
    page.route(
        "**/telegram-web-app.js",
        lambda route: route.fulfill(
            status=200, content_type="text/javascript; charset=utf-8", body=TG_STUB_JS
        ),
    )

    page.add_init_script(
        """
        window.Telegram = { WebApp: {
          initData: 'query_id=AAH&user=%7B%22id%22%3A100200300%2C%22first_name%22%3A%22%D8%B9%D9%84%DB%8C%22%2C%22username%22%3A%22ali%22%7D&auth_date=1700000000&hash=test',
          initDataUnsafe: { user: { id: 100200300, first_name: 'علی', username: 'ali', language_code: 'fa' }, start_param: '' },
          colorScheme: 'dark', themeParams: {}, version: '7.10', platform: 'android',
          ready(){}, expand(){}, setHeaderColor(){}, setBackgroundColor(){},
          enableClosingConfirmation(){}, disableVerticalSwipes(){}, close(){},
          HapticFeedback:{ impactOccurred(){}, notificationOccurred(){} },
          openLink(u){ window.__opened = u; }, BackButton:{ show(){}, hide(){}, onClick(){} },
          MainButton:{ show(){}, hide(){}, setText(){}, onClick(){} }
        }};
        """
    )

    def handle(route):
        url = route.request.url
        path = "/" + url.split("/", 3)[3] if url.count("/") >= 3 else url
        path = path.split("?")[0]
        body = FIXTURES.get(path, DEFAULT_PAYLOAD)
        route.fulfill(
            status=200,
            content_type="application/json; charset=utf-8",
            body=json.dumps(body, ensure_ascii=False),
        )

    page.route("**/api/**", handle)

    page.on("console", lambda m: console.append({"type": m.type, "text": m.text[:400]})
            if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: console.append({"type": "pageerror", "text": str(e)[:400]}))


def shoot(browser, base, out, tag, viewport, report):
    name, w, h, dsf = viewport
    ctx = browser.new_context(
        # سرویس‌ورکر عمداً بلاک است: در تست، پاسخ‌های /api از route های
        # Playwright می‌آیند و SW شبکه‌ی واقعی را صدا می‌زد (مسیر تست را
        # دور می‌زد). در production رفتار SW جدا تست می‌شود (test_pwa_contract).
        service_workers="block",
        viewport={"width": w, "height": h},
        device_scale_factor=dsf,
        is_mobile=w < 700,
        has_touch=w < 700,
        locale="fa-IR",
        timezone_id="Asia/Tehran",
        user_agent=(
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"
        ),
    )
    page = ctx.new_page()
    console = []
    install_mocks(page, console)

    url = base.rstrip("/") + "/#" + tag
    # مسیرها hash نیستند؛ از تاریخچه‌ی مرورگر استفاده می‌کنیم
    url = base.rstrip("/") + tag
    page.goto(url, wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(1200)

    metrics = page.evaluate(
        """() => {
          const de = document.documentElement;
          const cs = getComputedStyle(document.body);
          return {
            title: document.title,
            dir: de.getAttribute('dir') || cs.direction,
            lang: de.getAttribute('lang'),
            scrollW: de.scrollWidth,
            clientW: de.clientWidth,
            scrollH: de.scrollHeight,
            bodyBg: cs.backgroundColor,
            bodyColor: cs.color,
            fontFamily: cs.fontFamily,
            textLen: (document.body.innerText || '').trim().length,
            hasNav: !!document.querySelector('nav'),
            nodes: document.querySelectorAll('*').length,
          };
        }"""
    )
    metrics["horizontal_overflow"] = metrics["scrollW"] > metrics["clientW"] + 1
    metrics["console"] = console[:12]
    metrics["errors"] = [c for c in console if c["type"] in ("error", "pageerror")]

    fname = f"{name}{tag.replace('/', '_') or '_root'}.png"
    page.screenshot(path=str(out / fname))
    report.append({"viewport": name, "route": tag, "shot": fname, **metrics})

    ctx.close()


def contact_sheet(out, report, prefix_md, cols=4):
    try:
        from PIL import Image
    except ImportError:
        return None

    shots = [r for r in report if r["viewport"] == prefix_md]
    imgs = []
    for r in shots:
        p = out / r["shot"]
        if p.exists():
            imgs.append((r["route"], Image.open(p)))
    if not imgs:
        return None
    th_w = 240
    thumbs = []
    for route, im in imgs:
        ratio = th_w / im.width
        thumbs.append((route, im.resize((th_w, int(im.height * ratio)))))
    rows = (len(thumbs) + cols - 1) // cols
    row_h = max(t.height for _, t in thumbs) + 22
    sheet = Image.new("RGB", (cols * (th_w + 12) + 12, rows * row_h + 12), (8, 12, 22))
    from PIL import ImageDraw

    d = ImageDraw.Draw(sheet)
    for i, (route, t) in enumerate(thumbs):
        x = 12 + (i % cols) * (th_w + 12)
        y = 12 + (i // cols) * row_h
        sheet.paste(t, (x, y))
        d.text((x + 2, y + t.height + 4), route[:32], fill=(200, 220, 255))
    path = out / "sheet.png"
    sheet.save(path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8099/app/")
    ap.add_argument("--out", default="/tmp/ui-audit")
    ap.add_argument("--routes", default="", help="فهرست کاما-جدا؛ خالی = همه")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    routes = ROUTES
    if args.routes:
        want = {r.strip() for r in args.routes.split(",")}
        routes = [r for r in ROUTES if r[0] in want]

    report = []
    t0 = time.time()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for tag, _label in routes:
            for vp in VIEWPORTS:
                shoot(browser, args.base, out, tag, vp, report)
        browser.close()

    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")

    sheet = contact_sheet(out, report, "md")

    err_routes = [r for r in report if r.get("errors")]
    of_routes = [r for r in report if r.get("horizontal_overflow")]
    empty_routes = [r for r in report if r.get("textLen", 0) < 20]

    lines = [
        "# ممیزی رابط کاربری مینی‌اپ (Chromium واقعی)",
        "",
        f"- مبدأ: `{args.base}`",
        f"- مسیرها: {len(routes)} · اندازه‌ها: {len(VIEWPORTS)} · اسکرین‌شات: {len(report)}",
        f"- زمان اجرا: {time.time() - t0:.1f} ثانیه",
        "",
        "| مسیر | اندازه | متن | خطای JS | سرریز افقی | ارتفاع |",
        "|---|---|---|---|---|---|",
    ]
    for r in report:
        lines.append(
            f"| `{r['route']}` | {r['viewport']} | {r['textLen']} | "
            f"{len(r['errors'])} | {'⚠️' if r['horizontal_overflow'] else '—'} | {r['scrollH']} |"
        )
    lines += ["", "## خلاصه", ""]
    lines.append(f"- مسیرهای با خطای JS: {len({r['route'] for r in err_routes})}")
    lines.append(f"- مسیرهای با سرریز افقی: {len({r['route'] for r in of_routes})}")
    lines.append(f"- مسیرهای (تقریباً) خالی: {len({r['route'] for r in empty_routes})}")
    if sheet:
        lines.append(f"- کانتکت‌شیت: `{sheet}`")
    (out / "report.md").write_text("\n".join(lines) + "\n", "utf-8")

    print("\n".join(lines[-8:]))
    print(f"\nخروجی: {out}")


if __name__ == "__main__":
    main()
