# CHANGELOG — QBank (W5 Archive Import)

## Added

- `question_bank/exam_meta.py` — metadata data-driven برای year/session/track/title/exam_id
- `question_bank/archive_extract.py` — استخراج RAR/ZIP/7z + inventory با hash و subject
- `question_bank/ocr_pipeline.py` — OCR محلی (tesseract)، segmentation، answer-key parser، quality report
- `question_bank/archive_importer.py` — orchestration Archive → JSON schema 1.0
- `qbank_import_cli.py` — CLI پایدار برای همه سال‌ها/نوبت‌ها
- `requirements-qbank-ocr.txt` — وابستگی اختیاری OCR (خارج از image پیش‌فرض Railway)
- `docs/qbank-import.md` — راهنمای افزودن آزمون جدید
- `tests/test_qbank_w5.py` — unit tests session/OCR/metadata/inventory
- Dataset extract + OCR report برای **علوم پایه – شهریور ۱۴۰۴** (اولین dataset واقعی pipeline)

## Changed

- `question_bank/contracts.py`
  - `EXAM_SESSIONS` / `canonical_exam_session`
  - `validate_question_payload(..., allow_missing_answer=)` برای import بدون پاسخ جعلی
  - `public_question` فیلدهای `exam_session` / `exam_session_label`
- `question_bank/importer.py`
  - inference نوبت از filename/source
  - classification جدید `needs_review`
  - confirm: ردیف بدون پاسخ → `status=pending` (نه approved)
  - persistence `exam_session*` در document + provenance
- `question_bank/service.py` — eligible_query فقط `correct_answer ∈ {0,1,2,3}`
- `question_bank/__init__.py` — export session helpers
- `webadmin/src/pages/Questions.jsx` — UI برای needs_review + session + راهنمای CLI

## Fixed

- جلوگیری از ثبت پاسخ حدسی AI به‌عنوان پاسخ قطعی
- Import idempotent همچنان روی `import_identity` (بدون duplicate ناخواسته)

## Migration

- **بدون migration مخرب و بدون drop.**
- فیلدهای جدید (`exam_session`, …) sparse/additive هستند.
- داده‌های موجود دست‌نخورده می‌مانند؛ indexهای قبلی کافی‌اند.
- برای نصب‌های قدیمی فقط در صورت نیاز:
  `python qbank_migrate.py inspect-w1` (read-only)

## Tests

- `pytest tests/test_qbank_w1.py … test_qbank_w5.py` — regression W1–W5
- تست‌های static/jalali مرتبط

## Data Import — شهریور ۱۴۰۴

- منبع: آرشیو تصویری MedioFast (RAR)، ۱۵ درس/موضوع، ۱۹۶ تصویر
- Answer Key رسمی داخل آرشیو **وجود نداشت** → همه `correct_option=null` + needs_review
- خروجی JSON و گزارش کیفیت در بستهٔ تحویل (مسیر report داخل ZIP docs/data)

## Security

- هیچ secret/`.env`/token به repository اضافه نشده
- OCR deps اختیاری‌اند و image Railway را بی‌جهت سنگین نمی‌کنند
