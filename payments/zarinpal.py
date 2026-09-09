# -*- coding: utf-8 -*-
"""
💳 Zarinpal Gateway — sandbox + production

Env:
  ZARINPAL_MERCHANT_ID  — 36-char UUID (if empty → mock mode)
  ZARINPAL_SANDBOX      — 1/0 (default 1 if merchant empty else 0)
  ZARINPAL_CALLBACK_URL — frontend callback base, e.g. https://humsyar.ir/payment/verify
  WEBAPP_URL            — fallback

API v4: request.json + verify.json  (amount in Rial)
Our plan.price is in Toman → Rial = Toman * 10

Mock mode: when merchant unset, we generate TEST-authority and verify always succeeds.
This allows local dev / Railway without real Zarinpal credentials.

Idempotency: authority is stored on sub_payments doc (field zarinpal_authority)
and verified only once via atomic CAS (pending_zarinpal → approved).

"""
import os
import uuid
import logging
import httpx

logger = logging.getLogger(__name__)

MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID", "").strip()
# if merchant empty, default sandbox mock = true
_sandbox_env = os.getenv("ZARINPAL_SANDBOX", "").strip().lower()
if _sandbox_env in ("1", "true", "yes", "on"):
    SANDBOX = True
elif _sandbox_env in ("0", "false", "no", "off"):
    SANDBOX = False
else:
    SANDBOX = not bool(MERCHANT_ID)  # auto mock if no merchant

CALLBACK_BASE = (os.getenv("ZARINPAL_CALLBACK_URL", "") or os.getenv("WEBAPP_URL", "")).strip().rstrip("/")

def _is_mock() -> bool:
    return not MERCHANT_ID or MERCHANT_ID.lower() in ("test", "mock", "sandbox")

def _api_base() -> str:
    return "https://sandbox.zarinpal.com/pg/v4/payment" if SANDBOX else "https://api.zarinpal.com/pg/v4/payment"

def _pay_url(authority: str) -> str:
    if SANDBOX:
        return f"https://sandbox.zarinpal.com/pg/StartPay/{authority}"
    return f"https://www.zarinpal.com/pg/StartPay/{authority}"

async def zarinpal_request(amount_toman: int, description: str, callback_url: str = None,
                            mobile: str = None, email: str = None) -> dict:
    """
    Create payment request. Returns {authority, url, code}
    amount_toman: price in Toman (int)
    callback_url: where Zarinpal redirects after pay (with Authority & Status)
    """
    amount_rial = int(amount_toman) * 10
    if amount_rial < 1000:
        raise ValueError("amount too small for Zarinpal (min 1000 Rial)")
    if not description:
        description = "خرید اشتراک هامشیار"
    description = description[:120]
    cb = (callback_url or CALLBACK_BASE or "https://humsyar.ir/payment/verify").strip()
    # Mock
    if _is_mock():
        authority = f"A000000000000000000000000000{uuid.uuid4().hex[:6]}"
        # Use deterministic prefix for mock detection in verify
        authority = "TEST-" + uuid.uuid4().hex[:28].upper()
        url = _pay_url(authority)
        logger.info(f"[ZARINPAL MOCK] request amount={amount_toman}T ({amount_rial}R) desc={description} cb={cb} -> {authority}")
        return {"authority": authority, "url": url, "code": 100, "mock": True}

    url = f"{_api_base()}/request.json"
    payload = {
        "merchant_id": MERCHANT_ID,
        "amount": amount_rial,
        "callback_url": cb,
        "description": description,
    }
    metadata = {}
    if mobile:
        metadata["mobile"] = mobile
    if email:
        metadata["email"] = email
    if metadata:
        payload["metadata"] = metadata

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    # Zarinpal returns {"data": {"code":100, "authority":"...", ...}, "errors": {...}}
    d = data.get("data") or {}
    code = int(d.get("code", 0))
    authority = d.get("authority", "")
    if code != 100 or not authority:
        logger.warning(f"zarinpal request failed code={code} resp={data}")
        # Try to extract error message
        err = data.get("errors") or {}
        # errors may be dict with message/code
        raise RuntimeError(f"zarinpal_request_failed code={code} err={err}")
    pay_url = _pay_url(authority)
    return {"authority": authority, "url": pay_url, "code": code, "mock": False}

async def zarinpal_verify(authority: str, amount_toman: int) -> dict:
    """
    Verify payment after redirect. Returns {ok, ref_id, card_pan, fee, code, mock}
    amount_toman must match original request (Toman)
    """
    amount_rial = int(amount_toman) * 10
    if not authority:
        raise ValueError("authority required")
    # Mock verify
    if authority.startswith("TEST-") or _is_mock():
        # In mock, authority starting with TEST- always succeeds
        ref_id = int(uuid.uuid4().int % 900000) + 100000
        logger.info(f"[ZARINPAL MOCK] verify authority={authority} amount={amount_toman}T -> ref {ref_id}")
        return {"ok": True, "ref_id": str(ref_id), "code": 100, "mock": True, "card_pan": "6037-****-****-0000"}

    url = f"{_api_base()}/verify.json"
    payload = {
        "merchant_id": MERCHANT_ID,
        "amount": amount_rial,
        "authority": authority,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    d = data.get("data") or {}
    code = int(d.get("code", -1))
    # 100 success, 101 already verified
    if code in (100, 101):
        return {"ok": True, "ref_id": str(d.get("ref_id", "")), "code": code,
                "card_pan": d.get("card_pan", ""), "card_hash": d.get("card_hash", ""),
                "fee": d.get("fee", 0), "mock": False}
    logger.warning(f"zarinpal verify failed authority={authority} code={code} resp={data}")
    return {"ok": False, "code": code, "errors": data.get("errors"), "mock": False}
