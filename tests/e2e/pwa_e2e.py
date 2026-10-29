# -*- coding: utf-8 -*-
"""📲 تست E2E واقعی نسخهٔ نصب‌شدنی (PWA) در مرورگر واقعی.

چه چیزی را ثابت می‌کند؟
───────────────────────
۱) `/pwa/` بالا می‌آید و **صفحهٔ ورود وب** نشان داده می‌شود (نه پیام
   «از داخل تلگرام باز کنید») — یعنی مسیر نصب‌شدنی مستقل کار می‌کند.
۲) جریان ورود: شناسه → کد → ورود → اپ بالا می‌آید؛ کد غلط خطا می‌دهد
   و اپ را باز نمی‌کند.
۳) نشست بعد از reload می‌ماند (کوکی)، و «خروج» نشست را می‌بندد.
۴) manifest قابل‌خواندن، آیکون‌ها ۲۰۰، service worker ثبت‌شده.
۵) با قطع شبکه، reload صفحهٔ آفلاین/کش را می‌دهد (نه صفحهٔ سفید).
۶) سه اندازهٔ واقعی: iPhone (390×844)، Android (360×800)، Windows
   (1440×900) — بدون سرریز افقی و بدون خطای JS.

اجرا (سرور استاتیک روی dist-pwa لازم است):
    python3 tests/e2e/serve_dist.py --dir miniapp/dist-pwa --prefix /pwa --port 8104 &
    python3 tests/e2e/pwa_e2e.py --base http://127.0.0.1:8104 --out /home/user/design-audit/pwa

خروجی: ۰ = همه سبز، ۱ = شکست.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

STATE = {"authenticated": False, "requested": 0, "verified": 0, "code": "123456",
         "logged_out": 0}
FAILS: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> bool:
    print(("  ✅ " if cond else "  ❌ ") + label + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(label + (f" — {detail}" if detail else ""))
    return cond


USER = {"uid": 100200300, "display_name": "علی رضایی", "role": "student",
        "group": "1", "intake": "۱۴۰۴-۲", "permissions": []}
FIX = {"user": USER, "items": [], "weekly": [], "leaderboard": [], "unread": 2,
       "stats": {"percentage": 77, "total_answers": 412, "correct_answers": 351,
                 "level": {"icon": "🥈", "label": "نقره‌ای"}, "weak_topics": []},
       "upcoming_exams": [], "schedule": [], "ok": True,
       "weekly_activity": [3, 8, 5, 6, 2, 9, 4], "selected_count": 6,
       "term": "1405-1", "group": "1", "computed_group": "1",
       "registered_group": "1", "has_custom_selection": True, "conflicts": [],
       "mismatched_selections": [], "needs_educational_group_confirmation": False}


def api_handler(route):
    """مرورگر ← همان قرارداد واقعی API؛ فقط منبع داده فیکسچر است."""
    path = "/" + route.request.url.split("//", 1)[1].split("/", 1)[1]
    path = path.split("?")[0]

    if path == "/api/web-auth/session":
        return route.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"authenticated": STATE["authenticated"]}))
    if path == "/api/web-auth/request":
        STATE["requested"] += 1
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"ok": True, "message": "اگر این حساب تأیید شده باشد، کد در تلگرام می‌آید."},
            ensure_ascii=False))
    if path == "/api/web-auth/verify":
        body = json.loads(route.request.post_data or "{}")
        STATE["verified"] += 1
        if str(body.get("code")) == STATE["code"]:
            STATE["authenticated"] = True
            return route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"ok": True, "user": {"uid": 100200300, "name": "علی رضایی",
                                                      "expires_in_days": 30}}, ensure_ascii=False),
                headers={"Set-Cookie": "hu_session=e2e-token; Path=/; HttpOnly; SameSite=Lax"})
        return route.fulfill(status=401, content_type="application/json", body=json.dumps(
            {"detail": "کد نامعتبر یا منقضی است."}, ensure_ascii=False))
    if path == "/api/web-auth/logout":
        STATE["authenticated"] = False
        STATE["logged_out"] += 1
        return route.fulfill(status=200, content_type="application/json", body='{"ok": true}',
                             headers={"Set-Cookie": "hu_session=; Path=/; Max-Age=0"})
    if not STATE["authenticated"]:
        return route.fulfill(status=401, content_type="application/json",
                             body='{"detail": "missing_init_data"}')
    return route.fulfill(status=200, content_type="application/json",
                         body=json.dumps(FIX, ensure_ascii=False))


def skip_onboarding(page):
    for label in ("رد کردن", "بعدی", "شروع"):
        try:
            btn = page.get_by_text(label, exact=True)
            if btn.count():
                btn.first.click()
                page.wait_for_timeout(900)
        except Exception:
            pass


def overflow(page) -> int:
    return page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")


def run(base: str, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # ── بخش ۱–۴: جریان ورود روی موبایل ──
        print("\n[1] ورود با کد — iPhone 390×844")
        STATE.update(authenticated=False, requested=0, verified=0, logged_out=0)
        ctx = browser.new_context(service_workers="allow",
                                  viewport={"width": 390, "height": 844},
                                  device_scale_factor=2, is_mobile=True, has_touch=True,
                                  locale="fa-IR",
                                  user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
                                              "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 "
                                              "Mobile/15E148 Safari/604.1"))
        page = ctx.new_page()
        # خطای JS (استثنا در کد) با «نویز شبکه» فرق دارد: ۴۰۱ نخستین
        # بررسی نشست و ERR_INTERNET_DISCONNECTED در حالت آفلاین عمدی‌اند
        # و نباید تست را قرمز کنند — ولی استثنای واقعی باید.
        errors: list[str] = []
        noise: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))
        page.on("console", lambda m: (errors if "Uncaught" in m.text else noise).append(
            "CONSOLE " + m.text[:160]) if m.type == "error" else None)
        page.route("**/api/**", api_handler)

        page.goto(base + "/pwa/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(900)
        check(page.is_visible(".pwa-auth"), "صفحهٔ ورود وب نمایش داده شد")
        check(not page.is_visible(".app-root"), "قبل از ورود، اپ باز نشده")
        page.screenshot(path=str(out / "01-login-iphone.png"))

        page.fill("#pwa-ident", "@ali_rezaei")
        page.click("button[type=submit]")
        page.wait_for_timeout(700)
        check(page.is_visible("#pwa-code"), "مرحلهٔ کد نمایش داده شد")
        check(STATE["requested"] == 1, "درخواست کد فقط یک‌بار رفت", str(STATE["requested"]))
        page.screenshot(path=str(out / "02-code-iphone.png"))

        page.fill("#pwa-code", "000000")
        page.click("button[type=submit]")
        page.wait_for_timeout(700)
        check(page.is_visible(".pwa-auth__error"), "کد غلط → پیام خطا")
        check(not page.is_visible(".app-root"), "کد غلط → اپ باز نشد")

        page.fill("#pwa-code", STATE["code"])
        page.click("button[type=submit]")
        page.wait_for_timeout(2500)
        check(page.is_visible(".app-root"), "کد درست → اپ بالا آمد")
        skip_onboarding(page)
        page.wait_for_timeout(1200)
        check(page.is_visible(".app-root"), "داشبورد بعد از آنبوردینگ پایدار است")
        check(overflow(page) <= 0, "بدون سرریز افقی (داشبورد)", str(overflow(page)))
        page.screenshot(path=str(out / "03-dashboard-iphone.png"))

        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1500)
        check(page.is_visible(".app-root") and not page.is_visible(".pwa-auth"),
              "reload → نشست حفظ شد (کوکی)")

        # کارت نصب + خروج، در صفحهٔ «حساب من»
        page.goto(base + "/pwa/me", wait_until="networkidle")
        page.wait_for_timeout(1200)
        page.evaluate("""() => { const e = new Event('beforeinstallprompt');
            e.prompt = () => {}; e.userChoice = Promise.resolve({outcome: 'dismissed'});
            window.dispatchEvent(e); }""")
        page.wait_for_timeout(800)
        check(page.is_visible(".pwa-install"), "کارت «نصب هامزیار» ظاهر شد")
        page.screenshot(path=str(out / "04-me-install-iphone.png"), full_page=True)

        # ── بخش ۵: نصب‌پذیری ──
        print("\n[2] manifest / آیکون‌ها / service worker")
        info = page.evaluate("""async () => {
          const link = document.querySelector('link[rel=manifest]');
          const href = link ? link.href : null;
          let manifest = null; const icons = [];
          if (href) {
            try { manifest = await (await fetch(href)).json(); } catch (e) {}
            for (const ic of (manifest && manifest.icons) || []) {
              const r = await fetch(new URL(ic.src, href).href);
              icons.push([ic.sizes, r.status, ic.purpose || 'any']);
            }
          }
          const reg = await navigator.serviceWorker.getRegistration();
          return {href, manifest: manifest && {name: manifest.name, display: manifest.display,
                  start: manifest.start_url, scope: manifest.scope, dir: manifest.dir,
                  screenshots: (manifest.screenshots || []).map(s => s.src)},
                  icons, sw: reg ? reg.scope : null, controlled: !!navigator.serviceWorker.controller};
        }""")
        check(bool(info["href"]), "لینک manifest در HTML هست", str(info["href"]))
        check(bool(info["manifest"]), "manifest خوانده شد")
        m = info["manifest"] or {}
        check(m.get("display") == "standalone", "display=standalone", str(m.get("display")))
        check(m.get("dir") == "rtl", "جهت RTL در manifest", str(m.get("dir")))
        check(all(i[1] == 200 for i in info["icons"]) and len(info["icons"]) >= 3,
              "همهٔ آیکون‌های manifest با ۲۰۰", str(info["icons"]))
        check(any(i[2] and "maskable" in i[2] for i in info["icons"]),
              "آیکون maskable وجود دارد (اندروید)", str(info["icons"]))
        check(len(info["manifest"]["screenshots"]) > 0, "اسکرین‌شات برای نصب‌شیت موجود است")
        shot_status = page.evaluate("""async (list) => {
            const out = [];
            for (const s of list) { const r = await fetch(new URL(s, document.baseURI).href);
              out.push([s, r.status]); }
            return out; }""", info["manifest"]["screenshots"])
        check(all(s[1] == 200 for s in shot_status), "فایل اسکرین‌شات‌ها ۲۰۰", str(shot_status))
        check(bool(info["sw"]), "service worker ثبت شده", str(info["sw"]))
        check(overflow(page) <= 0, "بدون سرریز افقی (حساب من)", str(overflow(page)))

        # ── بخش ۶: آفلاین ──
        print("\n[3] آفلاین")
        page.goto(base + "/pwa/schedule", wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(2000)
        check(page.is_visible(".app-root"), "صفحهٔ برنامه قبل از آفلاین لود شد")
        ctx.set_offline(True)
        try:
            page.reload(wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2000)
            body = page.inner_text("body")
            check(len(body.strip()) > 40, "آفلاین: صفحهٔ سفید نیست", body[:60])
            check("برنامه" in body or "آفلاین" in body, "آفلاین: محتوای معنادار نمایش داده شد",
                  body[:80])
        except Exception as exc:
            check(False, "reload آفلاین", str(exc)[:120])
        page.screenshot(path=str(out / "05-offline-iphone.png"))
        ctx.set_offline(False)

        # ── بخش ۷: خروج ──
        print("\n[4] خروج از حساب")
        try:
            page.goto(base + "/pwa/me", wait_until="networkidle")
            page.wait_for_timeout(1000)
            btn = page.get_by_text("خروج از حساب (نسخهٔ وب)", exact=False)
            if btn.count():
                btn.first.click()
                page.wait_for_timeout(2000)
            check(STATE["logged_out"] >= 1, "درخواست خروج به API رسید", str(STATE["logged_out"]))
            check(page.is_visible(".pwa-auth"), "بعد از خروج، صفحهٔ ورود برگشت")
        except Exception as exc:
            check(False, "جریان خروج", str(exc)[:120])

        check(not errors, "هیچ استثنای JS (Uncaught) رخ نداد", "; ".join(errors[:3]))
        print("  ℹ️ نویز شبکهٔ مورد انتظار:", len(noise), "مورد (۴۰۱ بررسی نشست / قطع عمدی شبکه)")
        ctx.close()

        # ── بخش ۸: اندازه‌های دیگر (Android / Windows) ──
        for label, w, h, ua, touch in (
            ("android", 360, 800, "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                                  "(KHTML, like Gecko) Chrome/126 Mobile Safari/537.36", True),
            ("windows", 1440, 900, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                   "(KHTML, like Gecko) Chrome/126 Safari/537.36", False),
        ):
            print(f"\n[5] اندازهٔ {label} — {w}×{h}")
            STATE.update(authenticated=True, requested=0, verified=0)
            c2 = browser.new_context(viewport={"width": w, "height": h}, locale="fa-IR",
                                     user_agent=ua, is_mobile=touch, has_touch=touch,
                                     service_workers="allow")
            p2 = c2.new_page()
            errs2: list[str] = []
            p2.on("pageerror", lambda e: errs2.append(str(e)[:160]))
            p2.route("**/api/**", api_handler)
            p2.goto(base + "/pwa/", wait_until="networkidle", timeout=60000)
            p2.wait_for_timeout(1500)
            skip_onboarding(p2)
            p2.wait_for_timeout(800)
            check(p2.is_visible(".app-root"), f"{label}: اپ باز شد")
            check(overflow(p2) <= 0, f"{label}: بدون سرریز افقی", str(overflow(p2)))
            p2.screenshot(path=str(out / f"06-dashboard-{label}.png"), full_page=False)
            check(not errs2, f"{label}: بدون خطای JS", "; ".join(errs2[:2]))
            c2.close()

        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8104")
    ap.add_argument("--out", default="/home/user/design-audit/pwa")
    args = ap.parse_args()
    run(args.base.rstrip("/"), Path(args.out))
    print("\n" + "=" * 62)
    if FAILS:
        print(f"❌ {len(FAILS)} مورد ناموفق:")
        for f in FAILS:
            print("   -", f)
        return 1
    print("✅ همهٔ بررسی‌های PWA سبز است.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
