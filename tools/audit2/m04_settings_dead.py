# -*- coding: utf-8 -*-
"""ماتریس تنظیمات (فاز ۲.۶) + توابع تعریف‌شده-بی‌استفاده (فاز ۲.۵).

خروجی: docs/audit2-data/04_settings_matrix.txt و 05_dead_funcs.txt
"""
import ast
import os
import re
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'docs', 'audit2-data')
os.makedirs(OUT, exist_ok=True)

EXCLUDE_DIRS = {'__pycache__', '.git', 'node_modules', '.venv', 'audit2-data',
                'tests', 'tools', 'webadmin', 'miniapp', 'docs', '.pytest_cache'}

py_files = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
    for f in filenames:
        if f.endswith('.py'):
            py_files.append(os.path.join(dirpath, f))
py_files = [p for p in py_files if os.path.basename(p) != 'resources.py'
            or True]  # resources.py را نگه می‌داریم (زنجیره‌ی مرده)

# ── ۱) کلیدهای تنظیمات ──
readers = defaultdict(set)
writers = defaultdict(set)
for path in py_files:
    rel = os.path.relpath(path, ROOT)
    src = open(path, encoding='utf-8', errors='replace').read()
    for m in re.finditer(r"get_setting\(\s*['\"]([\w.\-]+)['\"]", src):
        readers[m.group(1)].add(rel)
    for m in re.finditer(r"set_setting\(\s*['\"]([\w.\-]+)['\"]", src):
        writers[m.group(1)].add(rel)

# کلیدهای تنظیمات در UI پنل (api.js و صفحات webadmin)
panel_keys = set()
wa_dir = os.path.join(ROOT, 'webadmin', 'src')
for dp, dn, fn in os.walk(wa_dir):
    dn[:] = [d for d in dn if d != 'node_modules']
    for f in fn:
        if f.endswith(('.js', '.jsx')):
            s = open(os.path.join(dp, f), encoding='utf-8', errors='replace').read()
            for m in re.finditer(r"['\"]([a-z][a-z0-9_]*(?:_[a-z0-9_]+)+)['\"]", s):
                panel_keys.add(m.group(1))

code_keys = set(readers) | set(writers)

with open(os.path.join(OUT, '04_settings_matrix.txt'), 'w', encoding='utf-8') as f:
    f.write(f'کلیدهای یکتا در کد پایتون: {len(code_keys)} '
            f'(خوانده: {len(readers)}, نوشته: {len(writers)})\n\n')
    f.write('══ فقط خوانده می‌شود — نویسنده‌ای در کد ندارد ══\n')
    for k in sorted(code_keys):
        if k in readers and k not in writers:
            f.write(f'  {k}  ← {", ".join(sorted(readers[k])[:4])}\n')
    f.write('\n══ نوشته می‌شود ولی هیچ خواننده‌ای ندارد ══\n')
    for k in sorted(code_keys):
        if k in writers and k not in readers:
            f.write(f'  {k}  ← {", ".join(sorted(writers[k])[:4])}\n')
    f.write('\n══ در UI پنل نیست (تنظیم فقط از env/دیتابیس مستقیم) ══\n')
    for k in sorted(code_keys):
        if k not in panel_keys:
            f.write(f'  {k}\n')

# ── ۲) توابع تعریف‌شده-بی‌استفاده ──
defs = {}
decorated = set()
srcs = {}
for path in py_files:
    rel = os.path.relpath(path, ROOT)
    src = open(path, encoding='utf-8', errors='replace').read()
    srcs[rel] = src
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs.setdefault(node.name, set()).add(rel)
            if node.decorator_list:
                decorated.add(node.name)

uses = defaultdict(int)
for rel, src in srcs.items():
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Name):
            uses[node.id] += 1
        elif isinstance(node, ast.Attribute):
            uses[node.attr] += 1
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                # نام اصلی و alias هر دو مصرف‌اند (import x as y → x تعریف، y مصرف)
                base = a.name.split('.')[-1]
                uses[base] += 1
                if a.asname:
                    uses[a.asname] += 1
    for m in re.finditer(r"['\"](\w{3,})['\"]", src):
        uses[m.group(1)] += 1

dead = []
for name, rels in defs.items():
    if uses.get(name, 0) == 0:
        dead.append((sorted(rels), name))

with open(os.path.join(OUT, '05_dead_funcs.txt', ), 'w', encoding='utf-8') as f:
    f.write(f'توابع تعریف‌شده: {len(defs)} | صفر ارجاع: {len(dead)}\n')
    f.write('(نویز: هندلرهای PTB از طریق رشته ارجاع می‌شوند و شمرده شده‌اند؛ '
            'توابع دکوریتوردار = احتمالاً ثبت‌شده از طریق دکوریتور)\n\n')
    for rels, name in sorted(dead):
        tag = ' [decorated]' if name in decorated else ''
        f.write(f'  {name}{tag}  ← {", ".join(rels)}\n')

print(f'settings: {len(code_keys)} (ro={len(set(readers)-set(writers))}, '
      f'wo={len(set(writers)-set(readers))}) | dead-funcs: {len(dead)}')
