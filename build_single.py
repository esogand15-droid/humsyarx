#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ساخت نسخهٔ «یک‌فایلی» پروتوتایپ برای بازبینی بدون سرور.

همهٔ CSS، JS، فونت‌ها و نشان برند به base64 تبدیل و داخل یک index.html
قرار می‌گیرند. نتیجه: یک فایل که با دوبار کلیک در مرورگر باز می‌شود و
هیچ درخواست بیرونی ندارد (بدون CDN، بدون فونت آنلاین، بدون شبکه).
"""
import base64
import mimetypes
import os
import re
import shutil
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
OUT = os.path.join(ROOT, "humsyar-prototype.html")


def data_uri(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def main() -> None:
    if not os.path.isdir(DIST):
        subprocess.run(["npm", "run", "build"], cwd=ROOT, check=True)

    with open(os.path.join(DIST, "index.html"), encoding="utf-8") as f:
        html = f.read()

    # ── CSS: فونت‌ها را درون CSS جایگزین کن
    css_ref = re.search(r'href="\./(assets/[^"]+\.css)"', html)
    assert css_ref, "css asset not found"
    css_path = os.path.join(DIST, css_ref.group(1))
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    # هر ارجاع url(...) که به یک فایل موجود در dist/assets اشاره کند
    names = {n for n in os.listdir(os.path.join(DIST, "assets"))}

    def inline_css_url(m: "re.Match[str]") -> str:
        ref = m.group(1).strip("\"'")
        base = os.path.basename(ref)
        if base in names:
            return f"url({data_uri(os.path.join(DIST, 'assets', base))})"
        return m.group(0)

    css = re.sub(r"url\(([^)]+)\)", inline_css_url, css)

    # ── JS: نشان برند را data-uri کن
    js_ref = re.search(r'src="\./(assets/[^"]+\.js)"', html)
    assert js_ref, "js asset not found"
    js_path = os.path.join(DIST, js_ref.group(1))
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    for name in sorted(n for n in names if n.endswith((".png", ".woff2"))):
        uri = data_uri(os.path.join(DIST, "assets", name))
        js = js.replace(f'"assets/{name}"', f'"{uri}"').replace(f'"{name}"', f'"{uri}"')

    out = html
    out = out.replace(
        f'<link rel="stylesheet" crossorigin href="./{css_ref.group(1)}">',
        f"<style>\n{css}\n</style>",
    )
    out = out.replace(
        f'<script type="module" crossorigin src="./{js_ref.group(1)}"></script>',
        f'<script type="module">\n{js}\n</script>',
    )
    # manifest و آیکن‌های PWA را هم درون فایل می‌بریم تا نسخهٔ تک‌فایلی
    # هیچ درخواست بیرونی نداشته باشد
    man_path = os.path.join(DIST, "manifest.webmanifest")
    if os.path.exists(man_path):
        with open(man_path, encoding="utf-8") as f:
            import json as _json

            man = _json.load(f)
        for ic in man.get("icons", []):
            rel = ic["src"].lstrip("./")
            local = os.path.join(DIST, rel)
            if os.path.exists(local):
                ic["src"] = data_uri(local)
        out = out.replace(
            '<link rel="manifest" href="./manifest.webmanifest" />',
            "<style>/* manifest inline */</style>",
        )
        out = out.replace(
            "</head>",
            f'<link rel="manifest" href="data:application/manifest+json;base64,'
            f'{base64.b64encode(_json.dumps(man, ensure_ascii=False).encode()).decode()}">\n</head>',
        )

    # favicon → هم داده‌ای
    out = re.sub(
        r'<link rel="icon" href="\./(assets/[^"]+)"\s*/?>',
        lambda m: f'<link rel="icon" href="{data_uri(os.path.join(DIST, m.group(1)))}">',
        out,
    )

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(out)

    size = os.path.getsize(OUT) / 1024
    print(f"✅ {os.path.basename(OUT)} — {size:.0f} KB — بدون هیچ درخواست بیرونی")


if __name__ == "__main__":
    main()
