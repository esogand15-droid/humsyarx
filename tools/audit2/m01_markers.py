# -*- coding: utf-8 -*-
"""سرشماری نشانه‌های ناقص‌کاری — فاز ۲.۱ ماموریت تکمیل.

خروجی: docs/audit2-data/01_markers.txt
"""
import ast
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'docs', 'audit2-data')
os.makedirs(OUT, exist_ok=True)

PY_FILES = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in
                   ('__pycache__', '.git', 'node_modules', '.venv',
                    'audit2-data')]
    for f in filenames:
        if f.endswith(('.py', '.js', '.jsx', '.ts', '.tsx', '.html')):
            PY_FILES.append(os.path.join(dirpath, f))
PY_FILES = [p for p in PY_FILES if '/tests/' not in p.replace('\\', '/')]

MARKERS = [
    (r'\bTODO\b', 'TODO'), (r'\bFIXME\b', 'FIXME'), (r'\bXXX\b', 'XXX'),
    (r'\bHACK\b', 'HACK'),
    (r'NotImplementedError', 'NotImplementedError'),
    (r'placeholder', 'placeholder'), (r'\bdummy\b', 'dummy'),
    (r'\bmock(?!ed)', 'mock-ish'), (r'\bfake\b', 'fake'),
    (r'به[\u200c ]?زودی', 'به‌زودی'), (r'در دست ساخت', 'در-دست-ساخت'),
    (r'coming soon', 'coming-soon'), (r'not implemented', 'not-implemented'),
    (r'فعلا[\u200c ]?این[\u200c ]?طوری|placeholder only', 'stub'),
]

results = {m[1]: [] for m in MARKERS}
results['print-temp'] = []
results['pass-only-func'] = []
results['commented-block'] = []

for path in PY_FILES:
    rel = os.path.relpath(path, ROOT)
    try:
        src = open(path, encoding='utf-8').read()
    except Exception:
        continue
    lines = src.split('\n')
    for i, ln in enumerate(lines, 1):
        for pat, name in MARKERS:
            if name == 'mock-ish' and '/tests/' not in rel and 'mock' in ln.lower():
                # فقط وقتی شبیه موکِ رهاشده است نه import تست
                if 'import' not in ln:
                    results['mock-ish'].append(f'{rel}:{i}: {ln.strip()[:110]}')
                continue
            if name == 'placeholder' and re.search(
                    r'placeholder\s*[=:]|input_field_placeholder|::placeholder', ln):
                # placeholder= اتریبیوت JSX/CSS «کادر راهنما» است، نه نشانه ناقص‌کاری
                continue
            if re.search(pat, ln):
                results[name].append(f'{rel}:{i}: {ln.strip()[:110]}')
        if re.search(r'\bprint\(', ln) and path.endswith('.py'):
            results['print-temp'].append(f'{rel}:{i}: {ln.strip()[:110]}')
    # بلوک کامنت‌شده بزرگ (۵+ خط پیاپی # با کد‌مانند)
    run = []
    for i, ln in enumerate(lines, 1):
        if re.match(r'^\s*#\s*\w', ln) and not ln.strip().startswith('#!'):
            run.append((i, ln))
        else:
            if len(run) >= 6:
                results['commented-block'].append(
                    f'{rel}:{run[0][0]}-{run[-1][0]} ({len(run)} خط)')
            run = []
    if len(run) >= 6:
        results['commented-block'].append(
            f'{rel}:{run[0][0]}-{run[-1][0]} ({len(run)} خط)')
    # توابع فقط-pass / خالی (AST — فقط پایتون)
    if path.endswith('.py'):
        try:
            tree = ast.parse(src)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = [n for n in node.body
                        if not (isinstance(n, ast.Expr)
                                and isinstance(n.value, ast.Constant))]
                real = [n for n in body
                        if not isinstance(n, (ast.Pass, ast.DocString
                                              if hasattr(ast, 'DocString')
                                              else ast.Pass))]
                # body فقط از pass/docstring تشکیل شده
                if len(body) <= 2 and all(
                        isinstance(n, ast.Pass) for n in body) and body:
                    results['pass-only-func'].append(
                        f'{rel}:{node.lineno}: def {node.name}()')

with open(os.path.join(OUT, '01_markers.txt'), 'w', encoding='utf-8') as f:
    for k, v in results.items():
        f.write(f'══ {k} ({len(v)}) ══\n')
        for item in v[:80]:
            f.write(f'  {item}\n')
        if len(v) > 80:
            f.write(f'  … و {len(v) - 80} مورد دیگر\n')
        f.write('\n')

print('SUMMARY:', {k: len(v) for k, v in results.items()})
