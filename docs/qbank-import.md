# QBank Import — زیرساخت پایدار (QBANK-W5)

این سند نحوهٔ افزودن **هر** آزمون علوم‌پایه (شهریور/اسفند و سال‌های آینده) را توضیح می‌دهد.
**سال و نوبت hard-code نمی‌شوند**؛ فقط به‌صورت آرگومان/metadata وارد pipeline می‌شوند.

## معماری موجود (حفظ‌شده)

| لایه | مسیر | نقش |
|---|---|---|
| Contracts | `question_bank/contracts.py` | schema، status، year/session/source |
| JSON Import (preview→confirm) | `question_bank/importer.py` | idempotent، taxonomy، duplicate |
| Exam runtime | `question_bank/exam.py` | session تمرین/آزمون |
| Images | `question_bank/images.py` | file_id تلگرام، pending upload |
| Admin API | `api/routers/web_admin.py` | upload JSON، preview، confirm |
| WebAdmin UI | `webadmin/src/pages/Questions.jsx` | ImportWizard |
| Bot/MiniApp | `questions.py` / `miniapp` | فیلتر year/source بدون hard-code نوبت |

**QBank موازی ساخته نشد.** لایهٔ جدید فقط *منبع آرشیو → OCR → JSON schema 1.0* است و خروجی‌اش همان importer موجود را تغذیه می‌کند.

## افزودن آزمون جدید (هر سال/نوبت)

```text
1. Archive را آماده کن (RAR/ZIP/پوشهٔ تصاویر یا PDFهای از پیش استخراج‌شده).
2. (اختیاری) Answer Key رسمی را در یک فایل متنی بگذار.
3. Import CLI را اجرا کن.
4. JSON خروجی را در WebAdmin → بانک سؤال → درون‌ریزی JSON بارگذاری کن.
5. Preview / Validation / نگاشت taxonomy را بررسی کن.
6. ردیف‌های needs_review را اصلاح/تأیید کن.
7. Confirm (idempotent).
8. تصاویر pending را در صف تصویر وصل کن (در صورت نیاز).
9. Publish = status approved + correct_answer معتبر.
```

### فرمان CLI

```bash
# وابستگی OCR فقط روی ماشین worker/dev (در Docker runtime پیش‌فرض نیست)
pip install -r requirements-qbank-ocr.txt
# apt: tesseract-ocr tesseract-ocr-fas tesseract-ocr-eng unrar

python qbank_import_cli.py extract \
  --source "path/to/archive-or-folder" \
  --work /tmp/qbank-work \
  --exam-year 1404 \
  --session shahrivar \
  --exam-type basic_sciences \
  --exam-track medicine \
  --content-source konkoor_sarasari \
  --title "آزمون علوم پایه پزشکی - شهریور ۱۴۰۴"

# همان pipeline برای آزمون بعدی — فقط آرگومان عوض می‌شود:
python qbank_import_cli.py extract \
  --source esfand-1403.rar \
  --work /tmp/qbank-esfand-1403 \
  --exam-year 1403 \
  --session esfand
```

خروجی‌ها در `--work`:

- `import_questions.json` — schema_version `1.0` سازگار با `QuestionImportService`
- `import_report.json` / `import_report.md` — کیفیت OCR/پاسخ/duplicate

### نوبت‌های پشتیبانی‌شده (قابل گسترش)

کلیدهای `EXAM_SESSIONS` در `contracts.py`:

`shahrivar`, `esfand`, `ordibehesht`, `mehr`, `azar`, `dey`, `farvardin`, `mordad`, `other`

افزودن نوبت جدید = یک سطر در دیکشنری؛ **بدون** `if year == ...`.

## ساختار Exam Metadata

```text
exam_id, title, exam_type, year, jalali_year,
session, session_label, field/exam_track,
category, description, source, source_file
```

روی هر سؤال ذخیره‌شده:

- `exam_year`, `exam_year_confidence`
- `exam_session`, `exam_session_label`
- `provenance.exam_track`, `provenance.exam_id`, `provenance.import.*`
- `content_source`

## Import Pipeline

```text
Archive/Folder
  → extract (RAR/ZIP/7z) + inventory (hash, subject folders, order)
  → OCR (tesseract fas+eng, optional)
  → segmentation (stem + 4 options; never invent)
  → answer-key attach (optional file; never medical guess)
  → normalize + quality report
  → import_questions.json (schema 1.0)
  → WebAdmin preview (taxonomy/duplicate)
  → confirm (idempotent upsert by import_identity)
  → admin review for needs_review / pending answers
  → approved → Bot / MiniApp / Practice
```

## قوانین کیفیت (قطعی)

1. **هیچ stem/option/answer جعلی نوشته نمی‌شود.**
2. بدون Answer Key رسمی: `correct_option = null` و classification `needs_review`.
3. OCR ناقص → errors + needs_review؛ silent production ممنوع.
4. Import دوباره همان فایل → duplicate/`import_identity` upsert (idempotent).
5. سؤال بدون `correct_answer ∈ {0,1,2,3}` در practice/exam eligible نیست.
6. تصویر منبع با `image.required=true` برای attach بعدی نگه داشته می‌شود.

## Admin

- Upload JSON → preview counts شامل `needs_review`
- Decision `import` برای `needs_review` → سند با `status=pending`
- صف تصاویر pending بدون تغییر قرارداد W3

## CLI کمکی

```bash
python qbank_import_cli.py ocr-status
python qbank_import_cli.py sessions
```
