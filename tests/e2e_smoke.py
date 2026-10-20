#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""دود-تست پروتوتایپ (۲۵ بررسی) — Playwright.

اجرا:  npm run dev   (پورت ۵۱۷۸)   سپس   python3 tests/e2e_smoke.py
پوشش: ناوبری، جست‌وجو/فیلتر، جزئیات منبع، ورق زدن پیش‌نمایش، تمرین و بازخورد،
آزمون و تایمر، دیالوگ + Escape، هوشیار (حالت فکر کردن/پاسخ/منابع)، تقویم،
سیستم طراحی، تم روشن، پیش‌نمایش عرض، جهت A/B، فوکوس با Tab، نبود خطای کنسول.
"""
import os
from playwright.sync_api import sync_playwright
BASE="http://127.0.0.1:5178"; SH=os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(SH, exist_ok=True)
errs=[]; ok=[]
def chk(l,c,n=""):
    ok.append(bool(c)); print(("✅" if c else "❌"), l, ("— "+str(n)) if n else "")
import traceback
with sync_playwright() as p:
    b=p.chromium.launch()
    pg=b.new_context(viewport={"width":1440,"height":900}, device_scale_factor=1).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type=="error" else None)

    pg.goto(BASE+"/", wait_until="networkidle")
    chk("خانه بارگذاری شد", pg.locator(".continue").count()==1)
    # ناوبری: منابع
    pg.click("text=منابع درسی"); pg.wait_for_timeout(600)
    chk("ناوبری به منابع", "#/library" in pg.url)
    n_all = pg.locator(".rrow").count()
    pg.fill('input[aria-label="جست‌وجو در منابع"]', "قلب"); pg.wait_for_timeout(500)
    n_q = pg.locator(".rrow").count()
    chk("جست‌وجو فیلتر می‌کند", n_q < n_all and n_q>0, f"{n_all} → {n_q}")
    pg.click("text=پاک‌کردن فیلترها"); pg.wait_for_timeout(300)
    pg.click("text=جزوه (PDF)"); pg.wait_for_timeout(400)
    chk("فیلتر نوع فایل", pg.locator(".rrow").count() < n_all, f'{pg.locator(".rrow").count()} نتیجه')
    # جزئیات منبع
    pg.goto(BASE+"/#/library/R1", wait_until="networkidle"); pg.wait_for_timeout(500)
    chk("صفحهٔ جزئیات منبع", "جزوهٔ فیزیولوژی قلب" in pg.inner_text(".page"))
    pg.click(".preview__bar button[aria-label='صفحهٔ بعد']"); pg.wait_for_timeout(300)
    chk("ورق زدن پیش‌نمایش", "۱۹ / ۴۲" in pg.inner_text(".preview__bar").replace("۴۲ / ۱۹","۱۹ / ۴۲") or pg.locator(".preview__bar").inner_text().count("۱۹")>0)
    # منبع قفل
    pg.goto(BASE+"/#/library/R8", wait_until="networkidle"); pg.wait_for_timeout(400)
    j=pg.inner_text(".page")
    chk("منبع قفل علامت‌گذاری شده", "قفل" in j and "پیش‌نمایش قفل است" in j)

    # تمرین: پاسخ و بازخورد
    pg.goto(BASE+"/#/exam/practice", wait_until="networkidle"); pg.wait_for_timeout(500)
    pg.click(".qopt >> nth=0"); pg.click("text=ثبت پاسخ"); pg.wait_for_timeout(500)
    t=pg.inner_text(".page")
    chk("بازخورد بعد از پاسخ", "درست بود" in t and "پاسخ درست" not in t.split("درست بود")[0][-40:])
    chk("توضیح نمایش داده شد", ".explain" and pg.locator(".explain").count()==1)
    pg.click("text=سؤال بعدی"); pg.wait_for_timeout(500)
    chk("سؤال بعدی می‌آید", "سؤال" in pg.inner_text(".qmeta"))
    # آزمون زمان‌دار: شروع و تایمر
    pg.goto(BASE+"/#/exam/run", wait_until="networkidle"); pg.wait_for_timeout(400)
    pg.click("text=شروع آزمون"); pg.wait_for_timeout(600)
    tv=pg.inner_text(".timer")
    chk("تایمر با رقم فارسی", any(d in tv for d in "۰۱۲۳۴۵۶۷۸۹"), tv)
    chk("هیچ کلیدی در آزمون نیست", "پاسخ درست:" not in pg.inner_text(".qcard") and "توضیح" not in pg.inner_text(".qcard"))
    pg.click("text=خروج"); pg.wait_for_timeout(300)
    chk("دیالوگ خروج باز شد", pg.locator("[role=dialog]").count()==1)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    chk("Escape دیالوگ را می‌بندد", pg.locator("[role=dialog]").count()==0)

    # هوشیار: پیام و پاسخ
    pg.goto(BASE+"/#/ai", wait_until="networkidle"); pg.wait_for_timeout(500)
    pg.fill("textarea[aria-label='متن پیام به هوشیار']", "برون‌ده قلبی را ساده بگو")
    pg.get_by_role("button", name="ارسال").click(); pg.wait_for_timeout(1200)
    chk("حالت فکر کردن", pg.locator(".typing").count()==1 or pg.locator(".msg").count()>=3)
    pg.wait_for_timeout(2000)
    chk("پاسخ هوشیار با منابع اضافه شد", pg.locator(".msg").count()>=4 and pg.locator(".msg__src").count()>=1, f'{pg.locator(".msg").count()} پیام')

    # برنامه: تسک
    pg.goto(BASE+"/#/plan", wait_until="networkidle"); pg.wait_for_timeout(500)
    chk("تقویم هفته ۷ ستون", pg.locator(".week__d").count()==7)
    # سیستم طراحی
    pg.goto(BASE+"/#/system", wait_until="networkidle"); pg.wait_for_timeout(500)
    chk("سیستم طراحی: سواچ‌ها", pg.locator(".swatch").count()>=12, f'{pg.locator(".swatch").count()} رنگ')
    chk("سیستم طراحی: نمونه‌های تایپ", pg.locator(".type-row").count()>=8)
    # تم روشن
    pg.click("button[aria-label='تم روشن']"); pg.wait_for_timeout(500)
    chk("تم روشن اعمال شد", pg.evaluate("document.documentElement.dataset.theme")=="light")
    pg.screenshot(path=f"{SH}/1440-system-light.png")
    pg.click("button[aria-label='تم تیره']"); pg.wait_for_timeout(300)
    # ابزار بازبینی: عرض موبایل
    pg.locator("button[aria-label='ابزار بازبینی طراحی']").click(force=True)
    pg.wait_for_selector(".review-dock .seg", timeout=5000)
    pg.locator(".review-dock .seg button").nth(2).click()
    pg.wait_for_timeout(600)
    chk("پیش‌نمایش ۳۹۰ در دسکتاپ", pg.evaluate("document.documentElement.dataset.preview")=="mobile")
    pg.screenshot(path=f"{SH}/1440-preview390.png")
    # جهت A (آکادمیک آرام)
    pg.locator(".review-dock .seg button").nth(4).click()  # جهت A
    pg.wait_for_timeout(500)
    chk("جهت A فعال شد", pg.evaluate("document.documentElement.dataset.vdir")=="quiet")
    pg.goto(BASE+"/#/", wait_until="networkidle"); pg.wait_for_timeout(700)
    pg.screenshot(path=f"{SH}/1440-dirA.png")
    pg.goto(BASE+"/#/handoff", wait_until="networkidle"); pg.wait_for_timeout(600)
    pg.locator("button[aria-label='ابزار بازبینی طراحی']").click(force=True)
    pg.wait_for_selector(".review-dock .seg", timeout=5000)
    # بازگشت به B و دسکتاپ
    pg.locator(".review-dock .seg button").nth(3).click()  # بازگشت به B
    pg.locator(".review-dock .seg button").nth(0).click()
    pg.wait_for_timeout(600)
    chk("بازگشت به B/دسکتاپ", pg.evaluate("document.documentElement.dataset.vdir")=="intelligent"
        and pg.evaluate("document.documentElement.dataset.preview")=="desktop")
    # دسترس‌پذیری: کیبورد روی نخستین لینک
    pg.keyboard.press("Tab"); pg.wait_for_timeout(200)
    focused = pg.evaluate("document.activeElement?.tagName")
    chk("فوکوس با Tab کار می‌کند", focused in ("A","BUTTON"), focused)
    b.close()
chk("بدون خطای کنسول", len(errs)==0, errs[:2])
print(f"\nنتیجه: {sum(ok)}/{len(ok)}")
