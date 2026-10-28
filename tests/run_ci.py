#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""🏃 اجراکنندهٔ تست‌های CI با «خط‌مبنای شکست‌های شناخته‌شده».

چرا این فایل لازم شد
────────────────────
۱) ورک‌فلوی قبلی `python -m unittest discover` را **بدون نصب
   `requirements.txt`** اجرا می‌کرد ⇒ تست‌های وابسته در محیط CI اصلاً
   بالا نمی‌آمدند و چراغ CI هیچ سیگنالی نداشت.
۲) مخزن از قبل ۱۹ شکست/خطای واقعی دارد (فهرست در
   `tests/known_failures.txt` با دلیل هرکدام). اگر CI را صادق کنیم،
   بلافاصله قرمز می‌شود و دیگر به آن نگاه نمی‌کنیم — یعنی همان حالت
   بی‌سیگنال، فقط با رنگ قرمز.

قاعدهٔ کار
──────────
* شکست‌های موجود در خط‌مب = «بدهی شناخته‌شده» ⇒ CI سبز می‌ماند ولی
  با شمارش دقیق چاپ می‌شود.
* **هر شکست تازه** (که در خط‌مب نیست) ⇒ CI قرمز می‌شود. این همان
  چیزی است که رگرسیون را قبل از Production می‌گیرد.
* تستی که قبلاً خراب بود و حالا سبز شده ⇒ خبر خوب، چاپ می‌شود و از
  خط‌مب قابل حذف است (`--update`).

استفاده
───────
    python tests/run_ci.py             # اجرای کامل + مقایسه با خط‌مب
    python tests/run_ci.py --update    # بازتولید خط‌مب (بعد از اصلاح)
    python tests/run_ci.py -v          # خروجی کامل یونیت‌تست
"""
from __future__ import annotations

import argparse
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASELINE_PATH = os.path.join(HERE, "known_failures.txt")

sys.path.insert(0, ROOT)


def _prepare_env() -> None:
    """محیط حداقلیِ قابل‌اجرا؛ هرگز روی Production اجرا نمی‌شود."""
    os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017/humsyar_test")
    os.environ.setdefault("ADMIN_ID", "1")
    os.environ.setdefault("TELEGRAM_TOKEN", "123:TEST")
    os.environ.setdefault("TZ", "Asia/Tehran")


class _CollectingResult(unittest.TextTestResult):
    """نتیجه‌ای که شناسهٔ هر شکست/خطا را نگه می‌دارد."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.problem_ids: list[str] = []

    def _record(self, test) -> None:
        try:
            self.problem_ids.append(test.id())
        except Exception:                      # pragma: no cover
            self.problem_ids.append(str(test))

    def addError(self, test, err):             # noqa: N802
        self._record(test)
        super().addError(test, err)

    def addFailure(self, test, err):           # noqa: N802
        self._record(test)
        super().addFailure(test, err)

    def addUnexpectedSuccess(self, test):      # noqa: N802
        self._record(test)
        super().addUnexpectedSuccess(test)


def _load_baseline() -> dict[str, str]:
    """{test_id: دلیل} — خطوط با # کامنت‌اند."""
    out: dict[str, str] = {}
    if not os.path.isfile(BASELINE_PATH):
        return out
    for raw in open(BASELINE_PATH, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            test_id, reason = line.split("#", 1)
            out[test_id.strip()] = reason.strip()
        else:
            out[line] = ""
    return out


def _write_baseline(ids: list[str], reasons: dict[str, str]) -> None:
    with open(BASELINE_PATH, "w", encoding="utf-8") as f:
        f.write(
            "# شکست‌های شناخته‌شدهٔ مخزن — «بدهی فنی» با دلیل.\n"
            "# هر خط: test_id  # دلیل\n"
            "# CI فقط روی شکست‌های *جدید* قرمز می‌شود.\n"
            "# وقتی یکی از این‌ها اصلاح شد، با `python tests/run_ci.py --update`\n"
            "# خط‌مب را بازتولید کن تا فهرست کوتاه‌تر شود.\n\n"
        )
        for test_id in sorted(ids):
            reason = reasons.get(test_id, "").strip()
            f.write(f"{test_id}{'  # ' + reason if reason else ''}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true",
                        help="خط‌مب را با وضعیت فعلی بازتولید کن")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    _prepare_env()

    suite = unittest.defaultTestLoader.discover(start_dir=HERE, pattern="test_*.py")
    runner = unittest.TextTestRunner(
        verbosity=2 if args.verbose else 1,
        resultclass=_CollectingResult,
        stream=sys.stdout,
    )
    result = runner.run(suite)

    ran = result.testsRun
    problems = list(dict.fromkeys(result.problem_ids))
    skipped = len(result.skipped) if hasattr(result, "skipped") else 0

    print("\n" + "=" * 68)
    print(f"اجرا: {ran} تست | سبز: {ran - len(problems)} | مشکل: {len(problems)} "
          f"| skip: {skipped}")
    print("=" * 68)

    if args.update:
        previous = _load_baseline()
        _write_baseline(problems, previous)
        print(f"✅ خط‌مب بازتولید شد: {len(problems)} مورد → "
              f"{os.path.relpath(BASELINE_PATH, ROOT)}")
        return 0

    baseline = _load_baseline()
    new = [p for p in problems if p not in baseline]
    fixed = [p for p in baseline if p not in problems]

    if baseline:
        print(f"بدهی شناخته‌شده: {len(baseline)} مورد "
              f"(فهرست: {os.path.relpath(BASELINE_PATH, ROOT)})")

    if fixed:
        print(f"\n🎉 {len(fixed)} مورد از بدهی قبلی اصلاح شد — "
              "با `python tests/run_ci.py --update` خط‌مب را کوتاه کن:")
        for f in fixed[:15]:
            print(f"   ✔ {f}")

    if new:
        print(f"\n❌ {len(new)} شکستِ تازه (رگرسیون):")
        for n in new:
            print(f"   ✘ {n}")
        print("\nنتیجه: FAILED — این‌ها در خط‌مب نبودند و باید قبل از merge "
              "اصلاح شوند.")
        return 1

    print("\nنتیجه: PASSED — هیچ رگرسیون تازه‌ای نیست.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
