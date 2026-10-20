#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ماتریس واکنش‌گرایی — اسکرین‌شات + بازرسی خودکار.

اجرا:  npm run dev  →  python3 tests/viewport_matrix.py
اندازه‌ها همان‌هایی هستند که در پذیرش خواسته شده‌اند.
خروجی: tests/shots/vp-<w>x<h>-<route>.png  و گزارش کنسولی.
"""
import os

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5178"
SH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(SH, exist_ok=True)

SIZES = [
    (360, 800, "phone-360"),
    (375, 812, "phone-375"),
    (393, 852, "phone-393"),
    (430, 932, "phone-430"),
    (768, 1024, "tablet-768"),
    (800, 1280, "tablet-800"),
    (1024, 768, "tablet-land-1024"),
    (1280, 800, "laptop-1280"),
    (1440, 900, "desktop-1440"),
    (1920, 1080, "desktop-1920"),
]
ROUTES = [
    ("/", "home"),
    ("/library", "library"),
    ("/library/R1", "resource"),
    ("/exam", "qbank"),
    ("/exam/practice", "practice"),
    ("/exam/run", "examrun"),
    ("/exam/result", "result"),
    ("/plan", "plan"),
    ("/notes/N1", "notes"),
    ("/ai", "ai"),
    ("/me", "progress"),
    ("/me/subscription", "sub"),
    ("/me/settings", "settings"),
]

AUDIT = """() => {
  const m = document.getElementById('main');
  const over = [];
  // عنصری که داخل یک ناحیهٔ اسکرول افقیِ عمدی است، «بریدگی» نیست
  const inScroller = (el) => {
    for (let n = el.parentElement; n; n = n.parentElement) {
      const ox = getComputedStyle(n).overflowX;
      if (ox === 'auto' || ox === 'scroll') return true;
    }
    return false;
  };
  document.querySelectorAll('#main *').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && (r.left < -2 || r.right > innerWidth + 2) && !inScroller(el)) {
      over.push((el.className || el.tagName).toString().slice(0, 40));
    }
  });
  const tiny = [...document.querySelectorAll('#main button, #main a')].filter((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.height < 28;
  }).length;
  const cs = getComputedStyle(document.querySelector('.sidebar') || document.body);
  const tabs = document.querySelector('.tabbar');
  // شاخص‌های کیفیت چیدمان (نه فقط سرریز)
  const cards = document.querySelectorAll('#main .panel, #main .qcard, #main .ncard, #main .continue').length;
  const borderNesting = document.querySelectorAll('#main .panel .panel').length;
  const firstFold = (() => {
    // چه سهمی از اولین نمای دیداری با محتوای مفید پر شده است
    const vh = m.clientHeight;
    let bottom = 0;
    document.querySelectorAll('#main .page > *, #main .home > *, #main .exam-shell > *').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.top < vh && r.height > 20) bottom = Math.max(bottom, Math.min(r.bottom, vh));
    });
    return Math.round((bottom / vh) * 100);
  })();
  return {
    cards, borderNesting, firstFold,
    screens: +(m.scrollHeight / m.clientHeight).toFixed(1),
    hOverflow: m.scrollWidth - m.clientWidth,
    docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    clipped: [...new Set(over)],
    tinyTargets: tiny,
    nav: tabs && getComputedStyle(tabs).display === 'grid' ? 'tabbar' : cs.display === 'none' ? 'none' : 'sidebar',
    firstPaint: Math.round(document.querySelector('#main .page, #main .notes, #main .ai-shell')?.getBoundingClientRect().top ?? -1),
  };
}"""

fails = 0
with sync_playwright() as p:
    b = p.chromium.launch()
    for w, h, name in SIZES:
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1.25)
        pg = ctx.new_page()
        for route, tag in ROUTES:
            pg.goto(BASE + "/#" + route, wait_until="networkidle")
            pg.wait_for_timeout(420)
            d = pg.evaluate(AUDIT)
            bad = d["hOverflow"] > 0 or d["docOverflow"] > 0 or d["clipped"]
            fails += 1 if bad else 0
            print(
                ("!! " if bad else "OK ") + f"{name:16} {tag:8} "
                f"hOver={d['hOverflow']} docOver={d['docOverflow']} "
                f"nav={d['nav']:8} screens={d['screens']:>4} cards={d['cards']:>2} "
                f"panelInPanel={d['borderNesting']} firstFold={d['firstFold']}% tiny={d['tinyTargets']} "
                f"{'clipped=' + str(d['clipped'][:2]) if d['clipped'] else ''}"
            )
            if tag == "home":
                pg.screenshot(path=os.path.join(SH, f"vp-{w}x{h}-{tag}.png"))
            if (w, tag) in ((1024, "library"), (768, "notes"), (1440, "ai")):
                pg.screenshot(path=os.path.join(SH, f"vp-{w}x{h}-{tag}.png"))
        ctx.close()
    b.close()

print(f"\nقاب‌های مشکل‌دار: {fails} — بقیه بدون سرریز و بدون بریدگی")
