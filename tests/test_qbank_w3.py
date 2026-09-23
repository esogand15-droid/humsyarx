"""🌊 QBANK-W3 — regression tests: question images (pure, no MongoDB)."""
import pytest

from question_bank.contracts import QuestionDomainError, public_question
from question_bank.images import (
    MAX_IMAGE_BYTES, image_state, parse_bulk_filename, split_photo_caption,
    validate_image_upload,
)
from question_bank.importer import PROMPT_PATH
from question_bank.service import QuestionBankService


class TestImageState:
    def test_new_shape(self):
        out = image_state({"image": {"has_image": True, "pending_upload": False,
                                     "storage_ref": "abc", "alt_text": "شکل"}})
        assert out == {"has_image": True, "pending_upload": False,
                       "alt_text": "شکل", "storage_ref": "abc"}

    def test_missing_is_clean(self):
        out = image_state({})
        assert out["has_image"] is False and out["pending_upload"] is False

    def test_legacy_required_becomes_pending(self):
        out = image_state({"image": {"required": True, "description": "نمودار"}})
        assert out["has_image"] is True and out["pending_upload"] is True
        assert out["alt_text"] == "نمودار"


class TestUploadValidation:
    @pytest.mark.parametrize("mime", ["image/jpeg", "image/png", "IMAGE/WEBP",
                                      "image/gif; charset=x"])
    def test_accepted(self, mime):
        assert validate_image_upload(mime_type=mime, size=100).startswith("image/")

    def test_rejected_type(self):
        with pytest.raises(QuestionDomainError) as exc:
            validate_image_upload(mime_type="application/pdf", size=100)
        assert exc.value.code == "unsupported_image_type"

    def test_too_large(self):
        with pytest.raises(QuestionDomainError) as exc:
            validate_image_upload(mime_type="image/png", size=MAX_IMAGE_BYTES + 1)
        assert exc.value.code == "image_too_large"


class TestBulkFilenames:
    def test_full_fingerprint(self):
        fp = "a" * 64
        assert parse_bulk_filename(f"{fp}_12.png") == (fp, 12)

    def test_short_prefix_and_dash(self):
        assert parse_bulk_filename("abc12345-3.jpg") == ("abc12345", 3)

    @pytest.mark.parametrize("bad", ["page3.png", "abc_3.png", "zzzzzzzz_3.png",
                                     "abc12345.png", "abc12345_x.png"])
    def test_invalid(self, bad):
        assert parse_bulk_filename(bad) is None


class TestCaptionSplit:
    def test_short_stays_single(self):
        caption, followup = split_photo_caption("متن کوتاه")
        assert (caption, followup) == ("متن کوتاه", False)

    def test_long_splits(self):
        caption, followup = split_photo_caption("x" * 2000)
        assert followup is True
        assert len(caption) <= 901


class TestPublicImageBlock:
    def test_ready_image_exposes_url(self):
        out = public_question({"_id": "q1", "image": {"has_image": True,
                                                      "pending_upload": False}})
        assert out["image_url"] == "/api/questions/image/q1"
        assert out["image"]["has_image"] is True

    def test_pending_hides_url(self):
        out = public_question({"_id": "q1", "image": {"has_image": True,
                                                      "pending_upload": True}})
        assert out["image_url"] is None
        assert out["image"]["pending_upload"] is True

    def test_plain_question(self):
        out = public_question({"_id": "q1"})
        assert out["image_url"] is None
        assert out["image"]["has_image"] is False


class TestPendingHiddenFromPractice:
    def test_eligible_query_excludes_pending(self):
        svc = QuestionBankService.__new__(QuestionBankService)
        query = svc.eligible_query({"lesson_id": "L1"}, intakes=[""])

        def _flatten(node):
            found = []
            stack = [node]
            while stack:
                current = stack.pop()
                if isinstance(current, dict):
                    for key, value in current.items():
                        if key in ("$and", "$or"):
                            stack.extend(value)
                        else:
                            found.append({key: value})
                elif isinstance(current, list):
                    stack.extend(current)
            return found

        assert {"image.pending_upload": {"$ne": True}} in _flatten(query)


class TestPromptRule9:
    def test_pending_import_documented(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        assert "منتظر تصویر" in text
        assert "import نمی‌شود" not in text
