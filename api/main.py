"""🏥 هامزیار Mini App — FastAPI Backend v2.0"""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.routers import (
    academic_admin,
    admin_panel,
    ai,
    ai_management,
    content_admin,
    dashboard,
    faq,
    global_search,
    grades,
    notifications,
    profile,
    questions,
    rbac,
    references,
    registration,
    reports,
    resources,
    schedule,
    subscription,
    subscription_management,
    tickets,
    web_admin,
)
from database import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.gather(
        db.ensure_indexes(),
        questions.ensure_indexes(),
    )

    yield

    db.client.close()


app = FastAPI(
    title="Humsyar API",
    version="2.0.0",
    lifespan=lifespan,
)

WEBAPP_URL = os.getenv(
    "WEBAPP_URL",
    "*",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        [WEBAPP_URL]
        if WEBAPP_URL != "*"
        else ["*"]
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🗜 موج ۴.۶۰ — فشرده‌سازی پاسخ‌های JSON بزرگ؛
# payloadهای چند‌ده‌KB (لیست کاربران/رسیدها/آمار)
# روی شبکه‌ی موبایل محسوس کوچک‌تر و سریع‌تر می‌شوند.
# فقط بالای ۱KB — پاسخ‌های کوچک سربار نمی‌گیرند.
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,
)


app.include_router(
    dashboard.router,
    prefix="/api/dashboard",
)

app.include_router(
    questions.router,
    prefix="/api/questions",
)

app.include_router(
    schedule.router,
    prefix="/api/schedule",
)

app.include_router(
    resources.router,
    prefix="/api/resources",
)

app.include_router(
    profile.router,
    prefix="/api/profile",
)

app.include_router(
    notifications.router,
    prefix="/api/notifications",
)

app.include_router(
    references.router,
    prefix="/api/references",
)

app.include_router(
    faq.router,
    prefix="/api/faq",
)

app.include_router(
    tickets.router,
    prefix="/api/tickets",
)

app.include_router(
    registration.router,
    prefix="/api/auth",
)

app.include_router(
    reports.router,
    prefix="/api/reports",
)

app.include_router(
    grades.router,
    prefix="/api/grades",
)

app.include_router(
    subscription.router,
    prefix="/api/subscription",
)

app.include_router(
    ai.router,
    prefix="/api/ai",
)

app.include_router(
    global_search.router,
    prefix="/api/search",
)

app.include_router(
    subscription_management.router,
    prefix="/api/subscription-admin",
)

app.include_router(
    ai_management.router,
    prefix="/api/ai-admin",
)

app.include_router(
    content_admin.router,
    prefix="/api/content",
)

app.include_router(
    academic_admin.router,
    prefix="/api/academic-admin",
)

app.include_router(
    admin_panel.router,
    prefix="/api/admin",
)

# 🛡 موج RBAC-W1 — مدیریت نقش‌ها/مجوزها (تک‌منبع حقیقت)
# افزایشی خالص: هیچ route قدیمی جابه‌جا/تغییر نکرده است.
app.include_router(
    rbac.router,
    prefix="/api/admin/rbac",
    tags=["rbac"],
)

# 🖥️ موج WA — Web Admin API (احراز هویت OTP + سشن، داشبورد و اکشن‌های وب)
app.include_router(
    web_admin.router,
    prefix="/api/web-admin",
    tags=["web-admin"],
)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0.0",
    }


# ──────────────────────────────────────────────────────────
#  🖥️ موج WA — سرو Web Admin SPA روی همان دامنه‌ی Railway:
#  /admin/* → فایل‌های استاتیک build فرانت (webadmin/dist)
#  - SPA fallback: هر مسیر /admin/... بدون فایل ⇒ index.html
#  - /api/* و سایر routeهای فعلی کاملاً دست‌نخورده‌اند.
# ──────────────────────────────────────────────────────────
_WA_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "webadmin", "dist")
if os.path.isdir(_WA_DIST):
    from fastapi.staticfiles import StaticFiles

    class _WebAdminSPA(StaticFiles):
        """StaticFiles + fallback به index.html برای مسیرهای SPA (بدون تغییر 404های /api)."""

        async def get_response(self, path: str, scope):   # noqa: D401
            from starlette.exceptions import HTTPException as StarletteHTTPException
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code == 404:
                    return await super().get_response("index.html", scope)
                raise

    app.mount("/admin", _WebAdminSPA(directory=_WA_DIST, html=True), name="web-admin-spa")
else:
    @app.get("/admin")
    async def _wa_not_built():
        return {"detail": "web-admin build not present (webadmin/dist)"}
