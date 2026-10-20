#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""بازرسی کنتراست واقعی در مرورگر.

برای هر گرهٔ متنیِ قابل مشاهده، رنگ متن و رنگ پس‌زمینهٔ مؤثر (با ترکیب
شفافیت روی والدها) محاسبه و نسبت کنتراست WCAG گزارش می‌شود.
آستانه: 4.5:1 برای متن عادی، 3:1 برای متن بزرگ (>=18.66px bold یا >=24px).

اجرا:  python3 tests/contrast_audit.py [--theme light|dark] [--width 1440]
"""
import argparse
import json

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5178"
ROUTES = [
    ("/", "خانه"),
    ("/library", "منابع"),
    ("/library/R1", "جزئیات منبع"),
    ("/exam", "بانک سؤال"),
    ("/exam/practice", "تمرین"),
    ("/ai", "هوشیار"),
    ("/notes", "یادداشت‌ها"),
    ("/notes/N1", "یادداشت"),
    ("/capability", "ماتریس"),
    ("/plan", "برنامه"),
    ("/me", "پیشرفت"),
    ("/me/subscription", "اشتراک"),
    ("/settings", "تنظیمات"),
    ("/system", "سیستم طراحی"),
]

JS = r"""
() => {
  const parse = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const over = (fg, bg) => ({
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  });
  const lum = (c) => {
    const f = (v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  // رنگ‌های یک gradient را از background-image بیرون می‌کشد
  const gradStops = (img) => {
    const out = [];
    const re = /rgba?\(([^)]+)\)/g;
    let m;
    while ((m = re.exec(img))) {
      const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
      out.push({ r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 });
    }
    return out;
  };
  const nearestGradient = (el) => {
    let n = el;
    while (n && n.nodeType === 1) {
      const bg = getComputedStyle(n).backgroundImage;
      if (bg && bg !== "none" && bg.includes("gradient")) return bg;
      n = n.parentElement;
    }
    return null;
  };
  const effBg = (el) => {
    let stack = [];
    let n = el;
    while (n && n.nodeType === 1) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) {
        stack.push(c);
        if (c.a >= 0.999) break;
      }
      n = n.parentElement;
    }
    let base = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = stack.length - 1; i >= 0; i--) base = over(stack[i], base);
    return base;
  };
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode()) {
    const t = walker.currentNode;
    const txt = t.textContent.trim();
    if (!txt) continue;
    const el = t.parentElement;
    if (!el || seen.has(el)) continue;
    seen.add(el);
    const st = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (st.visibility === "hidden" || st.display === "none") continue;
    if (parseFloat(st.opacity) < 0.15) continue;
    if (el.closest(".review-dock")) continue;
    const fg0 = parse(st.color);
    if (!fg0) continue;
    // نزدیک‌ترین پس‌زمینهٔ مات و نزدیک‌ترین gradient را مقایسه کن
    let solidDepth = -1, gradDepth = -1, d = 0;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement, d++) {
      const cs = getComputedStyle(n);
      if (solidDepth < 0) {
        const c = parse(cs.backgroundColor);
        if (c && c.a >= 0.999) solidDepth = d;
      }
      if (gradDepth < 0 && cs.backgroundImage.includes("gradient")) gradDepth = d;
    }
    const grad = gradDepth >= 0 && (solidDepth < 0 || gradDepth < solidDepth)
      ? nearestGradient(el) : null;
    if (grad) {
      // روی gradient: بدترین ایست را مبنا بگیر
      const stops = gradStops(grad);
      const gradEl = (() => {
        let n = el;
        while (n && n.nodeType === 1) {
          if (getComputedStyle(n).backgroundImage.includes('gradient')) return n;
          n = n.parentElement;
        }
        return el;
      })();
      const gradBase = effBg(gradEl.parentElement || document.body);
      let worst = null;
      for (const stop of stops) {
        // ایست‌های نیمه‌شفاف روی پس‌زمینهٔ واقعی ترکیب می‌شوند، نه روی سفید
        const solid = stop.a < 1 ? over(stop, gradBase) : stop;
        const f = fg0.a < 1 ? over(fg0, solid) : fg0;
        const l1 = lum(f), l2 = lum(solid);
        const r = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        if (!worst || r < worst.ratio) worst = { ratio: r, bg: solid };
      }
      const size0 = parseFloat(st.fontSize);
      const w0 = parseInt(st.fontWeight, 10) || 400;
      const large0 = size0 >= 24 || (size0 >= 18.66 && w0 >= 700);
      const need0 = large0 ? 3 : 4.5;
      if (worst && worst.ratio < need0) {
        out.push({
          text: txt.slice(0, 34),
          cls: (el.className || "").toString().slice(0, 60),
          fg: `rgb(${Math.round(fg0.r)},${Math.round(fg0.g)},${Math.round(fg0.b)})`,
          bg: `gradient→rgb(${Math.round(worst.bg.r)},${Math.round(worst.bg.g)},${Math.round(worst.bg.b)})`,
          ratio: Math.round(worst.ratio * 100) / 100,
          need: need0, size: size0, weight: w0,
        });
      }
      continue;
    }
    const bg = effBg(el);
    const fg = fg0.a < 1 ? over(fg0, bg) : fg0;
    const l1 = lum(fg), l2 = lum(bg);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const size = parseFloat(st.fontSize);
    const weight = parseInt(st.fontWeight, 10) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = large ? 3 : 4.5;
    if (ratio < need) {
      out.push({
        text: txt.slice(0, 34),
        cls: (el.className || "").toString().slice(0, 60),
        fg: `rgb(${Math.round(fg.r)},${Math.round(fg.g)},${Math.round(fg.b)})`,
        bg: `rgb(${Math.round(bg.r)},${Math.round(bg.g)},${Math.round(bg.b)})`,
        ratio: Math.round(ratio * 100) / 100,
        need,
        size,
        weight,
      });
    }
  }
  return out;
}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default="light")
    ap.add_argument("--width", type=int, default=1440)
    args = ap.parse_args()

    total = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context(viewport={"width": args.width, "height": 900}).new_page()
        pg.goto(BASE + "/", wait_until="networkidle")
        for route, name in ROUTES:
            pg.goto(BASE + "/#" + route, wait_until="networkidle")
            pg.wait_for_timeout(400)
            # تم را با همان کنش واقعی رابط تنظیم می‌کنیم (React در هر بارگذاری آن را بازنشانی می‌کند)
            if pg.evaluate("document.documentElement.dataset.theme") != args.theme:
                pg.locator("button[aria-label='تم روشن'], button[aria-label='تم تیره']").first.click()
                pg.wait_for_timeout(350)
            fails = pg.evaluate(JS)
            for f in fails:
                f["route"] = name
            total.extend(fails)
            print(f"— {name}: {len(fails)} مورد")
        b.close()

    print("\n" + "=" * 72)
    seen = set()
    for f in sorted(total, key=lambda x: x["ratio"]):
        key = (f["cls"], f["fg"], f["bg"])
        if key in seen:
            continue
        seen.add(key)
        print(
            f'{f["ratio"]:>5}:1  (نیاز {f["need"]})  {f["route"]:>12} | '
            f'{f["fg"]} روی {f["bg"]} | {f["size"]:.0f}px w{f["weight"]} | '
            f'.{f["cls"]} | «{f["text"]}»'
        )
    print("=" * 72)
    print(f"مجموع: {len(total)} گره، {len(seen)} الگوی یکتا")


if __name__ == "__main__":
    main()
