# syntax=docker/dockerfile:1
# ════════════════════════════════════════════════════════════════════
#  🚂 هامزیار — تصویر یکپارچه‌ی Railway
#
#  یک image، دو process (زیر supervisord):
#    api → uvicorn api.main:app --host 0.0.0.0 --port $PORT
#    bot → python -u bot.py
#
#  و سه namespace روی یک origin:
#    /app/*  → Telegram Mini App   (از سورس، در همین build)
#    /admin/*→ Web Admin             (از سورس، در همین build)
#    /api/*  → FastAPI
#
#  Vercel در این معماری هیچ نقشی ندارد؛ مینی‌اپ هم‌ریشه‌ی API است.
#
#  ⚠️ replica باید ۱ بماند (railway.json) — job_queue و یادآوری‌ها
#  در هر replica جدا اجرا می‌شوند و پیام‌ها تکراری می‌شوند.
#
#  layer caching: فایل‌های package*.json و requirements.txt جدا کپی
#  می‌شوند تا نصب وابستگی‌ها تا زمانی که تغییر نکرده‌اند کش بماند.
# ════════════════════════════════════════════════════════════════════

# ────────────────────────────────────────────────────────────
#  Stage 1 — فرانت‌اندها (Node فقط برای build؛ در runtime نیست)
# ────────────────────────────────────────────────────────────
FROM node:20-bookworm-slim AS frontend

WORKDIR /build

# ── Mini App ──
# VITE_BASE=/app/ → تمام assetها، فونت‌ها و chunkهای lazy با پیشوند
# /app/ تولید می‌شوند و react-router هم همان را basename می‌گیرد.
ENV VITE_BASE=/app/
COPY miniapp/package.json miniapp/package-lock.json ./miniapp/
RUN npm --prefix ./miniapp ci --no-audit --no-fund
COPY miniapp/ ./miniapp/
RUN npm --prefix ./miniapp run build

# ── Web Admin ── (base آن از قبل در webadmin/vite.config.js روی /admin/ است)
COPY webadmin/package.json webadmin/package-lock.json ./webadmin/
RUN npm --prefix ./webadmin ci --no-audit --no-fund
COPY webadmin/ ./webadmin/
RUN npm --prefix ./webadmin run build


# ────────────────────────────────────────────────────────────
#  Stage 2 — runtime پایتون
# ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# PYTHONUNBUFFERED: لاگ‌ها بی‌فاصله به stdout/stderr می‌روند (Railway
# فقط همین را می‌بیند). PIP_NO_CACHE_DIR: لایه‌ی cache در image نماند.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# reportlab/Pillow به libjpeg و zlib برای PDF/تصویر نیاز دارند؛
# curl فقط برای HEALTHCHECK. (supervisor را با pip می‌گذاریم تا
# image قابل بازتولید باشد و به نسخه‌ی apt وابسته نماند.)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl \
      libjpeg62-turbo \
      zlib1g \
      libfreetype6 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/humsyar

# ── وابستگی پایتون ──
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir "supervisor==4.3.0"

# ── کد بک‌اند + ربات ──
COPY . .

# ── خروجی build فرانت‌اندها (dist داخل git نبود؛ از stage 1 می‌آید) ──
COPY --from=frontend /build/miniapp/dist  ./miniapp/dist
COPY --from=frontend /build/webadmin/dist ./webadmin/dist

# ── کاربر غیرroot ──
# /tmp تنها جایی است که این process می‌نویسد (heartbeat ربات) و
# از قبل world-writable است؛ هیچ داده‌ی ماندگار دیگری روی دیسک
# نوشته نمی‌شود (همه‌ی خروجی‌ها BytesIO و آپلودها در حافظه‌اند).
RUN groupadd --gid 10001 humsyar \
 && useradd  --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin humsyar \
 && mkdir -p /tmp \
 && chmod 1777 /tmp \
 && chown -R humsyar:humsyar /srv/humsyar
USER humsyar

ENV PORT=8000 \
    PYTHONPATH=/srv/humsyar \
    BOT_HEARTBEAT_FILE=/tmp/humsyar-bot-heartbeat.json

COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

# startCommand در railway.json همین است؛ اینجا هم به‌عنوان پیش‌فرض
# می‌گذاریم تا `docker run` خالی (بدون config) همان رفتار را داشته باشد.
ENTRYPOINT ["/entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf", "-n"]

# سلامت API — همان endpointی که Railway healthcheck می‌کند.
# عمداً /api/health و نه /api/health/deep: کرش‌کردن ربات نباید
# کانتینر را unhealthy و restart کند.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1
