# -*- coding: utf-8 -*-
"""🏠 تست E2E واقعی لندینگ (صفحهٔ ریشهٔ دامنه) در مرورگر واقعی.

چه چیزی را ثابت می‌کند؟
───────────────────────
• RTL و زبان فارسی، ساختار سرفصل درست (h1 یکتا)
• صفر اسکرول افقی در ۳۹۰ / ۷۶۸ / ۱۰۲۴ / ۱۴۴۰
• فونت خودمیزبان Vazirmatn واقعاً لود می‌شود (نه فونت سیستم)
• هدف لمسی دکمه‌ها و لینک‌های ناوبری ≥ ۴۴px
• skip-link با Tab واقعاً دیده می‌شود
• `prefers-reduced-motion` محترم است
• کنتراست متن/پس‌زمینه (پروب سادهٔ WCAG)
• تمام لینک‌ها به مسیرهای واقعیِ همین پروژه اشاره می‌کنند
• هیچ استثنای JS

اجرا:
    python3 -m http.server 8121 --directory miniapp/dist-landing &
    python3 tests/e2e/landing_e2e.py --base http://127.0.0.1:8121 --out /home/user/design-audit/landing

خروجی: ۰ = سبز، ۱ = شکست.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

FAILS: list[str] = []

ALLOWED_HREF = {
    "/", "/pwa/", "/app/", "/admin/", "/api/health", "#main",
    "#features", "#how", "#platforms", "#faq",
}

CONTRAST_JS = r"""
() => {
  const parse = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const over = (f, b) => ({
    r: f.r * f.a + b.r * (1 - f.a),
    g: f.g * f.a + b.g * (1 - f.a),
    b: f.b * f.a + b.b * (1 - f.a), a: 1,
  });
  const lum = (c) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const effBg = (el) => {
    const stack = [];
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) { stack.push(c); if (c.a >= 0.999) break; }
    }
    let base = { r: 6, g: 11, b: 22, a: 1 };  /* پس‌زمینهٔ صفحه */
    for (let i = stack.length - 1; i >= 0; i--) base = over(stack[i], base);
    return base;
  };
  const out = [];
  /* فقط گره‌های متنیِ داخل محتوا؛ پس‌زمینهٔ گرادیانی صفحه ساده‌سازی شده */
  document.querySelectorAll('main p, main li, main h1, main h2, main h3, main summary, .lp-btn, .lp-pill, .lp-soon__badge, .lp-footer__links a, .lp-nav a, .lp-proof__item span, .lp-proof__item b')
    .forEach((el) => {
      const txt = (el.textContent || '').trim();
      if (!txt) return;
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      const st = getComputedStyle(el);
      if (st.visibility === 'hidden' || st.display === 'none') return;
      if (st.backgroundClip === 'text' || st.webkitBackgroundClip === 'text') return; /* متن گرادیانی */
      const fg0 = parse(st.color);
      if (!fg0) return;
      const bg = effBg(el);
      const fg = fg0.a < 1 ? over(fg0, bg) : fg0;
      const l1 = lum(fg), l2 = lum(bg);
      const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
      const size = parseFloat(st.fontSize);
      const weight = parseInt(st.fontWeight, 10) || 400;
      const large = size >= 24 || (size >= 18.66 && weight >= 700);
      const need = large ? 3 : 4.5;
      if (ratio < need) {
        out.push({ text: txt.slice(0, 26), cls: (el.className || '').toString().slice(0, 40),
                   ratio: Math.round(ratio * 100) / 100, need, size, weight });
      }
    });
  return out;
}
"""


def check(cond: bool, label: str, detail: str = "") -> bool:
    print(("  ✅ " if cond else "  ❌ ") + label + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(label + (f" — {detail}" if detail else ""))
    return cond


def run(base: str, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        for label, w, h, dpr, mobile in (
            ("390", 390, 844, 2, True),
            ("768", 768, 1024, 1, False),
            ("1024", 1024, 768, 1, False),
            ("1440", 1440, 900, 1, False),
        ):
            print(f"\n[{label}px] چیدمان، RTL، کنتراست")
            ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr,
                                      locale="fa-IR", is_mobile=mobile, has_touch=mobile)
            page = ctx.new_page()
            errs: list[str] = []
            page.on("pageerror", lambda e: errs.append(str(e)[:160]))
            page.goto(base + "/", wait_until="load", timeout=45000)
            page.wait_for_timeout(600)

            info = page.evaluate(
                """() => {
                  const de = document.documentElement;
                  const h1 = document.querySelectorAll('h1');
                  const links = [...document.querySelectorAll('a')].map(a => a.getAttribute('href'));
                  const small = [...document.querySelectorAll('.lp-btn, .lp-nav a, .lp-footer__links a, .lp-faq__item summary')]
                      .map(e => Math.round(e.getBoundingClientRect().height))
                      .filter(v => v > 0 && v < 44);
                  return {
                    dir: de.getAttribute('dir'), lang: de.getAttribute('lang'),
                    sw: de.scrollWidth, cw: de.clientWidth,
                    h1: h1.length, h1Text: h1[0] ? h1[0].textContent.trim() : '',
                    fontLoaded: document.fonts.check('16px Vazirmatn'),
                    fontFamily: getComputedStyle(document.body).fontFamily,
                    links, smallTargets: small,
                    title: document.title,
                    metaDesc: (document.querySelector('meta[name=description]') || {}).content || '',
                    imgsNoAlt: [...document.images].filter(i => !i.hasAttribute('alt')).length,
                  };
                }"""
            )

            check(info["dir"] == "rtl", f"{label}: dir=rtl", str(info["dir"]))
            check(info["lang"] == "fa", f"{label}: lang=fa", str(info["lang"]))
            check(info["h1"] == 1, f"{label}: دقیقاً یک h1", str(info["h1"]))
            check(info["sw"] <= info["cw"], f"{label}: بدون اسکرول افقی",
                  f"{info['sw']} > {info['cw']}")
            check(info["fontLoaded"], f"{label}: فونت Vazirmatn لود شد", info["fontFamily"])
            check(not info["smallTargets"], f"{label}: هدف‌های لمسی ≥44px",
                  str(info["smallTargets"][:6]))
            check(info["imgsNoAlt"] == 0, f"{label}: همهٔ تصاویر alt دارند")
            check(bool(info["metaDesc"]), f"{label}: meta description موجود است")

            bad = [h for h in info["links"] if h not in ALLOWED_HREF and not h.startswith("http")]
            check(not bad, f"{label}: همهٔ لینک‌ها به مسیر واقعی", str(bad[:4]))

            fails = page.evaluate(CONTRAST_JS)
            check(not fails, f"{label}: کنتراست متن کافی است", str(fails[:3]))

            page.screenshot(path=str(out / f"landing-{label}.png"), full_page=True)
            check(not errs, f"{label}: بدون استثنای JS", "; ".join(errs[:2]))
            ctx.close()

        # ── skip-link با Tab واقعی ──
        print("\n[صفحه‌کلید]")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="fa-IR")
        page = ctx.new_page()
        page.goto(base + "/", wait_until="load")
        # منتظر mount شدن React بمان؛ وگرنه فوکوس روی <body>/noscript می‌افتد
        page.wait_for_selector(".lp-skip", state="attached", timeout=15000)
        page.wait_for_timeout(200)
        page.keyboard.press("Tab")
        first = page.evaluate(
            """() => { const a = document.activeElement;
                 const r = a.getBoundingClientRect();
                 return {cls: a.className, text: a.textContent.trim(),
                         visible: r.top >= 0 && r.height > 10,
                         outline: getComputedStyle(a).outlineStyle}; }"""
        )
        check("lp-skip" in str(first["cls"]), "اولین Tab روی «پرش به محتوا» است", str(first))
        check(first["visible"], "skip-link در فوکوس دیده می‌شود", str(first))
        check(first["outline"] != "none", "حلقهٔ فوکوس رسم دارد", str(first))
        page.screenshot(path=str(out / "landing-focus.png"),
                        clip={"x": 0, "y": 0, "width": 1440, "height": 90})
        ctx.close()

        # ── reduced motion ──
        print("\n[prefers-reduced-motion]")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  reduced_motion="reduce", locale="fa-IR")
        page = ctx.new_page()
        page.goto(base + "/", wait_until="load")
        dur = page.evaluate(
            """() => { const d = getComputedStyle(document.querySelector('.lp-btn')).transitionDuration;
                 const first = String(d).split(',')[0].trim();
                 const sec = first.endsWith('ms') ? parseFloat(first) / 1000 : parseFloat(first);
                 return {raw: d, sec}; }"""
        )
        check(dur["sec"] < 0.01, "با reduce، ترنزیشن خنثی می‌شود", str(dur))
        ctx.close()

        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8121")
    ap.add_argument("--out", default="/home/user/design-audit/landing")
    args = ap.parse_args()
    run(args.base.rstrip("/"), Path(args.out))
    print("\n" + "=" * 62)
    if FAILS:
        print(f"❌ {len(FAILS)} مورد ناموفق:")
        for f in FAILS:
            print("   -", f)
        return 1
    print("✅ همهٔ بررسی‌های لندینگ سبز است.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
