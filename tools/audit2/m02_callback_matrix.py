# -*- coding: utf-8 -*-
"""ماتریس callback_data ↔ هندلر (فاز ۲.۲) + پوشش answer().

callback ساخته‌شده (لیترال یا f-string) → template با ⟨X⟩؛
تطبیق با الگوی ثبت‌شده در bot.py (جدول cbs + ثبت مستقیم) و ماژول‌ها.
خروجی: docs/audit2-data/02_callback_matrix.txt
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'docs', 'audit2-data')
os.makedirs(OUT, exist_ok=True)

BOT_DIRS = ['.', 'ring', 'qbank', 'question_bank', 'payments']
py_files = []
for d in BOT_DIRS:
    dp = os.path.join(ROOT, d)
    if os.path.isdir(dp):
        for f in sorted(os.listdir(dp)):
            if f.endswith('.py') and f != 'resources.py':
                py_files.append(os.path.join(dp, f))

# ── ۱) callbackهای ساخته‌شده → template (متغیرها ⇒ ⟨X⟩) ──
built = {}          # template -> set(rel)
BUILT_RE = re.compile(r"callback_data\s*=\s*([fF]?)(['\"])(.*?)\2")
# ساخت داینامیک: CB = 'dun:' … callback_data=CB+'x' یا f'{CB}resume'
CONST_CB = {}


def templ(s):
    return re.sub(r"\{[^{}]*\}", "⟨X⟩", s)


for path in py_files:
    rel = os.path.relpath(path, ROOT)
    src = open(path, encoding='utf-8').read()
    consts = dict(re.findall(r"^(\w+)\s*=\s*['\"]([\w:]+)['\"]", src, re.M))
    for m in BUILT_RE.finditer(src):
        lit = m.group(3)
        if not lit:
            continue
        # گسترش ثابت‌های محلی در ابتدای رشته: {CB}menu → ring:menu
        while True:
            vm = re.match(r"\{(\w+)\}", lit)
            if vm and vm.group(1) in consts:
                lit = consts[vm.group(1)] + lit[vm.end():]
            else:
                break
        t = templ(lit)
        built.setdefault(t, set()).add(rel)
    CONST_CB.update(consts)

# کانکتناسیون: callback_data=CB+'…'
for path in py_files:
    rel = os.path.relpath(path, ROOT)
    src = open(path, encoding='utf-8').read()
    for m in re.finditer(
            r"callback_data\s*=\s*([fF]?)(['\"])(.*?)\2\s*\+", src):
        t = templ(m.group(3))
        built.setdefault(t, set()).add(rel)

# ── ۲) الگوهای ثبت‌شده ──
registered = []
bot_src = open(os.path.join(ROOT, 'bot.py'), encoding='utf-8').read()
for m in re.finditer(r"\(\s*(\w+)\s*,\s*r(['\"])(.*?)\2\s*\)", bot_src):
    registered.append((m.group(3), f'bot.py cbs-table → {m.group(1)}'))
for path in py_files:
    rel = os.path.relpath(path, ROOT)
    src = open(path, encoding='utf-8').read()
    for m in re.finditer(
            r"CallbackQueryHandler\(\s*([\w.]+)\s*,\s*(?:pattern\s*=\s*)?r(['\"])(.*?)\2",
            src):
        registered.append((m.group(3), f'{rel} → {m.group(1)}'))

SUFFIXES = ['', 'X', '1', 'abc', 'x:y', 'ok']


def rx_covers_template(rx, t):
    """آیا regex می‌تواند callbackای بسازد که با template سازگار باشد؟"""
    idx = t.find('⟨X⟩')
    pre = t if idx < 0 else t[:idx]
    samples = [pre + s for s in SUFFIXES] + [t.replace('⟨X⟩', 'X'),
                                              t.replace('⟨X⟩', 'x:y:z')]
    if idx < 0:
        samples.append(t)
    for smp in samples:
        try:
            if re.search(rx, smp):
                return True
        except re.error:
            return False
    return False


def template_covered_by(t):
    return [info for rx, info in registered if rx_covers_template(rx, t)]


# ── ۳) مقایسه ──
dead_buttons = {t: rels for t, rels in built.items()
                if not template_covered_by(t)}
unreachable = []
for rx, srcinfo in registered:
    if not any(rx_covers_template(rx, t) for t in built):
        unreachable.append((rx, srcinfo))

# ── ۴) هندلرهای جدول cbs بدون answer() ──
no_answer = []
handler_names = set(m.group(1) for m in
                    re.finditer(r"\(\s*(\w+)\s*,\s*r(['\"])", bot_src))
srcs = {}
for path in py_files:
    rel = os.path.relpath(path, ROOT)
    srcs[rel] = open(path, encoding='utf-8').read()
for h in sorted(handler_names):
    for rel, src in srcs.items():
        m = re.search(rf"(?:async )?def {h}\(", src)
        if not m:
            continue
        nxt = re.search(r"\n(?:async )?def \w+\(", src[m.end():])
        body = src[m.end():m.end() + (nxt.start() if nxt else 6000)]
        if not re.search(r"\.(answer|answer_callback_query)\(", body):
            no_answer.append((h, rel))
        break

with open(os.path.join(OUT, '02_callback_matrix.txt'), 'w', encoding='utf-8') as f:
    f.write(f'templateهای ساخته‌شده: {len(built)} | الگوهای ثبت‌شده: {len(registered)}\n\n')
    f.write(f'══ دکمه بدون هندلرِ تطبیق‌شونده ({len(dead_buttons)}) ══\n')
    for t in sorted(dead_buttons):
        f.write(f'  {t!r}  ← ساخته‌شده در: {", ".join(sorted(dead_buttons[t]))}\n')
    f.write(f'\n══ هندلر/الگوی بدون هیچ دکمه‌ای ({len(unreachable)}) ══\n')
    for rx, srcinfo in unreachable:
        f.write(f'  {rx!r}  ← {srcinfo}\n')
    f.write(f'\n══ هندلر بدون answer() ({len(no_answer)}) ══\n')
    for h, rel in no_answer:
        f.write(f'  {h}  ← {rel}\n')

print(f'built={len(built)} registered={len(registered)} '
      f'dead_buttons={len(dead_buttons)} unreachable={len(unreachable)} '
      f'no_answer={len(no_answer)}')
