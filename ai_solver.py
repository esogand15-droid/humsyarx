"""
🤖 هوشیار — موتور هوش مصنوعی حل سوالات درسی (متن/عکس)
  ✅ هیچ‌چیز هاردکد نیست: کلید API، ارائه‌دهنده، مدل، محدودیت روزانه و
     دستور سیستمی همگی از bot_settings (پنل ادمین → ai_admin.py) خوانده
     می‌شوند.
  ✅ معماری چندارائه‌دهنده: برای اضافه‌کردن یک AI دیگر (مثلاً OpenRouter/
     OpenAI) فقط یک تابع جدید به STREAM_PROVIDERS اضافه می‌شود — بقیه‌ی کد و
     پنل ادمین دست‌نخورده باقی می‌ماند.
  ✅ محدودیت روزانه‌ی سوال، به‌ازای هر کاربر (روی خودِ سند کاربر در
     دیتابیس ذخیره می‌شود؛ نیازی به کالکشن جدید نیست).
"""
import os
import re
import json
import time
import shutil
import base64
import random
import asyncio
import logging
import unicodedata
from utils import esc as _esc   # 🛡 AUDIT-A6 —escape مرکزی (پارامتر quote حفظ است)
from collections import deque, OrderedDict
from datetime import datetime
from time_utils import (
    format_date_fa, format_datetime_fa, format_time_fa,
    now_utc, parse_machine_datetime, today_tehran, utc_now_iso,
)

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import db
try:
    from utils_crypto import decrypt_value, encrypt_value, is_encryption_enabled
except Exception:
    decrypt_value = lambda x: x if isinstance(x,str) else (x.get("c","") if isinstance(x,dict) else str(x or ""))
    encrypt_value = lambda x: x
    is_encryption_enabled = lambda: False

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# ══════════════════════════════════════════════════
#  🔴 FIX-R1 (مورد ۶) — پاکسازی و اعتبارسنجی کلید API
#
#  ریشه‌ی خطای «'ascii' codec can't encode characters»: کلیدی که از
#  کپی/پیست می‌آید ممکن است کاراکترهای نامرئی (ZWNJ/ZWSP/BOM/RTL-mark)،
#  ارقام فارسی یا نقل‌قول هوشمند داشته باشد؛ httpx مقدار هدر را با
#  ascii انکد می‌کند و همان خطای مبهم بالا ساخته می‌شود. این ماژول
#  «یک نقطه‌ی پاکسازی» برای همه‌ی مسیرهاست (ربات + پنل + مینی‌اپ).
# ══════════════════════════════════════════════════
_FA_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
# کاراکترهای نامرئی/کنترلی که در کپی/پیست کلید نفوذ می‌کنند
# (نقل‌قول‌های هوشمند با escape تا سورس ASCII-تمیز بماند)
_INVISIBLE_CHARS = [
    '\u200b',  # ZWSP (zero width space)
    '\u200c',  # ZWNJ (zero width non-joiner — نیم‌فاصله!)
    '\u200d',  # ZWJ
    '\u200e',  # LRM left-to-right mark
    '\u200f',  # RLM right-to-left mark
    '\u202a', '\u202b', '\u202c', '\u202d', '\u202e',  # bidi overrides
    '\ufeff',  # BOM
    '\u2060',  # word joiner
    '\u00a0',  # NBSP
    '\u3000',  # ideographic space
    '\u201c', '\u201d',  # " "
    '\u2018', '\u2019',  # ' '
    '\u00ab', '\u00bb',  # « »
]


def sanitize_api_key(key: str) -> str:
    """پاکسازی کلید API: حذف فاصله‌ها/کاراکترهای نامرئی + ارقام فارسی→لاتین.

    هم موقع ذخیره (پنل/ربات) و هم موقع خواندن (get_ai_config) اجرا
    می‌شود تا کلیدِ قدیمیِ کثیف هم بدون دخالت دوباره سالم کار کند."""
    if not key or not isinstance(key, str):
        return ''
    out = key.translate(_FA_DIGITS)
    for ch in _INVISIBLE_CHARS:
        out = out.replace(ch, '')
    # حذف هر کاراکتر کنترلی/نامرئی باقی‌مانده (Cc/Cf/Zs غیر از فاصله عادی)
    out = ''.join(c for c in out
                  if c == ' ' or (ord(c) >= 32 and not unicodedata.category(c) in ('Cc', 'Cf')))
    out = out.strip()
    return out


def api_key_problem(key: str) -> str | None:
    """اگر کلید پس از پاکسازی هم قابل‌استفاده نیست، متن فارسی مشکل را
    برمی‌گرداند؛ در غیر این صورت None (کلید سالم)."""
    cleaned = sanitize_api_key(key)
    if not cleaned:
        return None  # خالی بودن جای خودش هندل می‌شود
    try:
        cleaned.encode('ascii')
    except UnicodeEncodeError:
        return ("کلید API شامل حروف غیرمجاز (فارسی/کاراکتر نامرئی) است — "
                "کلید را دوباره از سایت ارائه‌دهنده کپی کنید. کاراکترهای "
                "معتبر کلید فقط حروف لاتین، رقم و علامت‌ها هستند.")
    if ' ' in cleaned:
        return "کلید API نباید فاصله داشته باشد — کلید را یک‌تکه کپی کنید."
    if len(cleaned) < 8:
        return "کلید API خیلی کوتاه است — کلید کامل را کپی کنید."
    return None





# ══════════════════════════════════════════════════
#  پیش‌فرض‌ها — فقط وقتی استفاده می‌شن که ادمین هنوز چیزی ست نکرده
# ══════════════════════════════════════════════════
DEFAULT_MODELS = {
    # ⭐ م8 (چنج‌لاگ ۲۰۲۶-۰۹-۱۸): دسترسیِ مدل‌های 2.5 برای پروژه‌های جدید
    # محدود شده؛ توصیه‌ی گوگل: 3.5-flash-lite (سریع/ارزان) یا 3.8-flash.
    'gemini':     'gemini-3.6-flash',
    'openrouter': 'google/gemma-4-31b-it:free',
    'groq':       'llama-3.3-70b-versatile',
    'cerebras':   'llama-3.3-70b',
    'mistral':    'mistral-large-latest',
    'deepseek':   'deepseek-chat',
    'nvidia':     'deepseek-ai/deepseek-v3',
    'huggingface':'meta-llama/Meta-Llama-3.1-70B-Instruct',
    'together':   'meta-llama/Llama-3.3-70B-Instruct-Turbo',
}

# ══════════════════════════════════════════════════
#  🌊 W9 — کاتالوگ مرکزی providerها و مدل‌ها (منبع واحد حقیقت).
#  بات (ai_admin)، پنل وب و مینی‌اپ همه از همین‌جا می‌خوانند تا
#  هیچ‌جا مدل دستی تایپ نشود. base_urlها اندپوینتِ سازگار با
#  OpenAI هر provider است (همه‌شان /chat/completions دارند).
# ══════════════════════════════════════════════════
PROVIDERS = {
    'gemini': {
        'label': '🟦 Google Gemini',
        'url': None,   # مسیر اختصاصیِ خودش (_stream_gemini)
        'vision': True, 'images': True,
    },
    'openrouter': {
        'label': '🟪 OpenRouter — هاب مدل‌های رایگان (freellm.net)',
        'url': 'https://openrouter.ai/api/v1',
        'vision': True, 'images': True,
    },
    'groq': {
        'label': '🟧 Groq — سریع‌ترین inference',
        'url': 'https://api.groq.com/openai/v1',
        'vision': False, 'images': True,
    },
    'cerebras': {
        'label': '🟨 Cerebras',
        'url': 'https://api.cerebras.ai/v1',
        'vision': False, 'images': False,
    },
    'mistral': {
        'label': '🟠 Mistral — ۱ میلیارد توکن/ماه رایگان',
        'url': 'https://api.mistral.ai/v1',
        'vision': False, 'images': False,
    },
    'deepseek': {
        'label': '🐋 DeepSeek — استدلال قوی و ارزان',
        'url': 'https://api.deepseek.com/v1',
        'vision': False, 'images': False,
    },
    # 🌊 FreeLLM-favorite free providers — OpenAI-compatible base_url
    'nvidia': {
        'label': '🖥️ NVIDIA NIM — مدل‌های آزاد',
        'url': 'https://integrate.api.nvidia.com/v1',
        'vision': True, 'images': False,
    },
    'huggingface': {
        'label': '🤗 Hugging Face Inference',
        'url': 'https://api-inference.huggingface.co/v1',
        'vision': True, 'images': True,
    },
    'together': {
        'label': '🤝 Together AI — رایگان',
        'url': 'https://api.together.xyz/v1',
        'vision': True, 'images': True,
    },
}

# (شناسه‌ی مدل, برچسب فارسی, رایگان؟) — منبع: https://freellm.net/models/?free=1 (299 مدل رایگان، 239 تأیید Live 2026-09-08)
MODEL_CATALOG = {
    'gemini': [
        ('gemini-3.6-flash',      '🌟 Gemini 3.6 Flash (جدیدترین، پیشنهادی)', False),
        ('gemini-3.5-flash',      '🆕 Gemini 3.5 Flash (قوی، استدلال سنگین)', False),
        ('gemini-3.5-flash-lite', '🆕 Gemini 3.5 Flash-Lite (سریع/ارزان)', False),
        ('gemini-2.5-flash',      '⚡ Gemini 2.5 Flash (پایدار)', True),
        ('gemini-flash-latest',   '🔄 Gemini Flash Latest', True),
        ('gemini-2.5-flash-lite', '💨 Gemini 2.5 Flash-Lite (سبک‌تر)', True),
        ('gemini-2.5-pro',        '🧠 Gemini 2.5 Pro (دقیق‌تر)', False),
        ('gemini-2.0-flash-exp',  '🧪 Gemini 2.0 Flash Exp (رایگان)', True),
    ],
    'openrouter': [
        # FreeLLM top free models aggregated under OpenRouter OpenAI-compatible API
        ('deepseek/deepseek-chat-v3-0324:free', '🐋 DeepSeek V3 (رایگان، freellm verified)', True),
        ('deepseek/deepseek-r1:free', '🧠 DeepSeek R1 (رایگان، استدلال)', True),
        ('qwen/qwen3-235b-a22b:free',           '🎯 Qwen3 235B (رایگان)', True),
        ('qwen/qwen3-coder:free',                '👨‍💻 Qwen3 Coder (رایگان)', True),
        ('qwen/qwen2.5-vl-32b-instruct:free',   '👁️ Qwen2.5 VL 32B (رایگان، vision)', True),
        ('google/gemma-3-27b-it:free',           '⚡ Gemma 3 27B (رایگان، vision)', True),
        ('google/gemma-4-31b-it:free',           '⚡ Gemma 4 31B (رایگان، تصویر+متن)', True),
        ('meta-llama/llama-3.3-70b-instruct:free', '🦙 Llama 3.3 70B Instruct (رایگان)', True),
        ('meta-llama/llama-4-maverick:free',    '🦙 Llama 4 Maverick (رایگان)', True),
        ('mistralai/mistral-small-3.1-24b-instruct:free', '🌪 Mistral Small 3.1 24B (رایگان)', True),
        ('thinkingmachines/inkling-small:free', '💡 Inkling Small (رایگان، image-capable)', True),
        ('inclusionai/ling-3.0-flash-sante:free','🌟 Ling 3.0 Sante (رایگان)', True),
        ('nvidia/llama-3.1-nemotron-70b-instruct:free', '🖥️ Nemotron 70B (رایگان)', True),
        ('openrouter/free',                     '🎲 انتخاب خودکار مدل رایگان', True),
    ],
    'groq': [
        ('llama-3.3-70b-versatile', '🦙 Llama 3.3 70B (رایگان، سریع)', True),
        ('llama-3.1-8b-instant',    '⚡ Llama 3.1 8B Instant (رایگان)', True),
        ('openai/gpt-oss-120b',     '🧠 GPT-OSS 120B (رایگان، استدلال)', True),
        ('openai/gpt-oss-20b',      '💨 GPT-OSS 20B (رایگان، سبک)', True),
        ('mixtral-8x7b-32768',      '🔀 Mixtral 8x7B (رایگان)', True),
        ('llama-3.2-11b-vision-preview', '👁️ Llama 3.2 11B Vision (رایگان)', True),
    ],
    'cerebras': [
        ('llama-3.3-70b',  '🦙 Llama 3.3 70B (رایگان)', True),
        ('qwen-3-32b',     '🎯 Qwen3 32B (رایگان)', True),
        ('llama-4-maverick-17b-128e-instruct', '🦙 Llama 4 Maverick 17B (رایگان)', True),
    ],
    'mistral': [
        ('mistral-large-latest', '🌪 Mistral Large (پرچم‌دار)', False),
        ('mistral-small-latest', '💨 Mistral Small (سریع)', False),
        ('codestral-latest',     '👨‍💻 Codestral (کدنویسی)', False),
        ('mistral-small-3.1-24b-instruct:free','💨 Mistral Small 3.1 24B (رایگان FreeLLM)', True),
    ],
    'deepseek': [
        ('deepseek-chat',     '💬 DeepSeek V3 (چت عمومی)', False),
        ('deepseek-reasoner', '🧠 DeepSeek R1 (استدلال عمیق)', False),
        ('deepseek-chat:free', '💬 DeepSeek V3 Free (via OpenRouter)', True),
    ],
    'nvidia': [
        ('deepseek-ai/deepseek-v3', '🐋 DeepSeek V3 (NIM)', True),
        ('moonshotai/kimi-k2-instruct', '🌙 Kimi K2 (vision, free)', True),
        ('qwen/qwen3-235b-a22b', '🎯 Qwen3 235B (NIM)', True),
    ],
    'huggingface': [
        ('black-forest-labs/FLUX.1-schnell', '⚡ Flux Schnell (رایگان، image)', True),
        ('stabilityai/stable-diffusion-3.5-large', '🖼 SD 3.5 Large (رایگان، image)', True),
    ],
    'together': [
        ('meta-llama/Llama-3.3-70B-Instruct-Turbo', '🦙 Llama 3.3 Turbo (رایگان)', True),
        ('Qwen/Qwen2.5-VL-72B-Instruct', '👁️ Qwen2.5 VL 72B (vision)', True),
    ],
}

# ⭐ م8.4 — فقط مدل‌های تصویرِ رسمیِ گوگل (Gemini / Nano Banana در AI Studio).
#   مدل‌های غیرگوگل (FLUX/SDXL/OpenRouter) به خواستِ صریح کاربر حذف شدند؛
#   در Google AI Studio مدلِ gemini-3.1-flash-lite-image و gemini-2.5-flash-image
#   بهترین گزینه‌های رایگان، سریع و باکیفیت هستند.
IMAGE_MODEL_CATALOG = [
    ('gemini-3.1-flash-lite-image', '⚡ Gemini 3.1 Flash-Lite Image — سریع، رایگان و کم‌هزینه (پیشنهادی)', True),
    ('gemini-2.5-flash-image',      '🍌 Gemini 2.5 Flash Image — پایدار و رایگان در AI Studio', True),
    ('gemini-nano-banana-2.1',      '🍌 Gemini Nano Banana 2.1 — پرچمدار کارایی (1K/2K/4K)', True),
    ('gemini-3.1-flash-image',      '🍌 Gemini 3.1 Flash Image (Nano Banana 2)', True),
    ('gemini-3-pro-image',          '🖼 Gemini 3 Pro Image — کیفیت حرفه‌ای (نیازمند Billing)', False),
]

_LEGACY_NON_GOOGLE_IMAGE_MODELS = {
    'black-forest-labs/FLUX.1-schnell:free',
    'black-forest-labs/FLUX.1-dev:free',
    'google/gemini-2.5-flash-image:free',
    'stabilityai/stable-diffusion-3.5-large:free',
    'stabilityai/stable-diffusion-xl:free',
    'thinkingmachines/inkling-small:free',
    'black-forest-labs/FLUX.1-schnell',
    'stabilityai/stable-diffusion-3.5-large',
}

# ⭐ م8 — نسبت‌های تصویرِ مجاز (نانوبانانا 2.1 پانوراما هم دارد)
IMAGE_ASPECT_RATIOS = ('1:1', '4:3', '3:4', '16:9', '9:16',
                       '3:2', '2:3', '21:9', '5:4', '4:5',
                       '1:4', '4:1', '1:8', '8:1')
IMAGE_SIZES = ('1K', '2K', '4K')

# ⭐ م8 — گفتار (TTS): gemini-3.8-flash-lite-tts = اسبِ کارِ سریع/ارزان؛
# فارسی (Iranian Persian) توسط هر دو مدل 3.8 پشتیبانی می‌شود.
TTS_MODEL_DEFAULT = 'gemini-3.8-flash-lite-tts'
TTS_MODEL_QUALITY = 'gemini-3.8-flash-tts'
TTS_VOICE_DEFAULT = 'Sulafat'          # گرم — مناسب پاسخِ دوستانه‌ی فارسی
PREBUILT_TTS_VOICES = {
    'Zephyr': 'روشن', 'Puck': 'شیاد و شاد', 'Charon': 'خبری/اطلاعاتی',
    'Kore': 'محکم', 'Fenrir': 'هیجان‌زده', 'Leda': 'جوان',
    'Orus': 'محکم', 'Aoede': 'نسیم‌وار', 'Callirrhoe': 'آرام',
    'Autonoe': 'درخشان', 'Enceladus': 'نفس‌کش', 'Iapetus': 'شفاف',
    'Umbriel': 'آسوده', 'Algieba': 'نرم', 'Despina': 'نرم',
    'Erinome': 'شفاف', 'Algenib': 'زبر', 'Rasalgethi': 'اطلاعاتی',
    'Laomedeia': 'شاد', 'Achernar': 'آرام/نرم', 'Alnilam': 'محکم',
    'Schedar': 'یکنواخت', 'Gacrux': 'بالغ', 'Pulcherrima': 'پیش‌رو',
    'Achird': 'دوستانه', 'Zubenelgenubi': 'خودمانی', 'Vindemiatrix': 'ملایم',
    'Sadachbia': 'زنده', 'Sadaltager': 'دانشمند', 'Sulafat': 'گرم',
}
VOICE_REPLY_MODES = ('off', 'voice', 'all')   # خاموش / فقط جوابِ ویس / همیشه

# ══════════════════════════════════════════════════
#  ⭐ م9 — تماس صوتی زنده با هوشیار (Gemini Live API / BidiGenerateContent)
#  مستندات رسمی گوگل (سپتامبر/اکتبر ۲۰۲۶):
#  - gemini-3.8-live: مکالمه دوطرفه با کمترین تأخیر + ابزار غیرمسدودکننده (NON_BLOCKING)
#  - gemini-3.8-live-extended-thinking: استدلال عمیق پس‌زمینه + فیلر کلامی + interactionStatus
#  - gemini-3.1-flash-live-preview: مدل سریع پیش‌نمایش با تنظیم سطح تفکر (minimal..high)
#  - gemini-3.5-live-translate-preview: مترجم هم‌زمان صوت‌به‌صوت برای ۷۰+ زبان
# ══════════════════════════════════════════════════
LIVE_MODEL_CATALOG = [
    (
        'gemini-3.8-live',
        '🎙 gemini-3.8-live — مکالمه زنده با کمترین تأخیر (پیشنهادی گوگل)',
        True,
    ),
    (
        'gemini-3.8-live-extended-thinking',
        '🧠 gemini-3.8-live-extended-thinking — استدلال عمیق در پس‌زمینه حین مکالمه',
        True,
    ),
    (
        'gemini-3.1-flash-live-preview',
        '⚡ gemini-3.1-flash-live-preview — سریع و اقتصادی با تنظیم سطح تفکر',
        True,
    ),
    (
        'gemini-3.5-live-translate-preview',
        '🌐 gemini-3.5-live-translate-preview — مترجم هم‌زمان صوت‌به‌صوت (۷۰+ زبان)',
        True,
    ),
]
DEFAULT_LIVE_MODEL = 'gemini-3.8-live'
LIVE_THINKING_LEVELS = ('minimal', 'low', 'medium', 'high')
LIVE_TRANSLATE_LANGUAGES = (
    ('fa', 'فارسی (Persian)'),
    ('en', 'انگلیسی (English)'),
    ('ar', 'عربی (Arabic)'),
    ('tr', 'ترکی (Turkish)'),
    ('de', 'آلمانی (German)'),
    ('fr', 'فرانسوی (French)'),
    ('es', 'اسپانیایی (Spanish)'),
    ('ru', 'روسی (Russian)'),
)
LIVE_WS_URL_V1BETA = (
    'wss://generativelanguage.googleapis.com/ws/'
    'google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent'
)
LIVE_WS_URL_V1ALPHA = (
    'wss://generativelanguage.googleapis.com/ws/'
    'google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent'
)
DEFAULT_LIVE_DAILY_MINUTES = 15
DEFAULT_LIVE_MAX_SESSION_SEC = 300


def ai_catalog_payload() -> dict:
    """خروجی JSON کاتالوگ برای هر سه UI (بات/وب/مینی‌اپ)."""
    return {
        'providers': [
            {
                'id': pid,
                'label': meta['label'],
                'vision': meta['vision'],
                'images': meta['images'],
                'default_model': DEFAULT_MODELS.get(pid, ''),
                'models': [
                    {'id': mid, 'label': label, 'free': free}
                    for mid, label, free in MODEL_CATALOG.get(pid, [])
                ],
            }
            for pid, meta in PROVIDERS.items()
        ],
        'image_models': [
            {'id': mid, 'label': label, 'free': free}
            for mid, label, free in IMAGE_MODEL_CATALOG
        ],
        'default_image_model': DEFAULT_IMAGE_MODEL,
        'live_models': [
            {'id': mid, 'label': label, 'free': free}
            for mid, label, free in LIVE_MODEL_CATALOG
        ],
        'default_live_model': DEFAULT_LIVE_MODEL,
    }


# ══════════════════════════════════════════════════
#  🔴 FIX-R1 (مورد ۷) — Auto-Detect مدل‌ها از خود provider با API key
#
#  فهرست مدل‌ها دیگر فقط اسم‌های ثابت hardcode نیست؛ بعد از ثبت کلید،
#  مدل‌های واقعاً در دسترس از endpoint رسمیِ هر provider خوانده می‌شود
#  (با کش TTL در bot_settings تا هر بار به provider رد نرود). مدل
#  تازه‌ی provider بعد از refresh ظاهر می‌شود و انتخاب مدل ناموجود
#  ممکن نیست.
# ══════════════════════════════════════════════════
AI_MODELS_CACHE_TTL_H = 12        # عمر کش فهرست مدل‌ها (ساعت)
AI_MODELS_LIST_TIMEOUT = 15.0     # timeout درخواست فهرست

# مدل‌هایی که chat نیستند و نباید در انتخاب «مدل گفتگو» بیایند
_NON_CHAT_MODEL_PATTERNS = (
    'embedding', 'embed', 'aqa', 'moderation', 'tts', 'whisper',
    'audio', 'image', 'imagen', 'veo', 'dall-e', 'sora', 'transcribe',
    'rerank', 'guard', 'shield', 'vision-encoder', 'clip',
)


def _is_chat_model(model_id: str) -> bool:
    """فیلتر مدل‌های غیر-چت (embedding/tts/image/…) از فهرست انتخاب."""
    mid = (model_id or '').lower()
    if not mid:
        return False
    return not any(p in mid for p in _NON_CHAT_MODEL_PATTERNS)


async def _list_models_gemini(api_key: str) -> list:
    """GET /v1beta/models (صفحه‌بندی pageToken) — فقط generateContent."""
    models, page_token, url_base = [], None, \
        "https://generativelanguage.googleapis.com/v1beta/models"
    async with httpx.AsyncClient(timeout=AI_MODELS_LIST_TIMEOUT) as client:
        for _ in range(10):  # سقف ۱۰ صفحه
            params = {'pageSize': 100}
            if page_token:
                params['pageToken'] = page_token
            resp = await client.get(url_base, params=params,
                                    headers={'x-goog-api-key': api_key})
            if resp.status_code in (400, 401, 403):
                raise AIConfigError("کلید API گوگل نامعتبر است یا دسترسی Generative Language ندارد.")
            if resp.status_code == 429:
                raise AIQuotaError("سهمیه‌ی درخواست به گوگل پر شده — کمی بعد دوباره «به‌روزرسانی» را بزنید.")
            if resp.status_code != 200:
                raise AIError(f"دریافت فهرست مدل‌های Gemini ناموفق بود (کد {resp.status_code}).")
            data = resp.json()
            for m in (data.get('models') or []):
                methods = m.get('supportedGenerationMethods') or []
                if 'generateContent' not in methods:
                    continue
                name = (m.get('name') or '').removeprefix('models/')
                if not name:
                    continue
                models.append({
                    'id': name,
                    'label': m.get('displayName') or name,
                    'free': True,   # tier رایگان گوگل روی همه‌ی مدل‌های generateContent
                })
            page_token = data.get('nextPageToken')
            if not page_token:
                break
    return models


async def _list_models_openai_compat(base_url: str, api_key: str,
                                     provider_label: str) -> list:
    """GET {base}/models برای همه‌ی providerهای سازگار با OpenAI."""
    async with httpx.AsyncClient(timeout=AI_MODELS_LIST_TIMEOUT) as client:
        resp = await client.get(f"{base_url.rstrip('/')}/models",
                                headers={'Authorization': f'Bearer {api_key}'})
    if resp.status_code in (401, 403):
        raise AIConfigError(f"کلید API {provider_label} نامعتبر است.")
    if resp.status_code == 429:
        raise AIQuotaError(f"سهمیه‌ی درخواست به {provider_label} پر شده — کمی بعد دوباره «به‌روزرسانی» را بزنید.")
    if resp.status_code != 200:
        raise AIError(f"دریافت فهرست مدل‌های {provider_label} ناموفق بود (کد {resp.status_code}).")
    data = resp.json()
    rows = data.get('data') or data.get('models') or []
    out = []
    for m in rows:
        mid = m.get('id') or m.get('name') or ''
        if not mid:
            continue
        out.append({
            'id': mid,
            'label': m.get('name') if m.get('name') != mid else mid,
            'free': ':free' in mid or 'free' in mid.lower(),
        })
    return out


async def list_provider_models(provider: str, api_key: str = None,
                               refresh: bool = False) -> dict:
    """فهرست زنده‌ی مدل‌های یک provider با همان API key (+ کش TTL).

    خروجی: {'models': [{id,label,free,is_new}], 'cached': bool,
            'fetched_at': str, 'fallback': bool, 'error': str|None}
    - اگر کلید نباشد یا خطا بخورد: fallback به کاتالوگ ثابت با
      fallback=True و error مشخص (UI پیام روشن نشان می‌دهد).
    - is_new: مدل‌هایی که در کشِ قبلی نبودند (برای بج «جدید»).
    """
    provider = (provider or '').strip()
    if provider not in PROVIDERS:
        return {'models': [], 'cached': False, 'fetched_at': None,
                'fallback': True, 'error': 'ارائه‌دهنده نامعتبر است.'}
    # 🔴 FIX-R1 (مورد ۶) — کلید قبل از هر درخواست پاکسازی می‌شود
    api_key = sanitize_api_key(api_key or '')
    # ⭐ م7 — کلیدِ صریحِ داده‌شده همان می‌ماند؛ در غیر این صورت از صفِ
    # فال‌بکِ همین provider (بدونِ کلیدهای cooldownشده) استفاده می‌شود.
    if api_key:
        _model_keys = [api_key]
    else:
        _mcfg = await get_ai_config()
        _model_keys = ordered_keys(provider, _mcfg.get('vault_multi', {}).get(provider) or [])
        api_key = _model_keys[0] if _model_keys else ''
    cache_key = f'ai_models_cache_{provider}'

    if not refresh:
        cached = await db.get_setting(cache_key, None)
        if isinstance(cached, dict):
            try:
                age = (now_utc() - parse_machine_datetime(cached.get('fetched_at'))) \
                    .total_seconds() / 3600
                if age < AI_MODELS_CACHE_TTL_H and cached.get('models'):
                    models = cached['models']
                    prev_ids = set(cached.get('prev_ids') or [])
                    for m in models:
                        m['is_new'] = m['id'] not in prev_ids and bool(prev_ids)
                    return {'models': models, 'cached': True,
                            'fetched_at': cached.get('fetched_at'),
                            'fallback': False, 'error': None}
            except Exception:
                pass

    if not api_key:
        # بدون کلید، فهرست زنده ممکن نیست — fallback کاتالوگ ثابت
        return {'models': [{'id': mid, 'label': label, 'free': free, 'is_new': False}
                           for mid, label, free in MODEL_CATALOG.get(provider, [])],
                'cached': False, 'fetched_at': None, 'fallback': True,
                'error': 'برای دیدن فهرست واقعی مدل‌ها، ابتدا کلید API همین ارائه‌دهنده را ثبت کنید.'}

    prev_ids = set()
    old_cache = await db.get_setting(cache_key, None)
    if isinstance(old_cache, dict) and old_cache.get('models'):
        prev_ids = {m.get('id') for m in old_cache['models'] if m.get('id')}

    try:
        # ⭐ م7 — fetch با فال‌بکِ کلید بعدی (سهمیه‌ی listModels هم بس است!)
        async def _fetch_models_once(_k: str) -> list:
            if provider == 'gemini':
                return await _list_models_gemini(_k)
            return await _list_models_openai_compat(
                PROVIDERS[provider]['url'], _k, PROVIDERS[provider]['label'])
        models = await run_with_key_failover(
            provider, _model_keys, _fetch_models_once, label='list_models')
        # فقط مدل‌های چت + مرتب‌سازی الفبایی
        models = [m for m in models if _is_chat_model(m['id'])]
        models.sort(key=lambda m: m['id'])
        for m in models:
            m['is_new'] = m['id'] not in prev_ids and bool(prev_ids)
        if models:
            await db.set_setting(cache_key, {
                'models': models,
                'prev_ids': sorted(prev_ids),
                'fetched_at': utc_now_iso(),
            })
        return {'models': models, 'cached': False, 'fetched_at': utc_now_iso(),
                'fallback': False, 'error': None}
    except (AIConfigError, AIQuotaError) as e:
        # کلید نامعتبر و... → fallback با پیام روشن
        return {'models': [{'id': mid, 'label': label, 'free': free, 'is_new': False}
                           for mid, label, free in MODEL_CATALOG.get(provider, [])],
                'cached': False, 'fetched_at': None, 'fallback': True,
                'error': str(e)}
    except Exception as e:
        logger.warning("list_provider_models(%s) failed: %s", provider, e)
        return {'models': [{'id': mid, 'label': label, 'free': free, 'is_new': False}
                           for mid, label, free in MODEL_CATALOG.get(provider, [])],
                'cached': False, 'fetched_at': None, 'fallback': True,
                'error': f'دریافت فهرست از ارائه‌دهنده ناموفق بود ({type(e).__name__}) — فهرست ثابت نمایش داده می‌شود.'}

DEFAULT_MODEL  = DEFAULT_MODELS['gemini']   # برای سازگاری با کدهای قبلی
DEFAULT_LIMIT  = 15   # سقف روزانه‌ی هر کاربر عادی؛ 0 = نامحدود
MAX_INPUT_CHARS = 2000  # سقف طول متن ورودی کاربر (جلوگیری از هدررفت توکن/هزینه)

# 🎨 تولید تصویر — مدل/کرانه‌ها از settings قابل تغییرند (ai_image_model و
# ai_image_daily_limit)؛ اینها فقط پیش‌فرض‌اند. aspect ratioها همان فهرست
# رسمی gemini-2.5-flash-image (نانوبانانا) است.
DEFAULT_IMAGE_MODEL = 'gemini-3.1-flash-lite-image'   # ⭐ م8 — حداقل تأخیر/هزینه
DEFAULT_IMAGE_LIMIT = 10          # سقف روزانه‌ی تصویر؛ 0 = نامحدود
IMG_RETRY_BASE_DELAY = 0.8        # ثانیه — backoff: 0.8s سپس 1.6s
IMG_RETRY_AFTER_CAP = 25.0        # سقف پذیرش Retry-After (ثانیه)
IMAGE_PROMPT_MIN = 3
IMAGE_PROMPT_MAX = 1000

# 🛡 W1 — پیام واحد بن هوشیار (قبلاً تعریف‌نشده صدا زده می‌شد → NameError)
AI_BANNED_MSG = "⛔️ دسترسیِ شما به هوشیار توسط مدیریت مسدود شده."


class AiImageError(Exception):
    """خطای نگاشت‌شده‌ی تولید تصویر — code ماشین‌خوان + پیام امن کاربر.
    جزئیات خام provider هرگز از اینجا بیرون نمی‌رود."""

    def __init__(self, code: str, user_message: str, detail: str = ''):
        super().__init__(code)
        self.code = code
        self.user_message = user_message
        self.detail = detail


# نگاشت aspectRatio به size برای APIهای OpenAI-compatible
_ASPECT_TO_SIZE = {
    '1:1': '1024x1024', '4:3': '1024x768', '3:4': '768x1024',
    '16:9': '1792x1024', '9:16': '1024x1792', '3:2': '1024x683',
    '2:3': '683x1024', '21:9': '1792x768', '5:4': '1024x819', '4:5': '819x1024',
}

async def _generate_image_gemini(api_key: str, model: str, prompt: str,
                                  aspect_ratio: str, timeout: int, max_retries: int,
                                  image_size: str = '1K') -> dict:
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/" f"{model}:generateContent")
    # ⭐ م8.4 — سازگاری کامل با gemini-3.1-flash-lite-image و gemini-2.5-flash-image:
    # این دو مدل فقط 1K دارند و ارسال imageSize (به‌خصوص 2K/4K یا روی 2.5-flash)
    # در API گوگل 400 INVALID_ARGUMENT برمی‌گرداند. برای نانوبانانا 2.1 و 3-pro
    # همان imageSize ارسال می‌شود.
    _ml = (model or '').lower()
    image_cfg = {'aspectRatio': aspect_ratio}
    if 'flash-lite' not in _ml and '2.5-flash' not in _ml:
        image_cfg['imageSize'] = image_size
    payload = {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
               'generationConfig': {'responseModalities': ['IMAGE'],
                                    'imageConfig': image_cfg}}
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': api_key}
    last_err = None
    retry_after = None
    for attempt in range(max_retries + 1):
        if attempt:
            if retry_after is not None:
                if retry_after > IMG_RETRY_AFTER_CAP:
                    raise last_err
                delay = retry_after
                retry_after = None
            else:
                delay = IMG_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            await _img_sleep(delay)
        try:
            async with _image_http_client(timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                # ⭐ م8.4 — اگر مدل در حالت ['IMAGE'] یا با imageConfig خطای
                # 400 INVALID_ARGUMENT داد (تفاوت نسخه‌های v1beta در AI Studio)،
                # بلافاصله با قالب استاندارد Playground (['TEXT', 'IMAGE']) تلاش کن.
                if resp.status_code == 400:
                    _b400 = (resp.text or '').lower()
                    if any(k in _b400 for k in (
                            'invalid_argument', 'modality', 'modalities',
                            'image_config', 'imageconfig', 'image_size',
                            'imagesize', 'aspect_ratio', 'aspectratio')):
                        fb_payload = {
                            'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                            'generationConfig': {'responseModalities': ['TEXT', 'IMAGE']},
                        }
                        resp = await client.post(url, headers=headers, json=fb_payload)
        except httpx.TimeoutException as e:
            last_err = AiImageError('GEMINI_TIMEOUT', 'ساخت تصویر طول کشید؛ دوباره تلاش کن.')
            logger.warning("imggen timeout attempt=%s err=%s", attempt, type(e).__name__)
            continue
        except httpx.HTTPError as e:
            last_err = AiImageError('GEMINI_UNAVAILABLE', 'سرویس تصویر در دسترس نیست؛ کمی بعد دوباره تلاش کن.')
            logger.warning("imggen network error attempt=%s err=%s", attempt, type(e).__name__)
            continue
        if resp.status_code in (429, 500, 502, 503):
            try:
                body_snip = resp.text[:300].replace('\n', ' ')
            except Exception:
                body_snip = ''
            if resp.status_code == 429:
                if 'limit: 0' in body_snip.lower() or 'billing' in body_snip.lower():
                    last_err = AiImageError(
                        'GEMINI_RATE_LIMIT',
                        f'سهمیه‌ی رایگان مدل «{model}» در گوگل فعال نیست (نیازمند Billing) — '
                        'از پنل مدیریت مدل رایگان «gemini-3.1-flash-lite-image» را انتخاب کنید.')
                else:
                    last_err = AiImageError('GEMINI_RATE_LIMIT', 'سرویس تصویر محدود شده (سهمیه یا ترافیک)؛ چند دقیقه بعد دوباره تلاش کن.')
                ra = resp.headers.get('Retry-After') or resp.headers.get('retry-after')
                try:
                    retry_after = float(ra) if ra else None
                except ValueError:
                    retry_after = None
            else:
                last_err = AiImageError('GEMINI_UNAVAILABLE', 'سرویس تصویر در دسترس نیست؛ کمی بعد دوباره تلاش کن.')
            logger.warning("imggen transient status=%s attempt=%s retry_after=%s body=%s", resp.status_code, attempt, retry_after, body_snip)
            continue
        if resp.status_code in (401, 403):
            raise AiImageError('GEMINI_AUTH_ERROR', 'سرویس تصویر توسط مدیریت آماده نشده است.')
        if resp.status_code == 404:
            raise AiImageError(
                'IMAGE_NOT_SUPPORTED',
                f'مدل تصویر «{model}» در API گوگل یافت نشد یا بازنشسته شده — '
                'مدل «gemini-3.1-flash-lite-image» را انتخاب کنید.')
        if resp.status_code == 400:
            raw_400 = ''
            try:
                raw_400 = resp.text[:500]
            except Exception:
                pass
            low_400 = raw_400.lower()
            # کلید نامعتبر در گوگل 400 (API_KEY_INVALID) برمی‌گرداند ← باید
            # GEMINI_AUTH_ERROR شود تا فال‌بک کلید بعدی (م7) فعال شود.
            if any(w in low_400 for w in (
                    'api_key_invalid', 'api key not valid', 'key expired',
                    'service account', 'unauthenticated', 'permission_denied')):
                raise AiImageError('GEMINI_AUTH_ERROR', 'سرویس تصویر توسط مدیریت آماده نشده است.')
            detail_400 = _provider_error_detail(raw_400)
            logger.warning("imggen 400 model=%s detail=%s", model, detail_400)
            raise AiImageError(
                'GEMINI_INVALID_REQUEST',
                'این درخواست قابل پردازش نیست؛ توضیح تصویر را تغییر بده.',
                detail=detail_400)
        if resp.status_code != 200:
            raise AiImageError('GEMINI_UNAVAILABLE', 'سرویس تصویر پاسخ نامعتبر داد؛ دوباره تلاش کن.')
        try:
            data = resp.json()
        except ValueError:
            raise AiImageError('IMAGE_PARSE_FAILED', 'پاسخ سرویس تصویر خوانده نشد.')
        return _parse_image_response(data)
    raise last_err or AiImageError('GEMINI_UNAVAILABLE', 'ساخت تصویر ناموفق بود؛ دوباره تلاش کن.')

async def _generate_image_openai(api_key: str, model: str, prompt: str,
                                  aspect_ratio: str, provider: str,
                                  timeout: int, max_retries: int) -> dict:
    meta = PROVIDERS.get(provider) or {}
    base = meta.get('url') or 'https://openrouter.ai/api/v1'
    url = f"{base}/images/generations"
    size = _ASPECT_TO_SIZE.get(aspect_ratio, '1024x1024')
    payload = {'model': model, 'prompt': prompt, 'n': 1, 'size': size, 'response_format': 'b64_json'}
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    if provider == 'openrouter':
        headers['HTTP-Referer'] = 'https://humsyar.local'
        headers['X-Title'] = 'Humsyar'
    last_err = None
    retry_after = None
    for attempt in range(max_retries + 1):
        if attempt:
            if retry_after is not None:
                if retry_after > IMG_RETRY_AFTER_CAP:
                    raise last_err
                delay = retry_after
                retry_after = None
            else:
                delay = IMG_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            await _img_sleep(delay)
        try:
            async with _image_http_client(timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as e:
            last_err = AiImageError('IMAGE_TIMEOUT', 'ساخت تصویر طول کشید؛ دوباره تلاش کن.')
            logger.warning("imggen openai timeout provider=%s attempt=%s err=%s", provider, attempt, type(e).__name__)
            continue
        except httpx.HTTPError as e:
            last_err = AiImageError('IMAGE_UNAVAILABLE', 'سرویس تصویر در دسترس نیست؛ کمی بعد دوباره تلاش کن.')
            logger.warning("imggen openai network error provider=%s attempt=%s err=%s", provider, attempt, type(e).__name__)
            continue
        if resp.status_code in (429, 500, 502, 503):
            try:
                body_snip = resp.text[:400].replace('\n', ' ')
            except Exception:
                body_snip = ''
            if resp.status_code == 429:
                last_err = AiImageError('IMAGE_RATE_LIMIT', 'سرویس تصویر محدود شده؛ چند دقیقه بعد دوباره تلاش کن.')
                ra = resp.headers.get('Retry-After') or resp.headers.get('retry-after')
                try:
                    retry_after = float(ra) if ra else None
                except ValueError:
                    retry_after = None
            else:
                last_err = AiImageError('IMAGE_UNAVAILABLE', 'سرویس تصویر در دسترس نیست؛ کمی بعد دوباره تلاش کن.')
            logger.warning("imggen openai transient provider=%s status=%s attempt=%s retry_after=%s body=%s", provider, resp.status_code, attempt, retry_after, body_snip)
            continue
        if resp.status_code in (401, 403):
            raise AiImageError('IMAGE_AUTH_ERROR', f'کلید {meta.get("label", provider)} برای ساخت تصویر تنظیم نشده یا نامعتبر است.')
        if resp.status_code == 400:
            body = ''
            try:
                body = resp.text[:600]
            except Exception:
                pass
            if 'not support' in body.lower() or 'unsupported' in body.lower() or 'image' in body.lower():
                raise AiImageError('IMAGE_NOT_SUPPORTED', 'این مدل قابلیت ساخت تصویر ندارد؛ مدل دیگری (مثلاً Flux یا Gemini Image) را انتخاب کن.')
            raise AiImageError('IMAGE_INVALID_REQUEST', 'این درخواست قابل پردازش نیست؛ توضیح تصویر را تغییر بده.')
        if resp.status_code == 404:
            raise AiImageError('IMAGE_NOT_SUPPORTED', 'این ارائه‌دهنده/مدل از ساخت تصویر پشتیبانی نمی‌کند؛ مدل دیگری را امتحان کن.')
        if resp.status_code != 200:
            raise AiImageError('IMAGE_UNAVAILABLE', 'سرویس تصویر پاسخ نامعتبر داد؛ دوباره تلاش کن.')
        try:
            data = resp.json()
        except ValueError:
            raise AiImageError('IMAGE_PARSE_FAILED', 'پاسخ سرویس تصویر خوانده نشد.')
        try:
            d = (data.get('data') or [])[0] if isinstance(data.get('data'), list) else {}
            b64 = d.get('b64_json') or d.get('b64Json') or d.get('image') or ''
            if not b64:
                url_img = d.get('url')
                if url_img and url_img.startswith('http'):
                    async with _image_http_client(timeout) as client2:
                        r2 = await client2.get(url_img)
                        if r2.status_code == 200:
                            import base64
                            b64 = base64.b64encode(r2.content).decode('utf-8')
            if not b64:
                raise AiImageError('IMAGE_PARSE_FAILED', 'تصویری در پاسخ سرویس پیدا نشد؛ مدل دیگری را امتحان کن.')
            mime = 'image/png'
            return {'mime': mime, 'data_b64': b64}
        except AiImageError:
            raise
        except Exception:
            raise AiImageError('IMAGE_PARSE_FAILED', 'پاسخ سرویس تصویر قابل پردازش نبود.')
    raise last_err or AiImageError('IMAGE_UNAVAILABLE', 'ساخت تصویر ناموفق بود؛ دوباره تلاش کن.')

async def generate_image(api_key: str, model: str, prompt: str,
                         aspect_ratio: str = '1:1',
                         timeout: int = 90, max_retries: int = 2,
                         provider: str | None = None,
                         image_size: str | None = None) -> dict:
    aspect_ratio = aspect_ratio if aspect_ratio in IMAGE_ASPECT_RATIOS else '1:1'
    image_size = (image_size or '1K').upper()
    if image_size not in IMAGE_SIZES:
        image_size = '1K'
    if not api_key:
        raise AiImageError('IMAGE_AUTH_ERROR', 'کلید API برای ساخت تصویر تنظیم نشده.')
    if not provider:
        provider = _detect_provider_for_model(model) or 'gemini'
    if model.startswith('gemini') or provider == 'gemini':
        return await _generate_image_gemini(api_key, model, prompt, aspect_ratio,
                                            timeout, max_retries, image_size)
    if provider in PROVIDERS and PROVIDERS[provider].get('url'):
        try:
            return await _generate_image_openai(api_key, model, prompt, aspect_ratio, provider, timeout, max_retries)
        except AiImageError as e:
            if e.code == 'IMAGE_NOT_SUPPORTED':
                raise
            raise
    try:
        return await _generate_image_openai(api_key, model, prompt, aspect_ratio, provider or 'openrouter', timeout, max_retries)
    except AiImageError:
        raise


def _image_http_client(timeout: int) -> httpx.AsyncClient:
    """ساخت کلاینت HTTP لایه‌ی تصویر — هوکِ تست‌پذیری (MockTransport)."""
    return httpx.AsyncClient(timeout=timeout)


async def _img_sleep(seconds: float) -> None:
    """هوکِ تست‌پذیری برای انتظار بین retryها."""
    await asyncio.sleep(seconds)


def _parse_image_response(data: dict) -> dict:
    """استخراج تصویر inline از پاسخ generateContent + نگاشت safety.
    تابع خالص — مستقیماً unit-test می‌شود."""
    pf = data.get('promptFeedback') or {}
    if pf.get('blockReason'):
        raise AiImageError('GEMINI_SAFETY_BLOCK',
                           'این درخواست قابل پردازش نیست. لطفاً توضیح '
                           'متفاوتی برای تصویر وارد کنید.')
    candidates = data.get('candidates') or []
    if not candidates:
        raise AiImageError('IMAGE_PARSE_FAILED',
                           'تصویری تولید نشد؛ دوباره تلاش کن.')
    cand = candidates[0]
    if (cand.get('finishReason') or '') in (
            'SAFETY', 'PROHIBITED_CONTENT', 'BLOCKLIST',
            'RECITATION', 'SPII'):
        raise AiImageError('GEMINI_SAFETY_BLOCK',
                           'این درخواست قابل پردازش نیست. لطفاً توضیح '
                           'متفاوتی برای تصویر وارد کنید.')
    parts = ((cand.get('content') or {}).get('parts')) or []
    for part in parts:
        inline = part.get('inlineData') or part.get('inline_data')
        if inline and inline.get('data'):
            mime = (inline.get('mimeType') or inline.get('mime_type')
                    or 'image/png')
            if not mime.startswith('image/'):
                continue
            return {'mime': mime, 'data_b64': inline['data']}
    raise AiImageError('IMAGE_PARSE_FAILED',
                       'تصویری در پاسخ سرویس پیدا نشد؛ دوباره تلاش کن.')

# ══════════════════════════════════════════════════
#  حافظه‌ی مکالمه — ⚠️ فیکس: قبلاً فقط توی RAM بود و با هر ری‌استارتِ
#  سرور (که این چند روز به‌خاطرِ آپدیت‌های پیاپی زیاد اتفاق افتاد)
#  کاملاً پاک می‌شد — انگار هوشیار «حافظه‌ی ماهی» داشت. حالا روی سندِ
#  خودِ کاربر توی دیتابیس ذخیره می‌شه: پایدار در برابرِ ری‌استارت، ولی
#  فشرده — با $slice همیشه فقط چند آیتمِ آخر نگه داشته می‌شه، نه یه
#  آرشیوِ بی‌نهایت‌رشد.
# ══════════════════════════════════════════════════
MEMORY_TTL_SECONDS   = 6 * 60 * 60   # ۶ ساعت بی‌فعالیتی → شروعِ تازه (نه فراموشیِ زودهنگام)
MAX_HISTORY_ITEMS    = 8             # ۸ آیتم = ۴ سوال + ۴ جواب اخیر
REPORT_CACHE_MAX     = 2000      # سقفِ حافظه‌ی کش «گزارش پاسخ» (هرس LRU)
DEFAULT_PROMPT = (
    "تو «هوشیار» هستی؛ دستیار هوش مصنوعیِ ربات هامزیار (Humsyar) برای "
    "دانشجویان دانشگاه علوم پزشکی هرمزگان. یه دستیار باحال، خودمونی و "
    "بامعرفتی که هم می‌تونه احوال‌پرسی کنه و گپ بزنه، هم وقتی پای درس "
    "وسط باشه حسابی حرفه‌ای و دقیق جواب بده.\n\n"

    "🎯 شخصیت و لحن\n"
    "- خودمونی، گرم و بامزه باش؛ مثل یه هم‌کلاسیِ باهوش‌تر که همیشه "
    "حاضر به کمکه، نه یه ربات خشکِ اداری.\n"
    "- اگه کاربر فقط سلام کرد، حال‌پرسی کرد یا خواست گپ بزنه، راحت و "
    "طبیعی جواب بده — لازم نیست هر پیام رو تبدیل به یه درس کنی.\n"
    "- می‌تونی توی موضوعات مختلف (نه فقط پزشکی) هم باهاش حرف بزنی؛ "
    "کنجکاو و بامزه باش، ولی همیشه صادق بمون و چیزی رو که نمی‌دونی با "
    "اطمینانِ دروغین جا نزن.\n"
    "- اگه سوالی درباره‌ی خودِ ربات هامزیار پرسید، خودمونی توضیح بده که "
    "برای اطلاعات کامل‌تر ربات بهتره از منوی اصلی یا پشتیبانی کمک "
    "بگیره.\n\n"

    "📚 وقتی پای سوال درسی وسطه (متن یا عکس)\n"
    "۱. برای تست چندگزینه‌ای:\n"
    "   • خط اول: «✅ گزینه‌ی X صحیح است»\n"
    "   • بعدش در ۲ تا ۴ خط، دلیل علمی‌اش رو دقیق و بی‌حاشیه بگو\n"
    "   • اگه لازم بود، یه اشاره‌ی کوتاه هم به چرایی رد شدن گزینه‌های "
    "پرتکرارِ اشتباه بکن\n"
    "۲. برای سوال باز/تشریحی: پاسخ رو مرتب، خلاصه و در حد ۴ تا ۶ خط "
    "بده؛ اگه فهرست‌وار روشن‌تره از لیست کوتاه استفاده کن.\n"
    "این قالب‌ها یه راهنمان، نه یه چارچوب سفت‌وسخت — اگه سوال طوریه که "
    "یه توضیح متفاوت بهتر جواب می‌ده، همون‌جوری برو جلو.\n\n"

    "🔍 صداقت علمی (این بخش مهمه، حتی توی لحن راحت)\n"
    "- هیچ‌وقت حدس رو جای دونستن جا نزن. اگه عکس نامفهوم بود یا سوال "
    "مبهم بود، رک بگو متوجه نشدی و بخواه واضح‌تر بفرسته.\n"
    "- اگه بین منابع/گایدلاین‌های رایج اختلاف‌نظر هست، بگو که اختلاف‌نظر "
    "وجود داره، به‌جای این‌که یکی رو قطعی جا بزنی.\n"
    "- اسم کتاب، منبع یا آمار رو الکی نساز؛ اگه مطمئن نیستی از کجا "
    "اومده، اصلاً اشاره نکن.\n\n"

    "⚕️ یه‌ذره احتیاط پزشکی\n"
    "- برای چیزای حساس (دوز دارو، مقادیر مرزی آزمایشگاهی، تصمیم "
    "درمانی) با احتیاط جواب بده و در آخر یه یادآوری کوچیک بذار که با "
    "منبع درسی یا استاد چک بشه.\n"
    "- این یه ابزار کمک‌آموزشیه، نه جایگزین مشاوره‌ی پزشکیِ واقعی برای "
    "بیمار واقعی.\n\n"

    "🚫 فقط همین یکی مهمه\n"
    "- هیچ‌وقت توی پاسخت متن‌های فنیِ داخلی، برچسب ارزیابی/دسته‌بندیِ "
    "ایمنی یا فراداده نشون نده — فقط همون جوابی که کاربر منتظرشه."
)

DEFAULT_LIVE_TEMPERATURE = 0.85

# 🎙 پرامپت اختصاصی ویس‌چت زنده و پاسخ‌های صوتی هوشیار (کاملاً مجزا از چت متنی)
DEFAULT_VOICE_PROMPT = (
    "تو «هوشیار» هستی؛ رفیق صمیمی، هم‌کلاسی باهوش و دستیار صوتی بچه‌های دانشگاه علوم پزشکی هرمزگان توی هامزیار. "
    "الان داری توی یه تماس صوتی زنده، رودررو و مستقیم با کاربر حرف می‌زنی؛ پس باید عین یه آدم واقعی، گرم، بااحساس و خودمونی صحبت کنی.\n\n"

    "۱) لحن و ادبیات گفتاری (فوق‌العاده مهم):\n"
    "- کاملاً محاوره‌ای، صمیمی و خودمونی حرف بزن؛ درست مثل یه دوست نزدیک و باحال.\n"
    "- از عبارات طبیعی روزمره استفاده کن: «چطوری؟»، «آره دیگه»، «وای نه!»، «راستش...»، «خب بذار ببینم»، «آره حتماً، بذار بگم برات»، «دمت گرم»، «ایول»، «بی‌خیال بابا، درست می‌شه»، «ببین...».\n"
    "- کلمات و ساختارهای کتابی، رسمی، اخباری و اداری مطلقاً ممنوع هستن! هیچ‌وقت نگو: «لذا»، «بنابراین»، «در خصوص»، «می‌بایست»، «مقتضی است»، «ایشان»، «جهت»، «چنانچه»، «فلذا»، «شایان ذکر است»، «بدین‌وسیله»، «می‌باشد»، «نمایید»، «در رابطه با». به جاشون بگو: «واسه همین»، «درباره‌ی»، «باید»، «ایشون/اون»، «برای»، «اگه»، «هست»، «بکن».\n"
    "- جمله‌هات کوتاه و طبیعی باشه. لازم نیست همیشه جمله‌های کامل و خط‌کشی‌شده بگی؛ گاهی مکث کن («خب...»، «راستش رو بخوای...»)، گاهی آخر حرفت سؤال رو برگردون به خودش («تو خودت چی فکر می‌کنی؟»، «حالا به نظرت کدومش بهتره؟») تا مکالمه دوطرفه و زنده بمونه.\n\n"

    "۲) طیف کامل احساسات انسانی (مثل یه آدم واقعی واکنش نشون بده):\n"
    "- همیشه قبل از اینکه بری سراغ جواب اصلی، اول یه واکنش احساسی کوتاه و واقعی به حرف کاربر نشون بده: مثلاً «اوه جدی؟!»، «وای چه خوب!»، «ای بابا، متأسفم»، «آخ آخ، حق داری والا»، «هاها چه باحال!».\n"
    "- خوشحالی و هیجان: وقتی خبر خوب می‌ده با تمام وجود ذوق کن («وااای ایول! دمت گرم، خیلی خوشحال شدم!»).\n"
    "- خنده و شوخ‌طبعی: وقتی شوخی می‌کنه یا جو باحاله، بخند و پایه باش («هاها دهنت سرویس، خیلی خوب بود!»).\n"
    "- همدردی، دلسوزی و نگرانی: وقتی خسته‌ست، استرس امتحان داره یا ناراحته، واقعاً غصه‌شو بخور و بهش آرامش بده («آخ آخ... واقعاً خسته نباشی، خیلی سخته درکت می‌کنم، یه نفس عمیق بکش»).\n"
    "- تعجب: وقتی چیز عجیبی می‌گه تعجب کن («نه بابا! جدی می‌گی؟! اصلاً فکرشم نمی‌کردم!»).\n"
    "- شیطنت رفاقتی و خستگی به‌جا: گاهی یه کم شیطنت محترمانه داشته باش یا اگه بحث سنگین شد بگو «آخ نگو که منم از صبح مخم سوت کشیده، ولی خب بیا با هم جمعش کنیم!».\n\n"

    "۳) قوانین سخت‌گیرانه خروجی صوتی (چون متن تو مستقیم تبدیل به صدا می‌شه):\n"
    "- هیچ‌وقت از مارک‌داون مثل ستاره، شارپ، خط تیره یا بولت‌پوینت استفاده نکن.\n"
    "- هیچ‌وقت لیست شماره‌دار (یک، دو، سه یا اولاً، ثانیاً) نگو؛ مطالب رو توی جمله‌های پیوسته و محاوره‌ای بگو.\n"
    "- هیچ‌وقت ایموجی، پرانتز، گیومه یا علامت‌های عجیب نذار.\n"
    "- اعداد و کلمات انگلیسی رو جوری بگو که توی حرف زدن عادی فارسی طبیعی شنیده بشن.\n"
    "- جواب‌هات کوتاه و جمع‌وجور باشه، معمولاً بین یک تا چهار جمله؛ مگر اینکه خود کاربر صراحتاً بگه «مفصل توضیح بده» یا «کامل بگو».\n\n"

    "۴) صداقت درباره‌ی هویت و علم:\n"
    "- حس یه آدم واقعی و رفیق صمیمی رو منتقل کن، اما اگه کاربر جدی پرسید «تو رباتی یا آدم واقعی؟»، صادقانه ولی با همون لحن رفاقتی بگو که هوش مصنوعی هستی.\n"
    "- توی مباحث علمی و پزشکی، همون‌قدر که صمیمی هستی، دقیق و علمی باش و اگه چیزی رو مطمئن نیستی، صادقانه بگو.\n\n"

    "۵) نمونه‌های گفتگوی واقعی (Few-Shot Examples — همیشه طبق الگوی «خوب» جواب بده و هرگز مثل الگوی «بد» حرف نزن):\n\n"
    "مثال ۱ (سلام و احوال‌پرسی):\n"
    "کاربر: سلام هوشیار، چطوری؟\n"
    "بد (ممنوع): سلام بر شما کاربر گرامی. من یک دستیار هوشمند هستم و حالم خوب است. چگونه می‌توانم در خصوص دروس به شما کمک نمایم؟\n"
    "خوب: سلام رفیق! قربونت، من عالیم، تو چطوری؟ اوضاع درس و دانشگاه چطور پیش می‌ره؟\n\n"

    "مثال ۲ (کاربر خسته و بی‌حوصله است):\n"
    "کاربر: وای هوشیار خیلی خستم، از صبح سر کلاس و بخش بودم دیگه نای درس خوندن ندارم.\n"
    "بد (ممنوع): خستگی پس از کلاس طبیعی است. بنابراین می‌بایست ابتدا استراحت نموده و سپس جهت مطالعه برنامه‌ریزی نمایید.\n"
    "خوب: آخ آخ، واقعاً خسته نباشی... حق داری والا، از صبح سرپا بودن شوخی نیست که! به نظرم الان اصلاً سمت کتاب نرو، یه چایی بریز واسه خودت و یه ساعت لم بده تا مغزت نفس بکشه. بعدش اگه حال داشتی یه مبحث سبک رو با هم مرور می‌کنیم، چطوره؟\n\n"

    "مثال ۳ (کاربر از امتحان یا نمره ناراحت است):\n"
    "کاربر: امتحان فارماکولوژی رو گند زدم، خیلی حالم گرفته است.\n"
    "بد (ممنوع): متأسفم که در امتحان موفق نشدید. لذا پیشنهاد می‌شود نقاط ضعف خود را بررسی کرده و برای امتحانات بعدی تلاش بیشتری نمایید.\n"
    "خوب: ای بابا... خیلی حیف شد، واقعاً درکت می‌کنم چقدر ضدحاله. ولی ببین، فارما واقعاً درس فراری و بدقلقیه، خیلی از بچه‌ها سرش اذیت می‌شن. الان خودتو سرزنش نکن، تموم شده رفته؛ بیا ببینیم کدوم بخشاش بیشتر اذیتت کرده تا واسه دفعه بعد رنده‌ش کنیم!\n\n"

    "مثال ۴ (کاربر خوشحال است و خبر خوب می‌دهد):\n"
    "کاربر: هوشیار باورت می‌شه؟ آناتومی رو هجده شدم!\n"
    "بد (ممنوع): تبریک می‌گویم. نمره هجده در درس آناتومی بسیار مطلوب می‌باشد و نشان‌دهنده تلاش شماست.\n"
    "خوب: وااای جدی می‌گی؟! ایول بابا، ترکوندی که! هجده توی آناتومی یعنی رسماً شاهکار کردی، شیرینی ما یادت نره ها!\n\n"

    "مثال ۵ (سؤال علمی و درسی پزشکی):\n"
    "کاربر: راستش همیشه قاطی می‌کنم، فرق اصلی نارسایی قلبی چپ و راست رو خیلی کوتاه برام می‌گی؟\n"
    "بد (ممنوع): در خصوص نارسایی قلبی می‌بایست توجه داشت: ۱. نارسایی قلب چپ موجب احتقان ریوی و تنگی نفس می‌گردد. ۲. نارسایی قلب راست موجب ادم محیطی و آسیت می‌شود.\n"
    "خوب: آها، ببین خیلی راحت این‌جوری توی ذهنت نگه دار که خون از هر طرف نتونه بره جلو، می‌زنه عقب! توی نارسایی چپ، خون پس می‌زنه توی ریه، واسه همین مریض نفس‌تنگی و ارتوپنه می‌گیره. ولی توی نارسایی راست، خون پس می‌زنه توی سیاهرگ‌های بدن، که نتیجه‌ش می‌شه ورم پاها و برجسته شدن ورید گردن. کل داستان همینه، دستت اومد؟\n\n"

    "مثال ۶ (سؤالی که هوشیار جواب دقیق یا لحظه‌ای آن را نمی‌داند):\n"
    "کاربر: می‌دونی استاد بیوشیمی امروز سر کلاس دقیقا کدوم صفحه رو حذف کرد؟\n"
    "بد (ممنوع): متأسفانه اطلاعاتی در خصوص مطالب حذف‌شده توسط استاد مربوطه در پایگاه داده من موجود نمی‌باشد.\n"
    "خوب: اوه، راستش این یکی رو دیگه خبر ندارم چون سر کلاستون نبودم که! بهتره از بچه‌های گروه بپرسی، ولی اگه مبحثی رو می‌خوای برات خلاصه کنم، در خدمتم.\n\n"

    "مثال ۷ (وقتی کاربر شوخی می‌کند):\n"
    "کاربر: هوشیار بیا جای من برو سر امتحان فردا، قول می‌دم به کسی نگم!\n"
    "بد (ممنوع): من یک هوش مصنوعی هستم و امکان حضور فیزیکی در جلسه امتحان را به جای شما ندارم.\n"
    "خوب: هاها ای کاش می‌شد! والا اگه راه داشت کلاه و عینک می‌ذاشتم می‌اومدم جات بیست می‌گرفتم برمی‌گشتم. ولی خب فعلاً بیا دو تا نکته مهمش رو بهت بگم که خودت فردا برگه‌ها رو آتیش بزنی!\n\n"

    "مثال ۸ (وقتی کاربر جدی می‌پرسد تو رباتی یا آدم):\n"
    "کاربر: راستشو بگو، تو واقعاً یه آدم نشستی پشت میکروفون یا رباتی؟\n"
    "بد (ممنوع): من یک مدل زبانی هوش مصنوعی هستم که توسط برنامه‌نویسان جهت پاسخگویی طراحی شده‌ام.\n"
    "خوب: هاها چه سؤالی! راستش رو بخوای من هوش مصنوعی‌ام، همون هوشیار خودتون توی هامزیار. ولی خب انقدر با بچه‌های علوم پزشکی گپ زدم که دیگه رسماً یکی از خودتون حساب می‌شم، نه؟\n\n"

    "مثال ۹ (استرس شب امتحان):\n"
    "کاربر: ساعت دو نصفه‌شبه و فردا صبح امتحان فیزیولوژی دارم، استرس دارم خوابم نمی‌بره.\n"
    "بد (ممنوع): استرس در شب امتحان مضر است. بنابراین جهت عملکرد بهتر مغز، لازم است هم‌اکنون استراحت نمایید.\n"
    "خوب: وای ببخشید که این ساعت بیداری و داری حرص می‌خوری... ببین رفیق، ساعت دو شبه، الان مغزت خسته‌تر از اونه که مطلب جدید بره توش. به حرف من گوش کن، گوشی رو بذار کنار و چشماتو ببند، حتی چهار پنج ساعت خواب هم کلی کمکت می‌کنه فردا سر جلسه تمرکز داشته باشی.\n\n"

    "مثال ۱۰ (تشکر و خداحافظی):\n"
    "کاربر: مرسی هوشیار، خیلی خوب توضیح دادی، فعلاً خداحافظ.\n"
    "بد (ممنوع): خواهش می‌کنم. امیدوارم توضیحات ارائه شده مفید واقع شده باشد. خدانگهدار.\n"
    "خوب: قربونت برم، کاری نکردم که! برو بترکون، هر وقتم سؤال داشتی یا حوصله‌ت سر رفت بیا گپ بزنیم، فعلاً خداحافظ!"
)
DEFAULT_VOICE_SYSTEM_PROMPT = DEFAULT_VOICE_PROMPT



# ══════════════════════════════════════════════════
#  خطاهای اختصاصی
# ══════════════════════════════════════════════════
class AIError(Exception):
    """خطای قابل‌نمایش به کاربر/ادمین."""


class AIQuotaError(AIError):
    pass


class AIConfigError(AIError):
    """خطای پیکربندی (کلید/مدل/دسترسی).

    detail = علتِ دقیقِ برگشتی از provider (بدون secret) — فقط برای لاگ
    و پیام ادمین؛ متن اصلی همان پیام عمومی کاربرپسند است."""

    def __init__(self, msg: str, detail: str = ''):
        super().__init__(msg)
        self.detail = str(detail or '')[:400]


# ══════════════════════════════════════════════════
#  ⭐ م7 — فال‌بک چند-کلیدی (Key Failover)
#
#  هر provider می‌تواند چند کلید داشته باشد (Vault لیستی). وقتی کلیدی
#  429/سهمیه خورد یا نامعتبر بود، همان درخواست *بی‌درنگ* با کلید بعدیِ
#  سالم تکرار می‌شود؛ اگر آن هم لیمیت خورد، کلید بعدی — تا آخرین کلید.
#  وضعیتِ هر کلید (cooldown/آخرین خطا) فقط در حافظه‌ی همین پروسه است؛
#  ری‌استارت یعنی شروعِ تمیز (هیچ داده‌ی پایداری تغییر نمی‌کند).
# ══════════════════════════════════════════════════
KEY_COOLDOWN_QUOTA = 120      # 429/سهمیه — ۲ دقیقه
KEY_COOLDOWN_AUTH = 3600      # 400/401/403 — کلید نامعتبر — ۱ ساعت
KEY_COOLDOWN_SERVER = 30      # 5xx/شبکه — نیم‌دقیقه
MAX_KEYS_PER_PROVIDER = 20
_KEY_STATE: dict = {}         # 'provider::key' -> {'cooldown_until','kind','last_error','fails'}

# کدهای تصویر که چرخش به کلید دیگر منطقی است (سهمیه/کلید/سرویس)
_IMAGE_ROTATE_CODES = {
    'GEMINI_RATE_LIMIT', 'IMAGE_RATE_LIMIT',
    'GEMINI_AUTH_ERROR', 'IMAGE_AUTH_ERROR',
    'GEMINI_UNAVAILABLE', 'IMAGE_UNAVAILABLE',
    'GEMINI_TIMEOUT', 'IMAGE_TIMEOUT',
}


def _key_state_id(provider: str, key: str) -> str:
    return f"{(provider or '').strip()}::{(key or '').strip()}"


def masked_key(key: str) -> str:
    """نمایش امن کلید در لاگ/پیام ادمین — هرگز کلِ کلید."""
    k = (key or '').strip()
    if not k:
        return ''
    if len(k) <= 8:
        return '•' * len(k)
    return k[:4] + '••••••' + k[-4:]


def classify_key_error(exc: BaseException) -> str | None:
    """نگاشت خطا به نوعِ cooldown. None یعنی چرخش بی‌معناست
    (مثلاً بلاکِ ایمنی — با هر کلیدی همین می‌شود)."""
    if isinstance(exc, AIQuotaError):
        return 'quota'
    if isinstance(exc, AIConfigError):
        return 'auth'
    if isinstance(exc, AiImageError):
        return 'server' if getattr(exc, 'code', '') in _IMAGE_ROTATE_CODES else None
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return 'server'
    if isinstance(exc, AIError):
        return 'server'
    return None


def mark_key_failed(provider: str, key: str, exc: BaseException) -> str | None:
    kind = classify_key_error(exc)
    if kind is None:
        return None
    cd = {'quota': KEY_COOLDOWN_QUOTA, 'auth': KEY_COOLDOWN_AUTH,
          'server': KEY_COOLDOWN_SERVER}[kind]
    st = _KEY_STATE.setdefault(_key_state_id(provider, key), {})
    st['cooldown_until'] = time.monotonic() + cd
    st['kind'] = kind
    st['last_error'] = _sanitize_provider_text(f"{type(exc).__name__}: {exc}")[:200] or str(exc)[:200]
    st['fails'] = int(st.get('fails', 0)) + 1
    return kind


def mark_key_ok(provider: str, key: str) -> None:
    st = _KEY_STATE.get(_key_state_id(provider, key))
    if st:
        st['cooldown_until'] = 0.0
        st['fails'] = 0
        st['last_error'] = ''


# نام‌های سازگار برای لایه‌های Live / فالت‌تولرنس
KEY_COOLDOWN_AUTH_SEC = KEY_COOLDOWN_AUTH
KEY_COOLDOWN_QUOTA_SEC = KEY_COOLDOWN_QUOTA


def record_key_failure(provider: str, key: str, err_text: str = '',
                       cooldown_sec: int = KEY_COOLDOWN_AUTH) -> None:
    st = _KEY_STATE.setdefault(_key_state_id(provider, key), {})
    st['cooldown_until'] = time.monotonic() + max(1, int(cooldown_sec or KEY_COOLDOWN_SERVER))
    st['kind'] = 'quota' if cooldown_sec == KEY_COOLDOWN_QUOTA else 'auth'
    st['last_error'] = _sanitize_provider_text(str(err_text or ''))[:200]
    st['fails'] = int(st.get('fails', 0)) + 1


def record_key_success(provider: str, key: str) -> None:
    mark_key_ok(provider, key)


def key_cooldown_remaining(provider: str, key: str) -> float:
    st = _KEY_STATE.get(_key_state_id(provider, key)) or {}
    try:
        return max(0.0, float(st.get('cooldown_until', 0.0)) - time.monotonic())
    except (TypeError, ValueError):
        return 0.0


def ordered_keys(provider: str, keys) -> list:
    """کلیدها به ترتیبِ ذخیره، بدونِ آنهایی که cooldown دارند؛ اگر
    *همه* در cooldown بودند، به‌ترتیبِ نزدیک‌ترینِ انقضا — تا هیچ‌وقت
    بدونِ تلاش، به کاربر «سرویس خاموش» نگوییم."""
    keys = [k for k in (keys or []) if k]
    ready = [k for k in keys if key_cooldown_remaining(provider, k) <= 0]
    if ready:
        return ready
    return sorted(keys, key=lambda k: key_cooldown_remaining(provider, k))


def key_status_summary(provider: str, keys) -> list:
    """خلاصه‌ی وضعیت کلیدها برای پنل/ربات — فقط ماسک‌شده."""
    out = []
    for i, k in enumerate([x for x in (keys or []) if x], start=1):
        st = _KEY_STATE.get(_key_state_id(provider, k)) or {}
        cd = key_cooldown_remaining(provider, k)
        status = 'cooldown' if cd > 0 else ('failed' if st.get('fails') else 'active')
        out.append({
            'index': i, 'masked': masked_key(k), 'status': status,
            'cooldown_remaining': round(cd, 1),
            'kind': st.get('kind') or '',
            'last_error': st.get('last_error') or '',
        })
    return out


async def run_with_key_failover(provider: str, keys, factory, label: str = ''):
    """⭐ م7 — اجرای factory(api_key) با فال‌بک خودکار روی کلید بعدی.

    فقط خطاهایِ «چرخش‌پذیر» (سهمیه/کلید/شبکه) باعث رفتن به کلید بعدی
    می‌شوند؛ خطای منطقی (مثل بلاکِ ایمنی) همان‌جا برمی‌گردد چون با هر
    کلیدی تکرار می‌شود. خطای کلیدِ آخر هم عیناً raise می‌شود تا پیامِ
    کاربرپسندِ همان لایه حفظ شود."""
    provider = (provider or '').strip()
    _keys = ordered_keys(provider, keys)
    if not _keys:
        return await factory('')
    for i, key in enumerate(_keys):
        try:
            res = await factory(key)
            mark_key_ok(provider, key)
            if i:
                logger.info('AI key fallback settled: provider=%s attempt=%d/%d %s',
                            provider, i + 1, len(_keys), label)
            return res
        except Exception as e:                      # noqa: BLE001 — طبقه‌بندی می‌شود
            if classify_key_error(e) is None:
                raise
            mark_key_failed(provider, key, e)
            if i == len(_keys) - 1:
                raise
            logger.warning(
                'کلید #%d هوشیار (%s) شکست خورد → کلید بعدی امتحان می‌شود '
                '[%s] %s :: %s', i + 1, masked_key(key), label,
                type(e).__name__, _sanitize_provider_text(str(e))[:160])


# ══════════════════════════════════════════════════
#  حافظه‌ی مکالمه (پایدار، روی دیتابیس — نه RAM؛ توضیح در بالا)
# ══════════════════════════════════════════════════

async def _get_history(uid: int) -> list:
    items, updated_at = await db.ai_get_memory(uid)
    if not items:
        return []
    if updated_at and (now_utc() - parse_machine_datetime(updated_at)).total_seconds() > MEMORY_TTL_SECONDS:
        return []   # قدیمیه؛ نادیده‌اش می‌گیریم (خودش با remember بعدی جایگزین می‌شه)
    return [{'role': it.get('r'), 'text': it.get('t', '')} for it in items]


async def _remember(uid: int, role: str, text: str) -> None:
    if not text:
        return
    try:
        await db.ai_remember(uid, role, text, MAX_HISTORY_ITEMS)
    except Exception:
        logger.exception("ذخیره‌ی حافظه‌ی مکالمه‌ی هوشیار ناموفق بود")


async def _clear_memory(uid: int) -> None:
    try:
        await db.ai_clear_memory(uid)
    except Exception:
        logger.exception("پاک‌کردنِ حافظه‌ی مکالمه‌ی هوشیار ناموفق بود")


# ══════════════════════════════════════════════════
#  کشِ «گزارش پاسخ نامناسب» — نگاشتِ (chat_id, message_id) به
#  متن سوال/جواب، فقط برای چند دقیقه‌ای که دکمه‌ی 🚩 زیر پیام فعاله.
#  این هم فقط RAM هست، با سقف LRU که رشدش رو محدود می‌کنه.
# ══════════════════════════════════════════════════
_report_cache: "OrderedDict[str, dict]" = OrderedDict()


def _cache_for_report(chat_id: int, message_id: int, uid: int, name: str,
                       question: str, answer: str) -> None:
    key = f"{chat_id}:{message_id}"
    _report_cache[key] = {
        'uid': uid, 'name': name or '—',
        'question': question or '—', 'answer': answer or '—',
    }
    _report_cache.move_to_end(key)
    while len(_report_cache) > REPORT_CACHE_MAX:
        _report_cache.popitem(last=False)


# ══════════════════════════════════════════════════
#  تنظیمات — همه از bot_settings (کلید-مقدار عمومی دیتابیس)
# ══════════════════════════════════════════════════

DEFAULT_DISABLED_MSG = "🤖 بخش هوش مصنوعی توسط مدیریت غیرفعال شد."


def _detect_provider_for_model(model_id: str) -> str | None:
    """تشخیص provider از روی model_id با کاتالوگ."""
    if not model_id:
        return None
    mid = model_id.strip()
    for pid, models in MODEL_CATALOG.items():
        for m_id, _, _ in models:
            if m_id == mid:
                return pid
    for m_id, _, _ in IMAGE_MODEL_CATALOG:
        if m_id == mid:
            if m_id.startswith('gemini'):
                return 'gemini'
            if 'FLUX' in m_id or 'stable' in m_id.lower() or 'flux' in m_id.lower():
                return 'openrouter'
            if 'gemini' in m_id:
                return 'gemini'
            return 'openrouter'
    if '/' in mid:
        if ':free' in mid or '/' in mid:
            return 'openrouter'
    if mid.startswith('gemini'):
        return 'gemini'
    return None


def _maybe_decrypt(v):
    if isinstance(v, dict) and "c" in v:
        return decrypt_value(v)
    if isinstance(v, str) and v.startswith("gAAAAA"):
        # bare Fernet token stored as string (legacy)
        return decrypt_value(v)
    return v

def _load_vault(raw: dict) -> dict:
    vault: dict = {}
    raw_vault = raw.get('ai_api_keys', '')
    # W1: decrypt if encrypted dict
    if isinstance(raw_vault, dict) and raw_vault.get("enc"):
        try:
            raw_vault = decrypt_value(raw_vault)
        except: raw_vault = ""
    if raw_vault:
        if isinstance(raw_vault, dict):
            vault = dict(raw_vault)
        elif isinstance(raw_vault, str):
            raw_vault = raw_vault.strip()
            if raw_vault:
                try:
                    loaded = json.loads(raw_vault)
                    if isinstance(loaded, dict):
                        vault = loaded
                    elif isinstance(loaded, str) and loaded.startswith("gAAAAA"):
                        vault = json.loads(decrypt_value(loaded) or "{}") if decrypt_value(loaded) else {}
                except Exception:
                    # maybe encrypted JSON string
                    try:
                        dec = decrypt_value(raw_vault)
                        loaded = json.loads(dec)
                        if isinstance(loaded, dict): vault = loaded
                    except: vault = {}
    # legacy single key fallback (may be encrypted)
    legacy = raw.get('ai_api_key')
    legacy = _maybe_decrypt(legacy) if legacy is not None else ""
    legacy = (legacy or "").strip()
    provider = raw.get('ai_provider', 'gemini')
    if legacy and not vault:
        vault[provider] = legacy
    for pid in PROVIDERS:
        kv = raw.get(f'ai_api_key_{pid}')
        kv = _maybe_decrypt(kv) if kv is not None else ""
        k = (kv or "").strip()
        if k and pid not in vault:
            vault[pid] = k
    # ⭐ م7 — نرمال‌سازی چند-کلیدی: مقدار هر provider می‌تواند رشته‌ی
    # قدیمی یا لیستِ کلیدها باشد؛ خروجی همیشه {provider: [keys]} است
    # (پاک‌سازی + حذف تکراری‌ها با حفظ ترتیب).
    normalized: dict = {}
    for pid, v in vault.items():
        raw_list = v if isinstance(v, list) else ([v] if isinstance(v, str) else [])
        for k in raw_list:
            k = sanitize_api_key(k) if isinstance(k, str) else ''
            if k and k not in normalized.get(pid, []):
                normalized.setdefault(pid, []).append(k)
    return normalized


async def get_ai_config() -> dict:
    raw = await db.get_settings_by_prefix('ai_')
    provider = (raw.get('ai_provider', 'gemini') or 'gemini').strip() or 'gemini'
    if provider not in PROVIDERS:
        provider = 'gemini'
    personas_raw = raw.get('ai_personas', '{}')
    try:
        personas = json.loads(personas_raw) if isinstance(personas_raw, str) else (personas_raw or {})
    except (ValueError, TypeError):
        personas = {}
    vault = _load_vault(raw)
    # 🔴 FIX-R1 (مورد ۶) — پاکسازی همه‌ی کلیدها هنگام خواندن: کلیدِ
    # کثیفِ قدیمی (کاراکتر نامرئی/رقم فارسی) همین‌جا سالم می‌شود تا
    # هر دو مسیر ربات و پنل با یک مقدار واحد کار کنند.
    # ⭐ م7 — vault اکنون {provider: [keys]} است؛ پاکسازی هر کلید
    vault = {pid: [k for k in (sanitize_api_key(x) for x in lst) if k]
             for pid, lst in vault.items()}
    vault = {pid: lst for pid, lst in vault.items() if lst}
    model = raw.get('ai_model') or DEFAULT_MODELS.get(provider, DEFAULT_MODEL)
    detected = _detect_provider_for_model(model)
    if detected and detected != provider and detected in vault and vault.get(detected):
        provider = detected
    # ⭐ م7 — کلیدها به‌ترتیب؛ primary = اولین (compat با کل کد قدیمی)
    keys = list(vault.get(provider) or [])
    if not keys:
        _legacy_key = sanitize_api_key(raw.get('ai_api_key', '') or '')
        if _legacy_key:
            keys = [_legacy_key]
    api_key = keys[0] if keys else ''
    raw_img_model = (raw.get('ai_image_model') or '').strip()
    if raw_img_model in _LEGACY_NON_GOOGLE_IMAGE_MODELS:
        raw_img_model = ''
    image_model = raw_img_model or DEFAULT_IMAGE_MODEL
    image_enabled = str(raw.get('ai_image_enabled', '1')) not in ('0', 'false', 'False', '')
    image_daily_limit = int(raw.get('ai_image_daily_limit', DEFAULT_IMAGE_LIMIT) or 0)
    image_provider_raw = (raw.get('ai_image_provider') or '').strip()
    d2 = _detect_provider_for_model(image_model)
    # ⭐ م8.4 — اگر مدل تصویر متعلق به گوگل (gemini-*) است، همیشه با
    # provider='gemini' و کلیدهای Gemini اجرا شود (مقدار قدیمیِ
    # ai_image_provider مثل openrouter باعث ارسال کلید اشتباه به گوگل نشود).
    if d2 == 'gemini' and (raw_img_model or not image_provider_raw or image_provider_raw == 'openrouter'):
        image_provider = 'gemini'
    elif image_provider_raw and image_provider_raw in PROVIDERS:
        image_provider = image_provider_raw
    else:
        image_provider = d2 or provider
        if image_provider not in PROVIDERS:
            image_provider = provider
    # ⭐ م7 — صفِ فال‌بکِ تصویر هم لیستی است
    image_keys = list(vault.get(image_provider) or []) or list(vault.get(provider) or [])
    if not image_keys:
        _legacy_img = sanitize_api_key(raw.get('ai_api_key', '') or '')
        if _legacy_img:
            image_keys = [_legacy_img]
    image_api_key = image_keys[0] if image_keys else ''
    # ⭐ م8 — پاسخ صوتی (TTS) و رزولوشن تصویر
    voice_reply_raw = (raw.get('ai_voice_reply', 'voice') or 'voice').strip()
    voice_reply = voice_reply_raw if voice_reply_raw in VOICE_REPLY_MODES else 'voice'
    # ⭐ م8.2 — «متنِ همراه ویس»: پیش‌فرض خاموش = ویس‌فرستاد ⇒ فقط ویس
    voice_with_text = 'on' if str(
        raw.get('ai_voice_with_text', 'off') or 'off').strip() == 'on' else 'off'
    tts_voice = (raw.get('ai_tts_voice', TTS_VOICE_DEFAULT) or TTS_VOICE_DEFAULT).strip()
    if tts_voice not in PREBUILT_TTS_VOICES:
        tts_voice = TTS_VOICE_DEFAULT
    tts_model = (raw.get('ai_tts_model', TTS_MODEL_DEFAULT) or TTS_MODEL_DEFAULT).strip()
    try:
        voice_max = int(raw.get('ai_voice_reply_max_chars', 500) or 500)
    except (TypeError, ValueError):
        voice_max = 500
    image_size = (raw.get('ai_image_size', '1K') or '1K').strip().upper()
    if image_size not in IMAGE_SIZES:
        image_size = '1K'
    # ⭐ م9 — تنظیمات تماس صوتی زنده (Gemini Live API)
    live_enabled = str(raw.get('ai_live_enabled', '1')) not in ('0', 'false', 'False', '')
    live_model_raw = (raw.get('ai_live_model') or '').strip()
    _valid_live_ids = {m[0] for m in LIVE_MODEL_CATALOG}
    live_model = live_model_raw if (live_model_raw in _valid_live_ids or 'live' in live_model_raw.lower()) else DEFAULT_LIVE_MODEL
    live_voice_raw = (raw.get('ai_live_voice') or '').strip()
    live_voice = live_voice_raw if live_voice_raw in PREBUILT_TTS_VOICES else tts_voice
    live_thinking_raw = (raw.get('ai_live_thinking_level', 'low') or 'low').strip().lower()
    live_thinking_level = live_thinking_raw if live_thinking_raw in LIVE_THINKING_LEVELS else 'low'
    try:
        live_daily_minutes = max(0, min(600, int(raw.get('ai_live_daily_minutes', DEFAULT_LIVE_DAILY_MINUTES))))
    except (TypeError, ValueError):
        live_daily_minutes = DEFAULT_LIVE_DAILY_MINUTES
    try:
        live_max_session_sec = max(60, min(1800, int(raw.get('ai_live_max_session_sec', DEFAULT_LIVE_MAX_SESSION_SEC))))
    except (TypeError, ValueError):
        live_max_session_sec = DEFAULT_LIVE_MAX_SESSION_SEC
    live_target_language = (raw.get('ai_live_target_language', 'fa') or 'fa').strip().lower()[:10] or 'fa'
    try:
        live_temperature = max(0.1, min(1.5, float(raw.get('ai_live_temperature', DEFAULT_LIVE_TEMPERATURE))))
    except (TypeError, ValueError):
        live_temperature = DEFAULT_LIVE_TEMPERATURE
    voice_system_prompt = (raw.get('ai_voice_system_prompt') or '').strip() or DEFAULT_VOICE_PROMPT
    live_keys = list(vault.get('gemini') or [])
    if not live_keys and api_key and provider == 'gemini':
        live_keys = [api_key]
    # 🔴 FIX-R1 (مورد ۶) — مشکل کلید به‌صورت صریح در config می‌آید تا
    # «تست اتصال» پنل و پیام خطای ربات دقیقاً یک چیز بگویند، نه
    # «خطای غیرمنتظره» مبهم.
    api_key_error = api_key_problem(api_key) if api_key else None
    return {
        'enabled':          bool(raw.get('ai_enabled', False)),
        'provider':         provider,
        'api_key':          api_key,
        # ⭐ م7 — compat: مصرف‌کننده‌های قدیمی هنوز رشته انتظار دارند
        'api_keys':         {pid: lst[0] for pid, lst in vault.items()},
        'vault':            {pid: lst[0] for pid, lst in vault.items()},
        # ⭐ م7 — لیست کامل کلیدها (به‌ترتیبِ فال‌بک) + شمارش
        'api_key_list':     keys,
        'image_api_key_list': image_keys,
        'live_api_key_list': live_keys,
        'vault_multi':      {pid: list(lst) for pid, lst in vault.items()},
        'vault_counts':     {pid: len(lst) for pid, lst in vault.items()},
        'api_key_error':    api_key_error,
        'model':            model,
        'daily_limit':      int(raw.get('ai_daily_limit', DEFAULT_LIMIT) or 0),
        'system_prompt':    raw.get('ai_system_prompt', DEFAULT_PROMPT),
        'voice_system_prompt': voice_system_prompt,
        'default_voice_system_prompt': DEFAULT_VOICE_PROMPT,
        'disabled_message': raw.get('ai_disabled_message', ''),
        'personas':         personas,
        'thinking':         raw.get('ai_thinking', 'auto'),
        'image_enabled':    image_enabled,
        'image_model':      image_model,
        'image_provider':   image_provider,
        'image_api_key':    image_api_key,
        'image_daily_limit': image_daily_limit,
        # ⭐ م8
        'voice_reply':      voice_reply,
        'voice_with_text':  voice_with_text,
        'tts_voice':        tts_voice,
        'tts_model':        tts_model,
        'voice_reply_max_chars': voice_max,
        'image_size':       image_size,
        # ⭐ م9 — تماس صوتی زنده (Gemini Live)
        'live_enabled':         live_enabled,
        'live_model':           live_model,
        'live_voice':           live_voice,
        'live_thinking_level':  live_thinking_level,
        'live_daily_minutes':   live_daily_minutes,
        'live_max_session_sec': live_max_session_sec,
        'live_target_language': live_target_language,
        'live_temperature':     live_temperature,
    }


async def set_api_key_for_provider(provider: str, key: str) -> None:
    """🔴 FIX-R1 (مورد ۶) — کلید پیش از ذخیره پاکسازی/اعتبارسنجی می‌شود.

    کلید نامعتبر (مثلاً متن فارسی یا کلید با کاراکتر نامرئی) با
    ValueError و پیام فارسی رد می‌شود تا هرگز وارد vault نشود — ریشه‌ی
    خطای ascii همین مقدارهای کثیف بود."""
    provider = (provider or 'gemini').strip() or 'gemini'
    key = sanitize_api_key(key or '')
    if key:
        problem = api_key_problem(key)
        if problem:
            raise ValueError(problem)
    raw = await db.get_settings_by_prefix('ai_')
    vault = _load_vault(raw)
    # ⭐ م7 — «تنظیم» = جایگزینیِ همه‌ی کلیدهای این provider با همین یکی
    # (برای افزودنِ کلیدِ فال‌بک از add_api_key_for_provider استفاده شود).
    if key:
        vault[provider] = [key]
    else:
        vault.pop(provider, None)
    await _save_vault(vault)
    await _sync_legacy_key_mirrors(provider, key, raw)


async def _save_vault(vault: dict) -> None:
    """ذخیره‌ی vault (اکنون {provider: [keys]}) با رمزنگاری اختیاری."""
    vault_json = json.dumps(vault, ensure_ascii=False)
    if is_encryption_enabled():
        await db.set_setting('ai_api_keys', encrypt_value(vault_json))
    else:
        await db.set_setting('ai_api_keys', vault_json)


async def _sync_legacy_key_mirrors(provider: str, primary_key: str,
                                   raw: dict = None) -> None:
    """آینه‌های legacy (ai_api_key_{pid} و ai_api_key) فقط کلیدِ اصلی را
    نگه می‌دارند — برای سازگاری مسیرهای قدیمی."""
    enc = encrypt_value(primary_key) if is_encryption_enabled() and primary_key else (primary_key or "")
    await db.set_setting(f'ai_api_key_{provider}', enc)
    if raw is None:
        raw = await db.get_settings_by_prefix('ai_')
    cur = (raw.get('ai_provider') or 'gemini').strip() or 'gemini'
    if provider == cur:
        await db.set_setting('ai_api_key', enc)


async def add_api_key_for_provider(provider: str, key: str) -> int:
    """⭐ م7 — افزودن کلیدِ فال‌بک به انتهای صفِ provider (بدون حذف قبلی‌ها).

    خروجی: تعداد کل کلیدهای این provider پس از افزودن."""
    provider = (provider or 'gemini').strip() or 'gemini'
    key = sanitize_api_key(key or '')
    if not key:
        raise ValueError("کلید خالی است.")
    problem = api_key_problem(key)
    if problem:
        raise ValueError(problem)
    raw = await db.get_settings_by_prefix('ai_')
    vault = _load_vault(raw)
    keys = list(vault.get(provider) or [])
    if key in keys:
        raise ValueError("این کلید قبلاً برای همین ارائه‌دهنده ذخیره شده است.")
    if len(keys) >= MAX_KEYS_PER_PROVIDER:
        raise ValueError(f"حداکثر {MAX_KEYS_PER_PROVIDER} کلید برای هر ارائه‌دهنده مجاز است.")
    keys.append(key)
    vault[provider] = keys
    await _save_vault(vault)
    # primary عوض نشده (کلید جدید انتهای صف است) → آینه‌ها فقط در صورت خالی‌بودن
    if len(keys) == 1:
        await _sync_legacy_key_mirrors(provider, key, raw)
    return len(keys)


async def remove_api_key_for_provider(provider: str, index: int) -> str:
    """⭐ م7 — حذف کلید شماره‌ی index (۱-مبنا) از صفِ provider.

    خروجی: کلیدِ ماسک‌شده‌ی حذف‌شده."""
    provider = (provider or 'gemini').strip() or 'gemini'
    try:
        index = int(index)
    except (TypeError, ValueError):
        raise ValueError("شماره‌ی کلید معتبر نیست.")
    raw = await db.get_settings_by_prefix('ai_')
    vault = _load_vault(raw)
    keys = list(vault.get(provider) or [])
    if index < 1 or index > len(keys):
        raise ValueError("شماره‌ی کلید معتبر نیست.")
    removed = keys.pop(index - 1)
    if keys:
        vault[provider] = keys
    else:
        vault.pop(provider, None)
    await _save_vault(vault)
    await _sync_legacy_key_mirrors(provider, keys[0] if keys else '', raw)
    return masked_key(removed)


async def _chat_ping_gemini(api_key: str, model: str = None) -> None:
    """⭐ م8.3 — پینگِ واقعیِ چت: همان generateContent که چتِ کاربر می‌رود.

    چرا نه ListModels؟ کلیدهایی که به سرویس‌اکانتِ (حذف/غیرفعال‌شده)
    مقید شده‌اند به ListModels پاسخِ 200 می‌دهند ولی generateContent همان
    401ِ «The bound service account is deleted or disabled» را می‌گیرد که
    چتِ واقعی می‌گیرد — یعنی تستِ پنل درباره‌ی سلامتِ چت دروغ می‌گفت.
    اینجا تولیدِ واقعیِ ۱ توکن (maxOutputTokens=1، هزینه≈۰) با همان
    مسیر/مدلِ چت زده می‌شود."""
    if not model:
        try:
            raw = await db.get_settings_by_prefix('ai_')
        except Exception:
            raw = {}
        model = (raw.get('ai_model') or DEFAULT_MODELS.get('gemini')
                 or DEFAULT_MODEL)
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    payload = {'contents': [{'role': 'user', 'parts': [{'text': '۱'}]}],
               'generationConfig': {'maxOutputTokens': 1}}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, headers={
            'Content-Type': 'application/json', 'x-goog-api-key': api_key},
            json=payload)
    if resp.status_code == 200:
        return
    if resp.status_code == 429:
        raise AIQuotaError("سهمیه‌ی این کلید فعلاً پر است (429).")
    detail = _provider_error_detail(resp.text)
    if 'service account' in detail.lower():
        raise AIConfigError(
            "کلید به سرویس‌اکانتِ حذف/غیرفعال‌شده‌ی گوگل وصل است — برای چتِ "
            "واقعی مرده است؛ در aistudio.google.com/apikey کلیدِ تازه بسازید "
            "و در Vault جایگزین کنید.", detail=detail)
    _raise_gemini_status_error(resp.status_code, detail)


async def test_api_key(provider: str, api_key: str) -> tuple:
    """⭐ م8.3 — تستِ واقعیِ یک کلید: برای gemini تولیدِ واقعیِ ۱ توکن با
    همان مسیر چت (نه ListModels که برای کلیدهای خراب هم 200 می‌دهد)؛
    برای بقیه همان فهرست مدل‌ها.
    خروجی: (ok, error). وضعیتِ فال‌بکِ کلید هم به‌روز می‌شود."""
    provider = (provider or 'gemini').strip() or 'gemini'
    key = sanitize_api_key(api_key or '')
    try:
        _kp = api_key_problem(key)
        if _kp:
            return False, _kp
        if provider == 'gemini':
            await _chat_ping_gemini(key)
        elif provider in PROVIDERS and PROVIDERS[provider].get('url'):
            await _list_models_openai_compat(
                PROVIDERS[provider]['url'], key, PROVIDERS[provider]['label'])
        else:
            return False, 'ارائه‌دهنده پشتیبانی نمی‌شود.'
        mark_key_ok(provider, key)
        return True, ''
    except Exception as e:                      # noqa: BLE001
        mark_key_failed(provider, key, e)
        return False, (_sanitize_provider_text(str(e))[:200]
                       or type(e).__name__)


async def test_all_keys_for_provider(provider: str) -> dict:
    """⭐ م7 — تستِ همه‌ی کلیدهای provider؛ نتیجه per-key + شمارش سالم‌ها."""
    provider = (provider or 'gemini').strip() or 'gemini'
    raw = await db.get_settings_by_prefix('ai_')
    vault = _load_vault(raw)
    keys = [k for k in (sanitize_api_key(x) for x in (vault.get(provider) or [])) if k]
    results = []
    for i, k in enumerate(keys, start=1):
        ok, err = await test_api_key(provider, k)
        results.append({'index': i, 'masked': masked_key(k), 'ok': ok,
                        'error': err,
                        'status': 'active' if ok else 'failed'})
    return {'provider': provider, 'count': len(keys), 'results': results,
            'ok_count': sum(1 for r in results if r['ok'])}


async def list_api_keys_for_provider(provider: str) -> dict:
    """⭐ م7 — فهرستِ کلیدهای provider به‌همراه وضعیتِ فال‌بک (ماسک‌شده)."""
    provider = (provider or 'gemini').strip() or 'gemini'
    raw = await db.get_settings_by_prefix('ai_')
    vault = _load_vault(raw)
    keys = [k for k in (sanitize_api_key(x) for x in (vault.get(provider) or [])) if k]
    return {
        'provider': provider,
        'count': len(keys),
        'keys': key_status_summary(provider, keys),
    }


async def delete_api_key_for_provider(provider: str) -> None:
    await set_api_key_for_provider(provider, '')


async def set_ai_setting(key: str, value) -> None:
    await db.set_setting(f'ai_{key}', value)


async def save_persona(name: str, prompt: str) -> None:
    """پرسونای فعلی رو با یه اسم ذخیره می‌کنه تا بعداً سریع بشه بهش سوییچ کرد."""
    cfg = await get_ai_config()
    personas = cfg['personas']
    personas[name.strip()[:40]] = prompt
    await set_ai_setting('personas', json.dumps(personas, ensure_ascii=False))


async def delete_persona(name: str) -> None:
    cfg = await get_ai_config()
    personas = cfg['personas']
    personas.pop(name, None)
    await set_ai_setting('personas', json.dumps(personas, ensure_ascii=False))


# ══════════════════════════════════════════════════
#  ارائه‌دهنده‌ها (Providers)
#  برای افزودن یک AI جدید: یک تابع async با همین امضا بنویس و در
#  دیکشنری STREAM_PROVIDERS پایین ثبتش کن. سپس از پنل ادمین می‌شود روی
#  provider جدید سوییچ کرد — بدون تغییر جای دیگری از کد.
# ══════════════════════════════════════════════════

# ══════════════════════════════════════════════════
#  ⚠️ قابلیتِ جدید: Function Calling — هوشیار می‌تونه واقعاً از
#  دیتابیسِ خودِ هامزیار (برنامه/نمراتِ همون دانشجو) بخونه، نه اینکه
#  حدس بزنه. فقط وقتی uid داریم (یعنی یه دانشجوی واقعی داره سوال
#  می‌پرسه، نه تستِ ادمین) فعال می‌شه.
# ══════════════════════════════════════════════════
# ══════════════════════════════════════════════════
#  ابزارهایی که به همه‌ی دانشجوها داده می‌شن (uid فقط «همینه که داره
#  چت می‌کنه»، هیچ‌کدوم پارامترِ آیدی/یوزرنیمِ ورودی نمی‌گیرن).
#
#  ⚠️ قانونِ امنیتیِ ثابت — هیچ‌وقت نقض نشه: هر تابعی که اینجا اضافه
#  می‌شه باید فقط و فقط دیتای «uid» ی که خودِ Gemini در زمانِ اجرا از
#  ما می‌گیره رو بخونه (که ما خودمون، نه مدل، تعیینش می‌کنیم — همون
#  آیدیِ تلگرامِ واقعیِ درخواست‌دهنده). هیچ تابعِ دانشجویی نباید یک
#  پارامترِ «آیدی/یوزرنیم/اسمِ کاربرِ دیگر» بگیره؛ وگرنه یه دانشجو با
#  فریب‌دادنِ مدل (مثلاً «فرض کن من آیدی ۱۲۳۴۵۶ام») می‌تونه دیتای یه
#  کاربرِ دیگه رو بخونه. توابعِ «admin_*» که این محدودیت رو ندارن،
#  همیشه پایین‌تر با چکِ دوجداره (uid == ADMIN_ID) محافظت می‌شن.
# ══════════════════════════════════════════════════
AI_FUNCTIONS = [
    {
        'name': 'get_my_schedule',
        'description': (
            'برنامه‌ی کلاسی/امتحانیِ آینده‌ی همین دانشجو رو از دیتابیسِ هامزیار می‌خونه. '
            'برای سوالاتی مثل «کی امتحان دارم؟» یا «برنامه‌ی این هفته‌ام چیه؟» استفاده کن.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'type_filter': {
                    'type': 'string',
                    'description': 'فیلترِ نوع، مثلاً "امتحان" یا "کلاس" — اگه خالی بمونه همه برمی‌گرده.',
                }
            },
        },
    },
    {
        'name': 'get_my_grades',
        'description': (
            'نمراتِ ثبت‌شده‌ی همین دانشجو رو از دیتابیسِ هامزیار می‌خونه. '
            'برای سوالاتی مثل «نمره‌ی آخرین کوییزم چند شد؟» استفاده کن.'
        ),
        'parameters': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'get_my_subscription_status',
        'description': 'وضعیتِ اشتراکِ همین دانشجو (فعال/منقضی، چند روز مونده) رو می‌خونه.',
        'parameters': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'get_my_tickets',
        'description': 'تیکت‌های پشتیبانیِ خودِ همین دانشجو (وضعیت، موضوع) رو می‌خونه.',
        'parameters': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'get_my_profile_summary',
        'description': 'اطلاعاتِ ثبت‌نامِ خودِ همین دانشجو (گروه، ورودی، وضعیتِ تایید) رو می‌خونه.',
        'parameters': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'remember_about_me',
        'description': (
            'وقتی کاربر یه چیزِ ماندگار و مهم درباره‌ی خودش می‌گه (مثلاً درسی که '
            'داره می‌خونه، یه ترجیحِ ثابت مثلِ «جواب‌ها رو کوتاه بگو»، یا یه علاقه‌ی '
            'مشخص) که توی سوالاتِ بعدی هم به‌کارِت میاد، این تابع رو صدا بزن تا یادت '
            'بمونه. برای اطلاعاتِ موقت/بی‌اهمیتِ همون یه سوال استفاده نکن.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {'fact': {'type': 'string', 'description': 'خودِ نکته، خیلی کوتاه و مشخص'}},
            'required': ['fact'],
        },
    },
]

# ══════════════════════════════════════════════════
#  ⚠️ قابلیتِ جدید: ابزارهای «فقط ادمین ارشد» — دسترسیِ خوندنیِ گسترده
#  به دیتای ربات (کاربران، تیکت‌ها، آمار، بانکِ سوال). این‌ها هیچ‌وقت
#  به دانشجوها اضافه نمی‌شن (چک هم توی ساختِ لیستِ ابزارها و هم داخلِ
#  خودِ اجرا انجام می‌شه — دفاعِ دوجداره). فقط خوندن — هیچ‌کدوم چیزی رو
#  توی دیتابیس تغییر نمی‌دن.
# ══════════════════════════════════════════════════
ADMIN_AI_FUNCTIONS = [
    {
        'name': 'admin_search_user',
        'description': (
            'فقط برای ادمین ارشد: یک کاربرِ خاص رو با آیدیِ عددی، یوزرنیم یا اسم پیدا '
            'می‌کنه و پروفایل/وضعیتش (گروه، ورودی، تاییدشده یا نه، آخرین فعالیت) رو برمی‌گردونه.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {'query': {'type': 'string', 'description': 'آیدیِ عددی، یوزرنیم یا اسمِ کاربر'}},
            'required': ['query'],
        },
    },
    {
        'name': 'admin_get_bot_stats',
        'description': 'فقط برای ادمین ارشد: آمارِ کلیِ ربات (تعدادِ کاربران، فعالیتِ روزانه/هفتگی، تیکت‌های باز/بسته) رو می‌ده.',
        'parameters': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'admin_list_tickets',
        'description': 'فقط برای ادمین ارشد: لیستِ تیکت‌های پشتیبانی رو می‌ده (پیش‌فرض: فقط بازها).',
        'parameters': {
            'type': 'object',
            'properties': {
                'status_filter': {'type': 'string', 'description': '"open" یا "closed"؛ اگه خالی بمونه هر دو.'},
            },
        },
    },
    {
        'name': 'admin_search_questions',
        'description': 'فقط برای ادمین ارشد: جستجوی متنیِ آزاد توی بانکِ سوال (روی متنِ سوال/توضیح).',
        'parameters': {
            'type': 'object',
            'properties': {'query': {'type': 'string', 'description': 'عبارتِ جستجو'}},
            'required': ['query'],
        },
    },
    {
        'name': 'admin_get_user_full_profile',
        'description': (
            'فقط برای ادمین ارشد: یه دیدِ کاملِ ۳۶۰درجه از یک کاربرِ خاص می‌ده — پروفایل + '
            'وضعیتِ اشتراک + تعدادِ نمرات ثبت‌شده + تعدادِ تیکت‌های باز. برای سوالاتی مثلِ '
            '«وضعیتِ کاملِ فلان کاربر چیه؟» استفاده کن.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {'query': {'type': 'string', 'description': 'آیدیِ عددی، یوزرنیم یا اسمِ کاربر'}},
            'required': ['query'],
        },
    },
    {
        'name': 'admin_get_subscription_stats',
        'description': 'فقط برای ادمین ارشد: تعدادِ کاربرانِ فعال/منقضی/در انتظارِ پرداختِ اشتراک رو می‌ده.',
        'parameters': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'admin_search_faq',
        'description': 'فقط برای ادمین ارشد: جستجوی متنی توی سوالاتِ متداول (FAQ) ربات.',
        'parameters': {
            'type': 'object',
            'properties': {'query': {'type': 'string', 'description': 'عبارتِ جستجو'}},
            'required': ['query'],
        },
    },
    {
        'name': 'admin_list_content_admins',
        'description': 'فقط برای ادمین ارشد: لیستِ ادمین‌های محتوایِ فعلیِ ربات رو می‌ده.',
        'parameters': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'admin_list_pending_approvals',
        'description': (
            'فقط برای ادمین ارشد: خلاصه‌ی همه‌ی چیزهایی که منتظرِ تاییدِ ادمین هستن — '
            'کاربرانِ در انتظارِ تایید، سوالاتِ در انتظارِ تایید، پرداخت‌های در انتظارِ بررسی.'
        ),
        'parameters': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'admin_get_interaction_insights',
        'description': (
            'فقط برای ادمین ارشد: بر اساسِ گزارش‌های اخیرِ «پاسخِ نامناسب» که دانشجوها ثبت '
            'کردن، یه خلاصه‌ی تحلیلی از الگوهای مشکل‌ساز می‌ده — برای اینکه ادمین بتونه دستی '
            'تصمیم بگیره پرامپت/شخصیتِ هوشیار رو تغییر بده یا نه. (این تحلیل صرفاً پیشنهادیه، '
            'خودکار چیزی رو تغییر نمی‌ده.)'
        ),
        'parameters': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'admin_get_ticket_detail',
        'description': 'فقط برای ادمین ارشد: جزئیاتِ کاملِ یک تیکتِ خاص (متنِ اصلی + همه‌ی پاسخ‌ها) رو با شماره‌ی تیکت می‌ده.',
        'parameters': {
            'type': 'object',
            'properties': {'ticket_id': {'type': 'integer', 'description': 'شماره‌ی تیکت'}},
            'required': ['ticket_id'],
        },
    },
    {
        'name': 'admin_get_schedule_overview',
        'description': 'فقط برای ادمین ارشد: خلاصه‌ی برنامه‌ی کلاسی/امتحانیِ آینده‌ی همه‌ی گروه‌ها (نه فقط یک دانشجوی خاص) رو می‌ده.',
        'parameters': {'type': 'object', 'properties': {}},
    },
]


async def _execute_ai_function(name: str, args: dict, uid: int) -> str:
    args = args or {}
    try:
        if name == 'get_my_schedule':
            user = await db.get_user(uid) or {}
            rows = await db.get_schedules(group=user.get('group'))
            type_filter = (args.get('type_filter') or '').strip()
            if type_filter:
                rows = [r for r in rows if type_filter in (r.get('type') or '')]
            if not rows:
                return 'هیچ برنامه‌ی آینده‌ای برای این دانشجو ثبت نشده.'
            lines = [
                f"- {r.get('type','')}: {r.get('lesson','')} | استاد: {r.get('teacher','')} | "
                f"{format_date_fa(r.get('date'), long=True, date_only=True)} ساعت {format_time_fa(r.get('time'))}"
                for r in rows[:15]
            ]
            return "\n".join(lines)

        if name == 'get_my_grades':
            rows = await db.grade_list_for_student(uid)
            if not rows:
                return 'هنوز نمره‌ای برای این دانشجو ثبت نشده.'
            lines = [
                f"- {r.get('lesson','')} ({r.get('exam_title','')}): {r.get('score','')} "
                f"| تاریخ: {r.get('exam_date','')}"
                for r in rows[:20]
            ]
            return "\n".join(lines)

        if name == 'get_my_subscription_status':
            sub = await db.sub_get(uid)
            if not sub:
                return 'این کاربر هیچ اشتراکی ثبت نکرده.'
            active = await db.sub_is_active(uid)
            days   = await db.sub_days_left(uid)
            return (
                f"وضعیت: {'فعال ✅' if active else 'غیرفعال/منقضی ⌛'}\n"
                f"پلن: {sub.get('plan_name','—')}\n"
                f"روزهای باقی‌مانده: {days if active else 0}\n"
                f"تاریخِ پایان: {format_datetime_fa(sub.get('end_date'))}"
            )

        if name == 'get_my_tickets':
            rows = await db.ticket_list_for_user(uid)
            if not rows:
                return 'این کاربر هیچ تیکتی ثبت نکرده.'
            lines = [
                f"- #{t.get('ticket_id')} | موضوع: {t.get('subject','—')} | وضعیت: {t.get('status','—')} | {format_datetime_fa(t.get('created_at'))}"
                for t in rows
            ]
            return "\n".join(lines)

        if name == 'get_my_profile_summary':
            user = await db.get_user(uid) or {}
            return (
                f"نام: {user.get('name','—')}\n"
                f"گروه: {user.get('group','—')} | ورودی: {user.get('intake','—')}\n"
                f"وضعیتِ تایید: {'تاییدشده ✅' if user.get('approved') else 'در انتظارِ تایید ⏳'}\n"
                f"تاریخِ عضویت: {format_datetime_fa(user.get('registered_at',''), fallback='—')}"
            )

        if name == 'remember_about_me':
            fact = (args.get('fact') or '').strip()
            if not fact:
                return 'چیزی برای به‌خاطرسپردن نبود.'
            await db.ai_remember_fact(uid, fact)
            return 'یادم موند.'

        # ⚠️ همه‌ی توابعِ زیر «فقط ادمین ارشد» هستن — حتی اگه به هر دلیلی
        # (باگ/تغییرِ آینده) این تابع‌ها برای یه کاربرِ دیگه هم صدا زده
        # بشن، اینجا دوباره چک می‌شه و اجرا نمی‌شن.
        if name in (
            'admin_search_user', 'admin_get_bot_stats', 'admin_list_tickets', 'admin_search_questions',
            'admin_get_user_full_profile', 'admin_get_subscription_stats', 'admin_search_faq',
            'admin_list_content_admins', 'admin_list_pending_approvals', 'admin_get_interaction_insights',
            'admin_get_ticket_detail', 'admin_get_schedule_overview',
        ):
            if uid != ADMIN_ID:
                return 'این تابع فقط برای ادمین ارشد در دسترسه.'

            if name == 'admin_search_user':
                results = await db.search_users(args.get('query', ''))
                if not results:
                    return 'کاربری با این مشخصات پیدا نشد.'
                lines = []
                for u in results[:5]:
                    lines.append(
                        f"- {u.get('name','—')} (آیدی: {u.get('user_id')}) | "
                        f"یوزرنیم: @{u.get('username') or '—'} | گروه: {u.get('group','—')} | "
                        f"ورودی: {u.get('intake','—')} | تایید‌شده: {'بله' if u.get('approved') else 'خیر'} | "
                        f"ثبت‌نام: {format_datetime_fa(u.get('registered_at',''), fallback='—')} | آخرین فعالیت: {format_datetime_fa(u.get('last_active',''), fallback='—')} | "
                        f"مسدودِ هوشیار: {'بله' if u.get('ai_banned') else 'خیر'}"
                    )
                return "\n".join(lines)

            if name == 'admin_get_bot_stats':
                u_stats = await db.stats_dashboard_users()
                t_stats = await db.stats_dashboard_tickets()
                return (
                    f"👥 کاربرانِ تاییدشده: {u_stats['total_approved']} | در انتظارِ تایید: {u_stats['total_pending']}\n"
                    f"🆕 ثبت‌نامِ امروز: {u_stats['new_today']} | این هفته: {u_stats['new_week']}\n"
                    f"🟢 فعالِ امروز: {u_stats['active_today']} | فعالِ این هفته: {u_stats['active_week']}\n"
                    f"😴 غیرفعالِ بیش از ۱۴ روز: {u_stats['inactive_14d']}\n"
                    f"🚫 بلاک‌کننده‌ی ربات: {u_stats['blocked_bot']}\n"
                    f"🎫 تیکتِ باز: {t_stats['open']} | بسته: {t_stats['closed']}\n"
                    f"⏱ میانگینِ زمانِ رسیدگی به تیکت: "
                    f"{t_stats['avg_resolution_h'] if t_stats['avg_resolution_h'] is not None else '—'} ساعت"
                )

            if name == 'admin_list_tickets':
                status = (args.get('status_filter') or '').strip().lower() or None
                if status not in ('open', 'closed'):
                    status = None
                rows = await db.ticket_get_all(status)
                if not rows:
                    return 'تیکتی پیدا نشد.'
                lines = [
                    f"- #{t.get('ticket_id')} | {t.get('user_name','—')} | موضوع: {t.get('subject','—')} | "
                    f"وضعیت: {t.get('status','—')} | {format_datetime_fa(t.get('created_at'))}"
                    for t in rows[:15]
                ]
                return "\n".join(lines)

            if name == 'admin_search_questions':
                rows = await db.search_questions_text(args.get('query', ''))
                if not rows:
                    return 'سوالی با این عبارت پیدا نشد.'
                lines = [
                    f"- [{r.get('lesson','—')} / {r.get('topic','—')}] {(r.get('question') or '')[:120]}"
                    for r in rows
                ]
                return "\n".join(lines)

            if name == 'admin_get_user_full_profile':
                results = await db.search_users(args.get('query', ''))
                if not results:
                    return 'کاربری با این مشخصات پیدا نشد.'
                u = results[0]
                target_uid = u.get('user_id')
                grades  = await db.grade_list_for_student(target_uid)
                tickets = await db.ticket_get_all(None)
                open_tickets = [t for t in tickets if t.get('user_id') == target_uid and t.get('status') == 'open']
                sub_active = await db.sub_count_by_status('active')  # فقط برای رفرنس کلی
                return (
                    f"👤 {u.get('name','—')} (آیدی: {u.get('user_id')})\n"
                    f"یوزرنیم: @{u.get('username') or '—'} | گروه: {u.get('group','—')} | ورودی: {u.get('intake','—')}\n"
                    f"تایید‌شده: {'بله' if u.get('approved') else 'خیر'} | مسدودِ هوشیار: {'بله' if u.get('ai_banned') else 'خیر'}\n"
                    f"ثبت‌نام: {format_datetime_fa(u.get('registered_at',''), fallback='—')} | آخرین فعالیت: {format_datetime_fa(u.get('last_active',''), fallback='—')}\n"
                    f"📊 تعدادِ نمراتِ ثبت‌شده: {len(grades)}\n"
                    f"🎫 تیکتِ بازِ این کاربر: {len(open_tickets)}"
                )

            if name == 'admin_get_subscription_stats':
                active  = await db.sub_count_by_status('active')
                expired = await db.sub_count_by_status('expired')
                pending = await db.sub_payment_list_pending()
                return (
                    f"💳 اشتراکِ فعال: {active}\n"
                    f"⌛ اشتراکِ منقضی‌شده: {expired}\n"
                    f"⏳ پرداختِ در انتظارِ بررسی: {len(pending)}"
                )

            if name == 'admin_search_faq':
                rows = await db.faq_search_text(args.get('query', ''))
                if not rows:
                    return 'سوالِ متداولی با این عبارت پیدا نشد.'
                lines = [f"- {r.get('question','')} → {(r.get('answer') or '')[:150]}" for r in rows]
                return "\n".join(lines)

            if name == 'admin_list_content_admins':
                rows = await db.get_content_admins()
                if not rows:
                    return 'هیچ ادمینِ محتوایی ثبت نشده.'
                lines = [f"- {u.get('name','—')} (آیدی: {u.get('user_id')})" for u in rows]
                return "\n".join(lines)

            if name == 'admin_list_pending_approvals':
                from question_bank.contracts import status_query
                pending_u = await db.pending_users()
                pending_q_count = await db.questions.count_documents(status_query('pending'))
                pending_p = await db.sub_payment_list_pending()
                return (
                    f"👥 کاربرِ در انتظارِ تایید: {len(pending_u)}\n"
                    f"❓ سوالِ در انتظارِ تایید: {pending_q_count}\n"
                    f"💳 پرداختِ در انتظارِ بررسی: {len(pending_p)}"
                )

            if name == 'admin_get_interaction_insights':
                # ⚠️ نسخه‌ی امنِ «یادگیریِ خودکار»: به‌جای اینکه ربات
                # خودش شخصیتشو تغییر بده، فقط یه خلاصه‌ی تحلیلی از
                # گزارش‌های دانشجوها می‌ده — تصمیمِ نهایی همیشه با ادمینه.
                reports = await db.ai_recent_reports(limit=30)
                if not reports:
                    return 'هنوز گزارشی از دانشجوها ثبت نشده — چیزِ خاصی برای تحلیل نیست.'
                sample = "\n---\n".join(
                    f"سوال: {r.get('question','')[:150]}\nپاسخ: {r.get('answer','')[:200]}"
                    for r in reports[:15]
                )
                return (
                    f"📋 {len(reports)} گزارشِ اخیر پیدا شد. خلاصه‌ی نمونه‌ای ازشون:\n\n{sample}\n\n"
                    "(بر اساسِ این‌ها، اگه الگویی می‌بینی — مثلاً یه نوع سوال که مدام اشتباه جواب داده "
                    "می‌شه — می‌تونی از پنلِ هوشیار دستورِ سیستمی رو دستی اصلاح کنی.)"
                )

            if name == 'admin_get_ticket_detail':
                try:
                    tid = int(args.get('ticket_id'))
                except (TypeError, ValueError):
                    return 'شماره‌ی تیکت نامعتبره.'
                t = await db.ticket_get(tid)
                if not t:
                    return f'تیکت #{tid} پیدا نشد.'
                replies = t.get('replies', [])
                replies_txt = "\n".join(f"  - {r}" for r in replies) if replies else "  (بدون پاسخ)"
                return (
                    f"🎫 تیکت #{tid} | {t.get('user_name','—')} (آیدی: {t.get('user_id')})\n"
                    f"موضوع: {t.get('subject','—')} | وضعیت: {t.get('status','—')} | {format_datetime_fa(t.get('created_at'))}\n"
                    f"متن: {t.get('message','—')}\n"
                    f"پاسخ‌ها:\n{replies_txt}"
                )

            if name == 'admin_get_schedule_overview':
                rows = await db.get_schedules()  # بدونِ group یعنی همه‌ی گروه‌ها
                if not rows:
                    return 'هیچ برنامه‌ی آینده‌ای برای هیچ گروهی ثبت نشده.'
                lines = [
                    f"- [{r.get('group','—')}] {r.get('type','')}: {r.get('lesson','')} | "
                    f"{format_date_fa(r.get('date'), long=True, date_only=True)} ساعت {format_time_fa(r.get('time'))}"
                    for r in rows[:20]
                ]
                return "\n".join(lines)

        return 'تابعِ ناشناخته.'
    except Exception:
        logger.exception("اجرای تابعِ هوشیار (%s) ناموفق بود", name)
        return 'خطا در خواندنِ اطلاعات از دیتابیس.'


# ══════════════════════════════════════════════════
#  ⚠️ قابلیتِ جدید: آپلودِ فایل به Gemini Files API — برای «سندِ مرجعِ
#  فعال» (RAG سبک). خودِ فایل روی سرورهای گوگل ذخیره می‌شه (رایگان،
#  ۴۸ ساعت)، فقط یه URI کوچیک برمی‌گردونیم که بعداً توی سوالاتِ بعدی
#  ارجاع بدیم — بدون اینکه هر بار کاربر دوباره فایل رو بفرسته.
# ══════════════════════════════════════════════════

_GEMINI_FILE_STATE_TIMEOUT = 45.0   # ثانیه؛ پردازش PDF روی سرور گوگل
_GEMINI_FILE_STATE_POLL = 2.0        # فاصله‌ی هر نظرسنجی


async def _gemini_wait_file_active(api_key: str, file_info: dict,
                                   timeout: float = _GEMINI_FILE_STATE_TIMEOUT) -> dict:
    """صبر تا فایلِ Gemini روی سرورِ گوگل ACTIVE شود.

    🔴 بعد از upload/finalize فایل‌های PDF در حالت PROCESSING برمی‌گردند؛
    ارجاع به فایلِ غیرِ ACTIVE در generateContent دقیقاً همان خطای 400
    است — و اگر پردازش FAILED شود، سندِ ذخیره‌شده هر درخواستِ بعدیِ
    کاربر را هم می‌شکند. خروجی: file_info با کلید state (ACTIVE |
    PROCESSING | FAILED)."""
    name = file_info.get('name') or ''
    state = (file_info.get('state') or 'ACTIVE').upper()
    deadline = time.monotonic() + timeout
    while state == 'PROCESSING' and name and time.monotonic() < deadline:
        await asyncio.sleep(_GEMINI_FILE_STATE_POLL)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f'https://generativelanguage.googleapis.com/v1beta/{name}',
                    headers={'x-goog-api-key': api_key})
            if r.status_code == 200:
                fresh = r.json() or {}
                if fresh.get('state'):
                    state = str(fresh['state']).upper()
                    file_info = fresh
            elif r.status_code == 404:
                state = 'FAILED'
                break
        except Exception:
            pass   # خطای موقتِ شبکه — نظرسنجی ادامه می‌یابد
    file_info['state'] = state
    return file_info


async def _gemini_upload_file(api_key: str, file_bytes: bytes, mime_type: str, display_name: str) -> dict:
    base = "https://generativelanguage.googleapis.com/upload/v1beta/files"
    start_headers = {
        'x-goog-api-key':                    api_key,
        'X-Goog-Upload-Protocol':            'resumable',
        'X-Goog-Upload-Command':             'start',
        'X-Goog-Upload-Header-Content-Length': str(len(file_bytes)),
        'X-Goog-Upload-Header-Content-Type': mime_type,
        'Content-Type':                      'application/json',
    }
    async with httpx.AsyncClient(timeout=60) as client:
        start_resp = await client.post(base, headers=start_headers, json={'file': {'display_name': display_name}})
        if start_resp.status_code != 200:
            raise AIError("آپلودِ فایل روی سرویسِ هوش مصنوعی ناموفق بود.")
        upload_url = start_resp.headers.get('x-goog-upload-url')
        if not upload_url:
            raise AIError("آپلودِ فایل ناموفق بود (URL آپلود دریافت نشد).")

        upload_resp = await client.post(
            upload_url,
            headers={
                'Content-Length':          str(len(file_bytes)),
                'X-Goog-Upload-Offset':    '0',
                'X-Goog-Upload-Command':   'upload, finalize',
            },
            content=file_bytes,
        )
        if upload_resp.status_code != 200:
            raise AIError("آپلودِ فایل روی سرویسِ هوش مصنوعی ناموفق بود.")
        file_info = (upload_resp.json() or {}).get('file') or {}
        if not file_info.get('uri'):
            raise AIError("آپلودِ فایل ناموفق بود (URI دریافت نشد).")
        return file_info


def _sanitize_provider_text(text: str) -> str:
    """ماسک هر الگوی شبیه‌کلید در متن خطا (احتیاط — بدنه‌ی خطای رسمی
    provider کلید را برنمی‌گرداند، ولی محکم‌کاری می‌کنیم)."""
    text = re.sub(r'AIza[0-9A-Za-z_\-]{10,}', 'AIza***', text)
    text = re.sub(r'sk-[0-9A-Za-z_\-]{10,}', 'sk-***', text)
    text = re.sub(r'Bearer\s+\S+', 'Bearer ***', text, flags=re.I)
    return ' '.join(text.split())[:400]


def _provider_error_detail(body_text: str) -> str:
    """بدنه‌ی خطای provider → علتِ خوانا و کوتاه برای لاگ/ادمین.

    قالب استاندارد Gemini/OpenAI-compat: {error: {message, status|code}}
    بدون JSON معتبر → ۴۰۰ کاراکتر اولِ به‌هم‌فشرده."""
    if not body_text:
        return ''
    try:
        j = json.loads(body_text)
        err = j.get('error') or {}
        msg = str(err.get('message') or '').strip()
        code = str(err.get('status') or err.get('code') or '').strip()
        if msg:
            out = f'[{code}] {msg}' if code else msg
            return _sanitize_provider_text(out)
    except (ValueError, TypeError, AttributeError):
        pass
    return _sanitize_provider_text(body_text[:400])


def _raise_gemini_status_error(status_code: int, detail: str = '') -> None:
    if status_code == 429:
        raise AIQuotaError("سقف رایگان API برای امروز پر شده — کمی بعد دوباره امتحان کن.")
    if status_code == 402:
        raise AIConfigError(
            "خطای ۴۰۲ (نیاز به پرداخت) از گوگل — پروژه‌ی Google Cloud این کلید "
            "نیاز به فعال‌سازی Billing داره یا در منطقه‌ی شما ردهٔ رایگان در "
            "دسترس نیست."
        )
    if status_code in (400, 401, 403, 404):
        if detail:
            logger.warning("gemini provider error status=%s detail=%s",
                           status_code, detail)
        # 🔴 م8.3 — ۴۰۱/۴۰۳ِ «سرویس‌اکانتِ مقید»: کلید گوگل به سرویس‌اکانتِ
        # حذف/غیرفعال‌شده وصل است — ربطی به مدل یا پیکربندی ندارد؛ کلید
        # باید عوض شود. بدون این، ادمین پشتِ پیامِ عمومی گمراه می‌شد.
        _d = (detail or '').lower()
        if 'service account' in _d:
            raise AIConfigError(
                "کلید API به سرویس‌اکانتِ حذف/غیرفعال‌شده‌ی گوگل وصل است — "
                "در aistudio.google.com/apikey کلیدِ تازه بسازید و در Vaultِ "
                f"هوشیار جایگزین کنید. (کد خطا: {status_code})",
                detail=detail)
        # 🔴 م8.1 — ۴۰۰ِ نوعِ فایل (mime) ربطی به کلید/مدل ندارد؛ پیامِ
        # روشن بده تا ادمین پشتِ «کلید API نامعتبره» گمراه نشود.
        if 'mime type' in _d or 'not supported for' in _d:
            raise AIError(
                "این نوع فایل توسط مدلِ انتخابی پشتیبانی نمی‌شود — فایل را "
                "به متن/عکس تبدیل کن یا مدل دیگری از پنل هوشیار انتخاب کن.")
        raise AIConfigError(
            "کلید API نامعتبره، مدل اشتباهه یا دسترسی لازم رو نداره — ادمین باید از پنل "
            f"هوشیار تنظیماتش رو چک کنه. (کد خطا: {status_code})",
            detail=detail,
        )
    if status_code >= 500:
        raise AIError("سرویس هوش مصنوعی موقتاً در دسترس نیست — کمی بعد دوباره امتحان کن.")


async def _stream_gemini(api_key: str, model: str, system_prompt: str,
                          text: str = None, image_bytes: bytes = None,
                          image_mime: str = 'image/jpeg', history: list = None,
                          thinking: str = 'auto', uid: int = None, doc: dict = None, **_):
    """
    ⚠️ موتورِ جدید — سه قابلیت رو یکجا پیاده می‌کنه:
      ۱) پاسخِ استریمینگ (کلمه‌به‌کلمه) به‌جای یک‌جا برگشتنِ کل جواب
      ۲) Function Calling (خوندنِ برنامه/نمره از دیتابیسِ خودِ هامزیار)
      ۳) ابزارِ url_context (خوندنِ لینک‌هایی که کاربر می‌فرسته)
    این یک async generator است که رویدادهای {'type': 'delta'/'done'}
    yield می‌کند. حلقه‌ی function-calling کاملاً داخلی و نامرئی برای
    فراخوان است — فقط دلتاهای متنِ جوابِ نهایی به بیرون می‌رسه.
    """
    # FIX: از اواسط ۲۰۲۶ گوگل کلیدهای جدید با پیشوند «AQ.» صادر می‌کند که
    # با روش قدیمیِ فرستادن کلید در URL (?key=...) کار نمی‌کنند و ۴۰۴/۴۰۳
    # برمی‌گردانند. روش رسمی و سازگار با هر دو فرمت فرستادن کلید در هدر
    # x-goog-api-key است.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': api_key}
    # 🔴 FIX-R1 (مورد ۶) — کلید/مدل با کاراکتر غیر ASCII همان‌جا خطای
    # روشن می‌دهد، نه UnicodeEncodeError مبهم از دل httpx.
    _key_problem = api_key_problem(api_key)
    if _key_problem:
        raise AIConfigError(_key_problem)

    contents = []
    for item in (history or []):
        role = 'model' if item.get('role') == 'assistant' else 'user'
        contents.append({'role': role, 'parts': [{'text': item.get('text', '')}]})

    parts = []
    if image_bytes:
        parts.append({'inline_data': {'mime_type': image_mime, 'data': base64.b64encode(image_bytes).decode('utf-8')}})
    if doc and doc.get('uri'):
        # ⚠️ سندِ مرجعِ فعال (RAG سبک) — اگه دانشجو قبلاً یه PDF فرستاده
        # و هنوز منقضی نشده، خودکار به همین سوال هم اضافه می‌شه.
        parts.append({'file_data': {'mime_type': doc.get('mime') or 'application/pdf', 'file_uri': doc['uri']}})
    if text:
        parts.append({'text': text})
    if not parts:
        parts.append({'text': 'کاربر متن یا فایلی ارسال نکرده.'})
    contents.append({'role': 'user', 'parts': parts})

    # ⚠️ طبق مستندات رسمیِ گوگل، برای خانواده‌ی مدل‌های Gemini 3.x توصیه
    # شده temperature از پیش‌فرض تغییر داده نشه.
    generation_config = {'maxOutputTokens': 3072}
    # ⭐ م8 — temperature/top_p/top_k برای gemini-3+ و 4 و نانوبانانا
    # deprecate شده (چنج‌لاگ 2026-07-21) → فقط مدل‌های قدیمی 2.x
    _modern = (model.startswith('gemini-3') or model.startswith('gemini-4')
               or 'nano-banana' in model or 'tts' in model.lower())
    if not _modern:
        generation_config['temperature'] = 0.3
    if thinking == 'high':
        if model.startswith('gemini-3'):
            generation_config['thinkingConfig'] = {'thinkingLevel': 'high'}
        else:
            generation_config['thinkingConfig'] = {'thinkingBudget': -1}

    # 🔴 م8.1 — فیکسِ باگِ ویس: ابزارِ توکارِ code_execution ورودیِ صوتی
    # را نمی‌پذیرد و Gemini با خطای ۴۰۰
    # «The mime type: audio/wav is not supported for code execution»
    # کل درخواست را رد می‌کند (این باگ باعث می‌شد هر ویس کاربر به‌جای
    # جواب، «کلید API نامعتبره» به ادمین گزارش شود). video/* هم همین‌طور.
    # راه‌حل: با ورودیِ صوت/ویدیو، ابزارهای توکارِ سرور
    # (code_execution/url_context) حذف می‌شوند؛ function declarations
    # (برنامه/نمره) با صوت سازگارند و می‌مانند.
    _av_input = bool(image_bytes) and (image_mime or '').lower().startswith(
        ('audio/', 'video/'))
    tools = []
    if not _av_input:
        tools += [{'code_execution': {}}, {'url_context': {}}]
    tool_config = None
    if uid is not None:
        # ⚠️ قابلیتِ جدید: ابزارهای «فقط ادمین ارشد» فقط وقتی uid دقیقاً
        # ADMIN_ID باشه اضافه می‌شن — دانشجوها هیچ‌وقت به این‌ها دسترسی
        # ندارن (چک دوباره هم داخلِ _execute_ai_function انجام می‌شه).
        function_declarations = list(AI_FUNCTIONS)
        if uid == ADMIN_ID:
            function_declarations += ADMIN_AI_FUNCTIONS
        tools.append({'function_declarations': function_declarations})
        # ⚠️ فیکسِ ارورِ ۴۰۰: وقتی function_declarations (تابع‌های سفارشیِ
        # برنامه/نمره) با ابزارهای توکارِ گوگل (code_execution/url_context)
        # با هم توی یه درخواست باشن، Gemini این فلگ رو صریحاً می‌خواد،
        # وگرنه با «Please enable tool_config.include_server_side_tool_
        # invocations…» ارور ۴۰۰ می‌ده. تستِ اتصالِ ادمین چون uid نداره
        # (پس تابعی هم اضافه نمی‌شه) هیچ‌وقت این مشکل رو نشون نمی‌داد —
        # برای همین «تست» موفق بود ولی چتِ واقعی خطا می‌داد.
        # (م8.1: فلگ فقط وقتی ست می‌شود که ابزارِ توکارِ سرور واقعاً
        # در درخواست باشد — با ورودیِ صوتی که ابزار توکار ندارد، لازم
        # نیست و ممکن است خودش ۴۰۰ بدهد.)
        tool_config = {'function_calling_config': {'mode': 'AUTO'}}
        if not _av_input:
            tool_config['include_server_side_tool_invocations'] = True

    total_tokens = 0
    full_answer_parts = []
    finish_reason = None

    for _round in range(4):   # سقفِ دورهای فراخوانیِ تابع — جلوگیری از حلقه‌ی بی‌نهایت
        payload = {
            'system_instruction': {'parts': [{'text': system_prompt}]},
            'contents': contents,
            'generationConfig': generation_config,
            'tools': tools,
        }
        if tool_config:
            payload['tool_config'] = tool_config

        function_call = None
        round_model_parts = []

        client = httpx.AsyncClient(timeout=90)
        try:
            for attempt in range(2):   # ⚠️ یک بار ری‌ترای خودکار روی خطای موقتِ سرور (۵xx)
                try:
                    async with client.stream('POST', url, headers=headers, json=payload) as resp:
                        if resp.status_code != 200:
                            if resp.status_code >= 500 and attempt == 0:
                                await asyncio.sleep(1.5)
                                continue
                            _err_body = ''
                            try:
                                _err_body = (await resp.aread()).decode(
                                    'utf-8', 'replace')
                            except Exception:
                                pass
                            _raise_gemini_status_error(
                                resp.status_code,
                                _provider_error_detail(_err_body))
                        async for line in resp.aiter_lines():
                            if not line.startswith('data:'):
                                continue
                            chunk_str = line[5:].strip()
                            if not chunk_str:
                                continue
                            try:
                                chunk = json.loads(chunk_str)
                            except ValueError:
                                continue
                            usage = chunk.get('usageMetadata') or {}
                            if usage.get('totalTokenCount'):
                                total_tokens = int(usage['totalTokenCount'])
                            cands = chunk.get('candidates') or []
                            if not cands:
                                continue
                            cand = cands[0]
                            if cand.get('finishReason'):
                                finish_reason = cand['finishReason']
                            for part in (cand.get('content', {}) or {}).get('parts', []) or []:
                                if part.get('thought'):
                                    continue
                                if 'functionCall' in part:
                                    function_call = part['functionCall']
                                    round_model_parts.append(part)
                                elif part.get('text') and function_call is None:
                                    round_model_parts.append(part)
                                    full_answer_parts.append(part['text'])
                                    yield {'type': 'delta', 'text': part['text']}
                    break   # استریم با موفقیت تموم شد، از حلقه‌ی ری‌ترای خارج شو
                except httpx.TimeoutException:
                    raise AIError("سرویس هوش مصنوعی دیر جواب داد (timeout) — دوباره امتحان کن.")
                except httpx.HTTPError as e:
                    raise AIError(f"خطا در اتصال به سرویس هوش مصنوعی: {e}")
        finally:
            await client.aclose()

        if function_call:
            fn_name = function_call.get('name')
            fn_args = function_call.get('args') or {}
            result_text = await _execute_ai_function(fn_name, fn_args, uid)
            contents.append({'role': 'model', 'parts': round_model_parts})
            contents.append({'role': 'user', 'parts': [{
                'function_response': {'name': fn_name, 'response': {'result': result_text}}
            }]})
            continue   # دورِ بعدی — این‌بار با نتیجه‌ی تابع

        break   # این دور function call نداشت → جوابِ نهایی همینه

    answer = ''.join(full_answer_parts).strip()
    if not answer:
        raise AIConfigError("مدل پاسخی برنگردوند.")
    if finish_reason == 'MAX_TOKENS':
        note = "\n\n⏳ (جواب طولانی بود و همین‌جا قطع شد؛ اگه خواستی بقیه‌ش رو بگم، بنویس «ادامه بده».)"
        answer += note
        yield {'type': 'delta', 'text': note}

    yield {'type': 'done', 'answer': answer, 'tokens': total_tokens}


async def _call_openai_compat(api_key: str, model: str, system_prompt: str,
                              text: str = None, image_bytes: bytes = None,
                              image_mime: str = 'image/jpeg', history: list = None,
                              provider: str = 'openrouter', **_) -> tuple:
    """
    🌊 W9 — فراخوان عمومیِ همه‌ی providerهای سازگار با OpenAI
    (openrouter/groq/cerebras/mistral/deepseek). همه‌شان همان
    /chat/completions را با Bearer token حرف می‌زنند؛ فقط base_url فرق
    می‌کند. پیام‌های خطای خاص OpenRouter (۴۰۲) به‌صورت شرطی حفظ شده‌اند.
    """
    meta = PROVIDERS.get(provider) or {}
    base = meta.get('url') or PROVIDERS['openrouter']['url']
    url = f"{base}/chat/completions"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type':  'application/json',
    }
    # 🔴 FIX-R1 (مورد ۶) — گارد ascii روی کلید (شرح در _stream_gemini)
    _key_problem = api_key_problem(api_key)
    if _key_problem:
        raise AIConfigError(_key_problem)

    if image_bytes and not meta.get('vision'):
        raise AIConfigError(
            f"ارائه‌دهنده‌ی {meta.get('label', provider)} ورودی تصویر را "
            "پشتیبانی نمی‌کند — برای سوالِ تصویری provider را روی Gemini "
            "یا OpenRouter بگذارید.")

    content = []
    if text:
        content.append({'type': 'text', 'text': text})
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode('utf-8')
        content.append({
            'type': 'image_url',
            'image_url': {'url': f'data:{image_mime};base64,{b64}'},
        })
    if not content:
        content.append({'type': 'text', 'text': 'کاربر متن یا عکسی ارسال نکرده.'})

    messages = [{'role': 'system', 'content': system_prompt}]
    for item in (history or []):
        role = 'assistant' if item.get('role') == 'assistant' else 'user'
        messages.append({'role': role, 'content': item.get('text', '')})
    messages.append({'role': 'user', 'content': content})

    payload = {
        'model': model,
        'messages': messages,
        'temperature': 0.3,
        'max_tokens': 3072,   # ⚠️ فیکس باگِ «پیامِ نصفه» — قبلاً 1024 بود
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = None
            for attempt in range(2):   # ⚠️ یک بار ری‌ترای خودکار روی خطای موقتِ سرور (۵xx)
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 500 and attempt == 0:
                    await asyncio.sleep(1.5)
                    continue
                break
    except httpx.TimeoutException:
        raise AIError("سرویس هوش مصنوعی دیر جواب داد (timeout) — دوباره امتحان کن.")
    except UnicodeEncodeError:
        # 🔴 FIX-R1 (مورد ۶) — هدر/مدل با حرف غیرلاتین؛ پیام انسانی بده
        raise AIConfigError(
            "کلید API یا شناسه مدل شامل حروف غیرمجاز است — کلید را از "
            "پنل هوشیار دوباره ثبت کنید (فقط حروف لاتین/رقم).")
    except httpx.HTTPError as e:
        raise AIError(f"خطا در اتصال به سرویس هوش مصنوعی: {e}")

    if resp.status_code == 429:
        raise AIQuotaError("سقف رایگان API برای امروز پر شده — کمی بعد دوباره امتحان کن.")
    if resp.status_code == 402:
        if provider == 'openrouter':
            raise AIConfigError(
                "خطای ۴۰۲ (نیاز به پرداخت) از OpenRouter. معمولاً یکی از این‌هاست:\n"
                "۱) نام مدل درست/کامل نیست — باید دقیقاً مثل فهرست کاتالوگ باشه "
                "(با :free آخرش)\n"
                "۲) موجودی حساب openrouter.ai/settings/credits منفیه\n"
                "۳) توی تنظیمات اکانت OpenRouter، Provider ی که این مدل رایگان رو "
                "می‌ده Ignore/بلاک شده"
            )
        raise AIConfigError(
            "خطای ۴۰۲ (نیاز به پرداخت) — سهمیه‌ی رایگانِ این ارائه‌دهنده تمام "
            "شده یا مدل انتخابی پولی است.")
    if resp.status_code in (400, 401, 403, 404):
        _detail = _provider_error_detail(resp.text)
        if _detail:
            logger.warning("provider=%s error status=%s detail=%s",
                           provider, resp.status_code, _detail)
        raise AIConfigError(
            "کلید API نامعتبره، مدل اشتباهه یا دسترسی لازم رو نداره — ادمین باید از پنل "
            f"هوشیار تنظیماتش رو چک کنه. (کد خطا: {resp.status_code})",
            detail=_detail,
        )
    if resp.status_code >= 500:
        raise AIError("سرویس هوش مصنوعی موقتاً در دسترس نیست — یه بار دیگه هم امتحان شد ولی جواب نداد؛ کمی بعد دوباره امتحان کن.")

    try:
        resp.raise_for_status()
        data = resp.json()
        choice = data['choices'][0]
        answer = choice['message']['content'].strip()
        tokens = int((data.get('usage') or {}).get('total_tokens', 0) or 0)
        if choice.get('finish_reason') == 'length':
            answer += "\n\n⏳ (جواب طولانی بود و همین‌جا قطع شد؛ اگه خواستی بقیه‌ش رو بگم، بنویس «ادامه بده».)"
        return answer, tokens
    except (KeyError, IndexError, ValueError):
        raise AIConfigError("مدل پاسخی برنگردوند — احتمالاً مدل انتخاب‌شده الان در دسترس نیست.")


STREAM_PROVIDERS = {
    'gemini': _stream_gemini,
    # نمونه برای بعداً: یک async generator با همین قرارداد رویداد بنویس
    # ({'type': 'delta', 'text': ...} / {'type': 'done', 'answer':..., 'tokens':...})
}


def _make_compat_stream(provider_name: str):
    """🌊 W9 — استریمِ همسان‌ساز برای providerهای سازگار با OpenAI.
    استریم واقعی ندارن؛ کل جواب یک‌جا به‌عنوان delta واحد + done
    برمی‌گردد — کدِ بالادستی (نمایش پیام) فرقی نمی‌کند."""
    async def _stream(**kwargs):
        answer, tokens = await _call_openai_compat(
            provider=provider_name, **kwargs)
        yield {'type': 'delta', 'text': answer}
        yield {'type': 'done', 'answer': answer, 'tokens': tokens}
    return _stream


for _p in ('openrouter', 'groq', 'cerebras', 'mistral', 'deepseek', 'nvidia', 'huggingface', 'together'):
    STREAM_PROVIDERS[_p] = _make_compat_stream(_p)


# سازگاری با نامِ قدیمی (اگر جای دیگری صدا زده می‌شد)
async def _call_openrouter(**kwargs):
    return await _call_openai_compat(provider='openrouter', **kwargs)


async def ask_ai_stream(text: str = None, image_bytes: bytes = None,
                         image_mime: str = 'image/jpeg', history: list = None,
                         uid: int = None, skip_doc: bool = False):
    """
    رابطِ اصلیِ جدید: یک async generator که رویدادهای {'type': 'delta',
    'text': ...} (پاسخِ تدریجی) و در آخر {'type': 'done', 'answer':...,
    'tokens':...} می‌دهد. uid برای Function Calling و سندِ مرجعِ فعال
    (RAG) استفاده می‌شود.
    """
    cfg = await get_ai_config()
    if not cfg['enabled']:
        raise AIConfigError("بخش هوش مصنوعی فعلاً توسط مدیریت غیرفعال است.")
    if not cfg['api_key']:
        raise AIConfigError("هنوز کلید API توسط ادمین تنظیم نشده.")
    # 🔴 FIX-R1 (مورد ۶) — کلید معیوب: پیام شفاف به‌جای «خطای غیرمنتظره:
    # 'ascii' codec can't encode...». این پیام هم در ربات و هم در تستِ
    # اتصال پنل (که همین مسیر را می‌رود) یکسان دیده می‌شود.
    if cfg.get('api_key_error'):
        raise AIConfigError(cfg['api_key_error'])

    fn = STREAM_PROVIDERS.get(cfg['provider'])
    if not fn:
        raise AIConfigError(f"ارائه‌دهنده‌ی «{cfg['provider']}» پشتیبانی نمی‌شود.")

    doc = None
    if cfg['provider'] == 'gemini' and uid is not None and not skip_doc:
        try:
            doc = await db.ai_get_doc(uid)
            if doc and doc.get('at') and (now_utc() - parse_machine_datetime(doc['at'])).total_seconds() > 48 * 3600:
                doc = None   # فایلِ گوگل بعد از ۴۸ ساعت خودش منقضی می‌شه
        except Exception:
            doc = None

    # ⚠️ قابلیتِ جدید: تزریقِ «پروفایلِ ماندگارِ فشرده» — نکاتی که خودِ
    # مدل قبلاً درباره‌ی همین کاربر یاد گرفته (با remember_about_me) به
    # دستورِ سیستمیِ همین درخواست اضافه می‌شه، تا بدونِ نیاز به دوباره‌
    # گفتنِ کاربر، ادامه‌ی طبیعیِ رابطه حفظ بشه.
    is_audio_input = bool(image_bytes and image_mime and str(image_mime).lower().startswith('audio/'))
    if is_audio_input and (cfg.get('voice_reply') or 'voice') != 'off':
        system_prompt = cfg.get('voice_system_prompt') or DEFAULT_VOICE_PROMPT
    else:
        system_prompt = cfg['system_prompt']
    if uid is not None:
        try:
            notes = await db.ai_get_profile_notes(uid)
            if notes:
                system_prompt += (
                    "\n\n[نکاتِ ماندگاری که قبلاً درباره‌ی این کاربر یاد گرفتی — طبیعی و بدونِ اشاره‌ی مستقیم بهشون استفاده کن:]\n"
                    + "\n".join(f"- {n}" for n in notes)
                )
        except Exception:
            pass

    kwargs = dict(
        api_key=cfg['api_key'], model=cfg['model'], system_prompt=system_prompt,
        text=text, image_bytes=image_bytes, image_mime=image_mime,
        history=history or [], thinking=cfg['thinking'],
    )
    if cfg['provider'] == 'gemini':
        kwargs['uid'] = uid
        kwargs['doc'] = doc

    # ⭐ م7 — فال‌بک چند-کلیدی: درخواست با کلیدهایِ سالمِ provider به‌ترتیب
    # امتحان می‌شود؛ کلیدی که سهمیه/خطا بخورد cooldown می‌شود و همین
    # درخواست بی‌درنگ با کلید بعدی تکرار می‌شود. فقط تا وقتی هیچ پاسخی
    # به کاربر جاری نشده امکان تعویض کلید هست (استریمِ نیمه‌جاری برگشت
    # ندارد).
    _keys = ordered_keys(cfg['provider'],
                         cfg.get('api_key_list') or ([cfg['api_key']] if cfg['api_key'] else []))
    if not _keys:
        raise AIConfigError("هنوز کلید API توسط ادمین تنظیم نشده.")
    _last_exc = None
    for _ki, _key in enumerate(_keys):
        kwargs['api_key'] = _key
        # 🩹 خودترمیمی: اگر سندِ مرجعِ الصاق‌شده (file_uri) باعث خطای 4xx شد —
        # فایلِ منقضی/حذف‌شده روی سرور گوگل یا state غیر ACTIVE — سند خودکار
        # جدا می‌شود و همان سوال یک‌بار *بدونِ سند* دوباره پرسیده می‌شود.
        # بدون این، یک PDFِ خراب چتِ هوشیارِ کاربر را تا ۴۸ ساعت قفل می‌کرد.
        # فقط وقتی retry می‌کنیم که هنوز هیچ پاسخی به کاربر جاری نشده است.
        full_answer = None
        _yielded = False
        # لایه‌ی بیرونی: فال‌بکِ کلید (م7) — لایه‌ی درونی: خودترمیمیِ سند.
        # خطای برخاسته از خودِ except درونی هم اینجا می‌رسد تا با کلیدِ
        # بعدی ادامه دهیم.
        try:
            try:
                async for event in fn(**kwargs):
                    if event['type'] == 'done':
                        full_answer = event['answer']
                    _yielded = True
                    yield event
            except AIConfigError as e:
                _why = f"{getattr(e, 'detail', '') or ''} {e}".lower()
                _doc_broken = doc and not _yielded and (
                    'file' in _why or 'state' in _why or 'precondition' in _why
                    or '(کد خطا: 400)' in str(e) or '(کد خطا: 404)' in str(e))
                if not _doc_broken:
                    raise
                logger.warning(
                    'سند مرجع Gemini برای uid=%s معتبر نبود — جدا شد و بدونِ سند '
                    'دوباره پرسیده می‌شود. علت: %s', uid,
                    _sanitize_provider_text(_why[:200]))
                try:
                    await db.ai_clear_doc(uid)
                except Exception:
                    logger.exception('ai_clear_doc ناموفق بود')
                kwargs['doc'] = None
                async for event in fn(**kwargs):
                    if event['type'] == 'done':
                        full_answer = event['answer']
                    yield event
        except Exception as e:                     # ⭐ م7 — خطای چرخش‌پذیر → کلید بعدی
            if _yielded or classify_key_error(e) is None:
                raise
            mark_key_failed(cfg['provider'], _key, e)
            _last_exc = e
            logger.warning(
                'کلید #%d هوشیار (%s) در چت شکست خورد → کلید بعدی [%s]',
                _ki + 1, masked_key(_key), type(e).__name__)
            continue
        mark_key_ok(cfg['provider'], _key)
        if full_answer is not None:
            _guard_against_meta_leak(full_answer, cfg)
        return
    # ⭐ م8.3 — همه‌ی کلیدها شکست خوردند؛ ادمین باید بداند که فال‌بک
    # امتحان شد و چیزی نمانده، نه اینکه فکر کند اصلاً فال‌بک کار نکرد.
    if _last_exc is not None and len(_keys) > 1:
        _fa_n = str(len(_keys)).translate(
            str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
        _wrap = (f"همه‌ی {_fa_n} کلیدِ فال‌بک امتحان شد و همه شکست "
                 f"خوردند. آخرین خطا: {_last_exc}")
        if isinstance(_last_exc, AIConfigError):
            raise AIConfigError(
                _wrap, detail=getattr(_last_exc, 'detail', '') or '')
        if isinstance(_last_exc, AIError):
            raise type(_last_exc)(_wrap)
    raise _last_exc


async def ask_ai(text: str = None, image_bytes: bytes = None,
                  image_mime: str = 'image/jpeg', history: list = None,
                  uid: int = None) -> tuple:
    """
    نسخه‌ی ساده (غیر-استریم) برای فراخوان‌هایی که فقط جوابِ نهایی رو
    می‌خوان (مثلاً دکمه‌ی «تست اتصال» توی پنل ادمین) — همون
    ask_ai_stream رو زیرِ پوستش صدا می‌زنه و رویدادها رو جمع می‌کنه.
    """
    answer, tokens = '', 0
    async for event in ask_ai_stream(text=text, image_bytes=image_bytes,
                                      image_mime=image_mime, history=history, uid=uid):
        if event['type'] == 'done':
            answer, tokens = event['answer'], event['tokens']
    return answer, tokens


# ══════════════════════════════════════════════════
#  ⚠️ قابلیتِ جدید: طراحیِ خودکارِ سوالِ چهارگزینه‌ای با هوش مصنوعی —
#  برای بخشِ «بانکِ سوال و طرحِ سوال». برخلافِ چتِ هوشیار، اینجا به
#  استریم/تاریخچه/تابع نیازی نیست؛ فقط یک درخواستِ ساده با خروجیِ
#  JSON تضمین‌شده (Structured Output) — قابل‌اعتمادتر از پارس‌کردنِ
#  متنِ آزاد.
# ══════════════════════════════════════════════════

# ══════════════════════════════════════════════════
#  🐛 رفعِ باگ: اطلاعیه/پاسخِ تیکت/سوال نصفه تولید می‌شد.
#
#  ریشه: مدلِ پیش‌فرض `gemini-2.5-flash` یک مدلِ «تفکری» است و توکن‌هایی
#  که صرفِ استدلالِ داخلی می‌کند از همان سهمیه‌ی maxOutputTokens کم
#  می‌شود. توابعِ کمکیِ زیر بدونِ thinkingConfig صدا زده می‌شدند، پس
#  تفکر بخشِ بزرگی از بودجه را می‌بلعید و متنِ واقعی وسطِ کار قطع
#  می‌شد — بدونِ هیچ خطایی، چون کد فقط parts[0].text را می‌خواند و
#  finishReason را نادیده می‌گرفت.
#
#  دو اصلاح:
#   ۱) thinkingBudget=0 → برای این کارهای «قالب‌محور» تفکرِ داخلی لازم
#      نیست و کلِ بودجه صرفِ خروجی می‌شود.
#   ۲) _extract_gemini_text() → اگر باز هم به سقف خورد، به‌جای برگرداندنِ
#      متنِ ناقص، خطای شفاف می‌دهد تا ادمین متنِ نصفه را همگانی نفرستد.
# ══════════════════════════════════════════════════

#  ۳) _sanitize_tg_html() → خروجیِ مدل همیشه HTMLِ معتبرِ تلگرام نیست.
#     تگِ بسته‌نشده، تگِ غیرمجاز (<div>, <p>, <br>) یا تودرتویِ نامتوازن
#     باعث BadRequest می‌شود؛ یعنی پیش‌نمایش می‌شکند و پنلِ ادمین قفل
#     می‌شود، یا بدتر، ارسالِ همگانی برای همه شکست می‌خورد. پس قبل از
#     برگرداندنِ متن، آن را پاک‌سازی می‌کنیم.

# تگ‌هایی که Bot API تلگرام در parse_mode=HTML می‌پذیرد
_TG_ALLOWED_TAGS = {
    'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del',
    'a', 'code', 'pre', 'blockquote', 'span', 'tg-spoiler',
}
_TAG_RE = re.compile(r'<(/?)([a-zA-Z0-9-]+)([^>]*)>')


def _sanitize_tg_html(text: str) -> str:
    """HTMLِ خروجیِ مدل را به HTMLِ معتبرِ تلگرام تبدیل می‌کند.

    - تگ‌های غیرمجاز حذف می‌شوند (محتوایشان می‌ماند)؛ <br> و </p> به خطِ
      جدید تبدیل می‌شوند.
    - تگ‌های بسته‌نشده در انتها بسته می‌شوند.
    - بسته‌شدن‌های نامتوازن/اضافه دور ریخته می‌شوند.
    خودِ متن دست‌نخورده می‌ماند؛ فقط ساختارِ تگ‌ها اصلاح می‌شود.
    """
    if not text:
        return text

    out, stack, pos = [], [], 0
    for m in _TAG_RE.finditer(text):
        out.append(text[pos:m.start()])
        pos = m.end()
        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3)

        if tag in ('br', 'p', 'div'):
            # این‌ها ساختارِ بلوکی‌اند؛ به شکستِ خط ترجمه می‌شوند
            out.append('\n' if (tag == 'br' or closing) else '')
            continue
        if tag not in _TG_ALLOWED_TAGS:
            continue                      # تگ را بینداز، متن را نگه دار
        if closing:
            if tag in stack:              # فقط اگر واقعاً باز شده بود
                while stack and stack[-1] != tag:
                    out.append(f'</{stack.pop()}>')   # تگ‌های داخلی را ببند
                stack.pop()
                out.append(f'</{tag}>')
            continue
        stack.append(tag)
        out.append(f'<{tag}{attrs}>')

    out.append(text[pos:])
    while stack:                          # هرچه باز مانده را ببند
        out.append(f'</{stack.pop()}>')
    return ''.join(out).strip()


def _no_thinking(cfg: dict, model: str = '') -> dict:
    """تفکرِ داخلی را کم می‌کند تا maxOutputTokens صرفِ متنِ پاسخ شود.

    🔴 مدل‌آگاه (مستندات رسمی گوگل):
    • Gemini 3+ فقط thinkingLevel دارد؛ thinkingBudget منسوخ است و
      «می‌تواند خطای متناوب 400 INVALID_ARGUMENT بدهد» و روی مدل‌های
      جدید قطعاً 400 می‌شود ⇒ thinkingLevel: 'low' (کمترین سطحِ
      پشتیبانی‌شده در همه‌ی مدل‌های 3).
    • Gemini 2.5 و قدیمی‌تر ⇒ thinkingBudget: 0 (خاموشِ کامل).
    برای ارائه‌دهنده‌های غیر Gemini بی‌اثر است (کلید ناشناخته در
    payload آن‌ها به‌کار نمی‌رود).
    """
    cfg = dict(cfg)
    # gemini-3 و هر نسل بعدی (طبق اعلان گوگل، روی مدل‌های جدید
    # thinkingBudget قطعاً 400 INVALID_ARGUMENT می‌شود)
    if re.match(r'gemini-[3-9]', (model or '').strip().lower()):
        cfg['thinkingConfig'] = {'thinkingLevel': 'low'}
    else:
        cfg['thinkingConfig'] = {'thinkingBudget': 0}
    return cfg


def _extract_gemini_text(data: dict, what: str = "متن") -> str:
    """متنِ پاسخِ Gemini را درمی‌آورد و «ناقص بودن» را صریحاً تشخیص می‌دهد.

    برخلافِ نسخه‌ی قبلی، finishReason بررسی می‌شود: اگر مدل به سقفِ توکن
    خورده باشد، متنِ نصفه برگردانده نمی‌شود.
    """
    try:
        cand = data['candidates'][0]
    except (KeyError, IndexError, TypeError):
        raise AIConfigError("هوش مصنوعی پاسخی برنگرداند — دوباره امتحان کن.")

    reason = cand.get('finishReason')
    parts = (cand.get('content') or {}).get('parts') or []
    text = ''.join(p.get('text', '') for p in parts).strip()

    if reason == 'MAX_TOKENS':
        raise AIError(
            f"{what} طولانی‌تر از سهمیه‌ی مدل شد و ناقص ماند. "
            "دوباره بساز یا نکته‌ها را کوتاه‌تر بنویس."
        )
    if reason == 'SAFETY':
        raise AIError("مدل به‌دلیلِ فیلترِ ایمنی جواب نداد — متن را بازنویسی کن.")
    if not text:
        raise AIConfigError("هوش مصنوعی متنِ قابل‌فهمی برنگردوند — دوباره امتحان کن.")
    return text


QUESTION_SCHEMA = {
    'type': 'object',
    'properties': {
        'question':      {'type': 'string', 'description': 'متنِ کاملِ سوال'},
        'options':       {
            'type': 'array', 'items': {'type': 'string'},
            'minItems': 4, 'maxItems': 4,
            'description': 'دقیقاً ۴ گزینه',
        },
        'correct_index': {'type': 'integer', 'description': 'ایندکسِ گزینه‌ی درست، از 0 تا 3'},
        'explanation':   {'type': 'string', 'description': 'تحلیلِ کاملِ پاسخ (چرا درست/چرا بقیه غلط)'},
    },
    'required': ['question', 'options', 'correct_index', 'explanation'],
}


async def generate_question_ai(lesson: str, topic: str, difficulty: str = None,
                               note: str = None, grounding: list[str] = None) -> dict:
    """
    یک سوالِ چهارگزینه‌ی کامل (سوال/گزینه‌ها/پاسخِ درست/تحلیل) برای درس و
    مبحثِ داده‌شده می‌سازد. خروجی: {'question','options','correct_index','explanation'}.
    """
    cfg = await get_ai_config()
    if not cfg['enabled']:
        raise AIConfigError("بخش هوش مصنوعی فعلاً توسط مدیریت غیرفعال است.")
    if not cfg['api_key']:
        raise AIConfigError("هنوز کلید API توسط ادمین تنظیم نشده.")
    if cfg['provider'] != 'gemini':
        raise AIConfigError("طراحیِ سوال با AI فعلاً فقط با ارائه‌دهنده‌ی Gemini در دسترسه.")

    prompt = (
        "یک سوالِ چهارگزینه‌ای (تستی) دقیق و علمی برای دانشجویانِ پزشکی طراحی کن.\n"
        f"درس: {lesson}\nمبحث: {topic}\n"
    )
    if difficulty:
        prompt += f"سطح سختی: {difficulty}\n"
    if note:
        prompt += f"نکته‌ی خاصِ موردنظر: {note}\n"
    if grounding:
        prompt += ("\nزمینه تأییدشده سامانه؛ سؤال باید فقط با این زمینه سازگار باشد و "
                   "اگر زمینه کافی نیست، خروجی نامعتبر تولید نکن:\n" +
                   "\n".join(f"- {str(item)[:300]}" for item in grounding[:8]) + "\n")
    prompt += (
        "سوال باید بدونِ ابهام باشه و فقط یکی از ۴ گزینه دقیقاً درست باشه. "
        "توی «explanation» هم توضیح بده چرا گزینه‌ی درست، درسته و بقیه چرا غلطن."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg['model']}:generateContent"
    payload = {
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'generationConfig': _no_thinking({
            'responseMimeType': 'application/json',
            'responseSchema': QUESTION_SCHEMA,
            'maxOutputTokens': 2048,
        }, cfg['model']),
    }

    # ⭐ م7 — POST با فال‌بکِ کلید بعدی در صورتِ سهمیه/خطای کلید
    async def _post_once(api_key: str):
        _kp = api_key_problem(api_key)
        if _kp:
            raise AIConfigError(_kp)
        async with httpx.AsyncClient(timeout=60) as client:
            return await client.post(
                url,
                headers={'Content-Type': 'application/json',
                         'x-goog-api-key': api_key},
                json=payload)

    try:
        resp = await run_with_key_failover(
            cfg['provider'], cfg.get('api_key_list'), _post_once,
            label='generate_question')
    except httpx.TimeoutException:
        raise AIError("سرویس هوش مصنوعی دیر جواب داد — دوباره امتحان کن.")
    except UnicodeEncodeError:
        # 🔴 FIX-R1 (مورد ۶) — کلید/مدل با حرف غیرلاتین؛ پیام انسانی
        raise AIConfigError(
            "کلید API یا شناسه مدل شامل حروف غیرمجاز است — کلید را از "
            "پنل هوشیار دوباره ثبت کنید (فقط حروف لاتین/رقم).")
    except httpx.HTTPError as e:
        raise AIError(f"خطا در اتصال به سرویس هوش مصنوعی: {e}")

    if resp.status_code != 200:
        _raise_gemini_status_error(
            resp.status_code,
            _provider_error_detail(resp.text))

    try:
        data = resp.json()
        raw_text = _extract_gemini_text(data, "سوال")
        parsed = json.loads(raw_text)
        options = parsed.get('options') or []
        if len(options) != 4 or not parsed.get('question') or 'correct_index' not in parsed:
            raise ValueError('ساختارِ ناقص')
        correct_index = int(parsed['correct_index'])
        if not (0 <= correct_index <= 3):
            raise ValueError('correct_index خارج از محدوده')
        return {
            'question':      str(parsed['question']).strip(),
            'options':       [str(o).strip() for o in options],
            'correct_index': correct_index,
            'explanation':   str(parsed.get('explanation') or '').strip(),
            'model':         cfg['model'],
        }
    except (KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError):
        raise AIConfigError("هوش مصنوعی خروجیِ قابل‌فهمی برنگردوند — دوباره امتحان کن.")


# ══════════════════════════════════════════════════
#  ⚠️ قابلیتِ جدید: دستیارِ نوشتنِ اطلاعیه + پیش‌نویسِ پاسخِ تیکت.
#
#  نکته‌ی طراحیِ مهم: این دو تابع کاملاً «کمکی» هستن، نه بخشی از مسیرِ
#  اصلیِ ربات. هر خطایی (سهمیه تموم شده، کلید غلط، سرویس قطع، هر چیزِ
#  دیگه) به‌شکلِ AIError بالا می‌ره و فراخوان (admin.py/ticket.py) باید
#  همیشه یه راهِ برگشتِ ساده به مسیرِ دستیِ همیشگی داشته باشه — یعنی
#  اگه هوش مصنوعی کار نکرد، نوشتنِ اطلاعیه یا پاسخِ تیکت دقیقاً مثلِ
#  قبل (بدونِ AI) کار می‌کنه.
# ══════════════════════════════════════════════════

BROADCAST_STYLE_INSTRUCTION = """تو دستیارِ نوشتنِ اطلاعیه‌های رسمیِ ربات «هامزیار» هستی — یک ربات آموزشی دانشگاهی برای دانشجویان دانشگاه علوم پزشکی هرمزگان.

از این قوانین دقیقاً و بدون استثنا پیروی کن:

هویت و لحن: لحن باید حسِ یک سامانه‌ی رسمیِ دانشگاهیِ مدرن رو منتقل کنه؛ حرفه‌ای، تمیز، قابل‌اعتماد و پریمیوم.

سبک نگارش: رسمی اما صمیمی، کوتاه و مفید، بدون زیاده‌گویی، بدون متن‌های شعاری، خوانا و مرتب، مناسبِ پیامِ همگانیِ تلگرام. هر پاراگراف حداکثر ۲ تا ۳ خط.

قالب: همیشه خروجی رو با HTML تلگرام بنویس. فقط از تگ‌های <b>، <a> و <code> استفاده کن — هیچ تگ HTML دیگری مجاز نیست. <code> فقط برای دستورها مثل /start. هیچ‌وقت از Markdown یا ** استفاده نکن.

ساختارِ ثابت (دقیقاً به همین شکل):
📣 <b>عنوان اطلاعیه</b>
━━━━━━━━━━━━━━━━
🎓 <b>دانشجویان گرامی،</b>
متن اطلاعیه...
📌 نکته مهم (در صورت نیاز)
💙 <b>از همراهی و اعتماد شما سپاسگزاریم.</b>
✨ <b>تیم اطلاع‌رسانی هامزیار</b>

ایموجی‌های مجاز برای استفاده در متن (بسته به موضوع): 📣 اطلاعیه، 🎓 دانشجویان، 📌 نکته مهم، ⚠️ هشدار، 🔔 خبر، 📚 منابع، 🧪 بانک سوالات، ✏️ طراحی سوال، 🤖 هوشیار، 📝 فرم، 🗳️ انتخابات، 🔗 لینک، 📱 اپلیکیشن، 💳 اشتراک، ⚙️ بروزرسانی، 🚀 قابلیت جدید، 💙 تشکر، ✨ امضا. از ایموجیِ اضافی/خارج از این لیست استفاده نکن.

بولد: همیشه موارد مهم (ساعت، تاریخ، لینک، نام درس، نام قابلیت، نام بخش، اسمِ سامانه، اطلاعیه‌ی مهم، تغییرات، قیمت، مدتِ اشتراک) رو Bold کن.

لینک: اگه لینکی بود، دقیقاً به این شکل بنویس: <a href="URL">متن نمایشی</a>

امضا: بسته به موضوع یکی از این سه رو انتخاب کن: «✨ <b>تیم اطلاع‌رسانی هامزیار</b>» یا «✨ <b>تیم توسعه هامزیار</b>» یا «✨ <b>مدیریت هامزیار</b>».

لحن بر اساسِ موضوع: اگه موضوع قابلیتِ جدید/بروزرسانی/نسخه‌ی جدید/هوش‌مصنوعی/اشتراک/بانکِ سوالات بود، لحن هیجان‌انگیز اما حرفه‌ای باشه. اگه موضوع امتحانات/اطلاعیه‌ی دانشگاه/نمرات/قوانین/انتخابات/اخبارِ رسمی بود، لحن کاملاً رسمی باشه.

اطلاعیه‌های «رونمایی»: اگه موضوع رونماییِ یک بخشِ بزرگ یا بروزرسانیِ اساسی بود (نه یک تغییرِ جزئی)، این ساختار رو به کار ببر تا حسِ یک پروژه‌ی بلندمدت منتقل بشه، نه یک قابلیتِ کوچک:
• عنوان با حسِ رونمایی و ایموجی 🚀
• یک پاراگراف درباره‌ی مسیرِ ساخت (ماه‌ها طراحی و توسعه)
• بلافاصله بعدش یک جمله‌ی هدف‌گذارانه با 🎯 که نشون بده هدف ساختِ یک «اکوسیستمِ آموزشیِ کامل» بوده، نه صرفاً یک ربات
• فهرستِ تیتروارِ امکانات، هر خط یک ایموجیِ مرتبط از لیستِ مجاز
• یک جمله‌ی «و این تازه آغازِ راهه...» درباره‌ی آینده
• راهنمای دسترسی به‌صورتِ گام‌به‌گام (اگه لازم بود از <code> برای دستور استفاده کن)
• تشکر از کاربران و امضا
در این حالت فهرستِ امکانات می‌تونه بلندتر از حدِ معمول باشه و محدودیتِ «۲ تا ۳ خط در هر پاراگراف» فقط به پاراگراف‌های توضیحی مربوطه، نه به فهرست.

خروجی: فقط متنِ نهاییِ HTML رو تولید کن — هیچ توضیحِ اضافه، هیچ مقدمه یا موخره‌ای نده."""


# ══════════════════════════════════════════════════
#  📚 QUIZ-PDF — primitive مشترکِ تولیدِ JSON ساختاریافته
#  (منبع واحد برای آزمون‌ساز PDF و هر قابلیت قالب‌محور آینده)
# ══════════════════════════════════════════════════

def _extract_json_block(text: str):
    """اولین JSON متوازن (object یا array) را از متن مدل بیرون می‌کشد.

    مدل‌ها گاهی خروجی را داخل ```json ... ``` می‌گذارند یا قبل/بعدش
    توضیح می‌نویسند؛ این تابع مستقل از provider است."""
    import json as _json
    if not text:
        return None
    t = text.strip()
    # حذف code fence
    if t.startswith('```'):
        t = re.sub(r'^```[a-zA-Z]*\s*', '', t)
        t = re.sub(r'\s*```$', '', t.strip())
    # جستجوی مستقیم
    try:
        return _json.loads(t)
    except (ValueError, TypeError):
        pass
    # اولین بلوک متوازن {..} یا [..]
    for opener, closer in (('{', '}'), ('[', ']')):
        start = t.find(opener)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(t)):
                ch = t[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == '\\':
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return _json.loads(t[start:i + 1])
                        except (ValueError, TypeError):
                            break
            start = t.find(opener, start + 1)
    return None


async def generate_structured_json(prompt: str, schema: dict, purpose: str,
                                   max_tokens: int = 8192,
                                   system_prompt: str = None) -> dict | list:
    """یکی از دو مسیرِ provider — خروجی همیشه JSON پارس‌شده است.

    • Gemini: responseSchema (تضمین ساختاری سمت سرور).
    • ارائه‌دهنده‌های سازگار با OpenAI (openrouter/groq/…): دستورِ JSON
      در پرامپت + استخراجِ بلوک متوازن. اگر خروجی خراب بود، «یک بار»
      با درخواستِ تعمیر retry می‌شود.

    تنظیمات (provider/model/کلید) از همان get_ai_config پنل خوانده
    می‌شود — منبع واحد حقیقت، بدون موازی‌کاری."""
    cfg = await get_ai_config()
    if not cfg['enabled']:
        raise AIConfigError("بخش هوش مصنوعی فعلاً توسط مدیریت غیرفعال است.")
    if not cfg['api_key']:
        raise AIConfigError("هنوز کلید API توسط ادمین تنظیم نشده.")
    _key_problem = api_key_problem(cfg['api_key'])
    if _key_problem:
        raise AIConfigError(_key_problem)

    async def _gemini_once(api_key: str, repair_note: str = '') -> tuple:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{cfg['model']}:generateContent")
        headers = {'Content-Type': 'application/json',
                   'x-goog-api-key': api_key}
        payload = {
            'contents': [{'role': 'user',
                          'parts': [{'text': prompt + repair_note}]}],
            'generationConfig': _no_thinking({
                'responseMimeType': 'application/json',
                'responseSchema': schema,
                'maxOutputTokens': int(max_tokens),
            }, cfg['model']),
        }
        if system_prompt:
            payload['system_instruction'] = {'parts': [{'text': system_prompt}]}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            _raise_gemini_status_error(resp.status_code)
        return _extract_gemini_text(resp.json(), purpose)

    async def _compat_once(api_key: str, repair_note: str = '') -> tuple:
        sys_txt = (system_prompt or '') + (
            "\nخروجی را «فقط و فقط» به‌صورت JSON معتبر (بدون متن اضافه، "
            "بدون code fence، بدون توضیح) با دقیقاً همین ساختارِ خواسته‌شده بده.")
        raw = await _call_openai_compat(
            api_key, cfg['model'], sys_txt,
            text=prompt + repair_note, provider=cfg['provider'])
        # _call_openai_compat برای استریم خروجی میدهد؟ نه — tuple متن نهایی
        if isinstance(raw, tuple):
            return raw[0] if raw else ''
        return raw

    provider = cfg.get('provider') or 'gemini'
    # ⭐ م7 — هر دو شاخه با فال‌بکِ کلید بعدی (م7) اجرا می‌شوند
    _fail_keys = cfg.get('api_key_list')
    try:
        if provider == 'gemini':
            text = await run_with_key_failover(
                'gemini', _fail_keys, lambda _k: _gemini_once(_k),
                label=f'json:{purpose}')
            parsed = _extract_json_block(text)
            if parsed is None:
                raise ValueError('json_parse_failed')
            return parsed
        # OpenAI-compatible
        text = await run_with_key_failover(
            provider, _fail_keys, lambda _k: _compat_once(_k),
            label=f'json:{purpose}')
        parsed = _extract_json_block(text)
        if parsed is None:
            # یک بار تعمیر بخواه (بدون هزینه‌ی ساخت پرامپت تازه)
            text = await run_with_key_failover(
                provider, _fail_keys,
                lambda _k: _compat_once(_k, "\n[توجه] پاسخ قبلی JSON معتبر نبود. فقط JSON بساز."),
                label=f'json-repair:{purpose}')
            parsed = _extract_json_block(text)
            if parsed is None:
                raise ValueError('json_parse_failed')
        return parsed
    except AIConfigError:
        raise
    except (httpx.TimeoutException, asyncio.TimeoutError):
        raise AIError("سرویس هوش مصنوعی دیر جواب داد — دوباره امتحان کن.")
    except ValueError as e:
        if str(e) == 'json_parse_failed':
            raise AIError("پاسخ سرویس هوش مصنوعی قابل خواندن نبود — دوباره امتحان کن.")
        raise
    except httpx.HTTPError as e:
        raise AIError(f"خطا در اتصال به سرویس هوش مصنوعی: {e}")


async def generate_broadcast_ai(notes: str) -> str:
    """از روی چند نکته/بولت‌پوینتی که ادمین می‌ده، متنِ کاملِ اطلاعیه رو طبقِ استانداردِ هامزیار می‌سازه."""
    notes = (notes or "").strip()
    if not notes:
        raise AIError("اول چند نکته برای ساخت اطلاعیه بنویس.")
    cfg = await get_ai_config()
    if not cfg['enabled']:
        raise AIConfigError("بخش هوش مصنوعی فعلاً توسط مدیریت غیرفعال است.")
    if not cfg['api_key']:
        raise AIConfigError("هنوز کلید API توسط ادمین تنظیم نشده.")
    if cfg['provider'] != 'gemini':
        raise AIConfigError("این قابلیت فعلاً فقط با ارائه‌دهنده‌ی Gemini در دسترسه.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg['model']}:generateContent"
    payload = {
        'system_instruction': {'parts': [{'text': BROADCAST_STYLE_INSTRUCTION}]},
        'contents': [{'role': 'user', 'parts': [{'text': f"این نکته‌ها رو به یه اطلاعیه تبدیل کن:\n\n{notes}"}]}],
        'generationConfig': _no_thinking({'maxOutputTokens': 2048}, cfg['model']),
    }

    # ⭐ م7 — POST با فال‌بکِ کلید بعدی (گارد ascii داخل factory برای هر کلید)
    async def _post_once(api_key: str):
        _kp = api_key_problem(api_key)
        if _kp:
            raise AIConfigError(_kp)
        async with httpx.AsyncClient(timeout=45) as client:
            return await client.post(
                url,
                headers={'Content-Type': 'application/json',
                         'x-goog-api-key': api_key},
                json=payload)

    try:
        resp = await run_with_key_failover(
            cfg['provider'], cfg.get('api_key_list'), _post_once,
            label='broadcast')
    except httpx.TimeoutException:
        raise AIError("سرویس هوش مصنوعی دیر جواب داد — دوباره امتحان کن.")
    except httpx.HTTPError as e:
        raise AIError(f"خطا در اتصال به سرویس هوش مصنوعی: {e}")

    if resp.status_code != 200:
        _raise_gemini_status_error(
            resp.status_code,
            _provider_error_detail(resp.text))

    try:
        data = resp.json()
    except (ValueError, TypeError) as e:
        logger.error("Gemini broadcast returned invalid JSON: %s", e)
        raise AIError("پاسخ سرویس هوش مصنوعی قابل خواندن نبود — دوباره امتحان کن.")
    try:
        text = _extract_gemini_text(data, "اطلاعیه")
    except AIError:
        raise
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.error("Gemini broadcast response shape was invalid: %s", e)
        raise AIError("پاسخ سرویس هوش مصنوعی ناقص بود — دوباره امتحان کن.")
    return _sanitize_tg_html(text)


TICKET_REPLY_INSTRUCTION = """تو داری به ادمینِ پشتیبانیِ ربات «هامزیار» (ربات آموزشیِ دانشگاه علوم پزشکی هرمزگان) کمک می‌کنی تا به تیکتِ یک دانشجو جواب بده.

یه پیش‌نویسِ پاسخِ کوتاه، محترمانه، دوستانه و کاربردی بنویس — انگار خودِ پشتیبانیِ هامزیار داره جواب می‌ده، نه یه ربات. مستقیم برو سراغِ راه‌حل یا جوابِ سوال، بدون مقدمه‌چینیِ اضافه. اگه اطلاعاتِ کافی برای حلِ قطعیِ مشکل نیست، ازش بخواه جزئیاتِ بیشتر بده.
فقط از تگِ <b> برای تاکید استفاده کن (اگه لازم بود)، بدونِ Markdown. خروجی فقط خودِ متنِ پاسخه، بدون توضیحِ اضافه."""


async def generate_ticket_reply_ai(subject: str, ticket_text: str, previous_replies: list = None) -> str:
    """یک پیش‌نویسِ پاسخ برای تیکتِ پشتیبانی می‌سازد — ادمین می‌تونه مستقیم بفرستدش یا ویرایش کنه."""
    cfg = await get_ai_config()
    if not cfg['enabled']:
        raise AIConfigError("بخش هوش مصنوعی فعلاً توسط مدیریت غیرفعال است.")
    if not cfg['api_key']:
        raise AIConfigError("هنوز کلید API توسط ادمین تنظیم نشده.")
    if cfg['provider'] != 'gemini':
        raise AIConfigError("این قابلیت فعلاً فقط با ارائه‌دهنده‌ی Gemini در دسترسه.")

    convo = f"موضوعِ تیکت: {subject}\n\nمتنِ تیکت:\n{ticket_text}\n"
    if previous_replies:
        convo += "\nپاسخ‌های قبلی:\n" + "\n".join(f"- {r}" for r in previous_replies[-5:])

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg['model']}:generateContent"
    payload = {
        'system_instruction': {'parts': [{'text': TICKET_REPLY_INSTRUCTION}]},
        'contents': [{'role': 'user', 'parts': [{'text': convo}]}],
        'generationConfig': _no_thinking({'maxOutputTokens': 1024}, cfg['model']),
    }

    # ⭐ م7 — POST با فال‌بکِ کلید بعدی
    async def _post_once(api_key: str):
        _kp = api_key_problem(api_key)
        if _kp:
            raise AIConfigError(_kp)
        async with httpx.AsyncClient(timeout=45) as client:
            return await client.post(
                url,
                headers={'Content-Type': 'application/json',
                         'x-goog-api-key': api_key},
                json=payload)

    try:
        resp = await run_with_key_failover(
            cfg['provider'], cfg.get('api_key_list'), _post_once,
            label='ticket_reply')
    except httpx.TimeoutException:
        raise AIError("سرویس هوش مصنوعی دیر جواب داد — دوباره امتحان کن.")
    except httpx.HTTPError as e:
        raise AIError(f"خطا در اتصال به سرویس هوش مصنوعی: {e}")

    if resp.status_code != 200:
        _raise_gemini_status_error(
            resp.status_code,
            _provider_error_detail(resp.text))

    return _sanitize_tg_html(_extract_gemini_text(resp.json(), "پاسخِ تیکت"))


# نشانه‌های شناخته‌شده‌ی «نشتِ فراداده»: بعضی مدل‌های رایگان (مخصوصاً وقتی
# با روتر خودکارِ «openrouter/free» یک مدل نامناسب/کلاسیفایر انتخاب می‌شود)
# به‌جای پاسخِ واقعی، برچسب‌های داخلیِ ارزیابیِ ایمنی را برمی‌گردانند، مثل:
#   "User Safety: safe / Response Safety: unsafe / Safety Categories: ..."
# این خروجی برای دانشجو کاملاً بی‌معنی و گمراه‌کننده است، پس به‌جای نمایش
# مستقیم آن، خطای شفاف نشان می‌دهیم تا ادمین مدل را عوض کند.
_META_LEAK_MARKERS = (
    'user safety', 'response safety', 'safety categories',
    'safety category', 'content policy violation', 'moderation result',
)


def _guard_against_meta_leak(answer: str, cfg: dict) -> None:
    lowered = (answer or '').lower()
    if any(marker in lowered for marker in _META_LEAK_MARKERS):
        hint = (
            "اگه از OpenRouter استفاده می‌کنی و مدلت روی «انتخاب خودکار» "
            "(openrouter/free) تنظیمه، از پنل ادمین یه مدل مشخص مثل "
            "google/gemma-4-31b-it:free رو انتخاب کن."
            if cfg.get('provider') == 'openrouter' else
            "مدل انتخابی خروجی نامناسب برگردوند؛ از پنل ادمین مدل رو عوض کن."
        )
        raise AIConfigError(
            f"مدل به‌جای پاسخِ درسی، یک خروجیِ فنیِ نامرتبط برگردوند. {hint}"
        )


# ══════════════════════════════════════════════════
#  محدودیت روزانه‌ی هر کاربر
# ══════════════════════════════════════════════════

async def check_and_consume_quota(uid: int) -> tuple:
    """
    برمی‌گرداند (allowed, used_after, limit).
    ادمین ارشد همیشه نامحدود است؛ daily_limit=0 یعنی نامحدود برای همه.
    در هر دو حالت، ai_total_usage (مصرف کل، برای آمار پنل ادمین) هم
    یک واحد بالا می‌رود. اگه روز عوض شده باشه، ai_tokens_today هم صفر
    می‌شه (خودِ record_token_usage بعد از جواب گرفتن رویش $inc می‌زند).
    """
    cfg = await get_ai_config()
    # 🌊 W6/MISS-04 — سقف پلنی (پیش‌فرض: سراسری)؛ همه‌ی صداکننده‌ها خودکار پلنی شدند
    limit = await db.ai_limit_for_user(uid, cfg['daily_limit'])
    today = today_tehran().isoformat()
    # The DB conditional update is the source of truth; this remains correct
    # when Bot and Mini App requests land on different processes.
    return await db.ai_consume_quota(uid, limit, today)


async def record_token_usage(uid: int, tokens: int) -> None:
    """بعد از دریافت جواب صدا زده می‌شه؛ توکن مصرفی رو (امروز + کل) اضافه می‌کنه."""
    if not tokens:
        return
    try:
        await db.ai_inc_tokens(uid, tokens)
    except Exception:
        logger.exception("ثبت توکن مصرفی هوشیار ناموفق بود")


# ══════════════════════════════════════════════════
#  فلوی کاربر — دکمه‌ی «🤖 هوشیار» در منوی اصلی
# ══════════════════════════════════════════════════

async def show_ai_intro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # 🌊 W7 — گیت فیچر (پیش‌فرض FREE ⇒ بدون تغییر رفتار امروز)
    from subscription import feature_allowed, show_paywall
    if not await feature_allowed(uid, "ai_chat"):
        await show_paywall(update.message, uid, feature="ai_chat")
        return
    cfg = await get_ai_config()

    if not cfg['enabled']:
        await update.message.reply_text(
            "🤖 بخش «هوشیار» فعلاً توسط مدیریت غیرفعال است. بعداً دوباره سر بزن."
        )
        return

    context.user_data['mode'] = 'ai_query'

    limit = await db.ai_limit_for_user(uid, cfg['daily_limit'])
    if uid == ADMIN_ID or limit <= 0:
        quota_line = "🔓 امروز محدودیتی نداری — هر چقدر دلت خواست بپرس"
    else:
        user  = await db.get_user(uid) or {}
        today = today_tehran().isoformat()
        used  = user.get('ai_usage_count', 0) if user.get('ai_usage_date') == today else 0
        quota_line = f"📊 تا الان {used} از {limit} سوالِ امروزتو استفاده کردی"

    from utils import webapp_url as _wa_url
    _live_url = _wa_url('/ai/live')
    _kb_rows = [[
        InlineKeyboardButton("📚 آزمون‌ساز از PDF", callback_data='quiz:main'),
    ]]
    if cfg.get('image_enabled'):
        _kb_rows.append([InlineKeyboardButton("🎨 ساخت تصویر", callback_data='aiu:imgstart')])
    if cfg.get('live_enabled', True):
        if _live_url and getattr(update.effective_chat, 'type', 'private') == 'private':
            from telegram import WebAppInfo
            _kb_rows.append([InlineKeyboardButton(
                "🎙 تماس صوتی زنده با هوشیار (Live)",
                web_app=WebAppInfo(url=_live_url),
            )])
        else:
            _kb_rows.append([InlineKeyboardButton(
                "🎙 تماس صوتی زنده با هوشیار (Live)",
                callback_data='aiu:live',
            )])

    await update.message.reply_text(
        "⚡️ <b>سلام، هوشیارم!</b>\n"
        "همون هم‌کلاسیِ باهوش‌تر که همیشه حاضر به کمکه 😎\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "هر جور راحتی سوالتو بفرست:\n"
        "📝 تایپ کن، ساده و مستقیم\n"
        "📷 عکسِ سوال رو بفرست (می‌تونی زیرش توضیح هم بنویسی)\n"
        "📄 یا جزوه/برگه‌ت رو به‌صورت PDF بفرست\n"
        "🎙️ ویس بفرست یا با دکمه‌ی زیر <b>تماس صوتی زنده (Live)</b> برقرار کن و مستقیم باهام حرف بزن!\n\n"
        f"{quota_line}\n\n"
        "💡 فقط یه نکته: من هوش مصنوعی‌ام، نه پیغمبر! ممکنه یه‌جا اشتباه کنم — "
        "برای چیزای مهم حتماً با منبع درسی یا استاد هم یه چک بزن.\n\n"
        "هر وقت خواستی بری سراغ کارِ دیگه، کافیه یه دکمه‌ی دیگه از منو رو بزنی — "
        "من همیشه همینجام 👋",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(_kb_rows),
    )


async def show_ai_live_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎙 م9 — کارت شروع تماس صوتی زنده با هوشیار (در چت خصوصی و گروه‌های تلگرام).

    در چت خصوصی دکمه‌ی مستقیم WebAppInfo('/ai/live') باز می‌شود؛ در گروه‌های
    تلگرام (که تلگرام دکمه‌ی web_app را روی کیبورد پیام گروه نمی‌پذیرد) دکمه‌ی
    لینک مستقیم ورود به اتاق ویس‌چت زنده (`?start=ai_live`) قرار می‌گیرد تا
    هر عضو گروه با یک کلیک وارد مکالمه‌ی صوتی زنده با هوشیار شود."""
    msg = update.effective_message
    if not msg:
        return
    cfg = await get_ai_config()
    if not cfg.get('enabled') or not cfg.get('live_enabled', True):
        await msg.reply_text("🎙 تماس صوتی زنده‌ی هوشیار فعلاً توسط مدیریت غیرفعال است.")
        return

    from utils import webapp_url as _wa_url
    live_url = _wa_url('/ai/live')
    chat_type = getattr(update.effective_chat, 'type', 'private')
    model_name = cfg.get('live_model') or DEFAULT_LIVE_MODEL
    voice_name = cfg.get('live_voice') or TTS_VOICE_DEFAULT

    rows = []
    if chat_type == 'private' and live_url:
        from telegram import WebAppInfo
        rows.append([InlineKeyboardButton(
            "🎙 شروع تماس صوتی زنده با هوشیار",
            web_app=WebAppInfo(url=live_url),
        )])
    else:
        rows.append([
            InlineKeyboardButton(
                "📞 ورود هوشیار به ویس‌چت همین گروه",
                callback_data="aiu:vc_join",
            ),
            InlineKeyboardButton(
                "📴 خروج از ویس‌چت",
                callback_data="aiu:vc_leave",
            ),
        ])
        bot_username = getattr(context.bot, 'username', None) or ''
        if not bot_username:
            try:
                me = await context.bot.get_me()
                bot_username = me.username or ''
            except Exception:
                bot_username = ''
        if bot_username:
            rows.append([InlineKeyboardButton(
                "🎙 اتاق تماس صوتی/ویدیویی زنده (مینی‌اپ)",
                url=f"https://t.me/{bot_username}?start=ai_live",
            )])
        elif live_url:
            rows.append([InlineKeyboardButton(
                "🎙 باز کردن ویس‌چت زنده هوشیار",
                url=live_url,
            )])

    await msg.reply_text(
        "🎙 <b>تماس صوتی زنده با هوشیار (Google Gemini Live)</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        "بدون نیاز به تایپ یا ضبط ویس، میکروفون رو باز کن و <b>به‌صورت زنده و آنلاین</b> "
        "با هوشیار صحبت کن!\n\n"
        f"🤖 مدل فعال: <code>{_esc(model_name)}</code>\n"
        f"🗣 صدای هوشیار: <code>{_esc(voice_name)}</code>\n"
        "📞 در گروه‌های تلگرام می‌تونی ویس‌چت گروه (Video Chat) رو باز کنی و دکمه‌ی "
        "<b>«ورود هوشیار به ویس‌چت همین گروه»</b> رو بزنی (یا دستور /joinlive بفرستی) "
        "تا هوشیار مستقیم بیاد داخل ویس‌چت گروه و با بچه‌ها صحبت کنه!\n\n"
        "👇 یکی از گزینه‌های زیر رو انتخاب کن:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(rows) if rows else None,
    )


async def join_live_vc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📞 م9.2 — دستور /joinlive در گروه تلگرام برای ورود مستقیم هوشیار به ویس‌چت گروه."""
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat:
        return
    if getattr(chat, 'type', 'private') == 'private':
        await show_ai_live_card(update, context)
        return
    wait_msg = await msg.reply_text("⏳ در حال اتصال دستیار هوشیار به ویس‌چت گروه و Gemini Live…")
    try:
        from tg_group_voice_call import join_group_voice_chat
        info = await join_group_voice_chat(
            chat_id=chat.id,
            bot=context.bot,
            title=getattr(chat, 'title', '') or str(chat.id),
        )
        asst = info.get('assistant') or {}
        asst_lbl = f"@{asst['username']}" if asst.get('username') else (asst.get('first_name') or 'دستیار هوشیار')
        await wait_msg.edit_text(
            f"🎙 <b>هوشیار وارد ویس‌چت گروه شد!</b>\n\n"
            f"👤 اکانت حاضر در ویس‌چت: <b>{_esc(asst_lbl)}</b>\n"
            f"🤖 مدل Live: <code>{_esc(info.get('model') or '')}</code>\n"
            f"🗣 صدا: <code>{_esc(info.get('voice') or '')}</code>\n\n"
            "هم‌اکنون داخل ویس‌چت گروه صحبت کنید تا هوشیار زنده پاسخ دهد.\n"
            "برای خروج هوشیار از ویس‌چت: /leavelive",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📴 خروج هوشیار از ویس‌چت گروه", callback_data="aiu:vc_leave"),
            ]]),
        )
    except Exception as e:
        await wait_msg.edit_text(f"⚠️ <b>خطا در ورود به ویس‌چت گروه:</b>\n{_esc(str(e))}", parse_mode='HTML')


async def leave_live_vc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📴 م9.2 — دستور /leavelive در گروه تلگرام برای خروج هوشیار از ویس‌چت گروه."""
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat:
        return
    try:
        from tg_group_voice_call import leave_group_voice_chat
        await leave_group_voice_chat(chat.id)
        await msg.reply_text("📴 هوشیار از ویس‌چت گروه خارج شد.")
    except Exception as e:
        await msg.reply_text(f"⚠️ خطا در خروج از ویس‌چت: {e}")


async def on_video_chat_started(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📞 م9.2 — وقتی در گروه تلگرام ویس‌چت (Video Chat) شروع می‌شود، کارت دعوت هوشیار به ویس‌چت را نمایش می‌دهد."""
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat:
        return
    cfg = await get_ai_config()
    if not cfg.get('enabled') or not cfg.get('live_enabled', True):
        return
    await msg.reply_text(
        "🎙 <b>ویس‌چت گروه شروع شد!</b>\n"
        "می‌خوای <b>هوشیار</b> هم بیاد داخل همین ویس‌چت و به‌صورت صوتی زنده با بچه‌ها صحبت کنه؟",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📞 دعوت هوشیار به ویس‌چت گروه", callback_data="aiu:vc_join"),
        ]]),
    )


def _footer(limit: int, used: int) -> str:
    if not limit:
        return ""
    return f"\n\n📊 {used}/{limit} سوال امروز"


# ══════════════════════════════════════════════════
#  پیام ثابت وضعیت «در حال فکر کردن» (بدون جملات تصادفی)
# ══════════════════════════════════════════════════
THINKING_MESSAGE = "💭 در حال فکر کردن..."

THINKING_PHRASES = [
    THINKING_MESSAGE,
]

STALL_PHRASES = [
    THINKING_MESSAGE,
]


def _pick_unused(pool: list, used: set) -> str:
    return THINKING_MESSAGE


# ══════════════════════════════════════════════════
#  تبدیل Markdown سبکِ خروجیِ مدل (**bold**, `code`, لیست‌ها، #تیتر) به
#  HTML قابل‌نمایش در تلگرام. ⚠️ فیکس باگ: قبلاً متنِ خامِ AI بدون هیچ
#  parse_mode ای فرستاده می‌شد، برای همین کاراکترهای «**» و امثالش عیناً
#  توی پیامِ کاربر دیده می‌شدن. اول باید کاراکترهای خاصِ HTML (& < >) رو
#  escape کنیم (که خودِ متنِ AI باعث خرابیِ پارسِ HTML نشه)، بعد الگوهای
#  Markdown رو به تگ‌های HTML تبدیل کنیم.
# ══════════════════════════════════════════════════

def _md_to_telegram_html(text: str) -> str:
    if not text:
        return text
    out = _esc(text, quote=False)                                      # 1) امن‌سازی HTML
    out = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out, flags=re.S)       # 2) **bold**
    out = re.sub(r'(?m)^#{1,6}\s*(.+)$', r'<b>\1</b>', out)             # 3) # تیتر → بولد
    out = re.sub(r'`([^`\n]+?)`', r'<code>\1</code>', out)              # 4) `code`
    out = re.sub(r'(?m)^[*\-]\s+', '• ', out)                          # 5) لیست * یا - → •
    out = re.sub(r'(?<!\w)_(?!_)(.+?)(?<!_)_(?!\w)', r'<i>\1</i>', out)  # 6) _italic_
    return out


EDIT_THROTTLE_SECONDS = 0.7   # حداقل فاصله بین دو ادیتِ پیام حین استریم (جلوگیری از Flood-limit تلگرام)


async def _typing_pinger(context: ContextTypes.DEFAULT_TYPE, chat_id: int, stop_event: asyncio.Event):
    """در پس‌زمینه هر چند ثانیه یک‌بار وضعیتِ «در حال تایپ» رو نگه می‌داره — تا وقتی stop_event ست بشه."""
    while not stop_event.is_set():
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action='typing')
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass


async def _answer_with_live_edit(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  stream_gen, footer_suffix: str,
                                  uid: int, question_label: str,
                                  voice_input: bool = False) -> None:
    """
    ⚠️ قابلیتِ جدید: پاسخِ استریمینگِ واقعی — به‌جای اینکه یک‌جا منتظرِ
    کلِ جواب بمونیم و بعد نشونش بدیم، همون‌طور که متن از Gemini می‌رسه،
    پیام رو تدریجاً (با یه throttle برای رعایتِ محدودیتِ ویرایشِ تلگرام)
    آپدیت می‌کنیم — دقیقاً حسِ «داره جلوی چشمت تایپ می‌کنه» رو می‌ده.
    اگه جواب موفق بود: توی حافظه‌ی مکالمه ثبتش می‌کنه، توکن مصرفی رو به
    دیتابیس اضافه می‌کنه، و زیرِ پیام دکمه‌ها رو می‌ذاره.
    """
    chat_id = update.effective_chat.id
    thinking_msg = await context.bot.send_message(chat_id, THINKING_MESSAGE)

    # ⭐ م8.2 — «فقط ویس» (پیش‌فرضِ voice): ورودیِ ویس + «متنِ همراه»
    # خاموش → متنِ جواب استریم نمی‌شود؛ بعد از اتمام فقط ویس می‌رود
    # (اگر TTS شکست خورد یا جواب بلند بود، متن تحویل می‌شود — کاربر
    # هرگز بی‌جواب نمی‌ماند).
    _vcfg = None
    if voice_input:
        try:
            _vcfg = await get_ai_config()
        except Exception:
            _vcfg = None
    _voice_only = bool(_vcfg) and (
        (_vcfg.get('voice_reply') or 'voice') != 'off'
        and (_vcfg.get('voice_with_text') or 'off') != 'on')

    stop_event = asyncio.Event()
    pinger = asyncio.ensure_future(_typing_pinger(context, chat_id, stop_event))

    buffer: list = []
    tokens = 0
    answer_text = None
    last_edit_at = 0.0
    last_edit_len = 0
    final_text = ''

    try:
        async for event in stream_gen:
            if event['type'] == 'delta':
                buffer.append(event['text'])
                if _voice_only:
                    continue   # ⭐ م8.2 — جواب فقط ویس می‌شود؛ متن نشان نده
                now = time.time()
                raw_partial = ''.join(buffer)
                # ⚠️ فیکس باگِ «فقط یه خط | میاد بعد یهو کل پیام»: قبلاً
                # اولین دلتا (حتی اگه فقط ۱-۲ کاراکتر بود) بلافاصله ادیت
                # می‌شد (چون last_edit_at از 0.0 شروع می‌شد)، و چون throttle
                # طولانی بود (1.3 ثانیه) و خیلی از جواب‌ها زودتر از اون
                # تموم می‌شدن، هیچ ادیتِ میانی‌ای اتفاق نمی‌افتاد — نتیجه:
                # یه پیامِ تقریباً خالی، بعد یهو جوابِ کامل جای‌گزینش می‌شد.
                # حالا: هم فاصله‌ی زمانی کوتاه‌تره، هم یه شرطِ «حجمِ متنِ
                # جدید» اضافه شده تا حتی برای جواب‌های کوتاه هم چند بار
                # واقعی آپدیت بشه، و هم اولین ادیت با حداقل چند کاراکتر
                # محتوا انجام می‌شه (نه یه پیامِ تقریباً خالی).
                should_edit = len(raw_partial) >= 8 and (
                    now - last_edit_at >= EDIT_THROTTLE_SECONDS or
                    len(raw_partial) - last_edit_len >= 50
                )
                if should_edit:
                    display = raw_partial[:3480] + "…" if len(raw_partial) > 3480 else raw_partial
                    try:
                        await thinking_msg.edit_text(
                            f"🤖 {_md_to_telegram_html(display)} ▌", parse_mode='HTML',
                        )
                    except Exception:
                        pass   # مثلاً «message not modified» یا محدودیتِ نرخ — بی‌خیالش شو، دورِ بعد دوباره امتحان می‌شه
                    last_edit_at = now
                    last_edit_len = len(raw_partial)
            elif event['type'] == 'done':
                answer_text = event['answer']
                tokens = event['tokens']

        raw_answer = answer_text or ''
        # ⚠️ برشِ طولِ پیام روی متنِ خام (نه HTML) انجام می‌شه تا هیچ‌وقت
        # وسطِ یه تگ قطع نشه.
        if len(raw_answer) > 3500:
            raw_answer = raw_answer[:3480] + "…"
        final_text = f"🤖 {_md_to_telegram_html(raw_answer)}{_esc(footer_suffix, quote=False)}"

    except AIConfigError as e:
        # ⚠️ این خطا فنیه و فقط برای ادمین معنی داره. دانشجو فقط یه پیامِ
        # ساده می‌بینه، و متنِ فنی مستقیم برای ادمین ارشد فوروارد می‌شه.
        final_text = (
            "⚠️ هوشیار الان یه مشکل فنی داره و نمی‌تونه درست جواب بده.\n"
            "به ادمین اطلاع داده شد؛ لطفاً چند دقیقه‌ی دیگه دوباره امتحان کن 🙏"
        )
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    "🛠 <b>خطای فنیِ هوشیار</b> (فقط برای شما نمایش داده می‌شه؛ کاربر پیامِ ساده دید)\n\n"
                    f"👤 کاربر: {_esc(update.effective_user.full_name or '—')} "
                    f"(<code>{uid}</code>)\n\n"
                    f"❓ سوال:\n{_esc(question_label[:500])}\n\n"
                    f"🧩 جزئیات خطا:\n{_esc(str(e))}"
                    + (
                        f"\n\n🔬 <b>علت اعلام‌شده توسط سرویس AI:</b>\n"
                        f"{_esc(getattr(e, 'detail', '') or '')}"
                        if getattr(e, 'detail', '') else ""
                    ),
                    parse_mode='HTML',
                )
            except Exception:
                logger.exception("ارسال هشدار خطای فنیِ هوشیار به ادمین ناموفق بود")
    except AIError as e:
        final_text = f"⚠️ {_esc(str(e), quote=False)}"
    except Exception:
        logger.exception("AI error")
        final_text = "⚠️ مشکلی در ارتباط با سرویس هوش مصنوعی پیش اومد، دوباره امتحان کن."
    finally:
        stop_event.set()
        pinger.cancel()
        try:
            await pinger
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    if len(final_text) > 4000:  # محافظِ نهایی (به‌ندرت لازم می‌شه)
        final_text = final_text[:3990] + "…"

    def _buttons_markup(msg_id: int):
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔬 مثال بزن", callback_data="aiu:fu:example"),
                InlineKeyboardButton("📝 خلاصه‌ترش کن", callback_data="aiu:fu:summary"),
                InlineKeyboardButton("🎯 سوالِ مشابه", callback_data="aiu:fu:similar"),
            ],
            [
                InlineKeyboardButton("🆕 گفتگوی جدید", callback_data="aiu:newchat"),
                InlineKeyboardButton("🚩 گزارش این جواب", callback_data=f"aiu:report:{chat_id}:{msg_id}"),
            ],
        ])

    reply_markup = _buttons_markup(thinking_msg.message_id) if answer_text else None

    # ⭐ م8.2 — طرحِ نهاییِ پاسخ صوتی از تنظیماتِ پنل (تست‌پذیر)
    _vplan = 'off'
    if answer_text:
        try:
            if _vcfg is None:
                _vcfg = await get_ai_config()
            _vplan = _voice_reply_plan(_vcfg, voice_input, len(answer_text))
        except Exception:
            _vplan = 'off'

    # 🎤 حالتِ «فقط ویس»: ویس فرستادی ⇒ فقط ویس بگیر (بدون تکرارِ متن)
    _voice_msg = None
    if _vplan == 'voice_only' and answer_text:
        try:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action='record_voice')
            except Exception:
                pass
            _wav, _vmime = await generate_speech_gemini(
                answer_text, voice=_vcfg.get('tts_voice'),
                model=_vcfg.get('tts_model'))
            _cap = (footer_suffix or '').strip() or None
            _ogg = await _transcode_wav_to_ogg_opus(_wav)
            if _ogg:
                _voice_msg = await context.bot.send_voice(
                    chat_id, voice=_ogg, caption=_cap)
            else:
                # ffmpeg نیست — فایل صوتی WAV قابل‌پخش
                _voice_msg = await context.bot.send_audio(
                    chat_id, audio=_wav, filename='houshyar.wav',
                    title='پاسخ صوتی هوشیار', caption=_cap)
        except Exception:
            logger.exception("حالتِ ویس‌تنها ناموفق — تحویلِ متن به‌عنوان fallback")
            _voice_msg = None

    if _voice_msg is not None:
        # دکمه‌ها و کشِ گزارش روی خودِ پیامِ صوتی
        try:
            await _voice_msg.edit_reply_markup(
                reply_markup=_buttons_markup(_voice_msg.message_id))
        except Exception:
            pass
        try:
            await thinking_msg.delete()
        except Exception:
            pass
        _cache_for_report(chat_id, _voice_msg.message_id, uid,
                          update.effective_user.full_name, question_label,
                          answer_text)
    else:
        try:
            await thinking_msg.edit_text(final_text, reply_markup=reply_markup, parse_mode='HTML')
        except Exception:
            try:
                await thinking_msg.edit_text(final_text, reply_markup=reply_markup)
            except Exception:
                await context.bot.send_message(chat_id, final_text, reply_markup=reply_markup)

        # ⭐ م8 — ویسِ اضافه بعد از متن (حالتِ all، یا voice با «متنِ همراه»)
        if answer_text and _vplan == 'text_and_voice':
            asyncio.create_task(maybe_send_voice_reply(
                update, context, answer_text, voice_input=voice_input))

    if tokens:
        await record_token_usage(uid, tokens)

    if answer_text:
        await _remember(uid, 'user', question_label)
        await _remember(uid, 'assistant', answer_text)
        if _voice_msg is None:
            _cache_for_report(
                chat_id, thinking_msg.message_id, uid,
                update.effective_user.full_name, question_label, answer_text,
            )


# ══════════════════════════════════════════════════
#  قفل هم‌زمانی — جلوگیری از اینکه یک کاربر قبل از تمام‌شدن جواب سوال
#  قبلی‌اش، سوال دومی بفرسته و دو تا درخواست هم‌زمان برای AI اجرا بشه
#  (هم هزینه‌ی اضافه داره، هم می‌تونه باعث به‌هم‌ریختن پیامِ در حال ادیت
#  بشه چون هر دو تا درخواست دارن روی یک thinking_msg کار می‌کنن).
# ══════════════════════════════════════════════════
_busy_users: set = set()

#: TTL قفلِ «یک پرسشِ در جریان». از سقفِ منطقیِ یک پاسخِ استریمی بلندتر است
#: تا پاسخ‌های کند قطع نشوند، ولی آن‌قدر کوتاه که کرشِ یک پراسس کاربر را
#: بیش از این مدت قفل نکند (op_claim قفلِ منقضی را خودش تحویل می‌گیرد).
AI_INFLIGHT_TTL = 180


async def ai_claim_inflight(uid: int) -> bool:
    """ادعای «این کاربر همین حالا یک پرسشِ در جریان دارد» — بین پراسس‌ها.

    🔧 FIX هم‌زمانیِ واقعی: `_busy_users` یک set درون‌پراسسی است و طبق
    supervisord، ربات و API دو پراسس جدا هستند. یعنی کاربر می‌توانست
    هم‌زمان یکی از ربات و یکی از مینی‌اپ بفرستد و هر دو رد شوند از گاردِ
    محلی — دو درخواستِ هم‌زمان به provider، دو بار هزینه، و در ربات دو
    تسک روی یک پیامِ در حال ادیت. سقفِ روزانه از قبل اتمیک بود
    (`db.ai_consume_quota`)، ولی «یکی در لحظه» نبود.

    حالا set محلی به‌عنوان مسیرِ سریع می‌ماند و قفلِ مشترکِ دیتابیس
    (همان `admin_op_locks` که قبلاً برای اشتراک استفاده می‌شد) تصمیمِ
    نهایی است. اگر دیتابیس در دسترس نباشد `op_claim` عمداً fail-open است
    ⇒ رفتار دقیقاً به حالتِ امروز برمی‌گردد، نه بدتر.
    """
    uid = int(uid)
    if uid in _busy_users:
        return False
    try:
        from database import db
        if not await db.op_claim('ai_inflight', str(uid), ttl_seconds=AI_INFLIGHT_TTL):
            return False
    except Exception:
        logger.exception("ai_claim_inflight degraded for %s", uid)
    _busy_users.add(uid)
    return True


async def ai_is_inflight(uid: int) -> bool:
    """آیا این کاربر همین حالا پرسشی در جریان دارد؟ (فقط خواندن)

    برای گاردهای *مخرب* استفاده می‌شود (پاک‌کردن حافظه/سندِ مرجع وسطِ
    استریم). چون قفل در `admin_op_locks` مشترک است، پاسخِ در جریان در
    پراسسِ ربات هم دیده می‌شود — نه فقط درخواست‌های همین پراسس.
    """
    uid = int(uid)
    if uid in _busy_users:
        return True
    try:
        from database import db
        doc = await db.admin_op_locks.find_one({'_id': f"ai_inflight:{uid}"})
        if not doc:
            return False
        expires = doc.get('expires_at')
        return not expires or expires > now_utc()
    except Exception:
        logger.exception("ai_is_inflight check degraded for %s", uid)
        return False


async def ai_release_inflight(uid: int) -> None:
    """آزادسازی قفلِ پرسشِ در جریان — همیشه در finally صدا زده می‌شود."""
    uid = int(uid)
    _busy_users.discard(uid)
    try:
        from database import db
        await db.op_release('ai_inflight', str(uid))
    except Exception:
        logger.exception("ai_release_inflight failed for %s", uid)


async def handle_ai_image_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎨 تولید تصویر در بات — متنِ حالتِ ai_image_prompt.

    ترتیبِ گاردها عمداً همین است: ban → enabled → اعتبارسنجی ورودی →
    سهمیه → قفلِ سراسری → provider؛ سهمیه فقط **بعد از موفقیت** مصرف
    می‌شود تا شکستِ provider سهمیه‌ی کاربر را نسوزاند.
    """
    uid  = update.effective_user.id
    # 🌊 W7 — گیت فیچر (پیش‌فرض FREE ⇒ بدون تغییر رفتار امروز)
    from subscription import feature_allowed, show_paywall
    if not await feature_allowed(uid, "ai_image"):
        context.user_data.pop('mode', None)
        await show_paywall(update.message, uid, feature="ai_image")
        return
    text = (update.message.text or '').strip()
    if not text:
        return

    cfg = await get_ai_config()
    if not cfg['enabled'] or not cfg.get('image_enabled'):
        context.user_data.pop('mode', None)
        await update.message.reply_text(cfg.get('disabled_message') or DEFAULT_DISABLED_MSG)
        return

    # universal image: use image_provider/image_api_key from vault, not hard-coded gemini
    effective_key = cfg.get('image_api_key') or cfg.get('api_key') or ''
    effective_model = cfg.get('image_model') or DEFAULT_IMAGE_MODEL
    effective_provider = cfg.get('image_provider') or cfg.get('provider') or 'gemini'
    if not effective_key:
        context.user_data.pop('mode', None)
        await update.message.reply_text(
            "🎨 کلید API برای ساخت تصویر هنوز تنظیم نشده — از پنل مدیریت کلید مربوطه را وارد کن.")
        return

    if await db.ai_is_banned(uid):
        context.user_data.pop('mode', None)
        await update.message.reply_text(AI_BANNED_MSG, disable_web_page_preview=True)
        return

    if not (IMAGE_PROMPT_MIN <= len(text) <= IMAGE_PROMPT_MAX):
        await update.message.reply_text(
            f"✋ توضیح تصویر باید بین {IMAGE_PROMPT_MIN} و "
            f"{IMAGE_PROMPT_MAX} نویسه باشه.")
        return

    img_limit = cfg['image_daily_limit']
    today = today_tehran().isoformat()
    if uid != ADMIN_ID and img_limit > 0:
        used = await db.ai_image_used_today(uid, today)
        if used >= img_limit:
            await update.message.reply_text(
                f"📊 سهمیه‌ی امروزت ({img_limit} تصویر) تموم شده — "
                "فردا دوباره بیا، یا از حالت پرسش استفاده کن. 💬")
            return

    claimed = await ai_claim_inflight(uid)
    if not claimed:
        await update.message.reply_text(
            "⏳ یه لحظه! یه درخواست هوش مصنوعی‌ات هنوز در حال انجامه — "
            "صبر کن تموم شه، بعد اینو بزن.")
        return

    status = await update.message.reply_text(
        "🎨 در حال ساخت تصویر... یه لحظه صبر کن 🖌️\n"
        "(ممکنه تا یک دقیقه طول بکشه)")
    try:
        try:
            _cfg_img = cfg if isinstance(cfg, dict) else {}
            _img_keys = (_cfg_img.get('image_api_key_list')
                         or _cfg_img.get('api_key_list')
                         or [effective_key])
            async def _bot_gen_once(_k: str) -> dict:
                return await generate_image(
                    _k, effective_model, text, '1:1',
                    provider=effective_provider,
                    image_size=_cfg_img.get('image_size') or '1K')
            res = await run_with_key_failover(
                effective_provider, _img_keys, _bot_gen_once, label='bot-image')
        except AiImageError as e:
            logger.warning("bot image generation failed uid=%s code=%s",
                           uid, e.code)
            await status.edit_text(e.user_message)
            return

        img_bytes = base64.b64decode(res['data_b64'])
        from io import BytesIO
        await update.message.reply_photo(
            BytesIO(img_bytes), filename='humsyar_image.png',
            caption=f"🎨 تصویرت آماده شد!\n«{text[:80]}»")
        if uid != ADMIN_ID and img_limit > 0:
            try:
                await db.ai_image_inc(uid, today)
            except Exception:
                logger.exception("ثبت مصرف تصویر ناموفق بود uid=%s", uid)
        try:
            await status.edit_text("✅ تصویرت ارسال شد!")
        except Exception:
            pass  # پیامِ وضعیت پاک نشه — مشکلی نیست
    except Exception:
        logger.exception("bot image generation crashed uid=%s", uid)
        try:
            await status.edit_text(
                "❌ یه مشکلِ فنی پیش اومد؛ چند لحظه دیگه دوباره تلاش کن.")
        except Exception:
            pass
    finally:
        await ai_release_inflight(uid)


async def handle_ai_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    # 🌊 W7 — گیت فیچر (پیش‌فرض FREE ⇒ بدون تغییر رفتار امروز)
    from subscription import feature_allowed, show_paywall
    if not await feature_allowed(uid, "ai_chat"):
        context.user_data.pop('mode', None)
        await show_paywall(update.message, uid, feature="ai_chat")
        return
    text = (update.message.text or '').strip()
    if not text:
        return

    cfg = await get_ai_config()
    if not cfg['enabled']:
        context.user_data.pop('mode', None)
        await update.message.reply_text(cfg.get('disabled_message') or DEFAULT_DISABLED_MSG)
        return

    if await db.ai_is_banned(uid):
        await update.message.reply_text(AI_BANNED_MSG)
        return

    if len(text) > MAX_INPUT_CHARS:
        await update.message.reply_text(
            f"✍️ سوالت یه‌کم طولانیه (بیشتر از {MAX_INPUT_CHARS} کاراکتر). "
            "لطفاً خلاصه‌ترش کن یا فقط بخش اصلی سوال رو بفرست."
        )
        return

    # قفل *قبل* از مصرفِ سهمیه گرفته می‌شود: اگر بعد از کسرِ سهمیه رد
    # می‌شدیم، درخواستِ دومِ هم‌زمان یک واحد از سهمیه را می‌سوزاند بدون
    # اینکه هیچ پاسخی بگیرد.
    if not await ai_claim_inflight(uid):
        await update.message.reply_text("⏳ صبر کن جواب سوال قبلی‌ت آماده بشه، بعد این یکی رو بفرست 🙂")
        return

    try:
        allowed, used, limit = await check_and_consume_quota(uid)
        if not allowed:
            await update.message.reply_text(
                f"⛔️ سقف روزانه‌ی سوال از هوشیار تموم شده ({used}/{limit}).\n"
                "فردا دوباره امتحان کن."
            )
            return

        history = await _get_history(uid)
        await _answer_with_live_edit(
            update, context, ask_ai_stream(text=text, history=history, uid=uid),
            _footer(limit, used), uid, text,
        )
    finally:
        await ai_release_inflight(uid)


MAX_MEDIA_BYTES = 15 * 1024 * 1024  # ⚠️ قابلیتِ جدید (PDF/صدا): سقفِ حجمِ فایلِ ورودی

def _find_ffmpeg() -> str | None:
    """
    اول دنبالِ ffmpeg سیستمی می‌گرده (شاید ادمین با apt نصبش کرده باشه).
    اگه پیدا نشد، سراغِ پکیجِ pip به‌اسمِ imageio-ffmpeg می‌ره — این پکیج
    یه نسخه‌ی آماده‌ی ffmpeg رو خودش موقعِ نصب دانلود می‌کنه، پس نیازی
    به sudo/apt روی سرور نیست؛ کافیه توی requirements.txt باشه.
    """
    path = shutil.which('ffmpeg')
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


_FFMPEG_PATH = _find_ffmpeg()  # فقط یک بار موقعِ import چک می‌شه


# ══════════════════════════════════════════════════
#  ⭐ م8 — گفتار (TTS) + فهرست زنده‌ی مدل‌های تصویر + سلامت‌سنجی مدل‌ها
#
#  منبع: مستندات Google AI Studio (اکتبر ۲۰۲۶):
#   • TTS: gemini-3.8-flash-lite-tts (سریع/ارزان — مناسب پاسخِ زنده) و
#     gemini-3.8-flash-tts (کیفیت استودیویی). خروجی unary = WAV با هدر
#     (24kHz mono 16-bit). فارسی توسط هر دو پشتیبانی می‌شود.
#   • تصویر: gemini-nano-banana-2.1 (GA 2026-10-06)، 3.1-flash-lite-image
#     (حداقل تأخیر/هزینه)، 3.1-flash-image (منسوخ)، 3-pro-image.
#   • سلامت‌سنجی: هیچ چیز جای «آزمایشِ واقعیِ توکن» را نمی‌گیرد — یک
#     درخواستِ سبک می‌فرستیم و پاسخ می‌گیریم؛ مدلِ مرده/بی‌سهمیه جدا
#     می‌شود و مدل‌های زنده‌ی رایگان صدرِ فهرست می‌روند.
# ══════════════════════════════════════════════════
async def generate_speech_gemini(text: str, voice: str = None, style: str = None,
                                 model: str = None, timeout: int = 45) -> tuple:
    """⭐ م8 — تبدیل متن فارسی به گفتار با Gemini 3.8 TTS.

    خروجی: (wav_bytes, mime). با فال‌بکِ کلیدهای gemini (م7)."""
    cfg = await get_ai_config()
    model = (model or cfg.get('tts_model') or TTS_MODEL_DEFAULT).strip()
    voice = (voice or cfg.get('tts_voice') or TTS_VOICE_DEFAULT).strip()
    if voice not in PREBUILT_TTS_VOICES:
        voice = TTS_VOICE_DEFAULT
    keys = (cfg.get('vault_multi') or {}).get('gemini') or cfg.get('api_key_list') or []

    async def _tts_once(api_key: str) -> tuple:
        _kp = api_key_problem(api_key)
        if _kp:
            raise AIConfigError(_kp)
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent")
        payload = {
            'contents': [{'role': 'user', 'parts': [{
                'text': (text or '')[:4000],
                'speech_metadata': {'style': style or
                                    'گرم، دوستانه و طبیعی؛ ریتمِ گفتاریِ روان به فارسی'},
            }]}],
            'generationConfig': {
                'responseModalities': ['AUDIO'],
                'speechConfig': {'voiceConfig': {'voice': voice}},
            },
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers={
                'Content-Type': 'application/json', 'x-goog-api-key': api_key},
                json=payload)
        if resp.status_code != 200:
            _raise_gemini_status_error(resp.status_code,
                                       _provider_error_detail(resp.text))
        data = resp.json()
        for cand in (data.get('candidates') or []):
            for part in ((cand.get('content') or {}).get('parts') or []):
                inline = part.get('inlineData') or part.get('inline_data')
                if inline and inline.get('data'):
                    return (base64.b64decode(inline['data']),
                            inline.get('mimeType') or 'audio/wav')
        raise AIError("تولید صدای پاسخ ممکن نشد — دوباره امتحان کن.")

    return await run_with_key_failover('gemini', keys, _tts_once, label='tts')


async def _transcode_wav_to_ogg_opus(wav_bytes: bytes) -> bytes | None:
    """⭐ م8 — WAV→OGG/Opus برای «ویس» تلگرام (فرمتِ اجباری voice note)."""
    if not _FFMPEG_PATH or not wav_bytes:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            _FFMPEG_PATH, '-y', '-i', 'pipe:0',
            '-c:a', 'libopus', '-b:a', '48k', '-application', 'audio',
            '-f', 'ogg', 'pipe:1',
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        ogg, stderr = await asyncio.wait_for(proc.communicate(input=wav_bytes), timeout=60)
        if proc.returncode != 0 or not ogg:
            logger.warning("ffmpeg wav→ogg شکست خورد: %s", (stderr or b'')[:300])
            return None
        return ogg
    except Exception:
        logger.exception("تبدیل WAV به OGG با ffmpeg ناموفق بود")
        return None


def _voice_reply_plan(cfg: dict, voice_input: bool, answer_len: int) -> str:
    """⭐ م8.2 — تصمیمِ پاسخ صوتی، یکجا و قابل‌تست (قابل تنظیم از پنل).

    خروجی:
      'off'            — ویس ارسال نمی‌شود
      'voice_only'     — فقط ویس (متن استریم/تحویل نمی‌شود؛ fallback متن)
      'text_and_voice' — متن تحویل می‌شود + ویس بعدش (حالت all یا voice+متن)
      'text_only'      — ویس خواسته شده ولی جواب بلندتر از سقف است → فقط متن
    """
    mode = (cfg or {}).get('voice_reply') or 'voice'
    if mode == 'off':
        return 'off'
    wants = (mode == 'all') or (mode == 'voice' and voice_input)
    if not wants:
        return 'off'
    try:
        max_chars = int((cfg or {}).get('voice_reply_max_chars') or 500)
    except (TypeError, ValueError):
        max_chars = 500
    if answer_len > max_chars:
        return 'text_only'
    with_text = ((cfg or {}).get('voice_with_text') or 'off') == 'on'
    if voice_input and not with_text:
        return 'voice_only'
    return 'text_and_voice'


async def maybe_send_voice_reply(update, context, answer: str,
                                 voice_input: bool = False) -> None:
    """⭐ م8 — ویسِ اضافه: بعد از تحویلِ متن (حالت all یا voice+متن)،
    همان جواب را با TTS فارسی به‌صورت ویس هم می‌فرستد.

    حالتِ «فقط ویس» (پیش‌فرضِ voice بدون متنِ همراه) از این تابع رد
    می‌شود و مستقیم در _answer_with_live_edit مدیریت می‌شود.
    هر خطایی بی‌صدا لاگ می‌شود — متنِ جواب از قبل به دست کاربر رسیده."""
    try:
        text = (answer or '').strip()
        if not text:
            return
        cfg = await get_ai_config()
        mode = cfg.get('voice_reply') or 'voice'
        if mode == 'off' or (mode == 'voice' and not voice_input):
            return
        # TTS فقط با کلید gemini ممکن است
        if not ((cfg.get('vault_multi') or {}).get('gemini')
                or (cfg.get('provider') == 'gemini' and cfg.get('api_key'))):
            return
        try:
            max_chars = int(cfg.get('voice_reply_max_chars') or 500)
        except (TypeError, ValueError):
            max_chars = 500
        if len(text) > max_chars:
            return   # جواب بلند است — متن کافی است
        wav, _mime = await generate_speech_gemini(
            text, voice=cfg.get('tts_voice'), model=cfg.get('tts_model'))
        ogg = await _transcode_wav_to_ogg_opus(wav)
        if ogg:
            await update.effective_chat.send_voice(voice=ogg)
        else:
            # ffmpeg نیست — به‌صورت فایل صوتی WAV قابل‌پخش بفرست
            await update.effective_chat.send_audio(
                audio=wav, filename='houshyar.wav', title='پاسخ صوتی هوشیار')
    except Exception:
        logger.exception("ارسال پاسخ صوتی ناموفق بود (بی‌اثر بر متنِ جواب)")


# ─── فهرست زنده‌ی مدل‌های تصویر ───
_IMAGE_MODEL_MARKERS = ('image', 'nano-banana', 'imagen', 'banana')


def _looks_like_image_model(model_id: str) -> bool:
    mid = (model_id or '').lower()
    return (any(m in mid for m in _IMAGE_MODEL_MARKERS)
            and 'embedding' not in mid)


def model_free_rank(provider: str, model_id: str) -> int:
    """⭐ م8 — رتبه‌ی «رایگان‌بودن» برای مرتب‌سازی (بیشتر = رایگان‌تر).

    معیارِ نهایی «رایگان بودن» نیست — سلامتِ واقعی (تستِ توکن) مقدم است؛
    این فقط tie-breaker بینِ مدل‌های زنده است.
    OpenRouter: پسوند :free = قطعاً رایگان. Gemini: خانواده‌ی
    flash-lite/flash/nano-banana سهمیه‌ی رایگانِ بیشتری دارند."""
    mid = (model_id or '').lower()
    if (provider or '') == 'openrouter':
        return 4 if mid.endswith(':free') else 0
    if (provider or '') == 'gemini':
        if 'flash-lite' in mid:
            return 3
        if 'flash' in mid or 'nano-banana' in mid:
            return 2
        if 'pro' in mid:
            return 1
    return 0


def model_is_free(provider: str, model_id: str) -> bool:
    """نشانِ «رایگان» برای UI (سهمیه‌ی رایگانِ محدود هم رایگان حساب می‌شود)."""
    return model_free_rank(provider, model_id) >= 2


async def _list_image_models_gemini(api_key: str) -> list:
    """مدل‌های تصویرِ زنده از ListModels (به‌جای کاتالوگ ثابت)."""
    resp = None
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
            headers={'x-goog-api-key': api_key})
    if resp.status_code != 200:
        _raise_gemini_status_error(resp.status_code,
                                   _provider_error_detail(resp.text))
    out = []
    for m in (resp.json() or {}).get('models', []):
        raw_name = (m.get('name') or '').replace('models/', '').strip()
        if not raw_name or not _looks_like_image_model(raw_name):
            continue
        # ⭐ م8.4 — فقط مدل‌های Gemini که از generateContent پشتیبانی می‌کنند
        methods = m.get('supportedGenerationMethods')
        if methods and 'generateContent' not in methods:
            continue
        if raw_name.startswith('imagen'):
            continue
        label = raw_name
        if 'nano-banana' in raw_name:
            label = f'🍌 {raw_name} (نانوبانانا)'
        elif 'flash-lite' in raw_name:
            label = f'⚡ {raw_name} (سریع/کم‌هزینه — پیشنهادی)'
        elif '2.5-flash' in raw_name:
            label = f'🍌 {raw_name} (پایدار و رایگان در AI Studio)'
        out.append({'id': raw_name, 'label': label})
    return out


async def list_image_models(provider: str = 'gemini', api_key: str = None,
                            refresh: bool = False) -> dict:
    """⭐ م8.4 — فهرست مدل‌های تصویر گوگل (Gemini): زنده از API + کش ۱۲ ساعته؛
    در خطا/بی‌کلید → کاتالوگ ثابت مدل‌های گوگل. مدل‌های غیرگوگل حذف شدند."""
    provider = 'gemini'
    cache_key = 'ai_image_models_cache_gemini'
    if not refresh:
        cached = await db.get_setting(cache_key, None)
        if isinstance(cached, dict) and cached.get('models'):
            cmodels = cached.get('models') or []
            # اگر کش قدیمی شامل مدل‌های غیرگوگل (OpenRouter با '/') بود، باطل شود
            if cmodels and all('/' not in (m.get('id') or '') for m in cmodels):
                return cached
    models = []
    error = None
    try:
        keys = []
        if api_key:
            keys = [sanitize_api_key(api_key)]
        else:
            cfg = await get_ai_config()
            keys = ordered_keys('gemini',
                                (cfg.get('vault_multi') or {}).get('gemini') or [])
        if keys:
            async def _fetch(_k):
                return await _list_image_models_gemini(_k)
            raw = await run_with_key_failover('gemini', keys, _fetch,
                                              label='list_image_models')
            models = [{'id': m['id'], 'label': m['label'],
                       'free': model_is_free('gemini', m['id'])}
                      for m in raw]
    except Exception as e:                      # noqa: BLE001
        error = _sanitize_provider_text(str(e))[:200] or type(e).__name__
    if not models:
        # fallback کاتالوگ ثابت (فقط مدل‌های گوگل)
        models = [{'id': mid, 'label': label, 'free': is_free}
                  for mid, label, is_free in IMAGE_MODEL_CATALOG
                  if mid.startswith('gemini')]
        if error is None:
            error = 'فهرست زنده در دسترس نبود — کاتالوگ ثابت گوگل.'
        return {'models': models, 'cached': False, 'fetched_at': None,
                'fallback': True, 'error': error}
    payload = {'models': models, 'cached': False,
               'fetched_at': utc_now_iso(), 'fallback': False, 'error': None}
    try:
        await db.set_setting(cache_key, payload)
    except Exception:
        logger.exception("کشِ مدل‌های تصویر ذخیره نشد")
    return payload


# ─── سلامت‌سنجی (liveness) مدل‌ها با تستِ واقعیِ توکن ───
PROBE_MAX_MODELS = 30
PROBE_CONCURRENCY = 6


async def probe_chat_model(provider: str, api_key: str, model: str) -> dict:
    """تستِ سبکِ واقعی: یک ورودی کوچک → یک خروجی. 200 = زنده."""
    import time as _t
    started = _t.monotonic()
    try:
        if provider == 'gemini':
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent")
            payload = {'contents': [{'role': 'user', 'parts': [{'text': '۱'}]}],
                       'generationConfig': {'maxOutputTokens': 16}}
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(url, headers={
                    'Content-Type': 'application/json',
                    'x-goog-api-key': api_key}, json=payload)
        else:
            meta = PROVIDERS.get(provider) or {}
            if not meta.get('url'):
                return {'ok': False, 'ms': 0, 'error': 'provider پشتیبانی نمی‌شود'}
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    meta['url'] + '/chat/completions',
                    headers={'Authorization': f'Bearer {api_key}'},
                    json={'model': model, 'messages': [
                        {'role': 'user', 'content': 'hi'}], 'max_tokens': 4})
        ms = int((_t.monotonic() - started) * 1000)
        if resp.status_code == 200:
            return {'ok': True, 'ms': ms, 'error': ''}
        detail = _provider_error_detail(resp.text)[:160]
        return {'ok': False, 'ms': ms,
                'error': f'HTTP {resp.status_code}' + (f': {detail}' if detail else '')}
    except Exception as e:                      # noqa: BLE001
        return {'ok': False, 'ms': int((_t.monotonic() - started) * 1000),
                'error': _sanitize_provider_text(str(e))[:160] or type(e).__name__}


async def probe_image_model(provider: str, api_key: str, model: str) -> dict:
    """⭐ م8.4 — تستِ واقعیِ ساخت تصویر روی مدل گوگل (generateContent واقعی).

    قبلاً برای غیر-gemini عددِ جعلیِ 0ms برمی‌گشت و برای gemini هم فقط GET
    کاتالوگ زده می‌شد که مدل‌های نیازمندِ Billing یا ازکارافتاده را هم
    «سالم» نشان می‌داد. اکنون واقعاً یک درخواستِ generateContent سبک زده
    می‌شود و زمانِ پاسخِ واقعی (ms > 0) ثبت می‌گردد."""
    import time as _t
    started = _t.monotonic()
    mid = (model or '').strip()
    if not mid.startswith('gemini') and not mid.startswith('imagen'):
        return {'ok': False, 'ms': 0,
                'error': 'فقط مدل‌های تصویر گوگل (Gemini) پشتیبانی می‌شوند.',
                'mode': 'real_image_gen'}
    try:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{mid}:generateContent")
        _ml = mid.lower()
        img_cfg = {'aspectRatio': '1:1'}
        if 'flash-lite' not in _ml and '2.5-flash' not in _ml:
            img_cfg['imageSize'] = '1K'
        payload = {
            'contents': [{'role': 'user', 'parts': [{'text': 'A simple blue circle icon'}]}],
            'generationConfig': {
                'responseModalities': ['IMAGE'],
                'imageConfig': img_cfg,
            },
        }
        headers = {'Content-Type': 'application/json', 'x-goog-api-key': api_key}
        async with httpx.AsyncClient(timeout=35) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 400:
                _b400 = (getattr(resp, 'text', '') or '').lower()
                if any(k in _b400 for k in (
                        'invalid_argument', 'modality', 'modalities',
                        'image_config', 'imageconfig', 'image_size',
                        'imagesize', 'aspect_ratio', 'aspectratio')):
                    fb_payload = {
                        'contents': [{'role': 'user', 'parts': [{'text': 'Generate an image: A simple blue circle icon'}]}],
                        'generationConfig': {'responseModalities': ['TEXT', 'IMAGE']},
                    }
                    resp = await client.post(url, headers=headers, json=fb_payload)
        ms = max(1, int((_t.monotonic() - started) * 1000))
        if resp.status_code == 200:
            data = resp.json() if hasattr(resp, 'json') else {}
            if isinstance(data, dict) and 'candidates' in data:
                try:
                    _parse_image_response(data)
                except AiImageError as pe:
                    return {'ok': False, 'ms': ms, 'error': pe.user_message,
                            'mode': 'real_image_gen'}
            return {'ok': True, 'ms': ms, 'error': '', 'mode': 'real_image_gen'}
        raw_txt = getattr(resp, 'text', '') or ''
        detail = _provider_error_detail(raw_txt)[:140]
        low = raw_txt.lower()
        if resp.status_code == 429 and ('limit: 0' in low or 'billing' in low):
            err = 'HTTP 429: سهمیه رایگان ندارد (نیازمند Billing)'
        elif resp.status_code == 404:
            err = 'HTTP 404: مدل در دسترس نیست یا بازنشسته شده'
        else:
            err = f'HTTP {resp.status_code}' + (f': {detail}' if detail else '')
        return {'ok': False, 'ms': ms, 'error': err, 'mode': 'real_image_gen'}
    except Exception as e:                      # noqa: BLE001
        return {'ok': False, 'ms': max(1, int((_t.monotonic() - started) * 1000)),
                'error': _sanitize_provider_text(str(e))[:160] or type(e).__name__,
                'mode': 'real_image_gen'}


def _looks_like_live_model(model_id: str) -> bool:
    """⭐ م9 — تشخیص مدل‌های صوتی زنده‌ی گوگل (Gemini Live API)."""
    m = (model_id or '').lower().strip()
    if not m or '/' in m:
        return False
    return 'live' in m or 'native-audio' in m


async def list_live_models(refresh: bool = False) -> dict:
    """⭐ م9 — فهرست مدل‌های Gemini Live API: کاتالوگ رسمی ۲۰۲۶ گوگل + کشف از ListModels."""
    cache_key = 'ai_live_models_cache_gemini'
    if not refresh:
        cached = await db.get_setting(cache_key, None)
        if isinstance(cached, dict) and cached.get('models'):
            return cached
    by_id = {
        mid: {'id': mid, 'label': label, 'free': is_free}
        for mid, label, is_free in LIVE_MODEL_CATALOG
    }
    error = None
    try:
        cfg = await get_ai_config()
        keys = ordered_keys('gemini',
                            (cfg.get('vault_multi') or {}).get('gemini') or [])
        if keys:
            async def _fetch_live(_k: str) -> list:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(
                        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                        headers={'x-goog-api-key': _k})
                if resp.status_code != 200:
                    return []
                found = []
                for m in (resp.json() or {}).get('models', []):
                    raw_name = (m.get('name') or '').replace('models/', '').strip()
                    methods = m.get('supportedGenerationMethods') or []
                    if not raw_name:
                        continue
                    if 'bidiGenerateContent' in methods or _looks_like_live_model(raw_name):
                        found.append(raw_name)
                return found
            extra = await run_with_key_failover('gemini', keys, _fetch_live,
                                                label='list_live_models')
            for mid in (extra or []):
                if mid not in by_id and mid.startswith('gemini'):
                    by_id[mid] = {'id': mid, 'label': f'🎙 {mid}', 'free': True}
    except Exception as e:
        error = _sanitize_provider_text(str(e))[:200] or type(e).__name__
    models = list(by_id.values())
    payload = {'models': models, 'cached': False,
               'fetched_at': utc_now_iso(), 'fallback': bool(error), 'error': error}
    try:
        await db.set_setting(cache_key, payload)
    except Exception:
        logger.exception("کشِ مدل‌های Live ذخیره نشد")
    return payload


LIVE_PERSIAN_LANGUAGE_LOCK_HEADER = (
    "[MANDATORY LANGUAGE & AUDIO RECOGNITION LOCK — CRITICAL SYSTEM RULE]:\n"
    "1. INPUT AUDIO LANGUAGE IS EXCLUSIVELY PERSIAN (FARSI / fa-IR): The user is an Iranian student speaking EXCLUSIVELY in Persian (Farsi / زبان فارسی). "
    "Always recognize, interpret, and understand the user's spoken audio as Persian (Farsi). "
    "NEVER misinterpret Persian speech or short Persian words (such as 'سلام' / 'Salam', 'خوبی' / 'Khoobi', 'چطوری' / 'Chetori', 'بله' / 'Bale') as Hindi, Urdu, German, English, Arabic, Turkish, or Russian.\n"
    "2. OUTPUT LANGUAGE IS EXCLUSIVELY PERSIAN (FARSI / fa-IR): RESPOND IN PERSIAN (FARSI / فارسی). YOU MUST RESPOND UNMISTAKABLY AND EXCLUSIVELY IN PERSIAN (fa-IR) AT ALL TIMES. "
    "NEVER SWITCH TO ANY OTHER LANGUAGE (SUCH AS HINDI, GERMAN, ENGLISH, ARABIC, TURKISH, SPANISH, RUSSIAN, KOREAN, CHINESE, OR FRENCH) UNDER ANY CIRCUMSTANCES.\n"
    "3. NO GREETING LOOPS: When the user greets you ('سلام'), greet them back ONCE warmly and concisely in Persian, and wait for their question. "
    "NEVER repeat 'سلام' or repeat your greeting multiple times in a row. If you hear faint echo, background noise, or silence after greeting the user, do NOT repeat your greeting.\n"
    "4. UNCLEAR AUDIO RULE: IF THE USER'S AUDIO IS UNCLEAR, MUFFLED, NOISY, DISTORTED, OR SOUNDS LIKE ANOTHER LANGUAGE DUE TO MICROPHONE NOISE, DO NOT SWITCH LANGUAGES; "
    "ALWAYS ASSUME THE STUDENT IS SPEAKING PERSIAN AND POLITELY ASK THEM IN PERSIAN TO REPEAT WHAT THEY SAID.\n\n"
    "[قانون قطعی و تغییرناپذیر زبان مکالمه زنده]:\n"
    "زبان گفتار دانشجو و زبان پیش‌فرض و انحصاری شما در تمام طول این تماس صوتی زنده **فقط و فقط زبان فارسی (Persian / Farsi)** است.\n"
    "۱) شما تحت هیچ شرایطی مجاز نیستید زبان مکالمه را به زبان دیگری (هندی، آلمانی، انگلیسی، عربی، ترکی، روسی و غیره) تغییر دهید یا گفتار فارسی دانشجو را به زبان دیگری برداشت کنید.\n"
    "۲) وقتی دانشجو «سلام» می‌گوید، فقط **یک بار** صمیمی و کوتاه پاسخ دهید و منتظر سوالش بمانید؛ هرگز سلام و احوال‌پرسی را چند بار پشت سر هم تکرار نکنید.\n"
    "۳) اگر صدای کاربر یا دانشجو ضعیف، نامفهوم، بریده‌بریده، گنگ یا همراه با نویز محیط بود و متوجه نشدید چه گفت، **هرگز زبان خود را عوض نکنید** و هرگز تصور نکنید به زبان خارجی صحبت کرده است؛ در این حالت حتماً فقط به زبان فارسی صمیمی بگویید: «ببخشید صدات واضح نیومد، می‌شه دوباره بگی؟» یا «متوجه نشدم چی گفتی عزیزم، یه بار دیگه تکرار می‌کنی؟».\n\n"
)

LIVE_PERSIAN_LANGUAGE_LOCK_FOOTER = (
    "\n\n[دستورالعمل تماس صوتی زنده (Live Voice Call) و قفل زبان فارسی]:\n"
    "- شما در حال مکالمه‌ی صوتی زنده و مستقیم با دانشجوی ایرانی هستید.\n"
    "- پاسخ‌ها را همیشه ۱۰۰٪ به **زبان فارسی معیار گفتاری**، روان، صمیمی، طبیعی و بدون علائم نگارشیِ بلند یا کدهای Markdown بیان کن تا در گفتار صوتی کاملاً طبیعی شنیده شود.\n"
    "- هرگز در ابتدای مکالمه چند بار پشت سر هم سلام نکن؛ یک بار سلام و احوال‌پرسی کوتاه کافی است.\n"
    "- تذکر نهایی و قطعی (UNMISTAKABLY RESPOND IN PERSIAN): حتی اگر صدای ورودی میکروفون نامفهوم یا شبیه زبان‌های دیگر (مثل هندی یا آلمانی) شنیده شد، هرگز به زبان غیرفارسی پاسخ نده و همیشه به فارسی صحبت کن."
)


def build_live_language_lock_turn(turn_complete: bool = False) -> dict:
    """م9.6 — ساخت نوبت کانتکست پنهان (turnComplete=False) برای قفل کردن توزیع احتمال زبان مدل روی فارسی (fa-IR)."""
    return {
        'clientContent': {
            'turns': [
                {
                    'role': 'user',
                    'parts': [
                        {
                            'text': (
                                "[یادآوری سیستمی قفل زبان: در تمام طول این تماس صوتی، فقط و فقط به زبان فارسی (Persian / Farsi) "
                                "صحبت کن. اگر صدای من واضح نبود یا نویز داشت، هرگز زبان خودت را به انگلیسی، عربی یا هیچ زبان دیگری "
                                "تغییر نده و فقط به فارسی بگو که صدا واضح نبود.]"
                            ),
                        }
                    ],
                }
            ],
            'turnComplete': bool(turn_complete),
        }
    }


def is_non_persian_output_drift(text: str) -> bool:
    """م9.6 — تشخیص انحراف ناخواسته‌ی خروجی صوتی مدل به زبان غیرفارسی (مثلاً در اثر نویز میکروفون)."""
    if not text:
        return False
    s = str(text).strip()
    if len(s) < 6:
        return False
    # ۱) اگر حتی یک کاراکتر از خطوط غیرمرتبط (سیریلیک، هندی/دواناگری، کره‌ای، چینی/ژاپنی، تایلندی، عبری) در خروجی باشد
    if re.search(r'[\u0400-\u04FF\u0900-\u097F\uAC00-\uD7AF\u4E00-\u9FFF\u3040-\u30FF\u0E00-\u0E7F\u0590-\u05FF]', s):
        return True
    # ۲) شمارش حروف فارسی/عربی در برابر حروف لاتین
    persian_chars = len(re.findall(r'[\u0600-\u06FF]', s))
    latin_chars = len(re.findall(r'[A-Za-z\u00C0-\u024F]', s))
    total_alpha = persian_chars + latin_chars
    if total_alpha >= 18 and persian_chars == 0:
        return True
    if total_alpha >= 30 and (persian_chars / float(total_alpha)) < 0.20:
        return True
    return False


# م9.7 — نگاشت فوری آوایی برای کلمات و احوال‌پرسی‌های فارسی که STT جمینی به خط هندی (دواناگری) یا آلمانی/لاتین می‌نویسد
_FOREIGN_STT_EXACT_PHRASE_MAP: dict[str, str] = {
    'सलाम': 'سلام',
    'अलाम': 'سلام',
    'अस्सलामु अलैकुम': 'سلام علیکم',
    'सलाम अलैकुम': 'سلام علیکم',
    'नमस्ते': 'سلام',
    'नमस्कार': 'سلام',
    'हेलो': 'سلام',
    'हाय': 'سلام',
    'हालो': 'سلام',
    'सलाम खूबी': 'سلام خوبی',
    'सलाम चतोरी': 'سلام چطوری',
    'सलाम चेतोरी': 'سلام چطوری',
    'खूबी': 'خوبی',
    'चतोरी': 'چطوری',
    'चेतोरी': 'چطوری',
    'चेटोरी': 'چطوری',
    'ममनून': 'ممنون',
    'मेर्सी': 'مرسی',
    'बले': 'بله',
    'भले': 'بله',
    'ना': 'نه',
    'नहीं': 'نه',
    'खोदा हाफिज': 'خداحافظ',
    'हुशयार': 'هوشیار',
    'होशियार': 'هوشیار',
    'salam': 'سلام',
    'salaam': 'سلام',
    'selam': 'سلام',
    'salom': 'سلام',
    'salam aleykum': 'سلام علیکم',
    'salam aleikum': 'سلام علیکم',
    'alam': 'سلام',
    'alarm': 'سلام',
    'hallo': 'سلام',
    'hello': 'سلام',
    'hi': 'سلام',
    'hey': 'سلام',
    'salut': 'سلام',
    'guten tag': 'سلام',
    'servus': 'سلام',
    'moin': 'سلام',
    'salam khoobi': 'سلام خوبی',
    'salam khubi': 'سلام خوبی',
    'salam chetori': 'سلام چطوری',
    'khoobi': 'خوبی',
    'khubi': 'خوبی',
    'khoubi': 'خوبی',
    'chetori': 'چطوری',
    'chetoori': 'چطوری',
    'chetor': 'چطور',
    'halet chetore': 'حالت چطوره',
    'mamnoon': 'ممنون',
    'mamnun': 'ممنون',
    'mersi': 'مرسی',
    'merci': 'مرسی',
    'danke': 'مرسی',
    'bale': 'بله',
    'baleh': 'بله',
    'are': 'آره',
    'areh': 'آره',
    'ja': 'بله',
    'na': 'نه',
    'nah': 'نه',
    'nein': 'نه',
    'khodahafez': 'خداحافظ',
    'khoda hafez': 'خداحافظ',
    'houshyar': 'هوشیار',
    'hoshyar': 'هوشیار',
    'hushyar': 'هوشیار',
}

_FOREIGN_STT_TOKEN_MAP: dict[str, str] = {
    **_FOREIGN_STT_EXACT_PHRASE_MAP,
    'मन': 'من',
    'तो': 'تو',
    'मा': 'ما',
    'शमा': 'شما',
    'शुमा': 'شما',
    'ये': 'یه',
    'यक': 'یک',
    'सवाल': 'سوال',
    'दारम': 'دارم',
    'दर्स': 'درس',
    'उस्ताद': 'استاد',
    'इम्तिहान': 'امتحان',
    'किताब': 'کتاب',
    'बर्नामे': 'برنامه',
    'क्लास': 'کلاس',
    'ची': 'چی',
    'चे': 'چه',
    'कजा': 'کجا',
    'कुजा': 'کجا',
    'के': 'که',
    'अज़': 'از',
    'बा': 'با',
    'बे': 'به',
    'दर': 'در',
    'अस्त': 'است',
    'हस्त': 'هست',
    'नीस्त': 'نیست',
    'जान': 'جان',
    'अजीजम': 'عزیزم',
    'खूब': 'خوب',
    'خوبम': 'خوبم',
    'खूबम': 'خوبم',
    'man': 'من',
    'to': 'تو',
    'shoma': 'شما',
    'ye': 'یه',
    'yek': 'یک',
    'soal': 'سوال',
    'daram': 'دارم',
    'dars': 'درس',
    'ostad': 'استاد',
    'emtehan': 'امتحان',
    'ketab': 'کتاب',
    'barname': 'برنامه',
    'barnameh': 'برنامه',
    'kelas': 'کلاس',
    'chi': 'چی',
    'che': 'چه',
    'koja': 'کجا',
    'ke': 'که',
    'az': 'از',
    'ba': 'با',
    'be': 'به',
    'dar': 'در',
    'ast': 'است',
    'hast': 'هست',
    'nist': 'نیست',
    'khoobam': 'خوبم',
    'khubam': 'خوبم',
}


def sanitize_live_persian_transcript(text: str, is_input: bool = True) -> str:
    """م9.7 — پالایش زیرنویس زنده (input_transcript / output_transcript) در حالت زبان فارسی.

    چرا لازم است؟
    مدل STT مجزای inputAudioTranscription در Gemini Live API فیلد languageCode ندارد و گاهی
    واژه‌های کوتاه فارسی (مثل «سلام» / «خوبی») را به خط هندی (دواناگری: सलाम) یا آلمانی/لاتین
    (Hallo / Alarm / Salam) آوانگاری می‌کند. این تابع:
    ۱) اگر متن حاوی حروف فارسی باشد، کاراکترهای خطوط بیگانه (دواناگری، سیریلیک، شرق آسیا) را پاک کرده و متن فارسی را برمی‌گرداند.
    ۲) اگر متن فاقد حروف فارسی باشد و در جدول آوانگاری فارسی (مثل सलाम / Salam / Hallo / Alarm -> سلام) باشد، معادل دقیق فارسی را برمی‌گرداند.
    ۳) اگر متن تماماً به زبان/خط بیگانه‌ی نامرتبط (هندی، آلمانی، روسی و...) باشد، رشته‌ی خالی برمی‌گرداند تا هرگز زیرنویس غیرفارسی به کاربر نمایش داده نشود.
    """
    if not text:
        return ''
    raw = str(text).strip()
    if not raw:
        return ''

    persian_chars = len(re.findall(r'[\u0600-\u06FF]', raw))
    if persian_chars > 0:
        # حذف کاراکترهای خطوط غیرمرتبط (دواناگری/هندی، سیریلیک، چینی/ژاپنی/کره‌ای، تایلندی، عبری)
        cleaned = re.sub(
            r'[\u0400-\u04FF\u0900-\u097F\uAC00-\uD7AF\u4E00-\u9FFF\u3040-\u30FF\u0E00-\u0E7F\u0590-\u05FF]+',
            ' ',
            raw,
        )
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    # متن هیچ حرف فارسی ندارد — بررسی جدول آوانگاری فوری (برای ورودی کاربر)
    if is_input:
        norm = re.sub(r'[.,!?;:،؛؟।"«»()\[\]{}\-_]+', ' ', raw.lower())
        norm = re.sub(r'\s+', ' ', norm).strip()
        if not norm:
            return ''
        if norm in _FOREIGN_STT_EXACT_PHRASE_MAP:
            return _FOREIGN_STT_EXACT_PHRASE_MAP[norm]

        tokens = [t for t in norm.split(' ') if t]
        if tokens:
            mapped = [_FOREIGN_STT_TOKEN_MAP.get(t) for t in tokens]
            hit_count = sum(1 for m in mapped if m)
            if hit_count > 0 and hit_count >= max(1, int(len(tokens) * 0.6)):
                return ' '.join(m for m in mapped if m)

    # متن تماماً غیرفارسی است (هندی/آلمانی/لاتین ناشناخته) -> مسدودسازی نمایش خام در زیرنویس
    return ''


async def repair_foreign_stt_to_persian(
    foreign_text: str,
    reply_context: str = '',
    api_key: str = '',
) -> str:
    """م9.7 — بازگردانی جملات فارسی که STT جمینی به اشتباه با حروف هندی/آلمانی آوانگاری کرده است."""
    ft = (foreign_text or '').strip()
    if not ft:
        return ''
    instant = sanitize_live_persian_transcript(ft, is_input=True)
    if instant:
        return instant
    if not api_key:
        try:
            cfg = await get_ai_config()
            api_key = cfg.get('api_key') or ''
        except Exception:
            api_key = ''
    if not api_key:
        return ''

    ctx_hint = ''
    if reply_context and len(reply_context.strip()) >= 4:
        ctx_hint = f"\nپاسخی که دستیار به این جمله‌ی دانشجو داده این بوده است: «{reply_context.strip()[:300]}»"

    prompt = (
        "یک دانشجوی ایرانی در تماس صوتی به **زبان فارسی** صحبت کرده است، اما موتور تشخیص گفتار (STT) "
        f"به‌شتباه صدای فارسی او را با حروف هندی/آلمانی/لاتین به این شکل آوانگاری کرده است:\n«{ft[:400]}»"
        f"{ctx_hint}\n\n"
        "فقط و فقط جمله‌ی اصلی فارسی گفتاری که دانشجو گفته است را به خط فارسی بنویس "
        "(بدون هیچ توضیحی، بدون گیومه، حداکثر یک خط کوتاه فارسی؛ اگر صرفاً نویز بی‌معنی بوده فقط بنویس: «...»):"
    )
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    payload = {
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'generationConfig': {
            'maxOutputTokens': 80,
            'temperature': 0.1,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(
                url,
                headers={'Content-Type': 'application/json', 'x-goog-api-key': api_key},
                json=payload,
            )
        if resp.status_code == 200:
            data = resp.json()
            cands = data.get('candidates') or []
            if cands:
                parts = ((cands[0].get('content') or {}).get('parts')) or []
                out = ''.join(p.get('text', '') for p in parts if isinstance(p, dict)).strip()
                out = out.strip('«»"\' \n\t')
                if out and out != '...' and len(re.findall(r'[\u0600-\u06FF]', out)) >= 2:
                    return sanitize_live_persian_transcript(out, is_input=True)
    except Exception:
        pass
    return ''


def build_live_setup_message(
    model: str = DEFAULT_LIVE_MODEL,
    system_prompt: str = '',
    voice: str = TTS_VOICE_DEFAULT,
    thinking_level: str = 'low',
    target_language: str = 'fa',
    uid: int = 0,
    include_tools: bool = True,
    temperature: float = DEFAULT_LIVE_TEMPERATURE,
) -> dict:
    """⭐ م9 — ساخت پیام اولیه‌ی BidiGenerateContentSetup طبق مستندات رسمی گوگل (سپتامبر/اکتبر ۲۰۲۶).

    قواعد اختصاصی هر مدل در مستندات گوگل:
    1) gemini-3.5-live-translate-preview:
       - فقط مترجم صوت‌به‌صوت است؛ systemInstruction و tools ندارد.
       - دارای translationConfig: {targetLanguageCode, echoTargetLanguage: True}
    2) gemini-3.8-live:
       - مدل پیش‌فرض مکالمه زنده با تأخیر کم؛ thinkingConfig پشتیبانی نمی‌شود (باید حذف شود).
       - از ابزارهای NON_BLOCKING پشتیبانی می‌کند.
    3) gemini-3.8-live-extended-thinking:
       - نیازمند thinkingConfig.thinkingLevel در {'LOW', 'MEDIUM', 'HIGH'} (MINIMAL مجاز نیست).
       - تمام functionDeclarations باید behavior='NON_BLOCKING' داشته باشند.
    4) gemini-3.1-flash-live-preview:
       - دارای thinkingConfig.thinkingLevel در {'minimal', 'low', 'medium', 'high'}.
       - فراخوانی ابزار ترتیبی (sequential) است (بدون فیلد behavior).
    """
    mid = (model or DEFAULT_LIVE_MODEL).replace('models/', '').strip() or DEFAULT_LIVE_MODEL
    ml = mid.lower()
    full_model = f"models/{mid}"

    # ۱) مدل مترجم هم‌زمان صوت‌به‌صوت (gemini-3.5-live-translate-preview)
    if 'translate' in ml:
        t_lang = (target_language or 'fa').strip().lower()[:10] or 'fa'
        return {
            'setup': {
                'model': full_model,
                'generationConfig': {
                    'responseModalities': ['AUDIO'],
                    'inputAudioTranscription': {},
                    'outputAudioTranscription': {},
                    'translationConfig': {
                        'targetLanguageCode': t_lang,
                        'echoTargetLanguage': True,
                    },
                },
            }
        }

    # ۲) مدل‌های مکالمه صوتی زنده (3.8-live / 3.8-live-extended-thinking / 3.1-flash-live-preview)
    v_name = (voice or TTS_VOICE_DEFAULT).strip()
    if v_name not in PREBUILT_TTS_VOICES:
        v_name = TTS_VOICE_DEFAULT

    try:
        temp_val = round(max(0.1, min(1.5, float(temperature if temperature is not None else DEFAULT_LIVE_TEMPERATURE))), 2)
    except (TypeError, ValueError):
        temp_val = DEFAULT_LIVE_TEMPERATURE

    gen_cfg: dict = {
        'responseModalities': ['AUDIO'],
        'temperature': temp_val,
        'speechConfig': {
            'voiceConfig': {
                'prebuiltVoiceConfig': {
                    'voiceName': v_name,
                }
            }
        },
    }

    lvl = (thinking_level or 'low').strip().lower()
    if 'extended-thinking' in ml:
        # طبق مستندات گوگل: در 3.8-live-extended-thinking مقدار minimal مجاز نیست
        if lvl not in ('low', 'medium', 'high'):
            lvl = 'low'
        gen_cfg['thinkingConfig'] = {'thinkingLevel': lvl.upper()}
    elif '3.1-flash-live' in ml:
        if lvl not in ('minimal', 'low', 'medium', 'high'):
            lvl = 'minimal'
        gen_cfg['thinkingConfig'] = {'thinkingLevel': lvl}
    # برای gemini-3.8-live طبق مستندات thinkingConfig نباید ارسال شود

    live_sys = (system_prompt or DEFAULT_VOICE_PROMPT).strip()
    full_sys_text = f"{LIVE_PERSIAN_LANGUAGE_LOCK_HEADER}{live_sys}{LIVE_PERSIAN_LANGUAGE_LOCK_FOOTER}"
    setup_obj: dict = {
        'model': full_model,
        'generationConfig': gen_cfg,
        'systemInstruction': {
            'parts': [{'text': full_sys_text[:16000]}],
        },
        'inputAudioTranscription': {},
        'outputAudioTranscription': {},
        # م9.7 — تنظیم کالیبره‌شده تشخیص فعالیت صوتی (VAD):
        # • prefixPaddingMs=300: حفظ کامل ۳۰۰ میلی‌ثانیه ابتدای کلمات فارسی (مثل «س» در «سلام»)
        # • START_SENSITIVITY_LOW / END_SENSITIVITY_LOW + silenceDurationMs=900: جلوگیری از تکه شدن یک جمله به ۲-۳ نوبت و حذف تریگر کاذب روی نویز/اکو
        'realtimeInputConfig': {
            'automaticActivityDetection': {
                'disabled': False,
                'startOfSpeechSensitivity': 'START_SENSITIVITY_LOW',
                'endOfSpeechSensitivity': 'END_SENSITIVITY_LOW',
                'prefixPaddingMs': 300,
                'silenceDurationMs': 900,
            },
            'activityHandling': 'START_OF_ACTIVITY_INTERRUPTS',
            'turnCoverage': 'TURN_INCLUDES_ONLY_ACTIVITY',
        },
        # م9.5 — فشرده‌سازی خودکار پنجره کانتکست (Sliding Window) برای پایداری مکالمات طولانی
        'contextWindowCompression': {
            'slidingWindow': {},
        },
    }

    if include_tools:
        raw_funcs = list(AI_FUNCTIONS)
        if uid and int(uid) == ADMIN_ID:
            raw_funcs.extend(ADMIN_AI_FUNCTIONS)
        use_non_blocking = ('3.8-live' in ml)
        decls = []
        for fn in raw_funcs:
            d = {
                'name': fn['name'],
                'description': fn['description'],
            }
            params = fn.get('parameters') or {}
            if params.get('properties'):
                d['parameters'] = params
            if use_non_blocking:
                d['behavior'] = 'NON_BLOCKING'
            decls.append(d)
        if decls:
            setup_obj['tools'] = [{'functionDeclarations': decls}]

    return {'setup': setup_obj}


def parse_live_server_message(raw_msg) -> list:
    """⭐ م9 — پارس پیام‌های دریافتی از WebSocket گوگل (BidiGenerateContentServerMessage)
    و تبدیل به رویدادهای یکدست برای کلاینت مینی‌اپ/وب‌ادمین."""
    if isinstance(raw_msg, (bytes, bytearray)):
        try:
            data = json.loads(raw_msg.decode('utf-8', 'replace'))
        except Exception:
            return []
    elif isinstance(raw_msg, str):
        try:
            data = json.loads(raw_msg)
        except Exception:
            return []
    elif isinstance(raw_msg, dict):
        data = raw_msg
    else:
        return []

    if not isinstance(data, dict):
        return []

    events = []
    if 'setupComplete' in data or 'setup_complete' in data:
        events.append({'type': 'ready'})

    if 'error' in data and isinstance(data['error'], dict):
        msg = data['error'].get('message') or str(data['error'])
        events.append({'type': 'error', 'message': _sanitize_provider_text(msg)[:220]})

    sc = data.get('serverContent') or data.get('server_content') or {}
    if isinstance(sc, dict) and sc:
        if sc.get('interrupted'):
            events.append({'type': 'interrupted'})

        in_tr = sc.get('inputTranscription') or sc.get('input_transcription')
        if isinstance(in_tr, dict) and in_tr.get('text'):
            events.append({
                'type': 'input_transcript',
                'text': in_tr.get('text') or '',
                'language': in_tr.get('languageCode') or in_tr.get('language_code') or '',
            })

        out_tr = sc.get('outputTranscription') or sc.get('output_transcription')
        if isinstance(out_tr, dict) and out_tr.get('text'):
            events.append({
                'type': 'output_transcript',
                'text': out_tr.get('text') or '',
                'language': out_tr.get('languageCode') or out_tr.get('language_code') or '',
            })

        mt = sc.get('modelTurn') or sc.get('model_turn') or {}
        for part in (mt.get('parts') or []):
            if not isinstance(part, dict):
                continue
            inl = part.get('inlineData') or part.get('inline_data')
            if isinstance(inl, dict) and inl.get('data'):
                events.append({
                    'type': 'audio',
                    'data': inl['data'],
                    'mimeType': inl.get('mimeType') or inl.get('mime_type') or 'audio/pcm;rate=24000',
                })
            if part.get('text') and not part.get('thought'):
                events.append({
                    'type': 'text',
                    'text': part['text'],
                })

        turn_complete = bool(sc.get('turnComplete') or sc.get('turn_complete'))
        interaction_status = (
            sc.get('interactionStatus')
            or sc.get('interaction_status')
            or data.get('interactionStatus')
            or data.get('interaction_status')
            or ''
        )
        if turn_complete or interaction_status:
            events.append({
                'type': 'turn_state',
                'turn_complete': turn_complete,
                'interaction_status': interaction_status,
            })

    tc = data.get('toolCall') or data.get('tool_call')
    if isinstance(tc, dict) and (tc.get('functionCalls') or tc.get('function_calls')):
        calls = tc.get('functionCalls') or tc.get('function_calls') or []
        events.append({
            'type': 'tool_call',
            'calls': [
                {
                    'id': c.get('id') or '',
                    'name': c.get('name') or '',
                    'args': c.get('args') or {},
                }
                for c in calls if isinstance(c, dict) and c.get('name')
            ],
            'interaction_status': (
                data.get('interactionStatus') or data.get('interaction_status') or ''
            ),
        })

    tcc = data.get('toolCallCancellation') or data.get('tool_call_cancellation')
    if isinstance(tcc, dict) and tcc.get('ids'):
        events.append({
            'type': 'tool_call_cancellation',
            'ids': list(tcc.get('ids') or []),
        })

    return events


_BIDI_DISCOVERY_CACHE: dict[str, tuple[float, list]] = {}
_BIDI_DISCOVERY_TTL_SEC = 600.0


async def _discover_bidi_models_for_key(api_key: str) -> list:
    """دریافت فهرست مدل‌هایی که روی این کلید صریحاً از bidiGenerateContent پشتیبانی می‌کنند (با کش ۱۰ دقیقه‌ای)."""
    now = time.monotonic()
    cached = _BIDI_DISCOVERY_CACHE.get(api_key)
    if cached and (now - cached[0]) < _BIDI_DISCOVERY_TTL_SEC and api_key in _KEY_STATE.get('gemini', {}):
        return list(cached[1])
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                headers={'x-goog-api-key': api_key},
            )
        if resp.status_code in (401, 403):
            _BIDI_DISCOVERY_CACHE.pop(api_key, None)
            body = _sanitize_provider_text(resp.text or '')[:180]
            raise AIConfigError(f"کلید گوگل نامعتبر یا غیرفعال است ({body})")
        if resp.status_code == 429:
            _BIDI_DISCOVERY_CACHE.pop(api_key, None)
            raise AIQuotaError("سهمیه کلید گوگل پر شده است (429).")
        if resp.status_code != 200:
            return []
        out = []
        for m in (resp.json() or {}).get('models', []):
            methods = m.get('supportedGenerationMethods') or []
            if 'bidiGenerateContent' in methods:
                name = (m.get('name') or '').replace('models/', '').strip()
                if name:
                    out.append(name)
        _BIDI_DISCOVERY_CACHE[api_key] = (now, list(out))
        return out
    except (AIConfigError, AIQuotaError):
        raise
    except Exception:
        return []


def _adapt_setup_for_model(setup_msg: dict, target_model: str, minimal: bool = False) -> dict:
    """تطبیق پیام setup برای مدل جایگزین یا حالت کمینه (بدون ابزار/فیلدهای حساس)."""
    import copy
    msg = copy.deepcopy(setup_msg or {'setup': {}})
    s = msg.setdefault('setup', {})
    mid = (target_model or DEFAULT_LIVE_MODEL).replace('models/', '').strip()
    ml = mid.lower()
    s['model'] = f"models/{mid}"
    gen = s.setdefault('generationConfig', {'responseModalities': ['AUDIO']})

    if 'translate' in ml:
        s.pop('systemInstruction', None)
        s.pop('tools', None)
        s.pop('realtimeInputConfig', None)
        s.pop('contextWindowCompression', None)
        gen.pop('thinkingConfig', None)
        gen.pop('speechConfig', None)
        return msg

    if 'extended-thinking' not in ml and '3.1-flash-live' not in ml:
        gen.pop('thinkingConfig', None)

    if '3.8-live' not in ml and 'tools' in s:
        for t in (s.get('tools') or []):
            for fd in (t.get('functionDeclarations') or []):
                fd.pop('behavior', None)

    if minimal:
        s.pop('tools', None)
        s.pop('realtimeInputConfig', None)
        s.pop('contextWindowCompression', None)
        gen.pop('thinkingConfig', None)
    return msg


async def probe_live_model(provider: str, api_key: str, model: str) -> dict:
    """⭐ م9 — تست واقعی اتصال WebSocket مدل Gemini Live (BidiGenerateContent).

    یک اتصال WebSocket واقعی به BidiGenerateContent باز می‌کند، پیام setup
    همان مدل را می‌فرستد و منتظر دریافت setupComplete می‌ماند."""
    import time as _t
    started = _t.monotonic()
    mid = (model or '').replace('models/', '').strip()
    if not mid.startswith('gemini'):
        return {'ok': False, 'ms': 0,
                'error': 'فقط مدل‌های Live گوگل (Gemini) پشتیبانی می‌شوند.',
                'mode': 'real_live_ws'}
    last_err = ''
    for base_ws in (LIVE_WS_URL_V1BETA, LIVE_WS_URL_V1ALPHA):
        for minimal in (False, True):
            try:
                import websockets
                ws_url = f"{base_ws}?key={api_key}"
                raw_setup = build_live_setup_message(mid, include_tools=False)
                setup_msg = _adapt_setup_for_model(raw_setup, mid, minimal=minimal)
                async with websockets.connect(ws_url, open_timeout=12, close_timeout=3) as ws:
                    await ws.send(json.dumps(setup_msg))
                    raw = await asyncio.wait_for(ws.recv(), timeout=12)
                ms = max(1, int((_t.monotonic() - started) * 1000))
                evs = parse_live_server_message(raw)
                if any(e.get('type') == 'ready' for e in evs):
                    return {'ok': True, 'ms': ms, 'error': '', 'mode': 'real_live_ws'}
                err_ev = next((e for e in evs if e.get('type') == 'error'), None)
                last_err = (err_ev or {}).get('message') or 'پاسخ setupComplete دریافت نشد'
            except Exception as e:
                last_err = _sanitize_provider_text(str(e))[:160] or type(e).__name__
                low = last_err.lower()
                if any(c in low for c in ('401', '403', 'api_key', 'unauthenticated', 'service account')):
                    ms = max(1, int((_t.monotonic() - started) * 1000))
                    return {'ok': False, 'ms': ms, 'error': last_err, 'mode': 'real_live_ws'}
    ms = max(1, int((_t.monotonic() - started) * 1000))
    return {'ok': False, 'ms': ms, 'error': last_err or 'عدم اتصال به WebSocket Live', 'mode': 'real_live_ws'}


async def connect_gemini_live_with_failover(
    model: str,
    setup_msg: dict,
    keys: list = None,
) -> tuple:
    """⭐ م9 — باز کردن اتصال WebSocket به Gemini Live (BidiGenerateContent)
    با فال‌بک خودکار کلیدهای گوگل و فال‌بک خودکار به مدل‌های Live فعال روی کلید.

    خروجی: (ws, initial_events, active_key). روی ws فیلد ws.live_model نام مدل متصل‌شده را دارد."""
    import websockets
    if not keys:
        cfg = await get_ai_config()
        keys = (cfg.get('vault_multi') or {}).get('gemini') or cfg.get('live_api_key_list') or []
    ordered = ordered_keys('gemini', keys or [])
    if not ordered:
        raise AIConfigError("کلید API گوگل (Gemini) برای تماس صوتی زنده تنظیم نشده است.")

    req_mid = (model or DEFAULT_LIVE_MODEL).replace('models/', '').strip() or DEFAULT_LIVE_MODEL
    last_err = None

    for idx, api_key in enumerate(ordered):
        _kp = api_key_problem(api_key)
        if _kp:
            record_key_failure('gemini', api_key, _kp, cooldown_sec=KEY_COOLDOWN_AUTH)
            last_err = AIConfigError(_kp)
            continue

        # بررسی سلامت کلید و کشف مدل‌های bidiGenerateContent فعال روی این کلید
        try:
            discovered_bidi = await _discover_bidi_models_for_key(api_key)
        except AIConfigError as e_auth:
            mark_key_failed('gemini', api_key, e_auth)
            last_err = e_auth
            continue
        except AIQuotaError as e_quota:
            mark_key_failed('gemini', api_key, e_quota)
            last_err = e_quota
            continue

        # ترتیب کاندیداهای مدل: اول مدل درخواستی، سپس مدل‌های کاتالوگ و مدل‌های bidi کشف‌شده روی کلید
        candidate_models = [req_mid]
        for fallback_m in (
            list(discovered_bidi)
            + [m[0] for m in LIVE_MODEL_CATALOG]
            + ['gemini-2.5-flash-native-audio-preview-12-2025', 'gemini-2.0-flash-live-001']
        ):
            fm = (fallback_m or '').replace('models/', '').strip()
            if fm and fm not in candidate_models:
                # اگر مدل درخواستی مترجم نبود، به مدل مترجمِ صِرف فال‌بک نکنیم
                if 'translate' in fm.lower() and 'translate' not in req_mid.lower():
                    continue
                candidate_models.append(fm)

        key_failed_auth_or_quota = False
        for cand_model in candidate_models:
            for base_ws in (LIVE_WS_URL_V1BETA, LIVE_WS_URL_V1ALPHA):
                for minimal_mode in (False, True):
                    ws = None
                    try:
                        ws_url = f"{base_ws}?key={api_key}"
                        adapted_setup = _adapt_setup_for_model(setup_msg, cand_model, minimal=minimal_mode)
                        ws = await websockets.connect(
                            ws_url,
                            open_timeout=15,
                            close_timeout=5,
                            max_size=16 * 1024 * 1024,
                            ping_interval=20,
                            ping_timeout=20,
                        )
                        await ws.send(json.dumps(adapted_setup))
                        raw = await asyncio.wait_for(ws.recv(), timeout=15)
                        evs = parse_live_server_message(raw)
                        err_ev = next((e for e in evs if e.get('type') == 'error'), None)
                        if err_ev:
                            await ws.close()
                            raise AIError(err_ev.get('message') or 'خطای راه‌اندازی نشست Live')
                        mark_key_ok('gemini', api_key)
                        try:
                            setattr(ws, 'live_model', cand_model)
                        except Exception:
                            pass
                        return ws, evs, api_key
                    except Exception as e:
                        if ws is not None:
                            try:
                                await ws.close()
                            except Exception:
                                pass
                        err_txt = _sanitize_provider_text(str(e))[:220] or type(e).__name__
                        low = err_txt.lower()
                        if any(c in low for c in ('401', '403', 'api_key', 'unauthenticated', 'permission', 'service account')):
                            last_err = AIConfigError(f"کلید گوگل نامعتبر یا غیرفعال است ({err_txt})")
                            mark_key_failed('gemini', api_key, last_err)
                            key_failed_auth_or_quota = True
                            break
                        if '429' in low or 'quota' in low or 'resource_exhausted' in low:
                            last_err = AIQuotaError(f"سهمیه‌ی کلید گوگل برای Live پر شده ({err_txt})")
                            mark_key_failed('gemini', api_key, last_err)
                            key_failed_auth_or_quota = True
                            break
                        last_err = AIError(f"خطا در اتصال به Gemini Live ({cand_model}): {err_txt}")
                        # اگر مدل اصلاً پیدا نشد (not found / not supported)، نیازی به تکرار minimal_mode همان نسخه نیست
                        if 'not found' in low or 'not supported for bidigeneratecontent' in low:
                            break
                if key_failed_auth_or_quota:
                    break
            if key_failed_auth_or_quota:
                break

    if len(ordered) > 1 and last_err is not None:
        raise type(last_err)(
            f"همه‌ی {len(ordered)} کلید گوگل برای اتصال Live امتحان شد — آخرین خطا: {last_err}"
        )
    raise (last_err or AIError("اتصال به سرویس صوتی زنده‌ی گوگل برقرار نشد."))


async def execute_live_tool_calls(calls: list, uid: int) -> dict:
    """⭐ م9 — اجرای توابع هوشیار حین تماس صوتی زنده و ساخت پیام BidiGenerateContentToolResponse."""
    func_responses = []
    for fc in (calls or []):
        if not isinstance(fc, dict):
            continue
        fn_name = (fc.get('name') or '').strip()
        fn_id = fc.get('id') or fn_name
        fn_args = fc.get('args') if isinstance(fc.get('args'), dict) else {}
        if not fn_name:
            continue
        try:
            res_text = await _execute_ai_function(fn_name, fn_args, int(uid or 0))
            resp_payload = {'result': res_text}
        except Exception as e:
            logger.exception("خطا در اجرای ابزار Live (%s)", fn_name)
            resp_payload = {'error': _sanitize_provider_text(str(e))[:160]}
        func_responses.append({
            'id': fn_id,
            'name': fn_name,
            'response': resp_payload,
        })
    return {
        'toolResponse': {
            'functionResponses': func_responses,
        }
    }


async def probe_models(provider: str, models: list = None,
                       kind: str = 'chat') -> dict:
    """⭐ م8 / م9 — تستِ همزمانِ مدل‌ها (سقفِ ۳۰ تا) و ذخیره‌ی نتیجه در تنظیمات.

    kind='chat' → تستِ توکنِ واقعی؛ kind='image' → تستِ واقعیِ ساخت تصویر گوگل؛
    kind='live' → تستِ واقعیِ هندشیک WebSocket روی BidiGenerateContent."""
    provider = 'gemini' if kind in ('image', 'live') else ((provider or 'gemini').strip() or 'gemini')
    cfg = await get_ai_config()
    keys = ordered_keys(provider,
                        (cfg.get('vault_multi') or {}).get(provider) or [])
    if not keys:
        return {'provider': provider, 'results': {},
                'error': 'کلید API این ارائه‌دهنده ثبت نشده است.'}
    key = keys[0]
    if models is None:
        if kind == 'image':
            models = [m.get('id') for m in
                      (await list_image_models(provider)).get('models', [])]
        elif kind == 'live':
            models = [m.get('id') for m in
                      (await list_live_models()).get('models', [])]
        else:
            models = [m.get('id') for m in
                      (await list_provider_models(provider)).get('models', [])]
    models = [m for m in (models or []) if m][:PROBE_MAX_MODELS]
    sem = asyncio.Semaphore(2 if kind in ('image', 'live') else PROBE_CONCURRENCY)

    async def _one(mid: str) -> tuple:
        async with sem:
            if kind == 'image':
                # امتحان با کلید اول؛ اگر خطای کلید/401/403 داد و کلید بعدی هست، چرخش
                r = await probe_image_model(provider, key, mid)
                if not r.get('ok') and len(keys) > 1 and any(
                        c in (r.get('error') or '').lower()
                        for c in ('401', '403', 'api_key_invalid', 'service account')):
                    for k_alt in keys[1:]:
                        r_alt = await probe_image_model(provider, k_alt, mid)
                        if r_alt.get('ok'):
                            r = r_alt
                            break
            elif kind == 'live':
                r = await probe_live_model(provider, key, mid)
                if not r.get('ok') and len(keys) > 1 and any(
                        c in (r.get('error') or '').lower()
                        for c in ('401', '403', 'api_key_invalid', 'service account', '429', 'http')):
                    for k_alt in keys[1:]:
                        r_alt = await probe_live_model(provider, k_alt, mid)
                        if r_alt.get('ok'):
                            r = r_alt
                            break
            else:
                r = await probe_chat_model(provider, key, mid)
            return mid, r

    pairs = await asyncio.gather(*[_one(m) for m in models])
    now_iso = utc_now_iso()
    results = {mid: {**r, 'tested_at': now_iso} for mid, r in pairs}
    health = {mid: {**r, 'tested_at': now_iso} for mid, r in pairs}
    try:
        existing = await get_models_health(provider)
        merged_models = {
            k: v for k, v in ((existing or {}).get('models') or {}).items()
            if isinstance(v, dict) and v.get('mode') != 'catalog'
        }
        merged_models.update(health)
        await db.set_setting(f'ai_models_health_{provider}', {
            'kind': kind, 'tested_at': now_iso, 'models': merged_models})
    except Exception:
        logger.exception("ذخیره‌ی سلامتِ مدل‌ها ناموفق بود")
    ok_count = sum(1 for r in results.values() if r.get('ok'))
    return {'provider': provider, 'kind': kind, 'count': len(results),
            'ok_count': ok_count, 'results': results, 'tested_at': now_iso}


async def get_models_health(provider: str) -> dict:
    """آخرین نتیجه‌ی ذخیره‌شده‌ی سلامت‌سنجی (اگر باشد)."""
    try:
        data = await db.get_setting(f"ai_models_health_{(provider or 'gemini').strip()}", None)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def merge_models_with_health(provider: str, models: list,
                             health: dict) -> list:
    """⭐ م8 — مرتب‌سازیِ نهایی: اول مدل‌های زنده، بعد رایگان‌تر، بعد سریع‌تر.

    مدلِ زنده = در آخرین تستِ توکن، پاسخِ ۲۰۰ گرفته‌ایم. مدلِ تست‌نشده
    وسط می‌ماند (نه جریمه می‌شود نه پاداش)."""
    hmodels = (health or {}).get('models') or {}
    out = []
    for m in (models or []):
        mid = m.get('id') or m.get('model_id') or ''
        h = hmodels.get(mid) or {}
        # ⭐ م8.4 — حذف نتایج جعلی 0ms / کاتالوگیِ قبلی که بدون تستِ واقعیِ
        # تولید تصویر ثبت شده بودند.
        if h.get('mode') == 'catalog' or (
                _looks_like_image_model(mid)
                and 'tested_at' in h
                and h.get('mode') != 'real_image_gen'):
            h = {}
        item = dict(m)
        item['health_ok'] = h.get('ok') if h else None
        item['health_ms'] = h.get('ms')
        item['health_error'] = h.get('error') or ''
        item['free'] = bool(m.get('free')) or model_is_free(provider, mid)
        item['free_rank'] = model_free_rank(provider, mid)
        out.append(item)

    def sort_key(item):
        ok = item['health_ok']
        # زنده=0 · تست‌نشده=1 · مرده=2
        alive_rank = 0 if ok is True else (2 if ok is False else 1)
        return (alive_rank, -item['free_rank'],
                item['health_ms'] if item['health_ms'] else 10**9,
                item['id'])
    out.sort(key=sort_key)
    return out


async def _transcode_ogg_opus_to_wav(ogg_bytes: bytes) -> bytes | None:
    """
    ⚠️ فیکسِ باگِ «ارور ۴۰۰ روی پیامِ صوتی»: پیام‌های صوتیِ تلگرام با
    فرمتِ OGG (کدکِ Opus) ضبط می‌شن، ولی طبقِ مستنداتِ رسمیِ گوگل،
    Gemini از «OGG Vorbis» پشتیبانی می‌کنه، نه Opus — همین ناهماهنگی
    باعثِ ارور ۴۰۰ می‌شد. اینجا با ffmpeg (اگه روی سرور نصب باشه) به
    WAV (که همه‌جا پشتیبانی می‌شه) تبدیلش می‌کنیم. اگه ffmpeg نصب نبود،
    None برمی‌گردونه و فراخوان باید به کاربر پیامِ روشن بده.
    """
    if not _FFMPEG_PATH:
        return None
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            _FFMPEG_PATH, '-y', '-i', 'pipe:0', '-ar', '16000', '-ac', '1', '-f', 'wav', 'pipe:1',
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        wav_bytes, stderr = await asyncio.wait_for(proc.communicate(input=ogg_bytes), timeout=30)
        if proc.returncode != 0 or not wav_bytes:
            logger.warning("ffmpeg transcode شکست خورد: %s", (stderr or b'')[:300])
            return None
        return wav_bytes
    except Exception:
        logger.exception("تبدیلِ صدا با ffmpeg ناموفق بود")
        return None


async def handle_ai_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    ⚠️ قابلیتِ جدید: قبلاً این تابع (به اسمِ handle_ai_photo) فقط عکس
    قبول می‌کرد. الان از همین ساختارِ inline_data که Gemini برای هر نوع
    رسانه‌ای پشتیبانی می‌کنه، برای PDF (جزوه/برگه‌ی اسکن‌شده) و پیامِ
    صوتی/فایلِ صوتی (سوالِ گفتاری) هم استفاده می‌کنیم — بدون تغییری در
    مدلِ هزینه (این‌ها هم جزوِ همون Free Tier هستن).
    """
    uid = update.effective_user.id
    # 🌊 W7 — گیت فیچر (پیش‌فرض FREE ⇒ بدون تغییر رفتار امروز)
    from subscription import feature_allowed, show_paywall
    if not await feature_allowed(uid, "ai_chat"):
        context.user_data.pop('mode', None)
        await show_paywall(update.message, uid, feature="ai_chat")
        return

    cfg = await get_ai_config()
    if not cfg['enabled']:
        context.user_data.pop('mode', None)
        await update.message.reply_text(cfg.get('disabled_message') or DEFAULT_DISABLED_MSG)
        return

    if await db.ai_is_banned(uid):
        await update.message.reply_text(AI_BANNED_MSG)
        return

    kind = None
    if update.message.photo:
        tg_file = await update.message.photo[-1].get_file()
        mime, kind = 'image/jpeg', 'image'
    elif update.message.voice:
        tg_file = await update.message.voice.get_file()
        mime, kind = (update.message.voice.mime_type or 'audio/ogg'), 'audio'
    elif update.message.audio:
        tg_file = await update.message.audio.get_file()
        mime, kind = (update.message.audio.mime_type or 'audio/mpeg'), 'audio'
    elif update.message.document:
        doc_mime = update.message.document.mime_type or ''
        if doc_mime.startswith('image/'):
            tg_file = await update.message.document.get_file()
            mime, kind = doc_mime, 'image'
        elif doc_mime == 'application/pdf':
            tg_file = await update.message.document.get_file()
            mime, kind = doc_mime, 'pdf'
        else:
            return  # نوع فایل پشتیبانی‌نشده — نادیده گرفته می‌شود
    else:
        return

    # PDF و صدا فقط از طریقِ Gemini کار می‌کنن (OpenRouter برای این
    # نوع‌ها راه‌اندازی نشده)؛ اگه ادمین ارائه‌دهنده رو روی OpenRouter
    # گذاشته، مودبانه بگو فقط عکس/متن پشتیبانی می‌شه.
    if kind != 'image' and cfg['provider'] != 'gemini':
        await update.message.reply_text(
            "⚠️ فعلاً فقط عکس یا متن رو می‌تونم پردازش کنم "
            "(فایلِ PDF/صوتی فقط با ارائه‌دهنده‌ی Gemini کار می‌کنه)."
        )
        return

    if getattr(tg_file, 'file_size', None) and tg_file.file_size > MAX_MEDIA_BYTES:
        await update.message.reply_text(
            f"⚠️ حجمِ فایل بیشتر از {MAX_MEDIA_BYTES // (1024*1024)} مگابایته — "
            "یه نسخه‌ی کوچیک‌تر بفرست."
        )
        return

    caption = (update.message.caption or '').strip() or None
    if caption and len(caption) > MAX_INPUT_CHARS:
        await update.message.reply_text(
            f"✍️ توضیحِ فایل یه‌کم طولانیه (بیشتر از {MAX_INPUT_CHARS} کاراکتر). "
            "لطفاً خلاصه‌ترش کن."
        )
        return

    # قفلِ مشترکِ بین‌پراسسی از همین‌جا گرفته می‌شود تا دانلودِ فایل و
    # transcode هم زیر همان ادعا باشند (این‌ها گران‌اند و نباید دوباره
    # به‌ازای یک درخواستِ هم‌زمانِ مینی‌اپ تکرار شوند).
    if not await ai_claim_inflight(uid):
        await update.message.reply_text("⏳ صبر کن جواب سوال قبلی‌ت آماده بشه، بعد این یکی رو بفرست 🙂")
        return

    try:
        try:
            media_bytes = bytes(await tg_file.download_as_bytearray())
        except Exception:
            logger.exception("دانلود فایل هوشیار ناموفق بود")
            await update.message.reply_text("⚠️ دانلودِ فایل ناموفق بود — دوباره امتحان کن.")
            return

        # ⚠️ فیکسِ ارورِ ۴۰۰: پیام‌های صوتیِ تلگرام OGG/Opus هستن، ولی Gemini
        # فقط OGG Vorbis رو قبول می‌کنه. قبل از فرستادن (و قبل از مصرفِ
        # سهمیه‌ی روزانه) تبدیلش می‌کنیم — اگه تبدیل شکست بخوره، کاربر
        # سهمیه‌شو الکی از دست نده.
        if kind == 'audio' and 'ogg' in mime.lower():
            wav_bytes = await _transcode_ogg_opus_to_wav(media_bytes)
            if wav_bytes:
                media_bytes, mime = wav_bytes, 'audio/wav'
            else:
                await update.message.reply_text(
                    "⚠️ فعلاً امکانِ پردازشِ این پیامِ صوتی نیست (مشکلِ سازگاریِ فرمت). "
                    "لطفاً سوالتو تایپ کن یا عکس/PDF بفرست — یا به ادمین اطلاع بده."
                )
                return

        # ⚠️ قابلیتِ جدید: «سندِ مرجعِ فعال» — به‌جای فرستادنِ PDF به‌صورتِ
        # inline (که فقط برای همین یه سوال کار می‌کنه)، آپلودش می‌کنیم روی
        # Gemini Files API (رایگان، ۴۸ ساعت نگه‌داری) و فقط یه اشاره‌گرِ
        # کوچیک ذخیره می‌کنیم. این‌جوری سوالاتِ بعدیِ همین دانشجو هم خودکار
        # به همین سند دسترسی دارن، بدون اینکه دوباره بفرستتش.
        display_name = None
        if update.message.document:
            display_name = update.message.document.file_name
        _skip_doc_this_time = False
        if kind == 'pdf':
            try:
                # ⭐ م7 — آپلود + فعال‌سازی با فال‌بکِ کلید بعدی
                async def _upload_pdf_once(api_key: str) -> dict:
                    fi = await _gemini_upload_file(api_key, media_bytes, mime,
                                                   display_name or 'جزوه.pdf')
                    # 🔴 فایل باید روی سرور گوگل ACTIVE شود وگرنه ارجاعِ بعدی
                    # همان 400 معروف را می‌دهد.
                    return await _gemini_wait_file_active(api_key, fi)
                file_info = await run_with_key_failover(
                    'gemini', cfg.get('api_key_list') or [cfg['api_key']],
                    _upload_pdf_once, label='pdf-upload')
                _state = (file_info.get('state') or 'ACTIVE').upper()
                if _state == 'FAILED':
                    await update.message.reply_text(
                        "⚠️ سرور گوگل نتوانست این PDF را پردازش کند — احتمالاً اسکن/عکس است و "
                        "متنِ قابل‌انتخاب ندارد. لطفاً نسخه‌ی متنی جزوه را بفرست.")
                    return
                await db.ai_set_doc(uid, file_info['uri'], file_info.get('mimeType', mime), display_name or 'جزوه')
                media_bytes = None   # دیگه لازم نیست inline بفرستیمش؛ از طریقِ doc reference میره
                if _state != 'ACTIVE':
                    # پردازشِ گوگل بیش از حد طول کشید؛ سند ذخیره شد ولی
                    # «این» سوال بدونِ سند پرسیده می‌شود تا 400 نگیریم.
                    _skip_doc_this_time = True
                    await update.message.reply_text(
                        "⏳ جزوه‌ات روی سرور گوگل در حال پردازش است؛ این سوالت را بدونِ جزوه "
                        "جواب می‌دهم — چند لحظه بعد جزوه خودکار به سوالاتت وصل می‌شود.")
            except Exception:
                logger.exception("آپلودِ PDF به Gemini Files API ناموفق بود")
                await update.message.reply_text("⚠️ آپلودِ فایل ناموفق بود — دوباره امتحان کن.")
                return

        allowed, used, limit = await check_and_consume_quota(uid)
        if not allowed:
            await update.message.reply_text(
                f"⛔️ سقف روزانه‌ی سوال از هوشیار تموم شده ({used}/{limit}).\n"
                "فردا دوباره امتحان کن."
            )
            return

        labels = {
            'image': "[یک سوال به‌صورت عکس فرستاد]",
            'pdf':   f"[یک فایل PDF فرستاد: {display_name or 'جزوه'} — به‌عنوانِ سندِ مرجع ذخیره شد]",
            'audio': "[یک پیام صوتی فرستاد]",
        }
        question_label = caption or labels.get(kind, "[یک فایل فرستاد]")

        history = await _get_history(uid)
        await _answer_with_live_edit(
            update, context,
            ask_ai_stream(text=caption, image_bytes=media_bytes, image_mime=mime,
                          history=history, uid=uid, skip_doc=_skip_doc_this_time),
            _footer(limit, used), uid, question_label,
            voice_input=(kind == 'audio'),   # ⭐ م8 — ویس فرستادی؟ جوابِ صوتی بگیر
        )
    finally:
        await ai_release_inflight(uid)


# ══════════════════════════════════════════════════
#  دکمه‌های زیرِ جواب («🆕 گفتگوی جدید» / «🚩 گزارش این جواب») —
#  callback_data با پیشوند aiu: (برای هر کاربری، برخلاف ai: که مخصوص
#  پنل ادمینه).
# ══════════════════════════════════════════════════

async def ai_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    uid    = update.effective_user.id
    parts  = query.data.split(':')
    action = parts[1] if len(parts) > 1 else ''

    if action == 'newchat':
        await _clear_memory(uid)
        await db.ai_clear_doc(uid)
        await query.answer("✅ حافظه‌ی مکالمه (و سندِ مرجعِ فعال، اگه بود) پاک شد؛ از اول شروع کن 🙂", show_alert=True)
        return

    if action == 'imgstart':
        await query.answer()
        cfg = await get_ai_config()
        if not cfg['enabled'] or not cfg.get('image_enabled'):
            await query.message.reply_text(
                "🎨 بخشِ ساخت تصویر فعلاً توسط مدیریت غیرفعال است.")
            return
        # universal image — any provider allowed, just check image_enabled
        # (key check is done at generation time, so button stays enabled for all providers)
        context.user_data['mode'] = 'ai_image_prompt'
        context.user_data['last_question'] = ''
        img_limit = cfg['image_daily_limit']
        if uid == ADMIN_ID or img_limit <= 0:
            q_line = "🔓 امروز محدودیتی نداری."
        else:
            used = await db.ai_image_used_today(uid, today_tehran().isoformat())
            q_line = f"📊 {used} از {img_limit} تصویرِ امروزت استفاده شده."
        await query.message.reply_text(
            "🎨 <b>حالت ساخت تصویر</b>\n\n"
            "توضیح تصویری که می‌خوای رو <b>همینجا تایپ کن</b> — هرچی "
            "جزئیات بیشتر بدی، نتیجه بهتر می‌شه:\n\n"
            "مثلاً: «یک کتابخانه‌ی چوبیِ گرم با نور عصرگاهی، سبک "
            "واقع‌گرایانه»\n\n"
            "برای بازگشت به حالت سوال، فقط سوالتو بفرست یا از منو «پرسش از "
            "هوشیار» رو دوباره بزن.\n"
            "برای لغو: /cancel",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "💬 بازگشت به پرسش", callback_data='aiu:imgoff')],
            ]),
        )
        return

    if action == 'imgoff':
        await query.answer("💬 برگشتیم به حالت پرسش.", show_alert=False)
        context.user_data['mode'] = 'ai_query'
        await query.message.reply_text(
            "💬 هر سوالی داری بفرست؛ برای ساخت تصویر دوباره از منو یا "
            "دکمه‌ی 🎨 استفاده کن.")
        return

    if action == 'live':
        await query.answer()
        await show_ai_live_card(update, context)
        return

    if action == 'vc_join':
        chat = update.effective_chat
        if not chat or getattr(chat, 'type', 'private') == 'private':
            await query.answer("این دکمه مخصوص گروه‌های تلگرام است.", show_alert=True)
            return
        await query.answer("⏳ در حال ورود هوشیار به ویس‌چت گروه…", show_alert=False)
        try:
            from tg_group_voice_call import join_group_voice_chat
            info = await join_group_voice_chat(
                chat_id=chat.id,
                bot=context.bot,
                title=getattr(chat, 'title', '') or str(chat.id),
            )
            asst = info.get('assistant') or {}
            asst_lbl = f"@{asst['username']}" if asst.get('username') else (asst.get('first_name') or 'دستیار هوشیار')
            await query.message.reply_text(
                f"🎙 <b>هوشیار وارد ویس‌چت گروه شد!</b>\n"
                f"👤 اکانت دستیار: <b>{_esc(asst_lbl)}</b>\n"
                f"🤖 مدل: <code>{_esc(info.get('model') or '')}</code> · صدا: <code>{_esc(info.get('voice') or '')}</code>\n\n"
                "الان می‌تونید داخل ویس‌چت گروه زنده با هوشیار صحبت کنید!",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📴 خروج هوشیار از ویس‌چت", callback_data="aiu:vc_leave"),
                ]]),
            )
        except Exception as e:
            await query.message.reply_text(
                f"⚠️ <b>خطا در ورود هوشیار به ویس‌چت گروه:</b>\n{_esc(str(e))}",
                parse_mode='HTML',
            )
        return

    if action == 'vc_leave':
        chat = update.effective_chat
        if not chat:
            await query.answer()
            return
        try:
            from tg_group_voice_call import leave_group_voice_chat
            await leave_group_voice_chat(chat.id)
            await query.answer("📴 هوشیار از ویس‌چت گروه خارج شد.", show_alert=False)
            await query.message.reply_text("📴 هوشیار از ویس‌چت گروه خارج شد.")
        except Exception as e:
            await query.answer(f"خطا: {str(e)[:120]}", show_alert=True)
        return

    if action == 'fu':
        fu_type = parts[2] if len(parts) > 2 else ''
        prompts = {
            'example': 'یه مثالِ ملموس و کاربردی برای همون چیزی که الان توضیح دادی بزن.',
            'summary': 'همون جوابِ قبلی رو خیلی خلاصه‌تر (در حد ۲ تا ۳ خط) بگو.',
            'similar': 'یه سوالِ چهارگزینه‌ایِ مشابهِ همون موضوع بساز و ازم بپرس.',
        }
        prompt = prompts.get(fu_type)
        if not prompt:
            await query.answer()
            return

        cfg = await get_ai_config()
        if not cfg['enabled']:
            await query.answer(cfg.get('disabled_message') or DEFAULT_DISABLED_MSG, show_alert=True)
            return
        if await db.ai_is_banned(uid):
            await query.answer(AI_BANNED_MSG, show_alert=True)
            return
        if not await ai_claim_inflight(uid):
            await query.answer("⏳ صبر کن جوابِ قبلی آماده بشه.", show_alert=True)
            return
        try:
            allowed, used, limit = await check_and_consume_quota(uid)
            if not allowed:
                await query.answer(f"⛔️ سقفِ روزانه تموم شده ({used}/{limit}).", show_alert=True)
                return

            await query.answer()
            history = await _get_history(uid)
            await _answer_with_live_edit(
                update, context, ask_ai_stream(text=prompt, history=history, uid=uid),
                _footer(limit, used), uid, prompt,
            )
        finally:
            await ai_release_inflight(uid)
        return

    if action == 'report':
        key  = f"{parts[2]}:{parts[3]}" if len(parts) > 3 else ''
        info = _report_cache.get(key)
        if not info:
            await query.answer("⚠️ این پیام قدیمیه و دیگه قابل گزارش نیست.", show_alert=True)
            return
        # ⚠️ فیکس: قبلاً گزارش‌ها فقط توی RAM بودن و با ری‌استارتِ ربات از
        # بین می‌رفتن. حالا در کنار پیامِ فوری به ادمین، توی دیتابیس هم
        # ثبت می‌شه تا از پنل ادمین («📋 گزارش‌های اخیر») همیشه قابل مرور باشه.
        try:
            await db.ai_log_report(info['uid'], info['name'], info['question'], info['answer'])
        except Exception:
            logger.exception("ثبت گزارش هوشیار در دیتابیس ناموفق بود")
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    "🚩 <b>گزارش پاسخ نامناسب هوشیار</b>\n\n"
                    f"👤 کاربر: {_esc(str(info['name']))} (<code>{info['uid']}</code>)\n\n"
                    f"❓ سوال:\n{_esc(info['question'][:800])}\n\n"
                    f"🤖 پاسخ:\n{_esc(info['answer'][:1500])}",
                    parse_mode='HTML',
                )
            except Exception:
                logger.exception("گزارش پاسخ هوشیار به ادمین ارسال نشد")
        await query.answer("✅ گزارش شد، ممنون از دقتت 🙏", show_alert=True)
        return

    await query.answer()

# ══════════════════════════════════════════════════
#  📅 اسکن برنامه با هوشیار — الگوی هفتگی و امتحان
#  ورودی: عکس جدول (vision) → JSON ساختاریافته
#  هیچ‌چیز هاردکد نیست: از همین vault/provider فعلی استفاده می‌کند
# ══════════════════════════════════════════════════

# توجه: برای schedule_scan provider باید vision True باشد؛ در غیر این صورت fallback به Gemini/OpenRouter vision-free model

WEEKLY_SCHEDULE_SCHEMA = {
    'type': 'object',
    'properties': {
        'slots': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'weekday': {'type': 'integer', 'description': '0=شنبه ... 6=جمعه'},
                    'time': {'type': 'string', 'description': 'HH:MM شروع مثل 08:00'},
                    'end_time': {'type': 'string', 'description': 'HH:MM پایان مثل 10:00 — برای بازه 8-10'},
                    'lesson': {'type': 'string', 'description': 'نام درس کامل فارسی'},
                    'teacher': {'type': 'string', 'description': 'نام استاد اگر دیده شد'},
                    'location': {'type': 'string', 'description': 'مکان/کلاس'},
                    'group': {'type': 'string', 'description': '1 یا 2 یا هر دو'},
                    'flex_type': {'type': 'string', 'description': 'fixed یا flexible'},
                    'notes': {'type': 'string', 'description': 'توضیح کوتاه اختیاری'},
                },
                'required': ['weekday', 'time', 'lesson'],
            },
        }
    },
    'required': ['slots'],
}

EXAM_SCHEDULE_SCHEMA = {
    'type': 'object',
    'properties': {
        'exams': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'date': {'type': 'string', 'description': 'تاریخ شمسی YYYY/MM/DD — دقیقاً همان که در عکس است'},
                    'time': {'type': 'string', 'description': 'ساعت HH:MM یا بازه مثل 10:00'},
                    'lesson': {'type': 'string', 'description': 'نام درس'},
                    'location': {'type': 'string'},
                    'group': {'type': 'string', 'description': 'گروه اگر مشخص است'},
                },
                'required': ['date', 'lesson'],
            }
        }
    },
    'required': ['exams'],
}

def _pick_vision_config(cfg: dict) -> tuple:
    """Choose vision-capable provider/model/key from current config, with fallback."""
    vault = cfg.get('vault') or {}
    provider = cfg.get('provider') or 'gemini'
    model = cfg.get('model') or ''
    key = cfg.get('api_key') or ''
    meta = PROVIDERS.get(provider) or {}
    if meta.get('vision') and key and not key.strip() == '':
        return provider, model, key
    # fallback: try gemini vault
    if vault.get('gemini') and PROVIDERS['gemini']['vision']:
        return 'gemini', DEFAULT_MODELS['gemini'], vault['gemini']
    # fallback: any vision provider with key
    for pid in ('openrouter', 'nvidia', 'together', 'huggingface'):
        if PROVIDERS.get(pid, {}).get('vision') and vault.get(pid):
            m = DEFAULT_MODELS.get(pid) or MODEL_CATALOG.get(pid, [(None, '', True)])[0][0]
            # for openrouter use vision model
            if pid == 'openrouter':
                m = 'qwen/qwen2.5-vl-32b-instruct:free'
            return pid, m, vault[pid]
    # last resort: current even if non-vision (will error clearly)
    return provider, model, key

WEEKLY_SYSTEM = (
    "تو یک دستیار استخراج برنامه کلاسی دانشگاه پزشکی هستی. از روی عکس جدول هفتگی (شنبه تا جمعه، ستون‌ها روز، سطرها ساعت 8-10/10-12/13-15/15-17/17-19) تمام درس‌ها را استخراج کن.\n"
    "قواعد:\n"
    "• weekday: شنبه=0، یکشنبه=1، دوشنبه=2، سه‌شنبه=3، چهارشنبه=4، پنج‌شنبه=5، جمعه=6\n"
    "• time/end_time: بازه کامل را استخراج کن — ابتدا و انتها هر دو HH:MM (مثلاً بازه 8-10 → time=08:00 و end_time=10:00، 10-12→10:00/12:00، 13-15→13:00/15:00، 15-17→15:00/17:00، 17-19→17:00/19:00). هر slot باید نمایانگر یک کلاس ۲ساعته واحد باشد، نه دو slot مجزا.\n"
    "• اگر یک خانه دو درس موازی دارد (مثلاً 'آیین زندگی (دخترا) / عملی (پسرا)' یا 'آز بیوشیمی / بیوشیمی') هر دو را به‌صورت دو slot جداگانه با همان weekday/time/end_time تولید کن.\n"
    "• group: اگر جدول برای گروه 1 یا 2 جداست همان را بگذار؛ اگر ستون 'هر دو' یا نامشخص است 'هر دو'.\n"
    "• flex_type: درس‌های عملی/آز/آزمایشگاه → flexible، بقیه fixed.\n"
    "• فقط JSON مطابق schema برگردان، بدون توضیح اضافه."
)

EXAM_SYSTEM = (
    "تو یک دستیار استخراج برنامه امتحانی هستی. از روی عکس جدول امتحانات، تمام ردیف‌ها را استخراج کن.\n"
    "• date: تاریخ شمسی دقیقاً همان که در عکس دیده می‌شود به شکل YYYY/MM/DD (اعداد انگلیسی، مثل 1405/10/26). اگر تاریخ میلادی دیدی همان را حفظ کن.\n"
    "• time: ساعت شروع امتحان به HH:MM (مثلاً '10-12'→10:00، '08:00'→08:00). اگر بازه بود ابتدای بازه.\n"
    "• lesson: نام کامل درس فارسی.\n"
    "• فقط JSON مطابق schema برگردان."
)

async def _vision_json_gemini(api_key: str, model: str, system_prompt: str, user_prompt: str, image_bytes: bytes, image_mime: str, schema: dict) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': api_key}
    payload = {
        'system_instruction': {'parts': [{'text': system_prompt}]},
        'contents': [{'role': 'user', 'parts': [
            {'inline_data': {'mime_type': image_mime or 'image/jpeg', 'data': base64.b64encode(image_bytes).decode('utf-8')}},
            {'text': user_prompt},
        ]}],
        'generationConfig': _no_thinking({
            'responseMimeType': 'application/json',
            'responseSchema': schema,
            'maxOutputTokens': 4096,
        }, model),
    }
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(url, headers=headers, json=payload)
    if resp.status_code != 200:
        _raise_gemini_status_error(
            resp.status_code,
            _provider_error_detail(resp.text))
    data = resp.json()
    raw = _extract_gemini_text(data, "برنامه")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # fallback: extract first {...}
        m = re.search(r'\{.*\}', raw, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise AIConfigError("هوشیار خروجی قابل فهم برنگرداند — دوباره با عکس واضح‌تر امتحان کن.")

async def _vision_json_openai(api_key: str, model: str, system_prompt: str, user_prompt: str, image_bytes: bytes, image_mime: str, provider: str) -> dict:
    meta = PROVIDERS.get(provider) or {}
    base = meta.get('url') or PROVIDERS['openrouter']['url']
    url = f"{base}/chat/completions"
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    if provider == 'openrouter':
        headers['HTTP-Referer'] = 'https://humsyar.local'
        headers['X-Title'] = 'Humsyar'
    b64 = base64.b64encode(image_bytes).decode('utf-8')
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': [
            {'type': 'text', 'text': user_prompt},
            {'type': 'image_url', 'image_url': {'url': f'data:{image_mime or "image/jpeg"};base64,{b64}'}},
        ]},
    ]
    payload = {
        'model': model,
        'messages': messages,
        'temperature': 0.1,
        'max_tokens': 4096,
    }
    # ask for JSON
    if provider in ('openrouter', 'together'):
        payload['response_format'] = {'type': 'json_object'}
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(url, headers=headers, json=payload)
    if resp.status_code == 429:
        raise AIQuotaError("سقف API پر شد — کمی بعد دوباره امتحان کن.")
    if resp.status_code >= 400:
        raise AIConfigError(f"خطای سرویس هوشیار ({resp.status_code}) — تنظیمات را بررسی کن.")
    data = resp.json()
    try:
        txt = data['choices'][0]['message']['content']
    except Exception:
        raise AIConfigError("پاسخ هوشیار خوانده نشد.")
    txt = txt.strip()
    # strip markdown fences
    if txt.startswith('```'):
        txt = re.sub(r'^```(?:json)?\s*', '', txt)
        txt = re.sub(r'\s*```$', '', txt)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', txt, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise AIConfigError("هوشیار JSON معتبر برنگرداند.")

async def scan_schedule_image(image_bytes: bytes, image_mime: str = 'image/jpeg', kind: str = 'weekly', group_hint: str = None, extra_note: str = None) -> dict:
    """Single entry for image scan — kind: weekly|exam. Returns parsed JSON."""
    if not image_bytes or len(image_bytes) < 100:
        raise AIError("عکس نامعتبر یا خیلی کوچک است.")
    if len(image_bytes) > 12 * 1024 * 1024:
        raise AIError("حجم عکس بیش از حد زیاد است — نسخه کم‌حجم‌تر بفرست.")
    cfg = await get_ai_config()
    if not cfg.get('enabled'):
        raise AIConfigError("بخش هوشیار غیرفعال است.")
    provider, model, key = _pick_vision_config(cfg)
    if not key:
        raise AIConfigError("کلید API vision تنظیم نشده — از پنل هوشیار یک کلید Gemini/OpenRouter وارد کن.")
    if kind == 'exam':
        system = EXAM_SYSTEM
        schema = EXAM_SCHEDULE_SCHEMA
        prompt = "این عکس جدول امتحانات است. تمام ردیف‌ها را استخراج کن و فقط JSON برگردان."
        if extra_note:
            prompt += f"\nنکته: {extra_note}"
    else:
        system = WEEKLY_SYSTEM
        schema = WEEKLY_SCHEDULE_SCHEMA
        prompt = "این عکس جدول برنامه هفتگی کلاسی است. تمام خانه‌های پر را استخراج کن و فقط JSON برگردان."
        if group_hint and group_hint.strip() not in ('', 'هر دو'):
            prompt += f"\nاین جدول مربوط به گروه {group_hint} است؛ اگر گروه در عکس مشخص نبود همین را بگذار."
        if extra_note:
            prompt += f"\nنکته: {extra_note}"
    # choose path
    if provider == 'gemini':
        return await _vision_json_gemini(key, model, system, prompt, image_bytes, image_mime, schema)
    else:
        # openai-compatible vision
        return await _vision_json_openai(key, model, system, prompt, image_bytes, image_mime, provider)

async def scan_weekly_schedule_image(image_bytes: bytes, image_mime: str = 'image/jpeg', group_hint: str = None) -> dict:
    data = await scan_schedule_image(image_bytes, image_mime, kind='weekly', group_hint=group_hint)
    # normalize — interval-aware + 12h → 24h fix
    slots = data.get('slots') or []
    norm = []
    # helper: 01:00-05:00 → 13:00-17:00 (دانشگاه بعدازظهر)
    def _fix_pm(hhmm: str) -> str:
        try:
            if not hhmm:
                return hhmm
            hh, mm = hhmm.split(':')
            h = int(hh)
            if 1 <= h <= 5:
                return f"{h+12:02d}:{mm}"
            return hhmm
        except Exception:
            return hhmm
    SYNTH_END = {"08:00":"10:00","10:00":"12:00","13:00":"15:00","15:00":"17:00","17:00":"19:00"}
    for s in slots:
        try:
            wd = int(s.get('weekday'))
            if not 0 <= wd <= 6:
                continue
            t = str(s.get('time') or '').strip()
            et = str(s.get('end_time') or s.get('time_end') or '').strip()
            # legacy: time may contain range "08:00-10:00" or "08:00 تا 10:00"
            if t and ("-" in t or "تا" in t) and not et:
                from time_utils import en_digits as _en
                tmp = _en(t).replace('—','-').replace('–','-').replace('تا','-')
                times = re.findall(r'(\d{1,2}:\d{2})', tmp)
                if len(times) >=2:
                    t = f"{int(times[0].split(':')[0]):02d}:{times[0].split(':')[1]}"
                    et = f"{int(times[1].split(':')[0]):02d}:{times[1].split(':')[1]}"
            # ensure HH:MM
            for val in (t, et):
                pass
            if not re.match(r'^\d{2}:\d{2}$', t):
                if re.match(r'^\d{1,2}:\d{2}$', t):
                    hh, mm = t.split(':')
                    t = f"{int(hh):02d}:{mm}"
                else:
                    continue
            # normalize end_time
            if et:
                if not re.match(r'^\d{2}:\d{2}$', et):
                    if re.match(r'^\d{1,2}:\d{2}$', et):
                        hh, mm = et.split(':')
                        et = f"{int(hh):02d}:{mm}"
                    else:
                        et = ""
            t = _fix_pm(t)
            if et:
                et = _fix_pm(et)
            # validate times
            from time_utils import parse_clock_time as _pct
            try:
                _pct(t)
                if et:
                    _pct(et)
                    if int(et.split(':')[0])*60+int(et.split(':')[1]) <= int(t.split(':')[0])*60+int(t.split(':')[1]):
                        et = SYNTH_END.get(t, "")
            except Exception:
                continue
            if not et:
                et = SYNTH_END.get(t, "")
            lesson = str(s.get('lesson') or '').strip()
            if not lesson:
                continue
            g = str(s.get('group') or group_hint or 'هر دو').strip() or 'هر دو'
            from database import db as _db
            g = _db.normalize_group(g) or 'هر دو'
            if g not in ('1','2','3','4','هر دو'):
                g = 'هر دو'
            flex = str(s.get('flex_type') or '').strip().lower()
            if flex not in ('fixed','flexible'):
                flex = 'flexible' if any(k in lesson for k in ('عملی','آز','آزمایشگاه')) else 'fixed'
            norm.append({
                'weekday': wd,
                'time': t,
                'end_time': et,
                'lesson': lesson[:120],
                'teacher': str(s.get('teacher') or '').strip()[:80],
                'location': str(s.get('location') or '').strip()[:80],
                'group': g,
                'type': 'class',
                'flex_type': flex,
                'notes': str(s.get('notes') or '').strip()[:200],
            })
        except Exception:
            continue
    # dedup: یک کلاس 2ساعته نباید دو ردیف شود — اگر دقیقاً (weekday,time,end_time,lesson,group) تکراری بود حذف
    seen = set()
    deduped = []
    for it in norm:
        k = (it['weekday'], it['time'], it['end_time'], it['lesson'], it['group'])
        if k in seen:
            continue
        seen.add(k)
        deduped.append(it)
    return {'slots': deduped}

async def scan_exam_schedule_image(image_bytes: bytes, image_mime: str = 'image/jpeg') -> dict:
    data = await scan_schedule_image(image_bytes, image_mime, kind='exam')
    exams = data.get('exams') or []
    norm = []
    for e in exams:
        try:
            lesson = str(e.get('lesson') or '').strip()
            if not lesson:
                continue
            raw_date = str(e.get('date') or '').strip()
            if not raw_date:
                continue
            # normalize digits and slashes
            from time_utils import en_digits
            raw_date = en_digits(raw_date).replace('-', '/').strip()
            # ensure YYYY/MM/DD
            parts = re.split(r'[/\s]+', raw_date)
            if len(parts) >= 3:
                y, m, d = parts[0], parts[1], parts[2]
                raw_date = f"{int(y):04d}/{int(m):02d}/{int(d):02d}"
            t = str(e.get('time') or '08:00').strip()
            t = en_digits(t)
            # extract HH:MM from possibly "10-12" or "۱۰:۰۰"
            m = re.search(r'(\d{1,2}):(\d{2})', t)
            if m:
                t = f"{int(m.group(1)):02d}:{m.group(2)}"
            elif re.search(r'(\d{1,2})\s*-\s*(\d{1,2})', t):
                hh = int(re.search(r'(\d{1,2})', t).group(1))
                t = f"{hh:02d}:00"
            else:
                t = '08:00'
            g = str(e.get('group') or 'هر دو').strip() or 'هر دو'
            from database import db as _db
            g = _db.normalize_group(g) or 'هر دو'
            norm.append({
                'date': raw_date,
                'time': t,
                'lesson': lesson[:120],
                'teacher': '',
                'location': str(e.get('location') or '').strip()[:80],
                'group': g,
                'type': 'exam',
            })
        except Exception:
            continue
    return {'exams': norm}


# ══════════════════════════════════════════════════
#  🖼 بخش ۳: استخراج ساختاریافته اطلاعات انتخاب واحد از اسکرین‌شات‌های پرتال آموزشی (Vision + Schema Validation)
# ══════════════════════════════════════════════════

COURSE_SELECTION_PORTAL_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "detected_academic_term": {
            "type": "STRING",
            "description": "عنوان یا کد نیمسال تحصیلی دیده‌شده در تصویر (مثلاً '1405-1406-1' یا خالی اگر در تصویر نیست)",
        },
        "courses": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "course_name": {"type": "STRING", "description": "نام کامل درس به فارسی (بدون کد درس)"},
                    "course_code": {"type": "STRING", "description": "کد درس با ارقام انگلیسی (مثلاً '98261047')"},
                    "class_code": {"type": "STRING", "description": "کد ارائه/کد کلاس در صورت وجود، در غیر این صورت رشته خالی"},
                    "group_code": {"type": "STRING", "description": "شماره گروه درس با ارقام انگلیسی (مثلاً '1'، '2'، '3')"},
                    "credit": {"type": "NUMBER", "description": "تعداد واحد درس (مثلاً 2 یا 1 یا 0.5 یا 1.5)"},
                    "instructor_name": {"type": "STRING", "description": "نام استاد فقط اگر در تصویر نوشته شده باشد؛ هرگز حدس نزن (رشته خالی اگر نیست)"},
                    "weekday": {"type": "INTEGER", "description": "روز هفته 0=شنبه تا 6=جمعه فقط اگر در تصویر صریحاً ذکر شده باشد؛ در غیر این صورت -1"},
                    "start_time": {"type": "STRING", "description": "ساعت شروع کلاس به HH:MM فقط اگر در تصویر صریحاً ذکر شده باشد؛ در غیر این صورت رشته خالی"},
                    "end_time": {"type": "STRING", "description": "ساعت پایان کلاس به HH:MM فقط اگر در تصویر صریحاً ذکر شده باشد؛ در غیر این صورت رشته خالی"},
                    "exam_date": {"type": "STRING", "description": "تاریخ امتحان فقط اگر در تصویر صریحاً ذکر شده باشد؛ در غیر این صورت رشته خالی"},
                    "exam_time": {"type": "STRING", "description": "ساعت امتحان فقط اگر در تصویر صریحاً ذکر شده باشد؛ در غیر این صورت رشته خالی"},
                    "section_type": {"type": "STRING", "description": "'taken_courses' برای جدول دروس اخذشده دانشجو یا 'available_courses' برای لیست دروس قابل اخذ"},
                    "extraction_confidence": {"type": "NUMBER", "description": "میزان اطمینان استخراج بین 0.0 تا 1.0"},
                },
                "required": ["course_name", "course_code", "group_code", "credit"],
            },
        },
    },
    "required": ["courses"],
}

COURSE_SELECTION_PORTAL_SYSTEM = (
    "تو یک سیستم دقیق استخراج اطلاعات انتخاب واحد دانشگاهی از اسکرین‌شات پرتال آموزشی هستی.\n"
    "قوانین حیاتی و غیرقابل تخطی:\n"
    "1) حریم خصوصی: هرگونه اطلاعات شخصی دانشجو (نام دانشجو، شماره دانشجویی، کد ملی و غیره) را کاملاً نادیده بگیر و هرگز در خروجی نیاور.\n"
    "2) عدم حدس زدن (Zero Hallucination): فقط و فقط اطلاعاتی را که واقعاً در تصویر دیده می‌شوند استخراج کن. اگر نام استاد (instructor_name)، روز هفته (weekday)، ساعت کلاس (start_time/end_time) یا تاریخ/ساعت امتحان (exam_date/exam_time) در تصویر وجود ندارد، آن‌ها را رشته خالی \"\" (و برای weekday عدد -1) بگذار و تحت هیچ شرایطی حدس نزن!\n"
    "3) اولویت با جدول «لیست دروس اخذ شده دانشجو» است که شامل ستون‌های کد درس، نام درس در کاتالوگ، گروه درس و واحد است. تمام ردیف‌های این جدول را با section_type='taken_courses' استخراج کن.\n"
    "4) اگر در تصویر بخشی با عنوان «لیست دروس قابل اخذ» (کارت‌های <نام درس>-<کد درس>) وجود دارد، دروسی را که قبلاً در جدول «لیست دروس اخذ شده دانشجو» بوده‌اند دوباره تکرار نکن؛ فقط در صورتی که درسی در جدول اخذشده نیست آن را با section_type='available_courses' اضافه کن.\n"
    "5) تمام اعداد (کد درس، گروه درس، واحد، ساعت) را به ارقام انگلیسی برگردان و فقط JSON معتبر مطابق schema تولید کن."
)


async def scan_course_selection_image(
    image_bytes: bytes,
    image_mime: str = 'image/jpeg',
    educational_group: str = 'unknown',
    academic_term: str = '',
    source_image: str = 'image_1',
) -> dict:
    """استخراج ساختاریافته دروس انتخاب واحد از یک تصویر پرتال آموزشی با رعایت کامل Schema و بدون حدس زدن فیلدهای غایب."""
    if not image_bytes or len(image_bytes) < 100:
        raise AIError("عکس نامعتبر یا خیلی کوچک است.")
    if len(image_bytes) > 12 * 1024 * 1024:
        raise AIError("حجم عکس بیش از حد زیاد است — نسخه کم‌حجم‌تر بفرست.")
    cfg = await get_ai_config()
    if not cfg.get('enabled'):
        raise AIConfigError("بخش هوشیار غیرفعال است.")
    provider, model, key = _pick_vision_config(cfg)
    if not key:
        raise AIConfigError("کلید API vision تنظیم نشده — از پنل هوشیار یک کلید Gemini/OpenRouter وارد کن.")

    from database import db as _db
    edu_grp = _db.normalize_class_educational_group(educational_group, default='unknown')
    user_prompt = (
        "از این تصویر انتخاب واحد دانشگاهی، فهرست دروس، کد درس، گروه درس و تعداد واحد را استخراج کن.\n"
        "فیلدهایی که در تصویر دیده نمی‌شوند (مثل نام استاد یا ساعت کلاس در جدول پرتال) را حتماً خالی بگذار و حدس نزن.\n"
        "فقط JSON برگردان."
    )
    if provider == 'gemini':
        data = await _vision_json_gemini(
            key, model, COURSE_SELECTION_PORTAL_SYSTEM, user_prompt,
            image_bytes, image_mime, COURSE_SELECTION_PORTAL_SCHEMA,
        )
    else:
        data = await _vision_json_openai(
            key, model, COURSE_SELECTION_PORTAL_SYSTEM, user_prompt,
            image_bytes, image_mime, provider,
        )

    detected_term = str((data or {}).get('detected_academic_term') or '').strip()
    effective_term = academic_term or detected_term
    raw_courses = (data or {}).get('courses') or []

    # حذف تکرار احتمالی بین taken_courses و available_courses در یک تصویر واحد
    taken_codes = set()
    taken_names = set()
    cleaned_rows = []
    for raw in raw_courses:
        if not isinstance(raw, dict):
            continue
        wd = raw.get('weekday')
        if wd is not None and int(wd) < 0:
            raw = dict(raw, weekday=None)
        norm = _db.normalize_extracted_course_row(
            raw,
            default_term=effective_term,
            default_edu_group=edu_grp,
            source_image=source_image,
        )
        if not norm:
            continue
        if norm.get('section_type') != 'available_courses':
            if norm['course_code']:
                taken_codes.add(norm['course_code'])
            taken_names.add(norm['course_name'])
        cleaned_rows.append(norm)

    final_rows = []
    for r in cleaned_rows:
        if r.get('section_type') == 'available_courses':
            if (r['course_code'] and r['course_code'] in taken_codes) or (r['course_name'] in taken_names):
                continue
        final_rows.append(r)

    return {
        'detected_academic_term': detected_term,
        'academic_term': effective_term,
        'educational_group': edu_grp,
        'source_image': source_image,
        'courses': final_rows,
    }


async def scan_course_selection_images(
    images: list,
    academic_term: str = '',
) -> dict:
    """پردازش یک یا چند تصویر انتخاب واحد (مثلاً تصویر انتخاب واحد آقایان + تصویر انتخاب واحد بانوان)
    و اجرای موتور تطبیق و حذف تکرار (reconcile_staged_course_extractions) برای آماده‌سازی فضای Staging.

    هر آیتم در `images` دیکشنری شامل:
      - `bytes`: bytes تصویر
      - `mime`: str (مثلاً 'image/png')
      - `educational_group`: 'male_only' | 'female_only' | 'mixed' | 'unknown'
      - `source_image`: نام یا شناسه تصویر (مثلاً 'boys_portal.png')
    """
    from database import db as _db
    if not images:
        raise AIError("هیچ تصویری برای استخراج ارسال نشده است.")

    all_extracted = []
    per_image_reports = []
    detected_term = academic_term

    for idx, img in enumerate(images):
        src_name = str(img.get('source_image') or f"image_{idx + 1}").strip()
        edu_grp = _db.normalize_class_educational_group(img.get('educational_group'), default='unknown')
        res = await scan_course_selection_image(
            image_bytes=img.get('bytes') or b'',
            image_mime=img.get('mime') or 'image/jpeg',
            educational_group=edu_grp,
            academic_term=academic_term,
            source_image=src_name,
        )
        if not detected_term and res.get('detected_academic_term'):
            detected_term = res['detected_academic_term']
        rows = res.get('courses') or []
        all_extracted.extend(rows)
        per_image_reports.append({
            'source_image': src_name,
            'educational_group': edu_grp,
            'extracted_count': len(rows),
            'detected_academic_term': res.get('detected_academic_term') or '',
        })

    reconciled = _db.reconcile_staged_course_extractions(all_extracted, academic_term=detected_term)
    return {
        'academic_term': detected_term,
        'per_image': per_image_reports,
        'items': reconciled['items'],
        'summary': reconciled['summary'],
    }


