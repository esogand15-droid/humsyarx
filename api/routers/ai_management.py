"""Administrative controls for Hoshyar AI."""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from pydantic import (
    BaseModel,
    Field,
)

from api.auth import (
    require_perm,
)

from ai_solver import (
    AIError,
    ai_catalog_payload,
    ask_ai,
    get_ai_config,
    list_provider_models,
    set_ai_setting,
    set_api_key_for_provider,
    delete_api_key_for_provider,
    add_api_key_for_provider,
    remove_api_key_for_provider,
    list_api_keys_for_provider,
    test_all_keys_for_provider,
    get_models_health,
    merge_models_with_health,
    sanitize_api_key,
    api_key_problem,
)

# ⭐ م7 — providerهای مجازِ Vault (برای endpointهای چند-کلیدی)
_VAULT_PROVIDERS = ("gemini", "openrouter", "groq", "cerebras", "mistral",
                    "deepseek", "nvidia", "huggingface", "together")

from database import db
from request_context import current_request_id

async def _ai_audit(actor_id: int, action: str, *, before=None, after=None, target_id="", target_label=""):
    try:
        u = await db.get_user(actor_id)
        name = (u or {}).get("name", str(actor_id))
        try:
            role_label = await db.get_actor_role_label(actor_id)
        except Exception:
            role_label = "owner" if actor_id == 0 else "admin"
        await db.log_action(
            actor_id, name, role_label,
            action, "AI", category="ai", severity="HIGH",
            target_id=str(target_id), target_type="user", target_label=target_label or str(target_id),
            before=before, after=after, tags=["هوشیار", "دسترسی"],
        )
    except Exception:
        pass


router = APIRouter()


class ConfigUpdate(BaseModel):
    enabled: bool

    provider: str = Field(
        pattern=(
            "^(gemini|openrouter|groq|cerebras|mistral|deepseek|nvidia|huggingface|together)$"
        )
    )

    model: str = Field(
        min_length=2,
        max_length=150,
    )

    daily_limit: int = Field(
        ge=0,
        le=1000,
    )

    image_enabled: bool | None = None

    image_provider: str | None = Field(
        default=None,
        max_length=50,
    )

    image_model: str | None = Field(
        default=None,
        min_length=0,
        max_length=150,
    )

    # ⭐ م8 — پاسخ صوتی (TTS) + رزولوشن تصویر
    voice_reply: str | None = Field(default=None, max_length=8)

    voice_with_text: str | None = Field(default=None, max_length=4)

    tts_voice: str | None = Field(default=None, max_length=40)

    tts_model: str | None = Field(default=None, max_length=80)

    voice_reply_max_chars: int | None = Field(default=None, ge=100, le=4000)

    image_size: str | None = Field(default=None, max_length=4)

    image_daily_limit: int | None = Field(
        default=None,
        ge=0,
        le=1000,
    )

    # ⭐ م9 — تماس صوتی زنده (Gemini Live API)
    live_enabled: bool | None = None
    live_model: str | None = Field(default=None, max_length=150)
    live_voice: str | None = Field(default=None, max_length=40)
    live_thinking_level: str | None = Field(default=None, max_length=20)
    live_daily_minutes: int | None = Field(default=None, ge=0, le=600)
    live_max_session_sec: int | None = Field(default=None, ge=60, le=1800)
    live_target_language: str | None = Field(default=None, max_length=10)

    thinking: str = Field(
        pattern="^(auto|high)$"
    )

    system_prompt: str = Field(
        min_length=20,
        max_length=20000,
    )

    disabled_message: str = Field(
        default="",
        max_length=1000,
    )

    api_key: str | None = Field(
        default=None,
        max_length=500,
    )

    api_keys: dict | None = Field(
        default=None,
    )


class UserAction(BaseModel):
    user_id: int = Field(
        gt=0
    )


@router.get("/models")
async def models_catalog(
    provider: str | None = None,
    refresh: bool = False,
    admin=Depends(require_perm("ai.manage")),
):
    """🌊 W9 — کاتالوگ مرکزی providerها/مدل‌ها برای UI (بدون تایپ دستی).

    🔴 FIX-R1 (مورد ۷) — با provider: فهرست زنده‌ی مدل‌ها از خود
    ارائه‌دهنده با همان API key (auto-detect) برمی‌گردد؛ بدون provider
    همان کاتالوگ ثابت (fallback آفلاین)."""
    if provider:
        cfg = await get_ai_config()
        api_key = (cfg.get("api_keys") or {}).get(provider, "")
        listing = await list_provider_models(provider, api_key, refresh=refresh)
        # ⭐ م8 — ادغامِ سلامتِ ذخیره‌شده: زنده‌ها و رایگان‌ها صدر فهرست
        health = await get_models_health(provider)
        if health:
            listing = dict(listing)
            listing["models"] = merge_models_with_health(
                provider, listing.get("models") or [], health)
        return listing
    return ai_catalog_payload()


@router.get("/config")
async def config(
    admin=Depends(require_perm("ai.manage")),
):
    value = (
        await get_ai_config()
    )

    vault = value.get("vault") or value.get("api_keys") or {}
    return {
        "enabled":
            value["enabled"],

        "provider":
            value["provider"],

        "model":
            value["model"],

        "daily_limit":
            value["daily_limit"],

        "thinking":
            value["thinking"],

        "image_enabled":
            value["image_enabled"],

        "image_provider":
            value.get("image_provider", value["provider"]),

        "image_model":
            value["image_model"],

        "image_daily_limit":
            value["image_daily_limit"],

        "system_prompt":
            value[
                "system_prompt"
            ],

        "disabled_message":
            value[
                "disabled_message"
            ],

        # کلید API هیچ‌وقت به مرورگر ارسال نمی‌شود — فقط وضعیت وجود
        "has_api_key":
            bool(
                value["api_key"]
            ),

        "has_api_keys":
            {k: True for k, v in (vault or {}).items() if v},

        "vault":
            {k: bool(v) for k, v in (vault or {}).items()},

        # ⭐ م8 — پاسخ صوتی (TTS) + رزولوشن تصویر
        "voice_reply":
            value.get("voice_reply", "voice"),

        "voice_with_text":
            value.get("voice_with_text", "off"),

        "tts_voice":
            value.get("tts_voice", ""),

        "tts_model":
            value.get("tts_model", ""),

        "voice_reply_max_chars":
            value.get("voice_reply_max_chars", 500),

        "image_size":
            value.get("image_size", "1K"),

        # ⭐ م9 — تماس صوتی زنده (Gemini Live API)
        "live_enabled":
            value.get("live_enabled", True),

        "live_model":
            value.get("live_model", "gemini-3.8-live"),

        "live_voice":
            value.get("live_voice", value.get("tts_voice", "Sulafat")),

        "live_thinking_level":
            value.get("live_thinking_level", "low"),

        "live_daily_minutes":
            value.get("live_daily_minutes", 15),

        "live_max_session_sec":
            value.get("live_max_session_sec", 300),

        "live_target_language":
            value.get("live_target_language", "fa"),
    }


@router.put("/config")
async def update_config(
    body: ConfigUpdate,

    admin=Depends(require_perm("ai.manage")),
):
    editable_fields = (
        "enabled",
        "provider",
        "model",
        "daily_limit",
        "thinking",
        "system_prompt",
        "disabled_message",
        "image_enabled",
        "image_model",
        "image_daily_limit",
        "image_provider",
        # ⭐ م8 — پاسخ صوتی + رزولوشن تصویر + مدل TTS
        "voice_reply",
        "voice_with_text",
        "tts_voice",
        "tts_model",
        "voice_reply_max_chars",
        "image_size",
        # ⭐ م9 — تماس صوتی زنده (Gemini Live API)
        "live_enabled",
        "live_model",
        "live_voice",
        "live_thinking_level",
        "live_daily_minutes",
        "live_max_session_sec",
        "live_target_language",
    )

    for key in editable_fields:
        val = getattr(body, key, None)
        if val is not None:
            # image_provider may be None/empty meaning auto-detect
            if key == "image_provider" and not val:
                continue
            # ⭐ م8.4 — اگر image_model خالی فرستاده شده، مقدار فعلی دیتابیس را پاک نکن
            if key == "image_model":
                val = str(val).strip()
                if not val:
                    continue
                if val.startswith(("gemini", "imagen")):
                    await set_ai_setting("image_provider", "gemini")
            await set_ai_setting(
                key,
                val,
            )

    # Vault: اگر دیکشنری api_keys فرستاده شده — هر provider جداگانه
    if body.api_keys and isinstance(body.api_keys, dict):
        for prov, key in body.api_keys.items():
            if not prov:
                continue
            k = (key or "").strip()
            if k:
                await set_api_key_for_provider(prov.strip(), k)
            elif k == "":
                # خالی یعنی حذف
                await delete_api_key_for_provider(prov.strip())

    # فقط اگر کلید جدیدی وارد شده باشد کلید قبلی جایگزین می‌شود.
    # این کلید برای provider فعلی در vault ذخیره می‌شود (auto-vault)
    # 🔴 FIX-R1 (مورد ۶) — کلید پیش از ذخیره پاکسازی/اعتبارسنجی می‌شود؛
    # کلید کثیف (کاراکتر نامرئی/فارسی) همان‌جا 422 می‌گیرد و دیگر هرگز
    # خطای ascii موقع استفاده ساخته نمی‌شود.
    if (
        body.api_key
        and body.api_key.strip()
    ):
        try:
            await set_api_key_for_provider(body.provider, body.api_key)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    # 🔴 FIX-R1 (مورد ۷) — اعتبارسنجی مدل انتخاب‌شده با فهرست زنده‌ی
    # provider: اگر فهرست در دسترس بود و مدل داخلش نبود، ذخیره رد
    # می‌شود (مدل فیک/منقضی انتخاب‌شدنی نیست). فهرست در دسترس نبود
    # (شبکه/کلید) → عبور با هشدار تا عملیات آفلاین بلاک نشود.
    model_warning = ""
    if body.model and body.model.strip():
        model_id = body.model.strip()
        cfg_now = await get_ai_config()
        vault = cfg_now.get("api_keys") or {}
        live = await list_provider_models(body.provider, vault.get(body.provider, ""))
        if not live.get("fallback") and live.get("models"):
            ids = [m["id"] for m in live["models"]]
            if model_id not in ids:
                raise HTTPException(
                    status_code=422,
                    detail=("این مدل در فهرست واقعی مدل‌های ارائه‌دهنده "
                            f"«{body.provider}» نیست و انتخاب شدنی نیست. "
                            "از فهرست «به‌روزرسانی مدل‌ها» یکی انتخاب کنید."),
                )
        elif live.get("error"):
            model_warning = live["error"]

    return {
        "ok": True,
        "model_warning": model_warning,
    }


class KeyAdd(BaseModel):
    api_key: str = Field(min_length=8, max_length=400)


class VaultUpdate(BaseModel):
    api_key: str = Field(max_length=500)


@router.get("/vault")
async def vault_status(
    admin=Depends(require_perm("ai.manage")),
):
    cfg = await get_ai_config()
    vault = cfg.get("vault") or {}
    # فقط وضعیت وجود، نه خود کلید
    return {
        "vault": {k: bool(v) for k, v in vault.items()},
        "providers": list(vault.keys()),
    }


@router.put("/vault/{provider}")
async def vault_set(
    provider: str,
    body: VaultUpdate,
    admin=Depends(require_perm("ai.manage")),
):
    provider = provider.strip()
    if provider not in ("gemini","openrouter","groq","cerebras","mistral","deepseek","nvidia","huggingface","together"):
        raise HTTPException(status_code=400, detail="provider نامعتبر")
    key = (body.api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="کلید نمی‌تواند خالی باشد")
    # 🔴 FIX-R1 (مورد ۶) — اعتبارسنجی پیش از ذخیره (پیام فارسی روشن)
    problem = api_key_problem(key)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    try:
        await set_api_key_for_provider(provider, key)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # 🌊 W6/RBAC — نوشتن سکرت با actor تفویض‌شده: audit بدون ماده‌ی کلید
    await _ai_audit(admin["id"], "ثبت کلید API هوشیار",
                    target_id=provider, target_label=provider)
    return {"ok": True, "provider": provider}


@router.delete("/vault/{provider}")
async def vault_delete(
    provider: str,
    admin=Depends(require_perm("ai.manage")),
):
    provider = provider.strip()
    await delete_api_key_for_provider(provider)
    # 🌊 W6/RBAC — حذف سکرت: audit
    await _ai_audit(admin["id"], "حذف کلید API هوشیار",
                    target_id=provider, target_label=provider)
    return {"ok": True, "provider": provider}


# ══════════════════════════════════════════════════
# ⭐ م7 — مدیریت چند-کلیدی با فال‌بک خودکار
# هر provider می‌تواند چند کلید داشته باشد؛ در صورتِ سهمیه/خطا،
# درخواست به‌صورت خودکار با کلید بعدیِ سالم ادامه می‌یابد.
# ══════════════════════════════════════════════════
@router.get("/vault/{provider}/keys")
async def vault_keys_list(
    provider: str,
    admin=Depends(require_perm("ai.manage")),
):
    if provider.strip() not in _VAULT_PROVIDERS:
        raise HTTPException(status_code=400, detail="provider نامعتبر")
    return await list_api_keys_for_provider(provider.strip())


@router.post("/vault/{provider}/keys")
async def vault_key_add(
    provider: str,
    body: KeyAdd,
    admin=Depends(require_perm("ai.manage")),
):
    provider = provider.strip()
    if provider not in _VAULT_PROVIDERS:
        raise HTTPException(status_code=400, detail="provider نامعتبر")
    key = (body.api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="کلید نمی‌تواند خالی باشد")
    problem = api_key_problem(key)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    try:
        count = await add_api_key_for_provider(provider, key)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _ai_audit(admin["id"], "افزودن کلید فال‌بک هوشیار",
                    target_id=provider, target_label=provider)
    return {"ok": True, "provider": provider, "count": count}


@router.delete("/vault/{provider}/keys/{index}")
async def vault_key_delete(
    provider: str,
    index: int,
    admin=Depends(require_perm("ai.manage")),
):
    provider = provider.strip()
    if provider not in _VAULT_PROVIDERS:
        raise HTTPException(status_code=400, detail="provider نامعتبر")
    try:
        removed = await remove_api_key_for_provider(provider, index)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await _ai_audit(admin["id"], "حذف کلید فال‌بک هوشیار",
                    target_id=provider, target_label=provider)
    return {"ok": True, "provider": provider, "removed": removed}


@router.post("/vault/{provider}/keys/test")
async def vault_keys_test(
    provider: str,
    admin=Depends(require_perm("ai.manage")),
):
    if provider.strip() not in _VAULT_PROVIDERS:
        raise HTTPException(status_code=400, detail="provider نامعتبر")
    result = await test_all_keys_for_provider(provider.strip())
    await _ai_audit(admin["id"], "تست کلیدهای فال‌بک هوشیار",
                    target_id=provider, target_label=provider)
    return result


@router.get("/stats")
async def stats(
    admin=Depends(require_perm("ai.manage")),
):
    raw = await db.ai_usage_stats(
        10
    )
    # 🌊 W-Admin — سریالایزر ساخت‌یافته برای وب‌ادمین (کلیدهای قدیمی
    # دست‌نخورده می‌مانند تا مصرف‌کننده‌های فعلی نشکنند): لیست‌های خام
    # tuple به‌جای رشته‌ی comma-separated، آبجکت {name,user_id,count} می‌شوند.
    def _rows(lst):
        return [
            {
                "name": (t[0] or "—"),
                "user_id": t[1],
                "count": t[2],
            }
            for t in (lst or [])
        ]

    raw["top_today_users"] = _rows(raw.get("top_today"))
    raw["top_alltime_users"] = _rows(raw.get("top_alltime"))
    return raw


@router.get("/reports")
async def reports(
    limit: int = Query(
        default=30,
        ge=1,
        le=100,
    ),

    admin=Depends(require_perm("ai.manage")),
):
    items = (
        await db.ai_recent_reports(
            limit
        )
    )

    return {
        "reports": [
            {
                "id":
                    str(item["_id"]),

                "user_id":
                    item.get(
                        "user_id"
                    ),

                "name":
                    item.get(
                        "name",
                        "",
                    ),

                "question":
                    item.get(
                        "question",
                        "",
                    ),

                "answer":
                    item.get(
                        "answer",
                        "",
                    ),

                "created_at":
                    str(
                        item.get(
                            "created_at",
                            "",
                        )
                    )[:19],
            }

            for item in items
        ],
    }


@router.get("/banned")
async def banned(
    admin=Depends(require_perm("ai.manage")),
):
    items = (
        await db.ai_list_banned(
            100
        )
    )

    return {
        "users": [
            {
                "id":
                    item.get(
                        "user_id"
                    ),

                "name":
                    item.get(
                        "name",
                        "",
                    ),
            }

            for item in items
        ],
    }


@router.get("/users")
async def users(
    q: str = Query(
        ...,
        min_length=2,
        max_length=100,
    ),

    admin=Depends(require_perm("ai.manage")),
):
    items = (
        await db.search_users(
            q.strip()
        )
    )

    return {
        "users": [
            {
                "id":
                    item.get(
                        "user_id"
                    ),

                "name":
                    item.get(
                        "name",
                        "",
                    ),

                "banned":
                    bool(
                        item.get(
                            "ai_banned"
                        )
                    ),

                "usage_today":
                    item.get(
                        "ai_usage_count",
                        0,
                    ),

                "usage_total":
                    item.get(
                        "ai_total_usage",
                        0,
                    ),
            }

            for item in items

            if item.get(
                "approved"
            )
        ],
    }


@router.post("/users/ban")
async def toggle_ban(
    body: UserAction,

    admin=Depends(require_perm("ai.manage")),
):
    user = (
        await db.get_user(
            body.user_id
        )
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="کاربر پیدا نشد",
        )

    new_state = not bool(
        user.get("ai_banned")
    )

    await db.ai_set_banned(
        body.user_id,
        new_state,
    )
    # AUDIT — toggle AI ban
    await _ai_audit(admin["id"], "تغییر دسترسی کاربر به هوشیار", before={"banned": not new_state}, after={"banned": new_state}, target_id=str(body.user_id), target_label=(user or {}).get("name",""))

    return {
        "ok":
            True,

        "banned":
            new_state,
    }


@router.post(
    "/users/reset-quota"
)
async def reset_quota(
    body: UserAction,

    admin=Depends(require_perm("ai.manage")),
):
    result = (
        await db.users.update_one(
            {
                "user_id":
                    body.user_id,
            },

            {
                "$set": {
                    "ai_usage_count":
                        0,

                    "ai_tokens_today":
                        0,
                }
            },
        )
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="کاربر پیدا نشد",
        )
    # AUDIT — reset AI quota
    try:
        _target = await db.get_user(body.user_id)
    except Exception:
        _target = None
    await _ai_audit(admin["id"], "صفرکردن سهمیه روزانه هوشیار", before={"usage": int(( _target or {}).get("ai_usage_count") or 0)}, after={"usage": 0}, target_id=str(body.user_id), target_label=(_target or {}).get("name",""))

    return {
        "ok": True,
    }


@router.delete(
    "/users/{user_id}/profile"
)
async def clear_profile(
    user_id: int,

    admin=Depends(require_perm("ai.manage")),
):
    user = (
        await db.get_user(
            user_id
        )
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="کاربر پیدا نشد",
        )

    await db.ai_forget_profile(
        user_id
    )

    await db.ai_clear_memory(
        user_id
    )

    return {
        "ok": True,
    }


@router.post("/test")
async def test_connection(
    admin=Depends(require_perm("ai.manage")),
):
    try:
        answer, tokens = (
            await ask_ai(
                text=(
                    "فقط بنویس: "
                    "اتصال موفق است."
                ),

                history=[],

                uid=
                    admin["id"],
            )
        )

    except AIError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        )

    except Exception:
        raise HTTPException(
            status_code=502,

            detail=(
                "آزمایش اتصال "
                "ناموفق بود"
            ),
        )

    return {
        "ok":
            True,

        "answer":
            answer,

        "tokens":
            int(tokens or 0),
    }
