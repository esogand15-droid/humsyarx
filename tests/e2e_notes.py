#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمون محیط یادداشت و لایهٔ نصب — Playwright.

اجرا:  npm run dev  →  python3 tests/e2e_notes.py
هر بررسی وضعیت DOM را می‌سنجد، نه موفقیت کلیک را.
"""
import os

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5178"
SH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(SH, exist_ok=True)

ok, errs = [], []


def check(name: str, cond: bool, extra: str = "") -> None:
    (ok if cond else errs).append(f"{name} {extra}".strip())
    print(("✅ " if cond else "❌ ") + name + (f" — {extra}" if extra else ""))


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
    console = []
    pg.on("pageerror", lambda e: console.append(str(e)))

    # ۱) فهرست و جست‌وجو
    pg.goto(BASE + "/#/notes", wait_until="networkidle")
    pg.wait_for_timeout(500)
    total = pg.locator(".ncard").count()
    pg.fill("input[aria-label='جست‌وجو در یادداشت‌ها']", "گلیکولیز")
    pg.wait_for_timeout(350)
    check("جست‌وجوی یادداشت فیلتر می‌کند", pg.locator(".ncard").count() < total, f"{total} → {pg.locator('.ncard').count()}")
    pg.fill("input[aria-label='جست‌وجو در یادداشت‌ها']", "")

    # ۲) برچسب
    before = pg.locator(".ncard").count()
    pg.locator(".notes__tags .chip").first.click()
    pg.wait_for_timeout(300)
    after = pg.locator(".ncard").count()
    check("فیلتر برچسب اعمال شد", 0 < after <= before, f"{before} → {after}")
    pg.locator(".notes__tags .chip").first.click()
    pg.wait_for_timeout(250)

    # ۳) بازکردن یادداشت
    pg.locator(".ncard__main").first.click()
    pg.wait_for_url("**/notes/**", timeout=5000)
    pg.wait_for_timeout(500)
    check("یادداشت باز شد", pg.locator(".editor").count() == 1)
    check("لنگر سند در پنل زمینه هست", "این یادداشت به صفحهٔ" in pg.inner_text(".ctx"))

    # ۴) ویرایش و ذخیرهٔ خودکار
    pg.locator(".editor").click()
    pg.keyboard.press("Control+A")
    pg.keyboard.type("چرخهٔ قلبی — نسخهٔ ویرایش‌شده در آزمون.")
    pg.wait_for_timeout(200)
    saving = "در حال ذخیره" in pg.inner_text(".doc__head")
    pg.wait_for_timeout(1100)
    saved = "ذخیره شد" in pg.inner_text(".doc__head")
    check("ویرایش متن و وضعیت «در حال ذخیره»", saving)
    check("وضعیت «ذخیره شد» برمی‌گردد", saved)

    # ۵) شبیه‌سازی آفلاین
    pg.locator(".doc__head .chip").first.click()
    pg.wait_for_timeout(300)
    pg.locator(".editor").click()
    pg.keyboard.type("!")
    pg.wait_for_timeout(400)
    check("حالت آفلاین در وضعیت ذخیره دیده می‌شود", "آفلاین" in pg.inner_text(".doc__head"))
    pg.locator(".doc__head .chip").first.click()

    # ۶) نمای کنار‌هم سند
    pg.locator("button[aria-label='نمای کنار‌هم با سند']").click()
    pg.wait_for_timeout(500)
    check("پنل سند کنار یادداشت باز شد", pg.locator(".pdfpane").count() == 1)
    pg.fill("input[aria-label='جست‌وجو در متن سند']", "میترال")
    pg.wait_for_timeout(300)
    check("جست‌وجو در متن سند نتیجه می‌دهد", pg.locator(".pdfpane__page p").count() >= 1)
    pg.locator(".pdfpane__page .btn").click()
    pg.wait_for_timeout(300)
    check("پیوند پاراگراف در یادداشت درج شد", "پیوند" in pg.inner_text(".editor"))

    # ۷) شیت نسخه‌ها + Escape
    pg.locator("button[aria-label='نسخه‌ها و بازیابی']").click()
    pg.wait_for_timeout(400)
    check("شیت نسخه‌ها باز شد", pg.locator(".sheet[role='dialog']").count() == 1)
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    check("Escape شیت را می‌بندد", pg.locator(".sheet").count() == 0)

    # ۸) دست‌نویس: یک خط بکش
    canvas = pg.locator(".ink__canvas")
    box = canvas.bounding_box()
    if box:
        pg.mouse.move(box["x"] + 30, box["y"] + 40)
        pg.mouse.down()
        pg.mouse.move(box["x"] + 120, box["y"] + 70, steps=6)
        pg.mouse.up()
        pg.wait_for_timeout(250)
        painted = pg.evaluate(
            "() => { const c = document.querySelector('.ink__canvas');"
            "const x = c.getContext('2d').getImageData(0,0,c.width,c.height).data;"
            "let n = 0; for (let i = 3; i < x.length; i += 4) if (x[i] > 8) n++; return n; }"
        )
        check("دست‌نویس روی بوم کشیده شد", painted > 200, f"{painted} پیکسل جوهر")
    else:
        check("دست‌نویس روی بوم کشیده شد", False, "بوم پیدا نشد")

    # ۹) موبایل: جابه‌جایی فهرست ⇄ سند
    m = b.new_context(viewport={"width": 390, "height": 844}).new_page()
    m.goto(BASE + "/#/notes", wait_until="networkidle")
    m.wait_for_timeout(500)
    check("موبایل: فهرست دیده می‌شود", m.locator(".notes__list").is_visible())
    m.locator(".ncard__main").first.click()
    m.wait_for_timeout(600)
    doc_visible = m.locator(".notes__doc").is_visible()
    toolbar = m.locator(".doc__toolbar").bounding_box()
    tabbar = m.locator(".tabbar").bounding_box()
    check("موبایل: سند جای فهرست می‌آید", doc_visible)
    check(
        "موبایل: نوار ابزار بالای نوار پایین می‌نشیند",
        bool(toolbar and tabbar and abs((toolbar["y"] + toolbar["height"]) - tabbar["y"]) < 2),
        f"toolbar@{(toolbar or {}).get('y')} tabbar@{(tabbar or {}).get('y')}",
    )
    check(
        "موبایل: سرریز افقی ندارد",
        m.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") == 0,
    )

    # ۱۰) لایهٔ نصب
    meta = pg.evaluate(
        """() => ({
      manifest: !!document.querySelector('link[rel=manifest]'),
      apple: document.querySelector('meta[name=apple-mobile-web-app-capable]')?.content,
      touch: !!document.querySelector('link[rel=apple-touch-icon]'),
      standalone: document.documentElement.dataset.standalone,
      swReg: 'serviceWorker' in navigator,
    })"""
    )
    check("manifest و آیکن لمس متصل‌اند", meta["manifest"] and meta["touch"])
    check("متاتگ اجرای مستقل iOS", meta["apple"] == "yes", str(meta["apple"]))
    check("تشخیص حالت نصب‌شده", meta["standalone"] in ("true", "false"), str(meta["standalone"]))

    # ۱۱) ماتریس قابلیت
    pg.goto(BASE + "/#/capability", wait_until="networkidle")
    pg.wait_for_timeout(400)
    pg.locator(".chip", has_text="قابلیت‌ها").first.click()
    pg.wait_for_timeout(300)
    rows = pg.locator(".tbl tbody tr").count()
    pg.locator(".chip", has_text="بومی").first.click()
    pg.wait_for_timeout(300)
    filtered = pg.locator(".tbl tbody tr").count()
    check("ماتریس قابلیت رده‌بندی می‌شود", rows > 20 and 0 < filtered < rows, f"{rows} → {filtered}")
    pg.locator(".chip", has_text="نصب و PWA").first.click()
    pg.wait_for_timeout(300)
    check("تب PWA سه حالت اجرا را تفکیک می‌کند", "Add to Home Screen" in pg.inner_text(".page"))
    pg.locator(".chip", has_text="چیدمان واکنش‌گرا").first.click()
    pg.wait_for_timeout(300)
    check("تب چیدمان، بازرسی و سه حالت را نشان می‌دهد", "ریل آیکنی" in pg.inner_text(".page"))

    check("بدون خطای اجرا", len(console) == 0, f"{len(console)} خطا")
    b.close()

print(f"\nنتیجه: {len(ok)}/{len(ok) + len(errs)}")
if errs:
    print("ناموفق:", *errs, sep="\n  - ")
