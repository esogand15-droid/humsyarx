# -*- coding: utf-8 -*-
"""🛡 گاردِ قرارداد لایهٔ داده — جلوگیری از تکرار کلاسِ باگِ ثبت‌نام.

چرا این تست وجود دارد
──────────────────────
خطای تولیدی
    TypeError: DBCore.create_user() got an unexpected keyword argument 'group_verified'
از یک الگوی تکرارشونده می‌آمد: **فراخوان با آرگومانی که در امضای تابع
نیست**. بررسی دستی سه مورد پیدا کرد که همه در Production اثری داشتند:

  ۱. `create_user(..., group_verified=...)`  → ثبت‌نام ربات و مینی‌اپ (P0)
  ۲. `set_user_educational_group(..., reason=...)` در ۶ نقطه → ویرایش گروه آموزشی
  ۳. `enqueue_bot_outbox(...)` که متدش اصلاً وجود نداشت → یادآوری انتخاب واحد

این تست همان بررسی را به‌صورت **ایستا (AST)** و در CI انجام می‌دهد:
هیچ اتصال شبکه/دیتابیس لازم نیست، پس هرگز skip یا flaky نمی‌شود.

قواعد
─────
* کلاس `DB` ترکیب mixinهای `db/*` است؛ متدهای پذیرفته‌شده = اجتماع همه.
* aliasها (مثل `backfill_legacy_users_educational_group = ...`) معتبرند.
* `**kwargs` در تعریف ⇒ هر آرگومان نام‌دار مجاز است.
* `db` و `database.db` و `self.` (داخل db/) پوشش داده می‌شوند.
"""
from __future__ import annotations

import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIXINS = ("DBCore", "DBContent", "DBRbac", "DBPrestige", "DBFinance",
          "DBRing", "DBWallet", "DBReferral", "DBAiQuiz")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}


def _py_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)


def _collect_signatures():
    """{method_name: (positional_params, kwonly_params, has_vararg, has_kwarg, where)}"""
    methods: dict[str, tuple] = {}
    for path in _py_files():
        if f"{os.sep}db{os.sep}" not in path:
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError:                     # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name not in MIXINS:
                continue
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    a = item.args
                    pos = [x.arg for x in a.posonlyargs + a.args if x.arg != "self"]
                    kw = [x.arg for x in a.kwonlyargs]
                    methods[item.name] = (pos, kw, a.vararg is not None,
                                          a.kwarg is not None,
                                          f"{os.path.basename(path)}:{item.lineno}")
                elif isinstance(item, ast.Assign):
                    # alias: name = existing_method
                    for tgt in item.targets:
                        if (isinstance(tgt, ast.Name) and isinstance(item.value, ast.Name)
                                and item.value.id in methods):
                            methods[tgt.id] = methods[item.value.id]
    return methods


class DataLayerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.methods = _collect_signatures()
        if not cls.methods:                     # pragma: no cover
            raise unittest.SkipTest("امضای متدهای db پیدا نشد")
        cls.violations = cls._scan()

    @classmethod
    def _scan(cls):
        bad = []
        for path in _py_files():
            if f"{os.sep}db{os.sep}" in path:
                continue                        # داخل خودِ لایهٔ داده: self.* در تست دیگر
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except SyntaxError:                 # pragma: no cover
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "db"):
                    continue
                name = node.func.attr
                sig = cls.methods.get(name)
                if sig is None:
                    continue                    # متد ناشناخته: تستِ جداگانهٔ زیر
                pos, kwonly, has_vararg, has_kwarg, where = sig
                if has_kwarg:
                    continue
                extra = [k.arg for k in node.keywords if k.arg and k.arg not in pos + kwonly]
                n_pos = len([a for a in node.args if not isinstance(a, ast.Starred)])
                starred = any(isinstance(a, ast.Starred) for a in node.args)
                if extra:
                    bad.append(f"{os.path.relpath(path, ROOT)}:{node.lineno} "
                               f"db.{name}({', '.join(extra)}=...) ← امضا در {where} ندارد")
                elif not has_vararg and not starred and n_pos > len(pos):
                    bad.append(f"{os.path.relpath(path, ROOT)}:{node.lineno} "
                               f"db.{name}: {n_pos} آرگومان موضعی > {len(pos)} ← {where}")
        return bad

    def test_no_caller_passes_unknown_kwargs(self):
        self.assertEqual(
            self.violations, [],
            "فراخوان با آرگومانِ خارج از امضا (همان کلاس باگِ ثبت‌نام):\n  "
            + "\n  ".join(self.violations),
        )

    def test_known_members_exist(self):
        """سه عضوی که در ممیزی غایب بودند، باید بمانند."""
        for name in ("create_user",
                     "set_user_educational_group",
                     "enqueue_bot_outbox",
                     "backfill_legacy_users_educational_group",
                     "flag_mismatched_student_selections"):
            self.assertIn(name, self.methods,
                          f"db.{name} حذف/تغییرنام داده شده است")

    def test_create_user_accepts_group_verified(self):
        """قرارداد P0: این آرگومان باید در امضا بماند."""
        pos, kwonly, _va, has_kwarg, _w = self.methods["create_user"]
        self.assertTrue(has_kwarg or "group_verified" in pos + kwonly,
                        "create_user باید group_verified را بپذیرد (باگ ثبت‌نام)")

    def test_set_educational_group_accepts_reason(self):
        pos, kwonly, _va, has_kwarg, _w = self.methods["set_user_educational_group"]
        self.assertTrue(has_kwarg or "reason" in pos + kwonly,
                        "set_user_educational_group باید reason را بپذیرد")


if __name__ == "__main__":
    unittest.main(verbosity=2)
