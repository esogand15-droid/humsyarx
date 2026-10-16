# -*- coding: utf-8 -*-
"""ماتریس endpoint ↔ UI (فاز ۲.۳): سرور (main.py mount + routers)
در برابر مصرف‌کننده‌ها (wrapperهای webadmin/api.js + axios مستقیم مینی‌اپ).

خروجی: docs/audit2-data/03_endpoint_matrix.txt
دسته‌بندی «بدون مصرف‌کننده»: alias احتمالی (مسیر هم‌ارز مصرف‌شده)
در برابر کاملاً بی‌مصرف.
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'docs', 'audit2-data')
os.makedirs(OUT, exist_ok=True)

# ── ۱) endpointهای سرور ──
main_src = open(os.path.join(ROOT, 'api', 'main.py'), encoding='utf-8').read()
mounts = {}
for m in re.finditer(
        r"include_router\(\s*([\w.]+)(?:\([^)]*\))?\s*,\s*prefix=[\"']([^\"']+)[\"']",
        main_src, re.S):
    mounts[m.group(1)] = m.group(2)

endpoints = {}      # (method, full) -> 'file::func'
for f in sorted(os.listdir(os.path.join(ROOT, 'api', 'routers'))):
    if not f.endswith('.py'):
        continue
    rel = f'api/routers/{f}'
    src = open(rel, encoding='utf-8').read()
    mp = re.search(r"APIRouter\([^)]*prefix\s*=\s*[\"']([^\"']*)[\"']", src, re.S)
    router_prefix = mp.group(1) if mp else ''
    rv = re.search(r"(\w+)\s*=\s*APIRouter\(", src)
    rv_name = rv.group(1) if rv else 'router'
    mod = f[:-3]
    mount_prefix = ''
    for qname, p in mounts.items():
        if f'.{mod}.' in qname or qname.startswith(f'{mod}.'):
            mount_prefix = p
            break
    for m in re.finditer(
            r"@(\w+)\.(get|post|put|delete|patch)\(\s*[\"']([^\"']*)[\"']", src):
        var, method, sub = m.groups()
        if var == rv_name:
            full = mount_prefix + router_prefix + sub
        else:
            full = router_prefix + sub
        full = full or '/'
        fn = re.search(r"def (\w+)", src[m.end():m.end() + 150])
        endpoints[(method.upper(), full)] = f'{rel}::{fn.group(1) if fn else "?"}'

# ── ۲) مصرف‌کننده‌های فرانت ──
wa_wrappers = {}     # name -> path (webadmin/src/api.js)
src = open(os.path.join(ROOT, 'webadmin', 'src', 'api.js'), encoding='utf-8').read()
for m in re.finditer(
        r"(\w+)\s*:\s*(?:async\s*)?\([^)]*\)\s*=>\s*(?:await\s*)?req\(\s*[\"'`]([^\"'`]+)",
        src):
    wa_wrappers[m.group(1)] = m.group(2)


def page_calls(rootdir):
    """api.xxx( و fetch('path') و axios.get('path') و هر رشته‌ی '/api/…'"""
    api_used, paths = set(), set()
    for dp, dn, fn in os.walk(os.path.join(ROOT, rootdir)):
        dn[:] = [d for d in dn if d != 'node_modules']
        for f in fn:
            if not f.endswith(('.js', '.jsx')):
                continue
            s = open(os.path.join(dp, f), encoding='utf-8', errors='replace').read()
            for m in re.finditer(r"\bapi\.(\w+)\b", s):
                api_used.add(m.group(1))
            for m in re.finditer(r"fetch\(\s*[\"'`]([^\"'`]+)", s):
                paths.add(m.group(1))
            # axios مستقیم: api.get('/x'), api.post(`/x`, …)
            for m in re.finditer(
                    r"api\.(?:get|post|put|delete|patch)\(\s*[\"'`]([^\"'`]+)", s):
                paths.add(m.group(1))
            # هر رشته‌ی '/api/…' (فراخوانی زنجیره‌ای/چندخطی)
            for m in re.finditer(r"[\"'`]((?:/api|/app)/[^\"'`]*)[\"'`]", s):
                paths.add(m.group(1))
    return api_used, paths


wa_used, wa_paths = page_calls('webadmin/src')
ma_used, ma_paths = page_calls('miniapp/src')
for n, p in wa_wrappers.items():
    if n in wa_used:
        wa_paths.add(p)
front_paths = set(wa_paths) | set(ma_paths)


def norm(p):
    p = re.sub(r"\$?\{[^{}]*\}", 'X', p)   # ${id} و {param} هر دو
    p = re.sub(r"\?.*$", '', p)
    return p.rstrip('/') or '/'


front_norm = {norm(c) for c in front_paths}
ep_norm = {(m, norm(f)) for (m, f) in endpoints}


def hit(full, method=None):
    n = norm(full)
    if n in front_norm:
        return True
    rx = re.escape(n).replace(re.escape('X'), '[^/]+')
    if any(re.fullmatch(rx, c) for c in front_norm):
        return True
    # جهت معکوس: فرانت با ${var} مسیر را می‌سازد؛ endpoint لیتِرال است
    for c in front_norm:
        if 'X' in c:
            crx = re.escape(c).replace(re.escape('X'), '[^/]+')
            if re.fullmatch(crx, n):
                return True
    return False


# ── ۳) دسته‌بندی ──
no_consumer, consumed = [], []
for (mth, full), srcinfo in sorted(endpoints.items()):
    if hit(full):
        consumed.append((mth, full))
    else:
        no_consumer.append((mth, full, srcinfo))

# alias: endpoint بدون مصرف که «هم‌ارز متدی» دارد = همان ۲ سگمنت آخر +
# متد، با مسیر مصرف‌شده (مثلاً /api/admin/tickets ↔ /api/web-admin/tickets)
consumed_sigs = set()
for mth, full in consumed:
    segs = norm(full).split('/')
    consumed_sigs.add((mth, '/'.join(segs[-2:])))

alias, orphan = [], []
for mth, full, srcinfo in no_consumer:
    segs = norm(full).split('/')
    if (mth, '/'.join(segs[-2:])) in consumed_sigs:
        alias.append((mth, full, srcinfo))
    else:
        orphan.append((mth, full, srcinfo))

unused_wrappers = [n for n in wa_wrappers if n not in wa_used]

with open(os.path.join(OUT, '03_endpoint_matrix.txt'), 'w', encoding='utf-8') as out:
    out.write(f'endpointها: {len(endpoints)} | مصرف‌شده: {len(consumed)} | '
              f'بدون مصرف: {len(no_consumer)} (alias هم‌ارز: {len(alias)} | یتیم: {len(orphan)})\n')
    out.write(f'wrapperهای webadmin/api.js: {len(wa_wrappers)} | '
              f'بی‌استفاده در صفحات: {len(unused_wrappers)}\n\n')
    out.write(f'════ یتیم — هیچ مصرف‌کننده و هیچ هم‌ارزی ({len(orphan)}) ════\n')
    for mth, f, s in orphan:
        out.write(f'  [{mth}] {f}  ← {s}\n')
    out.write(f'\n════ alias احتمالی — هم‌ارزِ مصرف‌شده وجود دارد ({len(alias)}) ════\n')
    for mth, f, s in alias:
        out.write(f'  [{mth}] {f}  ← {s}\n')
    out.write('\n════ wrapperهای webadmin/api.js که هیچ صفحه‌ای صدا نمی‌زند ════\n')
    for n in sorted(unused_wrappers):
        out.write(f'  api.{n} → {wa_wrappers[n]}\n')

print(f'endpoints={len(endpoints)} consumed={len(consumed)} '
      f'alias={len(alias)} orphan={len(orphan)} unused_wr={len(unused_wrappers)}')
