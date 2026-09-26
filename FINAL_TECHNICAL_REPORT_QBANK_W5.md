# Final Technical Report — QBank W5 (Archive Import Infrastructure)

**Date:** 2026-09-26  
**Scope:** Minimal safe change + durable multi-year QBank import  
**First real dataset:** علوم پایه پزشکی — شهریور ۱۴۰۴

---

## 1. Repository Audit

| Area | Finding |
|---|---|
| Backend | FastAPI (`api/main.py`) + Telegram bot (`bot.py`) + Motor MongoDB |
| QBank domain | `question_bank/` (contracts, service, exam, importer, images, ai_practice) |
| Legacy PDF card renderer | `qbank/` (kept; not parallel bank) |
| Legacy files archive | `qbank_legacy_archive.py` / `qbank_files` (inspect/export only; no drop) |
| JSON import already existed | preview→map→confirm, schema 1.0, owner-only |
| Gap | No archive/OCR path; no `exam_session`; answers could not be null safely |

**Decision:** extend existing `question_bank`, do **not** create a second bank.

---

## 2. Architecture Changes

```
NEW (leaf modules, no parallel domain):
  archive_extract → ocr_pipeline → archive_importer → qbank_import_cli
       ↓ JSON schema 1.0
EXISTING:
  QuestionImportService.create_preview → confirm → questions collection
       ↓
  ExamService / Bot / MiniApp (year+source filters already data-driven)
```

Session metadata is additive on questions + provenance. No hard-coded `if shahrivar_1404`.

---

## 3. Database Changes

- **Additive fields only:** `exam_session`, `exam_session_label`, richer `provenance`.
- **No dropDatabase / drop collection / deleteMany({}).**
- Import identity upsert unchanged (`import_identity` unique sparse).
- Eligible practice/exam query now requires `correct_answer ∈ {0,1,2,3}` so pending/null answers never leak into student flows.
- Status path: needs_review import → `status=pending`, `approved=false`.

---

## 4. API Changes

- No new public student endpoints required.
- Existing WebAdmin import endpoints reused; preview payload gains `inferred_exam_session` + `counts.needs_review`.
- Admin confirm path accepts explicit decision on `needs_review` rows.

---

## 5. Admin Changes

- ImportWizard: label `needs_review`, count badge, session chip, CLI hint.
- Decision buttons for needs_review (import as pending / skip).

---

## 6. Mini App / Bot

- No unrelated UI rewrite.
- `public_question` exposes session fields when present.
- Year/source filters already generic; new exam appears after approve without new handlers.

---

## 7. Import + OCR Pipeline

| Step | Implementation |
|---|---|
| Extract | unrar / zip / 7z / folder |
| Inventory | sha256, subject folder, stable order |
| OCR | tesseract `fas+eng`, invert dark UI, upscale |
| Segment | stem + 4 options; never pad/invent |
| Answer key | optional text file parser only |
| Output | schema 1.0 JSON + MD/JSON quality report |

OCR deps are **optional** (`requirements-qbank-ocr.txt`) so Railway image stays slim.

---

## 8. Exam Imported — Shahrivar 1404

| Metric | Value |
|---|---|
| Source files / images | 196 / 196 |
| Subjects (folders) | 15 |
| Detected questions | 196 |
| Stem+4 options parsed | ~133–143 (OCR-limited) |
| Missing official answer | **196** (no key in archive) |
| needs_review | **196** |
| Answer key mismatches | 0 (no key) |
| Fabricated answers | **0** |

Source nature: MedioFast dark-theme screenshots; UI button «ثبت و مشاهده پاسخ صحیح» is visible but answers are not revealed in the image set. Per mission rules, answers stay `null`.

JSON path: `data/qbank/shahrivar_1404/import_questions.json`

---

## 9. Validation Results

- Idempotent identity = fingerprint + external_id + content_hash
- Duplicate image bytes flagged in inventory errors
- Invalid option counts marked in row `errors` (not silently approved)
- Cross-validation ready when `--answer-key` is supplied on future runs

---

## 10. Tests

```bash
pytest tests/test_qbank_w1.py tests/test_qbank_w2.py tests/test_qbank_w3.py \
       tests/test_qbank_w4.py tests/test_qbank_w5.py -q
# 81 passed (W1–W5)
```

Plus static/jalali contract smoke tests.

---

## 11. Docker / Railway

- Dockerfile **unchanged** regarding tesseract (keeps image small).
- OCR is offline-worker/CLI, not in-request synchronous HTTP.
- No new secrets. `.env` excluded from ZIP.

---

## 12. Known Limitations

1. **No official answer key** in the provided RAR → all answers null until admin supplies key or re-runs with `--answer-key`.
2. Tesseract on dark UI screenshots misses some option lines (~25–30% rows not exactly 4 options) → flagged needs_review; source image referenced for manual fix.
3. Taxonomy match depends on live `bs_lessons`/`bs_sessions` names; first import will show unmatched until mapped in Admin (existing flow).
4. Vision-LLM correction is intentionally **not** wired as authoritative answer writer (policy).
5. Full Mongo import not executed in this sandbox (no production Mongo URI); JSON is production-ready for WebAdmin upload.

---

## 13. Files Added / Edited

### Added
- `question_bank/exam_meta.py`
- `question_bank/archive_extract.py`
- `question_bank/ocr_pipeline.py`
- `question_bank/archive_importer.py`
- `qbank_import_cli.py`
- `requirements-qbank-ocr.txt`
- `docs/qbank-import.md`
- `tests/test_qbank_w5.py`
- `CHANGELOG_QBANK.md`
- `QBANK_IMPORT_REPORT_SHahrivar_1404.md`
- `FINAL_TECHNICAL_REPORT_QBANK_W5.md`
- `data/qbank/shahrivar_1404/*`

### Edited
- `question_bank/contracts.py`
- `question_bank/importer.py`
- `question_bank/service.py`
- `question_bank/__init__.py`
- `webadmin/src/pages/Questions.jsx`
- `README.md`

---

## 14. Success Criterion

```bash
# Future exam — zero Core changes:
python qbank_import_cli.py extract \
  --source esfand-1403.rar \
  --work /tmp/e1403 \
  --exam-year 1403 \
  --session esfand
```

Same path works for Shahrivar 1405, Esfand 1404, etc.
