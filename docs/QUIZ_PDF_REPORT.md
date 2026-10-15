# 📚 گزارش فاز A — «آزمون‌ساز هوشمند از روی PDF» (هوشیار)

**برنچ:** `feature/hooshyar-pdf-quiz` (از `cbad566`) • **کامیت‌ها:** `d127b6c` → `b1fc062` → `1e9e79a` → `6c46171` • **تاریخ:** ۲۰۲۶-۱۰-۱۵

---

## ۱) خلاصه اجرایی

قابلیت «آزمون‌ساز هوشمند» در فاز A (هسته) کامل شد: دانشجو PDF جزوه را در چت خصوصی می‌فرستد؛ ربات متن را صفحه‌به‌صفحه استخراج و نرمال‌سازی می‌کند، مباحث را تشخیص می‌دهد، سؤال چهارگزینه‌ای از دل متن می‌سازد، هر سؤال را با یک فراخوان مستقل «مخالف‌خوان» بازبینی می‌کند، به‌صورت Quiz Poll بومی تلگرام (غیرناشناس) می‌فرستد، بعد از هر جواب بازخورد «چرا درست/غلط» با شماره صفحه می‌دهد و در پایان گزارش نمره به تفکیک مبحث می‌سازد. کل نشست در DB است؛ ری‌استارت وسط آزمون چیزی از بین نمی‌برد.

**آمار:** ۹ فایل، ۳۱۲۶ خط افزوده، ۳۵ تست جدید (همگی سبز)، صفر رگرسیون در سوئیت موجود.

## ۲) معماری

```
PDF (چت خصوصی)
   │ unified_file_handler (bot.py) — هوک quiz_upload_hook *قبل از* ai_query
   ▼
hooshyar_quiz.process_document
   ├─ pypdf در asyncio.to_thread (event loop قفل نمی‌شود)
   ├─ _normalize_persian: NFKC (presentation forms)، ي→ی، ك→ک، حذف tatweel، حفظ ZWNJ
   ├─ _fix_visual_rtl: تشخیص/تعمیر متن معکوس (visual order) با امتیاز واژه‌های پرتکرار
   ├─ _page_quality: نسبت حروف + طول کلمه + کاراکتر خراب → کیفیت ۰..۱
   │    └─ کیفیت پایین/متن خالی → شکست شفاف «اسکن است؛ OCR پشتیبانی نمی‌شود»
   ├─ build_topic_structure: یک فراخوان AI روی page-map (۱۷۰ کاراکتر اول هر صفحه)
   │    └─ خطا/خروجی نامعتبر → fallback هیوریستیک (بلوک‌های ~۱۰ صفحه‌ای)
   ▼
DB: ai_documents (status=ready، صفحات + مباحث embedded)
   ▼
منوی stateless (همه‌ی انتخاب‌ها در callback_data؛ سقف ۶۴ بایت رعایت شد)
   حالت: 🧪 تمرینی (تک‌به‌تک + توضیح کامل) / 🏁 آزمونی (دسته ۵تایی)
   تعداد: ۱۰/۲۰/۳۰ (تا سقف ۵۰) — محدوده: کل جزوه یا یک مبحث (صفحه‌بندی ۸تایی)
   ▼
_build_and_start (asyncio.create_task — همه‌ی state در DB)
   ├─ توزیع سؤال بین مباحث به نسبت حجم متن (مبحث <۱۲۰ کاراکتر حذف)
   ├─ generate_questions_for_topic: چانک ~۹k کاراکتر، ۵+۲ سؤال/فراخوان
   │    ├─ _validate_question: اعتبارسنجی سخت سقف‌های تلگرام (ردِ بی‌ترمیم)
   │    ├─ verify_questions: فراخوان دوم AI (مخالف‌خوان) → ok/wrong/fixable
   │    │    └─ غیبت/خطای verification ⇒ سؤال ارسال نمی‌شود (سخت‌گیری عمدی)
   │    ├─ یک بازتولید برای مردودها + content_hash ضدتکرار (ناوردا به ترتیب گزینه)
   │    └─ semaphore سراسری AI(3) — یک کاربر بودجه را نمی‌سوزاند
   ▼
ارسال: send_poll(type=quiz, is_anonymous=False, correct_option_id, explanation,
                 open_period=۱۸۰/۳۰۰) + throttle ۱.۰۵s + RetryAfter
   ▼
PollAnswerHandler → quiz_question_by_poll (ایندکس unique-sparse)
   ├─ ثبت اتمیک با aggregation-pipeline: is_correct سمت سرور (نه کلاینت)
   ├─ idempotent: پاسخ تکراری = dup؛ سؤال بسته = stale؛ رأی پس‌گرفته نادیده
   ├─ بازخورد فوری + stop_poll + ارجاع صفحه (ارقام فارسی)
   ▼
پایان (همه answered/skipped) → گزارش تفکیک مبحث + نوار ■□ + پیام راهنما
```

**نقاط اتصال:** دکمه «📚 آزمون‌ساز از PDF» در `show_ai_intro` (ai_solver.py)؛ مسیر `quiz:*` در جدول cbs؛ `PollAnswerHandler` جداگانه؛ jobهای `quiz_housekeeping` (هر ۲ دقیقه) و `quiz_retention` (روزانه ۰۴:۴۰ تهران)؛ `set_application` برای دسترسی تسک‌های بک‌گراند به bot/job_queue.

## ۳) فایل‌های جدید/تغییرکرده

| فایل | تغییر | شرح |
|---|---|---|
| `hooshyar_quiz.py` | **جدید ۱۶۹۲ خط** | ماژول کامل قابلیت (پردازش، تولید، ارسال، UI) |
| `db/ai_quiz.py` | **جدید ۳۱۸ خط** | mixin `DBAiQuiz` — همه‌ی کوئری‌های داده |
| `tests/test_hooshyar_quiz.py` | **جدید ۹۱۲ خط** | ۳۵ تست در ۷ کلاس |
| `ai_solver.py` | +۱۴۴ خط | `generate_structured_json` + `_extract_json_block` (تک‌نقطه‌ی تماس AI) + دکمه‌ی ورود |
| `bot.py` | +۳۵ خط | import، هوک آپلود، cbs، PollAnswerHandler، jobs، set_application |
| `db/core.py` | +۲۱ خط | ۴ کالکشن + ۷ ایندکس در `ensure_indexes` |
| `database.py`، `db/__init__.py` | ±۴ خط | سیم‌کشی mixin |
| `requirements.txt` | +۱ | `pypdf>=4.0.0` |

## ۴) کالکشن‌ها و ایندکس‌ها

| کالکشن | فیلدهای کلیدی | ایندکس |
|---|---|---|
| `ai_documents` | owner_id, name, status(processing/ready/failed), error, size_bytes, page_count, quality, quality_note, topics[{id,title,page_start,page_end}], **pages[{no,text,topic_id,chars}]**, file_unique_id, created_at, last_used_at | `{owner_id:1, created_at:-1}` |
| `ai_quiz_sessions` | user_id, doc_id, doc_name, status(building/active/paused/finished/cancelled), mode(practice/exam), settings{mode,count,range,range_title}, total_planned, sent/answered/correct/wrong, current_order, build_attempts, timestamps | `{user_id:1, status:1}` + `{user_id:1, doc_id:1, created_at:-1}` |
| `ai_quiz_questions` | session_id, user_id, doc_id, order_index, stem(≤۳۰۰), options[۴×≤۱۰۰], correct_index, explanation_short(≤۲۰۰), explanation_long, difficulty, cognitive_level, concept_tags, source_evidence, topic_id/title, page_refs, content_hash, telegram_poll_id, chat_id, message_id, status(queued/sent/answered/skipped), answered_option, **is_correct (سمت سرور)**, time_ms | **`{telegram_poll_id:1} unique+sparse`** + `{session_id:1, order_index:1}` + `{user_id:1, doc_id:1, content_hash:1}` |
| `ai_generation_logs` | user_id, purpose(topics/questions/verify), provider, model, duration_ms, ok, chars_in/out, items_in/out, error_type, at | `{at:-1}` — **بدون هیچ محتوای سند/سؤال/کلید** |

**نکته‌ی ظریف که تست گرفت:** ایندکس unique-sparse روی `telegram_poll_id` مقدار `null` صریح را مثل مقدار تکراری می‌شمارد (E11000 روی درج دوم!). سؤال‌ها هنگام درج این فیلد را **ندارند**؛ فقط `quiz_bind_poll` بعد از ارسال موفق آن را می‌نویسد. این دقیقاً همان کلاس باگی است که در پروداکشن هر نشستِ بیش از یک سؤال را می‌شکست.

## ۵) Migration و ترتیب استقرار

- **Migration جدیدی لازم نیست:** همه‌ی کالکشن‌ها با اولین درج ساخته می‌شوند؛ ایندکس‌ها به `ensure_indexes` موجود اضافه شدند که از `db.bootstrap` استارتاپ (با bootstrap-lease موجود) اجرا می‌شود. هیچ schema-change ای روی کالکشن‌های موجود نیست؛ `users` فقط دو فیلد اختیاری (`quiz_usage_date/count`) می‌گیرد.
- **ترتیب استقرار:**
  1. `pip install -r requirements.txt` (pypdf جدید است).
  2. استقرار کد و ری‌استارت ربات — bootstrap خودش ایندکس‌ها را می‌سازد (background).
  3. پیش‌فرض‌ها فعال‌اند؛ اگر خواستید خاموش شروع کنید: `quiz_pdf_enabled=false` را قبل از ری‌استارت در `bot_settings` بگذارید.
  4. تست دودی با یک PDF کوچک (چک‌لیست بخش ۱۰).
- **rollback:** برگرداندن کد کافی است؛ کالکشن‌های جدید بی‌استفاده می‌مانند (یا با `quiz_cleanup_old_documents`/drop دستی پاک می‌شوند). هیچ تغییری روی مسیرهای موجود نیست — هوک آپلود فقط با فلگ `quiz_awaiting_pdf` فعال می‌شود.

## ۶) محدودیت‌های تاییدشده‌ی تلگرام (مستندات رسمی + PTB 21.3)

| محدودیت | مقدار | نحوه‌ی رعایت |
|---|---|---|
| question | ۱–۳۰۰ کاراکتر | validation سخت در `_validate_question` — رد بدون کوتاه‌سازی |
| option | ۱–۱۰۰ کاراکتر، ۱–۱۲ گزینه | دقیقاً ۴ گزینه (سازگار با Bot API قدیم و جدید)؛ رد بدون ترمیم |
| explanation | ۰–۲۰۰ کاراکتر، ≤۲ line feed | validation سخت + شمارش newline بعد از strip |
| quiz poll | دقیقاً یک `correct_option_id` | correct_index∈0..3 سمت سرور |
| `poll_answer` | فقط poll غیرناشناس + عضویت در allowed_updates | `is_anonymous=False` در send_poll؛ `Update.ALL_TYPES` از قبل در webhook و polling تنظیم است |
| getFile | دانلود حداکثر **۲۰MB** | چک `file_size` قبل از دانلود + پیام شفاف «بخش‌بندی/فشرده‌سازی» + try/except روی دانلود |
| open_period | ۵–600s (Bot API 7.x) | ۱۸۰ (تمرینی) / ۳۰۰ (آزمونی) |
| callback_data | ≤۶۴ بایت | طرح stateless؛ طولانی‌ترین حالت ≈۴۳ بایت |

## ۷) تصمیم‌های طراحی و انحراف‌ها از طرح اولیه

1. **حذف `ai_quiz_answers` و `ai_user_mastery` از فاز A** — پاسخ اتمیک در خود سؤال embedded شد (یک find_one_and_update به‌جای دو کوئری + race). mastery در فاز B با داده‌ی واقعیِ همین فیلدها ساخته می‌شود. *(انحراف از طرح — عمدی)*
2. **verification سخت‌گیرانه است:** اگر فراخوان بازبینی خطا بدهد، هیچ سؤالی ارسال نمی‌شود («سؤالِ مطمئن» > «سؤالِ کافی» — تاکید صریح شما). شکست کامل → پیام صادقانه به کاربر + پیشنهاد جزوه بهتر.
3. **هیچ فیلدی کوتاه/بلند نمی‌شود** — سؤال شکسته بهتر است رد شود تا در پروداکشن BadRequest بگیرد.
4. **selection کاملاً stateless** در callback_data (بدون user_data)؛ طبق قوانین شما «هیچ state در حافظه» — user_data فقط برای فلگ یک‌بارمصرفِ انتظارِ PDF (مثل الگوی موجود mode=ai_query).
5. **is_correct همیشه سمت سرور** با aggregation-pipeline محاسبه می‌شود (`$eq: [selected, '$correct_index']`) — کلاینت هیچ‌وقت نمی‌تواند «درست» ادعا کند.
6. **تعمیر visual-order RTL:** PDFهای فارسیِ برخی ابزارها متن را معکوس می‌دهند؛ تشخیص با امتیاز واژه‌های پرتکرار (`است، که، در، برای…`) و وارونه‌سازی خط‌به‌خط + بازگرداندن اعداد/لاتین. متن سالم دست نمی‌خورد (تست هر دو حالت).
7. **ساختار مباحث فقط از «سرِ صفحات»** (۱۷۰ کاراکتر) تغذیه می‌شود — حتی جزوه‌ی ۴۰۰ صفحه‌ای یک فراخوان سبک است؛ اعتبارسنجی (مرتب/پیوسته/بی‌همپوشانی/پوشش کامل) + fallback هیوریستیک.
8. **هزینه:** هر نشست ≈ ۱ (مباحث) + Σچانک (تولید) + Σچانک (بازبینی) فراخوان؛ semaphore(3) سراسری + سهمیه‌ی روزانه‌ی سؤال (۱۵۰ پیش‌فرض) + سقف نشست (۵۰).
9. **explanation بدون parse_mode** ارسال می‌شود — متن AI است و HTML شکسته می‌توانست کل poll را بکشد. توضیح بلند در پیام بازخورد با esc امن می‌آید.

## ۸) تنظیمات ادمین و env

**env جدید: هیچ.** همه‌ی تنظیمات از `bot_settings` (قابل تغییر بدون ری‌استارت، با الگوی موجود):

| کلید | پیش‌فرض | شرح |
|---|---|---|
| `quiz_pdf_enabled` | `true` | کل قابلیت |
| `quiz_max_pdf_mb` | `20` | سقف حجم (هم‌راستا با getFile) |
| `quiz_max_pages` | `400` | سقف صفحات |
| `quiz_max_questions_per_session` | `50` | سقف سؤال هر نشست |
| `quiz_daily_question_limit` | `150` | سقف سؤال تولیدی روزانه‌ی هر کاربر |
| `quiz_max_docs_per_user` | `10` | سقف اسناد ذخیره‌شده |
| `quiz_doc_retention_days` | `90` | حذف خودکار (retention) |
| `quiz_batch_questions` | `5` | سؤال در هر فراخوان تولید |
| `quiz_chunk_chars` | `9000` | کاراکتر منبع در هر فراخوان |

گیت دسترسی: `feature_allowed(uid, 'ai_chat')` (همان گیت هوشیار) + `get_ai_config().enabled`. شمارنده‌ی مصرف: `quiz_usage_date/count` روی سند کاربر (همان الگوی `ai_usage_*`).

## ۹) نتایج تست (با عدد)

**فایل جدید: ۳۵ تست، ۳۵ پاس (۱۰۰٪)** — `tests/test_hooshyar_quiz.py`:

| کلاس | تست | پوشش |
|---|---|---|
| QuizStaticWiring | ۶ | ترتیب هوک (قبل از ai_query)، cbs/PollAnswerHandler/jobs، ایندکس unique-sparse، pypdf، نبود متن PDF در لاگ |
| QuizPersianText | ۲ | نرمال‌سازی (presentation forms/ي/ك/tatweel/ZWNJ)، کیفیت صفحه (خوب ۰.۹۷ / خراب ۰.۲۶ / خالی ۰) |
| QuizTopicHelpers | ۳ | هیوریستیک (پوشش کامل ۲۲ صفحه)، تعمیر همپوشانی/شکاف/نامعتبر، انتخاب محدوده |
| QuizValidation | ۷ | سقف‌های ۳۰۰/۱۰۰/۲۰۰/≤۲خط، گزینه تکراری، correct_index، page_ref، shuffle+هش ناوردا (۲۰ تکرار) |
| QuizDbLifecycle | ۵ | چرخه‌ی سند، حذف آبشاری، پاسخ اتمیک first/dup/stale، شمارنده، retention (سند ۱۰۰ روزه حذف، ۱ روزه ماند) |
| QuizAiFlow | ۳ | مباحث AI+fallback، تولید (سؤال نامعتبر رد)، بازبینی ok/wrong/fixable + غیبت verify=رد همه |
| QuizUploadHookGuards | ۴ | غیر-PDF، >۲۰MB، سقف ۱۰ سند، عبور وقتی منتظر نیست |
| QuizPdfEndToEnd | ۳ | **PDF فارسی واقعی** (fpdf2+DejaVu): ۳ صفحه، کیفیت ۱.۰، ZWNJ سالم، انتساب مبحث؛ رد اسکن؛ رد magic جعلی |
| QuizReportAndFeedback | ۲ | گزارش (ارقام فارسی/■□/تفکیک)، بازخورد درست/غلط + «صفحه ۱۲» |

**کل سوئیت:** `504 passed, 43 failed` — فهرست ۴۳ شکست **بیت‌به‌بیت** با درخت تمیز (`cbad566`) یکسان است (شکست‌های محیطی/ترتیبی از‌قبل: reportlab، loop مشترک motor، تست همزمانی wallet که در ایزوله سبز است). **صفر رگرسیون.**

**باگ‌هایی که خودِ تست‌ها گرفتند:** ① E11000 null-unique-sparse (بخش ۴) ② شمارنده‌ی امتیاز در بازخورد از سند قدیمی خوانده می‌شد ③ مسیر بازگشتیِ شکست ارسال سؤال حلقه می‌ساخت → skip امن.

## ۱۰) چک‌لیست تست دستی (پیش از اتصال به کاربران واقعی)

1. ☐ دکمه «📚 آزمون‌ساز از PDF» در معرفی هوشیار → منو با فهرست خالی.
2. ☐ ارسال فایل غیر-PDF (مثلاً عکس) بعد از «ارسال جزوه» → پیام «فقط PDF».
3. ☐ ارسال PDF >۲۰MB → پیام سقف + راهنمای بخش‌بندی.
4. ☐ ارسال PDF اسکن‌شده (عکس صفحه) → پیام شفاف اسکن/OCR.
5. ☐ PDF متنی واقعی ۱۰–۵۰ صفحه → نوار پیشرفت ویرایش پیام، خروجی «N صفحه • M مبحث».
6. ☐ شروع تمرینی ۱۰ سؤالی از یک مبحث → poll غیرناشناس می‌آید؛ جواب درست → «✅ درست!» + صفحه؛ جواب غلط → نمایش گزینه‌ی درست + توضیح.
7. ☐ بی‌پاسخ گذاشتن یک سؤال (~۳ دقیقه) → پیام «زمان تمام شد» و سؤال بعدی خودکار.
8. ☐ وسط آزمون /start → منوی اصلی؛ «ادامه» از منوی آزمون‌ساز → نشست از سر گرفته می‌شود (بعد از ری‌استارتِ کامل ربات هم تست شود).
9. ☐ حالت آزمونی ۲۰ سؤالی → دسته‌های ۵تایی؛ پایان → گزارش تفکیک مبحث + نوار.
10. ☐ حذف جزوه (تایید دومرحله‌ای) → حذف از فهرست؛ ساخت سند دهم → پیام سقف.
11. ☐ (ادمیـن) `quiz_pdf_enabled=false` → پیام غیرفعال؛ برگرداندن true → کار کردن.
12. ☐ لاگ‌ها (journal/کنسول) نباید متن جزوه یا سؤال کامل داشته باشند.

## ۱۱) محدودیت‌ها و ریسک‌ها

| ریسک | شدت | وضعیت |
|---|---|---|
| کیفیت متن در PDFهای مشکل‌دار (چندستونه، جدول، فونت‌های embed ناقص) | متوسط | متریک کیفیت + پیام صادقانه؛ عملکرد روی PDFهای «Word-خروجی» خوب است (E2E سبز) |
| تعمیر visual-order هیوریستی است (واژه‌های پرتکرار)؛ متن خیلی کوتاه/فنی ممکن است تشخیص ندهد | کم | متن سالم هرگز خراب نمی‌شود (فقط در صورت «بهبود امتیاز» وارونه می‌کند) |
| OCR نیست — اسکن رد می‌شود | تصمیم عمدی | پیام شفاف + پیشنهاد نسخه متنی؛ OCR → پیشنهاد ۴ |
| هزینه AI در جزوه‌های بزرگ (۴۰۰ صفحه × چانک) | متوسط | semaphore(3) + سهمیه روزانه + سقف سؤال؛ لاگ مصرف برای پایش |
| حدس مدل درباره‌ی صفحه (page_ref) می‌تواند خطا کند | متوسط | validation بازه + بازبینی مخالف‌خوان؛ نادر بودن خطا پذیرفته شده (فاز B می‌تواند snapshot صفحه بدهد) |
| ری‌استارت وسط ارسال دسته | کم | jobهای تایم‌اوت از بین می‌روند اما housekeeping (۲ دقیقه) سرسیدگذشته‌ها را skip می‌کند؛ دکمه «ادامه» هم هست |
| رأی کاربر دیگر در poll (اگر پیام فوروارد شود) | کم | فیلتر `user_id` سؤال؛ آپلود فقط چت خصوصی |
| index unique روی telegram_poll_id در دیتابیس‌های replica-set قدیمی | کم | sparse است؛ در ساختار فعلی MongoDB پشتیبانی کامل |
| تست همزمانی wallet و چند تست محیطی دیگر از قبل fail | موجود | خارج از scope این فاز؛ در ایزوله سبز |

## ۱۲) پنج پیشنهاد برای ادامه (فاز B و بعد)

1. **موتور تسلط (mastery) + سؤال مشابه برای غلط‌ها** — داده‌ی لازم (`concept_tags`, `topic_id`, `is_correct`, `time_ms`) همین حالا ذخیره می‌شود؛ فاز B فقط تحلیل + prompt regeneration برای مفاهیم ضعیف است (بزرگ‌ترین ارزش آموزشی).
2. **انتخاب چندمبحثی + آزمون ترکیبی از چند جزوه** — طرح stateless فعلی با `t1,t3` گسترش می‌یابد؛ UI فقط صفحه‌بندی checkbox می‌خواهد.
3. **کش ساختار مباحث با `file_unique_id`** — جزوه‌ی دوباره‌فرست‌شده یک فراخوان AI صرفه‌جویی می‌کند (hash متن صفحات).
4. **OCR اسکن (Tesseract فارسی یا سرویس ابری) با گیت هزینه/ادمین** — بزرگ‌ترین شکایت قابل پیش‌بینی کاربران؛ با متریک کیفیت فعلی نقطه‌ی اتصالش آماده است.
5. **داشبورد ادمین روی `ai_generation_logs`** — نمودار مصرف/نرخ مردودی/مدت فراخوان به تفکیک provider؛ تصمیم‌گیری هزینه را عددی می‌کند.

---

*پیوست: فایل zip تحویل (`humsyar-quiz-phaseA.zip`) شامل patch کامل برنچ و همین گزارش.*
