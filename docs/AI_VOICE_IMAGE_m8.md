# ماموریت ۸ — پاسخ صوتی هوشیار (TTS فارسی) + مدل‌های تصویرِ زنده و سلامت‌سنجی

> کاندیدات رابط: **API آخرین** (2026-10). همه‌ی چیزها live از Google ListModels خوانده می‌شود؛
> کاتالوگ ثابت فقط fallback است.

## چه چیزی اضافه شد

### ۱) 🎤 پاسخ صوتی هوشیار (TTS فارسی)
- **مدل:** `gemini-3.8-flash-lite-tts` (پیش‌فرض؛ سریع/کم‌هزینه) — responseModalities `['AUDIO']` + `speechConfig.voiceConfig.voice`.
- **۳۰ صدای پیش‌ساخته** (`PREBUILT_TTS_VOICES`) — پیش‌فرض `Sulafat` (گرم). فارسی طبیعی.
- **حالت‌ها (`ai_voice_reply`):**
  - `voice` (پیش‌فرض) — فقط وقتی کاربر **ویس** فرستاده باشد، پاسخ هم متنی است هم صوتی.
  - `all` — همه‌ی پاسخ‌ها صوتی هم ارسال می‌شوند.
  - `off` — خاموش.
- **سقف طول** (`ai_voice_reply_max_chars`، پیش‌فرض ۵۰۰ نویسه): پاسخ بلندتر فقط متنی می‌ماند (سرعت حفظ شود). صدا بریده نمی‌شود — کلاً ارسال نمی‌شود.
- خروجی Gemini (WAV 24kHz) با ffmpeg به **OGG/Opus 48kHz** (فرمت ویس تلگرام) تبدیل می‌شود (`_transcode_wav_to_ogg_opus`)؛ نبود ffmpeg → fallback `send_audio` با فایل WAV.
- فرستادن صدا **best-effort** است (`asyncio.create_task`): اگر TTS شکست خورد، پاسخ متنی از قبل تحویل شده — کاربر چیزی از دست نمی‌دهد.
- سبک گفتار (`speech_metadata.style`) پیش‌فرض: «گرم، دوستانه و طبیعی؛ ریتم گفتاری روان به فارسی».
- **فال‌بک کلید (م۷):** TTS از همان vault چند-کلیدی gemini استفاده می‌کند؛ کلید لیمیت‌خورده → کلید بعدی.

### ۲) 🎨 مدل‌های تصویر — زنده، نه ثابت
- **فهرست زنده** (`list_image_models`): از `GET /v1beta/models?pageSize=200` همان ارائه‌دهنده، فقط مدل‌های تصویری واقعی (نه chat/embedding) — کش ۱۲ ساعته در setting `ai_image_models_cache_{provider}`؛ در خطا → کاتالوگ ثابت روزآمد (نانوبانانا 2.1 / 3.1-flash-lite-image / 3-pro-image / OpenRouter freeهای قبلی؛ مدل‌های مرده‌ی imagen-4 حذف).
- **رزولوشن (`ai_image_size`):** `1K` (پیش‌فرض) / `2K` / `4K` از طریق `generationConfig.imageConfig.imageSize` (مطابق SDK رسمی؛ همان‌جا که aspectRatio است).
  - ⚠️ نانوبانانا 2.1 همه‌ی رزولوشن‌ها را دارد؛ **3.1-flash-lite-image فقط 1K**.
- **نسبت‌های جدید** (nanobanana 2.1): `1:4`, `4:1`, `1:8`, `8:1`, `21:9`, … (پانوراما) + نسبت‌های قبلی.
- مدل پیش‌فرض تصویر: `gemini-3.1-flash-lite-image` (ultra-low-latency).

### ۳) 🧪 سلامت‌سنجی مدل‌ها — «توکن تست بشه»
- **probe چت** (`probe_chat_model`): درخواست واقعی با `maxOutputTokens=16` (یک ورودی کوچک → یک خروجی؛ مصرف ناچیز) — ۲۰۰ = زنده.
- **probe تصویر** (`probe_image_model`): فقط `GET` مدل (موجودی/دسترسی) — **تولید واقعی انجام نمی‌شود تا سهمیه نسوزد**؛ تولید واقعی فقط با دکمه‌ی دستی playground.
- اجرای همزمان محدود: حداکثر ۳۰ مدل، ۶ همزمان (`PROBE_MAX_MODELS/PROBE_CONCURRENCY`).
- نتیجه در setting `ai_models_health_{provider}` ذخیره می‌شود (`get_models_health`).
- **مرتب‌سازی** (`merge_models_with_health`) — خواسته‌ی کاربر:
  1. زنده (تست‌شده ok) صدر
  2. بعد «رایگان‌تر» (`model_free_rank`: openrouter `:free`=۴ > gemini flash-lite=۳ > flash/nano-banana=۲ > pro=۱)
  3. بعد سریع‌تر (ms پاسخ)
  4. تست‌نشده = وسط؛ مرده = آخر.
  - **رایگان‌بودن هرگز معیار حذف نیست** — فقط tie-breaker است.

## کلیدهای config جدید (همه در پنل و ربات قابل ویرایش)
| کلید | پیش‌فرض | معنا |
|---|---|---|
| `ai_voice_reply` | `voice` | off / voice / all |
| `ai_tts_voice` | `Sulafat` | یکی از ۳۰ صدای پیش‌ساخته |
| `ai_tts_model` | `gemini-3.8-flash-lite-tts` | مدل TTS |
| `ai_voice_reply_max_chars` | `500` | سقف طول پاسخ صوتی |
| `ai_image_size` | `1K` | رزولوشن پیش‌فرض تصویر |

مقادیر نامعتبر → پیش‌فرض امن (نه خطا). مدل‌های TTS بدون `temperature` ارسال می‌شوند (مثل نانوبانانا).

## API پنل (perm `ai.manage`)
| متد | مسیر | کار |
|---|---|---|
| GET | `/api/web-admin/ai/image/models` | مدل‌های تصویر زنده + سلامت + رایگان + نسبت‌ها/رزولوشن‌ها |
| POST | `/api/web-admin/ai/image/generate` | `{prompt, model?, aspect_ratio?, image_size?}` → `{mime, image_b64, model, ms}` — با فال‌بک کلید (م۷) |
| GET | `/api/web-admin/ai/models/health/{provider}` | آخرین نتیجه‌ی ذخیره‌شده |
| POST | `/api/web-admin/ai/models/{provider}/probe` | `{kind: chat\|image, models?}` → تست زنده‌بودن |
| GET | `/api/web-admin/ai/tts/voices` | ۳۰ صدا + مدل‌های TTS + حالت‌ها |

`GET /api/web-admin/ai/models` (فهرست مدل‌های چت) حالا سلامت را هم merge می‌کند → دراپ‌داون پنل خودکار مرتب است.

## پنل وب (AiAdmin)
- تب جدید **«🎨 تولید تصویر»**: playground کامل (پرامپت + مدل از فهرست زنده با نشان 🟢 زنده/🔴 مرده/🆓 رایگان + نسبت + رزولوشن → پیش‌نمایش + دانلود) + دکمه‌ی «🧪 تست زنده‌بودن».
- فرم پیکربندی: تنظیمات صدا (حالت پاسخ صوتی، انتخاب صدا از ۳۰تایی، مدل TTS، سقف کاراکتر) + رزولوشن پیش‌فرض تصویر.
- انتخاب مدل چت: دکمه‌ی «🧪 تست زنده‌بودن» + نشان سلامت/رایگان/latency داخل خود گزینه‌ها.

## ربات (ai_admin)
- دکمه‌ی **«🎤 پاسخ صوتی هوشیار»** در تنظیمات: چرخش حالت (off→voice→all)، انتخاب صدا از ۳۰تایی (با ✅ روی فعلی)، **تست صدای هوشیار** (نمونه‌ی صوتی واقعی می‌فرستد).
- «انتخاب مدل تصویر» حالا از **فهرست زنده‌ی API** می‌آید (نه کاتالوگ ثابت) + دکمه‌ی تازه‌سازی + نشان 🆓/✅.

## تست‌ها
`tests/test_ai_voice_image_m8.py` — ۱۳ تست بدون شبکه/Mongo:
- تشخیص مدل تصویر + رتبه‌ی رایگان + کاتالوگ/نسبت‌ها/۳۰ صدا.
- مرتب‌سازی سلامت (زنده‌ی سریعِ lite اول، مرده آخر، تست‌نشده وسط، نشان رایگان).
- فهرست زنده از ListModels (ردِ chat/embedding) + fallback کاتالوگ در خطا.
- probe چت (۲۰۰/۴۲۹) + probe تصویر (GET ارزان) + ذخیره/خواندن سلامت.
- TTS: شکل دقیق payload (responseModalities/voiceConfig/…) + فال‌بک کلید + خروجی WAV.
- payload تصویر: `imageConfig.aspectRatio + imageSize`.
- config: فیلدهای جدید + رد مقادیر نامعتبر.

**رگرسیون:** `pytest tests/ -q` → ۴۹۹ passed / ۱۸ failed / ۱۲۸ skipped — همان ۱۸ شکستِ محیطیِ مبنا (HEAD تمیز هم ۱۸ failed دارد؛ نصب fastapi در sandbox لازم است). صفر رگرسیون.

## 🔴 م8.1 — فیکس باگ ویس (پس از گزارش کاربر)
**علامت:** کاربر ویس می‌فرستاد → خطای ۴۰۰ `[INVALID_ARGUMENT] The mime type: audio/wav is not supported for code execution` که به ادمین به شکل گمراه‌کننده‌ی «کلید API نامعتبره…» گزارش می‌شد.

**ریشه:** `_stream_gemini` برای همه‌ی درخواست‌ها ابزارهای توکار `code_execution` و `url_context` را می‌چسباند؛ ابزار code execution گوگل ورودی صوتی (inline `audio/wav`) را نمی‌پذیرد و کل درخواست را ۴۰۰ می‌کند. (متن/عکس مشکلی نداشتند — فقط ویس/صوت.)

**فیکس (دو لایه):**
1. با ورودی صوت/ویدیو (`image_mime` با `audio/` یا `video/`)، ابزارهای توکار از `tools` حذف می‌شوند؛ `function_declarations` (برنامه/نمره) با صوت سازگارند و می‌مانند. `include_server_side_tool_invocations` هم فقط وقتی ست می‌شود که ابزار توکار واقعاً در درخواست باشد.
2. تور ایمنی در `_raise_gemini_status_error`: ۴۰۰ِ «mime type/not supported for» دیگر «کلید API نامعتبره» نمی‌گوید؛ پیام روشنِ «این نوع فایل توسط مدل انتخابی پشتیبانی نمی‌شود» می‌دهد.

**تست:** ۵ تست جدید (`VoiceToolsFixTests`) — ویس: بدون code_execution/url_context ولی با function_declarations و بدون فلگ server-side؛ ویدیونوت هم همین‌طور؛ عکس/متن: ابزارها سرِ جایشان؛ پیام خطای mime ≠ مشکل کلید.

## فایل‌های تغییرکرده
- `ai_solver.py` — TTS + تبدیل OGG + maybe_send_voice_reply + وایرینگ در `_answer_with_live_edit`/`handle_ai_media`؛ `generate_image(image_size=…)` + payload؛ کاتالوگ/نسبت‌ها/رزولوشن‌ها؛ ListModels زنده؛ probeها؛ مرتب‌سازی سلامت.
- `api/routers/ai.py` — پاس‌دادن image_size در endpoint تصویر (فال‌بک م۷).
- `api/routers/ai_management.py` — فیلدهای قابل‌ویرایش جدید + config() فیلدهای جدید + merge سلامت در فهرست مدل‌ها.
- `api/routers/web_admin.py` — ۵ endpoint جدید م۸.
- `webadmin/src/api.js` + `webadmin/src/pages/AiAdmin.jsx` — تب استودیوی تصویر + تنظیمات صدا + نشان‌های سلامت + دکمه‌های تست.
- `ai_admin.py` — صفحه‌ی تنظیمات صوتی ربات + تست TTS + فهرست زنده‌ی مدل تصویر.
- `tests/test_ai_voice_image_m8.py` — جدید.
