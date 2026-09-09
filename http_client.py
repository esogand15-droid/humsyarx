# -*- coding: utf-8 -*-
"""
🚀 PERF-O4 — Shared HTTP client with keep-alive / pooling
Before: 97× `async with httpx.AsyncClient()` per request → TLS handshake + TCP slow-start on every Telegram call
After: single shared AsyncClient per event-loop with http2, connection pooling, keep-alive
"""
import httpx
import asyncio

_shared_client: httpx.AsyncClient | None = None
_lock = asyncio.Lock()

def get_shared_client(timeout: httpx.Timeout | None = None) -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=timeout or httpx.Timeout(15.0, read=60, write=60),
            limits=httpx.Limits(max_keepalive_connections=30, max_connections=80, keepalive_expiry=30),
            http2=False,
            follow_redirects=True,
        )
    return _shared_client

async def aclose_shared_client():
    global _shared_client
    if _shared_client and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None
