# -*- coding: utf-8 -*-
"""🎨 موج v3 — گاردِ «یکپارچگی طراحی و یکی‌سازی رابط‌ها»

پیشینه
──────
مخزن یک دوره **سه** رابط دانشجو داشت: کرم (`apps/student`)، آبی
(مینی‌اپ روی `/app`) و پنل (`/admin`). نتیجه‌اش دوباره‌کاری، دو
زبان بصری و صفحه‌هایی که فقط در یکی از آن‌ها درست بودند.

تصمیم محصول: نسخهٔ آبی تنها رابط است؛ کرم حذف شد. این تست همان
تصمیم را «قابل‌شکستن» می‌کند تا موج‌های بعدی بی‌خبر آن را برنگردانند
و پالت رنگ هم بی‌صدا از پروتوتایپ جدا نشود.

اگر عمداً چیزی را عوض کردی، همین‌جا هم به‌روزش کن — نه اینکه تست را
skip کنی.
"""
from __future__ import annotations

import os
import pathlib
import re
import unittest

os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017/humsyar_test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("TELEGRAM_TOKEN", "123:TEST")

ROOT = pathlib.Path(__file__).resolve().parent.parent
MINIAPP = ROOT / "miniapp"


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


class CreamClientRetiredTests(unittest.TestCase):
    """کلاینت کرم باید رفته باشد — هم سورس، هم مسیر."""

    def test_source_tree_is_gone(self):
        self.assertFalse(
            (ROOT / "apps" / "student").exists(),
            "پوشهٔ apps/student برگشته است؛ رابط دانشجو باید فقط آبی باشد.",
        )

    def test_api_returns_410_for_every_student_path(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"TestClient در دسترس نیست: {exc}")

        try:
            import api.main as main
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"بارگذاری اپ ممکن نشد: {exc}")

        client = TestClient(main.app)
        for path in ("/student", "/student/", "/student/dashboard", "/student/me/profile"):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(
                    response.status_code,
                    410,
                    f"{path} باید 410 بدهد (بازنشسته)، نه {response.status_code}",
                )
                self.assertIn(
                    "retired",
                    str(response.json().get("detail", "")),
                    "پاسخ 410 باید صریحاً «بازنشسته» را اعلام کند",
                )

    def test_student_auth_api_is_still_alive(self):
        """حذف رابط نباید API احراز هویت `/api/web/*` را بکشد."""
        source = _read("api", "main.py")
        self.assertIn("web_student.router", source)
        self.assertTrue((ROOT / "api" / "routers" / "web_student.py").exists())


class DesignTokenTests(unittest.TestCase):
    """پالت باید با پروتوتایپ آبی هم‌تراز بماند (تک‌منبع رنگ)."""

    @classmethod
    def setUpClass(cls):
        cls.tokens = _read("miniapp", "src", "styles", "tokens.css")

    def test_brand_is_prototype_blue(self):
        self.assertIn("--hym-brand-default:      #3D86FF", self.tokens)
        self.assertIn("#1F6BFF", self.tokens)  # hover
        self.assertIn("#2ADAD7", self.tokens)  # accent (cyan)

    def test_page_surface_is_deep_navy(self):
        self.assertIn("--hym-bg-page:            #060B16", self.tokens)

    def test_v3_block_is_last_word(self):
        """بلوک v3 باید بعد از توکن‌های قدیمی باشد تا برندهٔ آبشار شود."""
        idx_v3 = self.tokens.find("موج v3 — هم‌ترازی پالت")
        idx_old = self.tokens.find("--hym-brand-default")
        self.assertGreater(idx_v3, 0, "بلوک v3 پیدا نشد")
        idx_v3_value = self.tokens.find("--hym-brand-default", idx_v3)
        self.assertGreater(idx_v3_value, idx_old)

    def test_no_stale_indigo_brand_left_unreferenced(self):
        """آبیِ indigo قدیمی (#6366F1) نباید در توکن‌های *استفاده‌شده* بماند.

        پالت primitive عمداً دست‌نخورده است (کسی از --hym-brand-500
        استفاده نمی‌کند)، ولی توکن معنایی باید آبی پروتوتایپ باشد.
        """
        semantic = re.search(
            r"--hym-brand-default:\s*(#[0-9A-Fa-f]{6})", self.tokens
        )
        self.assertIsNotNone(semantic)
        self.assertNotEqual(semantic.group(1).upper(), "#6366F1")


class IconSystemTests(unittest.TestCase):
    """زبان آیکون: SVG خطی، نه ایموجی — در ناوبری و هدر."""

    @classmethod
    def setUpClass(cls):
        cls.icon = _read("miniapp", "src", "components", "ui", "Icon.jsx")
        cls.nav = _read("miniapp", "src", "components", "layout", "BottomNav.jsx")
        cls.header = _read("miniapp", "src", "components", "layout", "Header.jsx")

    def test_icon_set_is_present(self):
        self.assertIn("const PATHS = {", self.icon)
        # هر آیکون یک خط «  name: 'path',» است
        entries = re.findall(r"^\s{2}[a-zA-Z]+:\s*'M", self.icon, re.MULTILINE)
        self.assertGreaterEqual(
            len(entries), 25, f"فقط {len(entries)} آیکون پیدا شد"
        )

    def test_icons_are_stroke_based(self):
        self.assertIn('stroke="currentColor"', self.icon)
        self.assertIn("strokeLinecap=\"round\"", self.icon)

    def test_bottom_nav_uses_icons_not_emoji(self):
        self.assertIn("iconKey", self.nav)
        self.assertIn("<Icon name={tab.iconKey}", self.nav)
        # هیچ ایموجی‌ای نباید در تعریف تب‌ها بماند
        tabs_block = self.nav.split("const MORE =")[0]
        emoji = re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", tabs_block)
        # فقط فیلد fallback مجاز است؛ اگر ایموجی در label برگردد تست قرمز می‌شود
        self.assertTrue(
            all("icon:" in line for line in tabs_block.splitlines() if any(e in line for e in emoji)),
            "در ناوبری اصلی ایموجیِ غیرِ fallback پیدا شد",
        )

    def test_header_uses_line_icons(self):
        self.assertIn("import Icon from '../ui/Icon'", self.header)
        self.assertIn('<Icon name="arrowRight"', self.header)
        self.assertIn('<Icon name="refresh"', self.header)


class HomeV3Tests(unittest.TestCase):
    """بلوک‌های تازهٔ خانه باید وصل و استایل‌دهی‌شده باشند."""

    def test_home_blocks_are_wired(self):
        dash = _read("miniapp", "src", "pages", "Dashboard", "index.jsx")
        self.assertIn("<HomeGreeting", dash)
        self.assertIn("<NextExamCard", dash)
        self.assertIn("<QuickGrid", dash)

    def test_home_stylesheet_is_imported(self):
        main = _read("miniapp", "src", "main.jsx")
        self.assertIn("v3-home.css", main)

    def test_home_blocks_do_not_invent_data(self):
        """هیچ دادهٔ ساختگی/جای‌نگهدار عددی در بلوک‌های خانه نباشد."""
        src = _read("miniapp", "src", "components", "home", "HomeV3.jsx")
        self.assertNotIn("Math.random", src)
        self.assertNotIn("لورم", src)
        # اعداد نمایشی باید از props بیایند
        self.assertIn("exam.days_left", src)

    def test_no_emoji_left_in_home_tabs(self):
        dash = _read("miniapp", "src", "pages", "Dashboard", "index.jsx")
        self.assertIn("['stats', 'عملکرد', 'chart']", dash)


if __name__ == "__main__":
    unittest.main(verbosity=2)
