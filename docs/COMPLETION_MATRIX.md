# 📋 ماتریس تکمیل قابلیت‌ها — فاز ۲ (سرشماری ناقص‌کاری‌ها)

> برنچ `feat/complete-and-sync` @ `a8d9df0` · ابزارها: `tools/audit2/m01…m04` · خروجی خام: `docs/audit2-data/`
> شدت: 🔴 بحرانی/اثر دیتابیسی-امنیتی · 🟠 ناقص‌کاری واقعی · 🟡 ناتمامی جزئی/پاک‌سازی · 🟢 پیشنهاد
> دسته: **کامل‌کن** (فاز ۴ پیاده می‌شود) · **نیازمند تصمیم** (پیاده نمی‌شود؛ گزینه می‌دهد) · **پیشنهاد** (ایده؛ اختراع نمی‌کنیم)

## ۰. خلاصه‌ی آماری

| سنجه | مقدار |
|---|---|
| endpointهای سرور | ۶۲۷ (در ۲۷ روتر) |
| مصرف‌شده توسط فرانت | ۵۶۲ (بعد از پاک‌سازی wrapperهای مرده) |
| یتیم واقعی (بعد از غربال دستی و پاک‌سازی) | ~۲۷ (۳۰ قبلی + ۷ِ آشکارشده در EP-31) |
| alias نسل‌قدیم (هم‌ارزِ مصرف‌شده دارند) | ۲۸ |
| wrapper مرده در webadmin/api.js | ۲۴ → ۱۹ حذف شد؛ ۵ زنده ماند (callback/داینامیک) |
| دکمه‌ی بدون هندلر | ۱ (ژنریک utils.py) |
| هندلر بدون دکمه (زنجیره‌ی مرده) | ۵ (همه resources) |
| هندلر cbs بدون answer() | ۰ |
| کلید settings فقط-خواندنی | ۲۲ |
| کلید settings فقط-نوشتنی | ۷ |
| توابع صفرارجاع (بدون دکوریتور، بعد از اصلاح alias-import) | ~۱۰۰ |
| نشانه‌های TODO/FIXME/stub واقعی | ~۰ (کد پاک است) |

---

## ۱. نشانه‌های ناقص‌کاری (m01)

نتیجه: **کد هیچ بدهی TODO/FIXME/NotImplementedError ندارد.** ۷ «به‌زودی» یافت‌شده همگی پیام‌های عمدی‌اند:

| شناسه | شدت | دسته | مورد |
|---|---|---|---|
| MK-01 | 🟡 | نیازمند تصمیم | `referral.py:112` — سوییچ خاموشِ دعوت دوستان: پیام «بخش دعوت دوستان به‌زودی فعال می‌شود». کل زیرساخت referral (bot/api/miniapp Growth) هست؛ فقط feature-flag خاموش است. آیا روشن شود؟ |
| MK-02 | 🟢 | پیشنهاد | سایر «به‌زودی»ها پیام وضعیت‌اند (تعلیق start.py:79، تعمیر ring/texts.py:582، SubscriptionLock.jsx:181) — اقدامی لازم ندارند. |

## ۲. callback ↔ هندلر (m02) — دامنه‌ی ربات

| شناسه | شدت | دسته | مورد |
|---|---|---|---|
| CB-01 | 🟠 | کامل‌کن | **زنجیره‌ی مرده‌ی resources.py** (~۲۰۰ خط): تنها ورودی‌اش دکمه‌های `download_resource:` است که خودِ همان فایل می‌سازد (resources.py:111) → از بیرون **غیرقابل دسترس**. به‌علاوه به `db.get_resources` ناموجود وابسته است (اگر فعال می‌شد crash می‌کرد). ثبت‌های مرده در bot.py:2164-2168: `^resources:bs`، `^resources:ref`، `^download_resource:`. مسیر زنده‌ی جایگزین: `route_resources` (bot.py:2022) با منوی bs:main/ref:main. **اقدام:** حذف ایمن resources.py + ۳ ثبت cbs + import در bot.py:107 (رفتار فعلی تغییر نمی‌کند؛ درAUDIT-R1 هم A-04 بود). |
| CB-02 | 🟡 | کامل‌کن | دکمه‌های داخلی زنجیره‌ی مرده (`resources:term/lesson/topic/files/search/main`) به `^resources:` → route_resources می‌روند که آن‌ها را نادیده می‌گیرد و منوی بالا را نشان می‌دهد — با حذف CB-01 خودبه‌خود تمیز می‌شود. |
| CB-03 | ✅ | — | پوشش answer() در همه‌ی هندلرهای جدول cbs کامل است؛ هیچ دکمه‌ی زنده‌ای بدون هندلر نیست (تنها مورد `(X):(X)` سازنده‌ی ژنریک utils.py است). |

## ۳. endpoint ↔ UI (m03) — یتیم‌های تأییدشده

> غربال دستی انجام شد: concatهای `${var}` و `${endpoint}` پنل/مینی‌اپ لحاظ شده‌اند (PATCHهای profile/name,intake,group,student-id مصرف‌شده‌اند؛ ai/status مصرف‌شده).

### ۳.الف. یتیم واقعی — قابلیت نیمه‌کاره یا سطح مرده

| شناسه | شدت | دسته | مورد |
|---|---|---|---|
| EP-01 | 🟠 | کامل‌کن ✅انجام شد | **تمرین هوشمند با AI** (کامیت cd48d84) — ۴ endpoint بدون هیچ مصرف‌کننده‌ای: `POST /api/questions/practice/ai/generate`، `…/ai/{id}/answer`، `…/ai/{id}/propose`، `GET /api/questions/practice/stats` (api/routers/questions.py). زیرساخت تنظیماتش هست (`qbank_ai_daily_limit`، `qbank_ai_topic_daily_limit` در question_bank/ai_practice.py) ولی هیچ ربات/پنل/مینی‌اپی صدا نمی‌زند. **نیت:** مسیر سمت سرور کامل است؛ لایه‌ی کلاینت هرگز وصل نشده. |
| EP-02 | 🟡 | نیازمند تصمیم | `GET/POST /api/questions/custom-exam/` (نسل v1 آزمون) — مینی‌اپ از `/start` و `/${sessionId}/next` استفاده می‌کند (Learn/)؛ این دو endpoint قدیمی بی‌مصرف‌اند. حذف API عمومی می‌تواند نسخه‌های مستقل مینی‌اپ را بشکند → تصمیمی. |
| EP-03 | 🟡 | نیازمند تصمیم | `GET /api/subscription/trial/status` (subscription.py::trial_status_ep) — پنل/مینی‌اپ وضعیت trial را از جای دیگری می‌گیرند یا اصلاً نشان نمی‌دهند؛ trial_enabled/trial_days هم فقط-خواندنی‌اند (ST-01). حذف یا اتصال به Me/Payment؟ |
| EP-04 | 🟡 | نیازمند تصمیم | `PATCH /api/profile/prestige/privacy` — کلید حریم خصوصی پرستیژ سمت سرور هست، هیچ UI‌ای ندارد (Me/). |
| EP-05 | 🟡 | نیازمند تصمیم | `POST /api/questions/my-designs/{qid}/resubmit` — «ارسال مجدد طرح سؤال» سمت سرور هست؛ مینی‌اپ دکمه‌اش را ندارد (my-designs لیست می‌شود ولی resubmit وصل نیست). |
| EP-06 | 🟡 | نیازمند تصمیم | `GET /api/questions/image/{qid}` — سرو تصویر سؤال؛ در فرانت‌ها فقط bulk-match پنل دیده شد. مصرف‌کننده‌اش شاید لینک مستقیم/ربات باشد؛ قبل از هر اقدام بررسی شود. |
| EP-07 | 🟡 | کامل‌کن | `POST /api/ring/maintenance/disable-all` (ring_admin.py::disable_all) — پنل رینگ همه‌ی کنترل‌ها را دارد جز این (RingStreet.jsx از pause/resume استفاده می‌کند). یا دکمه اضافه شود یا endpoint حذف. |
| EP-08 | 🟡 | کامل‌کن | `GET /api/notifications/inbox/unread-count` — مینی‌اپ inbox می‌گیرد ولی شمارنده‌ی ناخوانده را از `/api/tickets/unread-count` می‌گیرد؛ این endpoint بی‌مصرف است. |
| EP-09 | 🟡 | کامل‌کن | `GET /api/schedule/conflicts` + `GET /api/schedule/exams` (schedule.py) — مینی‌اپ فقط `/api/schedule` و `/ical` می‌گیرد؛ پنل نسخه‌ی web-admin دارد. یتیم نسل قدیم. |
| EP-10 | 🟡 | کامل‌کن | `GET/POST /api/content/schedule` + `GET /api/content/schedule/flex` — پنل محتوا از مسیر web-admin می‌رود؛ این ۳ تا نسل قدیم‌اند. |
| EP-11 | 🟡 | کامل‌کن | `PATCH /api/content/basic-science/content/{cid}/rename` + `PATCH /api/content/references/files/{fid}/rename` — rename در پنل از مسیر دیگر انجام می‌شود (Content.jsx). نسل قدیم. |
| EP-12 | 🟡 | کامل‌کن | `GET /api/subscription-admin/family` + `PATCH /api/subscription-admin/settings` — پنل اشتراک از معادل‌های web-admin استفاده می‌کند. |
| EP-13 | 🟡 | کامل‌کن | `DELETE /api/web-admin/schedule/templates/clear` (web_admin.py::wa_schedule_templates_clear_alias) — نامش alias است؛ معادل consumed در academic-admin هست. تکرار در همان روتر جدید. |
| EP-14 | 🔴* | نیازمند تصمیم | `GET/PUT/DELETE /api/ai-admin/vault/*` + `GET /api/ai-admin/banned` (ai_management.py) — **مخزن کلید API** (vault) سمت سرور هست ولی پنل از مسیرهای جدید web-admin/ai/* استفاده می‌کند. *اگر vault مسیر «تنها» محل چرخش کلید در جایی باشد، سطح حمله‌ی بی‌مصرف است؛ اگر کلاً بی‌مصرف است حذف شود. (سرکشی دقیق در فاز ۴ قبل از هر اقدام) |
| EP-15 | ✅ | — | `/api/subscription/zarinpal/callback` یتیم نیست — webhook سرویس بیرونی زرین‌پال است (fetch از سمت زرین‌پال). |
| EP-16 | ✅ | — | `GET /api/ai/conversations/{cid}/messages` — مصرف‌کننده‌اش از طریق concat در AiChat است؛ در بازبینی فاز ۴ دوباره چک می‌شود. |

### ۳.ب. سطح مرده‌ی نسل قدیم (aliasها)

| شناسه | شدت | دسته | مورد |
|---|---|---|---|
| EP-20 | 🟠 | نیازمند تصمیم | **۲۸ alias + ~۲۰ یتیم باقی‌مانده از نسل `/api/admin/*`, `/api/content/*`, `/api/academic-admin/*`, `/api/subscription-admin/*`, `/api/ai-admin/*`** — پنل به web-admin مهاجرت کرده؛ سطح قدیمی (admin_panel.py ۵۹ endpoint، content_admin.py ۶۶، …) هنوز mount است. RBAC همه را محافظت می‌کند (ممیزی قبلی) ولی «یک مفهوم دو پیاده‌سازی» است. **گزینه‌ها:** (الف) بایگانی/حذف روترهای قدیمی در چند PR ایمن، (ب) نگه‌داشتن به‌عنوان API عمومی برای اسکریپت‌ها. چون حذف اثر خارجی نامعلوم دارد → تصمیمی. |

### ۳.ج. wrapperهای مرده‌ی webadmin/src/api.js (۲۴)

| شناسه | شدت | دسته | مورد |
|---|---|---|---|
| EP-30 | 🟡 | کامل‌کن ✅انجام شد | ۱۹ wrapper مرده از webadmin/src/api.js حذف شد (userAction/userDetail/userPatch/stats/pendingUsers/ticketClose/ticketReopen/ringBans/ringState/ringSession/ringQueueRemove/activity/attentionDismissals/caIntakes/caOverview/caQuestionsPending/caScheduleTemplatesBulk/detachQuestionImage/discountBroadcastStatus/overview/urlImportJob). ⚠️ ۴ نام اولیه‌ی لیست در واقع زنده بودند و نگه داشته شدند — بدون پرانتز به‌عنوان callback پاس می‌شوند: `ticketClose`/`ticketReopen` (Tickets.jsx:253,259) و `ringPurge`/`ringReconcile` (RingStreet.jsx:226,227)؛ `dlqDiscard` هم داینامیک صدا زده می‌شود (DlqCenter.jsx:37). درس: تشخیص استفاده باید الگوی بدون-پرانتز را هم بپوشاند (m03 اصلاح شد). |
| EP-31 | 🟠 | نیازمند تصمیم | **۷ endpoint که فقط از طریق wrapperهای مرده قابل دسترس بودند** — با پاک‌سازی EP-30 آشکار شدند (تا قبل از آن، literalِ مسیر داخل خود api.js آن‌ها را «مصرف‌شده» جلوه می‌داد): `GET /api/web-admin/overview`، `GET /api/web-admin/activity`، `GET /api/ring/sessions/{sid}`، `POST /api/ring/profiles/{uid}/queue/remove`، `GET /api/content/url-import/jobs/{job_id}`، `POST /api/web-admin/schedule/templates/bulk`، `GET /api/web-admin/subscription/discounts/{code}/broadcast/{bid}`. حذف endpoint یا اتصال به UI؟ تصمیمی (احتمال مصرف توسط اسکریپت/نسخه‌ی مستقر قدیمی). |
| EP-34 | 🟡 | کامل‌کن | `DELETE /api/web-admin/questions/{qid}/image` (wa_detach_image) — detach تصویر سمت سرور هست؛ wrapper مرده است. آیا دکمه‌ی UI لازم دارد یا حذف endpoint؟ |

## ۴. ماتریس تنظیمات (m04)

| شناسه | شدت | دسته | مورد |
|---|---|---|---|
| ST-01 | 🟠 | نیازمند تصمیم | **۲۲ کلید فقط-خواندنی** (نویسنده‌ی پایتونی ندارند): gift_*، topup_*، trial_*، qbank_*، report_rate_*، url_import_max_mb، ticket_stale_hours، audit_retention_days، log_group_*، recon_window_days… — ست‌شدن‌شان فقط از دستکاری مستقیم DB ممکن است؛ برای کدام‌ها UI پنل بسازیم؟ (فهرست کامل: audit2-data/04_settings_matrix.txt) |
| ST-02 | 🟡 | کامل‌کن ✅حل شد | **۷ کلید فقط-نوشتنی** (خواننده‌ی `get_setting` ندارند): `required_channels` (تأیید شد: از `db.get_required_channels` خوانده می‌شود — db/core.py:3429؛ فقط-نوشتنیِ کاذب)، `ai_api_key`/`ai_api_keys` — ✅حل: هر دو از `_load_vault` (ai_solver.py:883) از طریق prefix-dict خوانده می‌شوند؛ زنده‌اند (مستند در DATA_CONTRACT §۶)، `index_status`، `audit_retention_last_run/deleted`، `grades_term_backfill` (state marker — طبیعی). |
| ST-03 | 🟡 | کامل‌کن | چند کلید در «UI پنل نیست»: تنظیم فقط با env/DB — برای قابلیت↔لایه‌ی همگام‌سازی، فهرست باید به DATA_CONTRACT منتقل و برای هرکدام مصدر حقیقت انتخاب شود. |

## ۵. توابع صفرارجاع (m04 → 05_dead_funcs.txt)

~۱۰۰ تابع بدون دکوریتور و بدون هیچ ارجاعی (بعد از اصلاح شمارش import-alias). کاندیدهای مهم (هرکدام در فاز ۴ با grep نهایی راستی‌آزمایی می‌شوند):

| شناسه | شدت | دسته | مورد |
|---|---|---|---|
| FN-01 | 🔴 | نیازمند تصمیم | `db/rbac.py::expire_due_roles` + `role_edit_lockout_risk` — **انقضای نقش RBAC پیاده‌سازی شده ولی هیچ‌جا صدا زده نمی‌شود** → نقش‌های موقت هرگز منقضی نمی‌شوند (اثر امنیتی/دسترسی). آیا عمداً غیرفعال مانده؟ فعال‌سازی = scheduler/cron لازم دارد. |
| FN-02 | 🟠 | نیازمند تصمیم | `core/access.py::require_access` + `has_access_bool` — لایه‌ی دسترسی جایگزین RBAC که فقط در `core/__init__` re-export شده و هیچ مصرف‌کننده‌ای ندارد. دو سیستم سلطه (core/access + core/rbac) — کدام مرجع؟ |
| FN-03 | 🟡 | کامل‌کن ✅انجام شد | ۵ wrapper `app_log_*` حذف شد (کامیت 3ef9e69)؛ `app_logger` مستقیم استفاده می‌شود. |
| FN-04 | 🟡 | کامل‌کن | `db/content.py` — qbank_* (۸ تابع: get_qbank_chapters/lessons/topics/difficulties، count_qbank_questions، qbank_file_add، qbank_file_mark_downloaded، bs_update_content_filename) — احتمالاً از دوران مهاجرت qbank؛ مصرف‌کننده‌ی router شاید حذف شده. |
| FN-05 | 🟡 | کامل‌کن | `ring/` — ~۱۵ تابع مرده (texts.py: help_ring/privacy_intro/profile_saved/controls_note؛ service.py: ensure_profile/resume_search/stop_timer؛ moderation.py: block_explicit/user_report_history؛ notify.py: send_to_peer_of؛ …) — بخشی شاید متن‌ها/رفتارهای فاز آزمایشی رینگ‌اند. |
| FN-06 | 🟡 | کامل‌کن ✅انجام شد | `_api_base`/`_is_mock`/`_pay_url` (نسخه‌های sync) حذف شدند (کامیت 11df60a)؛ `_api_base_async`/`_is_mock_async`/`_pay_url_async` زنده‌اند. |
| FN-07 | 🟡 | کامل‌کن | موارد تک‌افتاده: `api/auth.py::get_admin_user` (تست‌های امنیتی صراحتاً نبودنش را چک می‌کنند — عمداً مرده)، `db/core.py` (۶ تابع گزارش/جستجوی لاگ)، `db/ring.py` (۴ تابع)، `broadcast_service.finish_direct`، `api/telegram_send.reupload_with_new_filename`، `backup._snapshot_collection_iter`، `grades.show_my_grades_msg`، `question_bank/*` (۳ مورد)، `ai_solver._call_openrouter/_pick_unused`، `http_client.broadcast_semaphore`. |
| FN-08 | 🟢 | پیشنهاد | حذف توابع مرده در پاک‌سازی‌های کوچک جداگانه بعد از تأیید grep نهایی؛ هیچ حذفی بدون `git grep` سه‌لایه انجام نشود. |

## ۶. فیلد/enum نویسنده↔خواننده (m06 دستی)

| شناسه | شدت | دسته | مورد |
|---|---|---|---|
| EN-01 | 🟠 | کامل‌کن | **PAY_STATUS_FA ناقص** (webadmin/src/pages/Subscriptions.jsx:16): برچسب برای `pending/approved/rejected/failed` دارد ولی بک‌اند `cancelled` (۴ نقطه) و `refunded` هم می‌نویسد (db/finance.py) و `failed` هرگز نوشته نمی‌شود → دو وضعیت واقعی با enum انگلیسی خام نمایش داده می‌شوند. |
| EN-02 | 🟡 | کامل‌کن | `subscription.py:1385 status_icons` ربات — آیکون‌های pending/approved/rejected/… ؛ باید با EN-01 هم‌خوان شود (cancelled/refunded). |
| EN-03 | ✅ | — | enum سؤال (۴ وضعیت) و تیکت (۶ وضعیت) در پنل برچسب کامل دارند؛ وضعیت کاربر (approved/suspended) در Users.jsx برچسب دارد. |
| EN-04 | 🟡 | نیازمند تصمیم | چهار مکانیزم «قطع دسترسی» هم‌زمان: `blocked_bot` + کالکشن blacklist + `suspended` + `approved=False` — معناشناسی و اولویت‌شان در DATA_CONTRACT باید صریح شود (wa_user_action هر چهار را می‌نویسد: web_admin.py:4676). |
| EN-05 | 🟡 | کامل‌کن | مینی‌اپ PATCH پروفایل با concat می‌سازد (`/api/profile/${endpoint}` در Me/Profile.jsx:881) — قرارداد فیلدهای مجاز باید در DATA_CONTRACT لیست شود تا دو لایه هم‌خوان بمانند. |

## ۷. قابلیت ↔ لایه (✅🟡❌➖)

| قابلیت | ربات | API | پنل | مینی‌اپ | وضعیت |
|---|---|---|---|---|---|
| آزمون‌ساز PDF (hooshyar_quiz) | ✅ | ➖ | ➖ | ➖ | کامل (ماموریت ۴) |
| آزمون تشریحی v2 (custom-exam) | ➖ | 🟡 (v1 مرده: EP-02) | ✅ | ✅ | API نسل v1 پاک‌سازی شود |
| تمرین AI (practice/ai) | ❌ | ✅ | ❌ | ❌ | **EP-01 — کلاینت وصل نیست** |
| رینگ (گفتگوی ناشناس) | ✅ | 🟡 (disable-all: EP-07) | ✅ | ➖ | کامل تقریباً |
| هوشیار AI | ✅ | 🟡 (نسل قدیم ai_admin: EP-14) | ✅ | ✅ | سطح قدیم پاک‌سازی شود |
| پرداخت/اشتراک زرین‌پال | ✅ | ✅ (webhook: EP-15) | 🟡 (EN-01) | ✅ | برچسب enum ناقص |
| دعوت دوستان (referral) | 🟡 (سوییچ خاموش) | ✅ | ✅ (Growth) | ✅ | **MK-01 — تصمیم روشن‌کردن** |
| خانواده (subscription family) | ✅ | 🟡 (EP-12) | ✅ | ✅ | سطح قدیم پاک‌سازی |
| منابع درسی (resources) | 🟡 (زنجیره‌ی مرده CB-01) | 🟡 (preview: EP-06همانند) | ➖ | ➖ | پاک‌سازی CB-01 |
| تیکت | ✅ | ✅ | ✅ | ✅ | کامل |
| اعلان/همگانی | ✅ | ✅ | ✅ | 🟡 (unread: EP-08) | جزئی |
| RBAC | ✅ | ✅ | ✅ | ➖ | 🔴 **FN-01 انقضای نقش وصل نیست** |
| طرح سؤال کاربر (my-designs) | ✅ | 🟡 (EP-05) | ✅ | 🟡 (resubmit ندارد) | نیمه‌کاره |

## ۸. انتقال از ممیزی قبلی (AUDIT-R1)

| شناسه‌ی قدیم | وضعیت جدید |
|---|---|
| A-04 (resources.py مرده) | = CB-01 (کامل‌کن، 🟠) |
| A-05 (کش TTL داشبورد) | → **SY-01** 🟡 پیشنهاد — stats_dashboard_users بدون کش (۶۳ms با ۲۰k کاربر؛ TTL ۲۰-۳۰s) |
| A-09 (INIT_NONCE_ENABLED) | → **SY-02** 🟡 نیازمند تصمیم — nonce ضد replay مینی‌اپ پیاده شده ولی env پیش‌فرض خاموش است |
| A-06 (get_all_users مرده) | زیرمجموعه FN-07 (در 05_dead_funcs هست) |
| A-07 (فهرست except-pass) | → **SY-03** 🟢 پیشنهاد — در فاز ۴ فهرست‌بندی شود |
| A-10 (ارتقای pyrogram/fastapi) | → **SY-04** 🟢 پیشنهاد |
| A-11 (مشاهده بدون اقدام) | بسته |

## ۹. ترتیب اجرای فاز ۴ (به‌ترتیب شدت)

1. **FN-01** (🔴 تصمیمی — پیشنهاد فعال‌سازی انقضای نقش با jobqueue)
2. **EP-14** (🔴* تصمیمی — سرکشی vault)
3. 🟠های «کامل‌کن»: ~~EP-01~~✅ ~~CB-01~~✅ ~~EN-01~~✅ ~~EP-30~~✅ ~~FN-03~~✅ ~~FN-06~~✅ ~~ST-02~~✅(حل) · باقی: EP-07/08/09/10/11/12/13، FN-04، EP-34
4. 🟡های «نیازمند تصمیم»: MK-01، EP-03/04/05/06، EP-20، ST-01، FN-02، EN-04، SY-02
5. 🟢ها: SY-01، SY-03، FN-08

**قاعده‌ی تغییر:** هر آیتم = یک کامیت مجزا با ارجاع شناسه؛ قبل از تغییر هر نماد مشترک، همه‌ی مصرف‌کننده‌ها در ۴ لایه grep می‌شوند؛ عملیات تخریبی فقط گزارش.
