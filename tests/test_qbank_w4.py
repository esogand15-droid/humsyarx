"""🌊 QBANK-W4 — regression tests: §9 gap closure (no MongoDB).

- ai_practice: سؤالات AI پیش‌فرض hamsyar می‌گیرند (از طریق validate).
- PDF: زنجیره تصویر تا بایت نهایی (%PDF در هر دو mode).
- ربات: کال‌بک‌ها و threading فیلتر (static، به رسم تست‌های w6).
"""
import io
from pathlib import Path

from PIL import Image
from reportlab.lib.utils import ImageReader

from question_bank.contracts import validate_question_payload

ROOT = Path(__file__).resolve().parent.parent


def _payload(**over):
    base = {
        "question": "کدام گزینه دربارهٔ غشای سلولی صحیح است؟ " + "x" * 12,
        "options": ["الف", "ب", "ج", "د"],
        "correct_answer": 2,
        "explanation": "توضیح کافی برای عبور از حد نصاب کیفی",
    }
    base.update(over)
    return base


class TestAiPracticeDefaults:
    """§۹/ai_practice: بدون تغییر ساختاری، فقط تضمین پیش‌فرض."""

    def test_ai_payload_gets_hamsyar_default(self):
        # generate() همین دیکشنری حداقلی را به validate می‌دهد.
        out = validate_question_payload(_payload())
        assert out["content_source"] == "hamsyar"
        assert out["exam_year"] is None


class TestPdfImageChain:
    def _png_reader(self):
        buf = io.BytesIO()
        Image.new("RGB", (120, 60), color=(200, 30, 30)).save(buf, format="PNG")
        buf.seek(0)
        return ImageReader(buf)

    def _question(self):
        return {"_id": "q1", "lesson": "فیزیولوژی", "topic": "قلب",
                "difficulty": "medium", "question": "تست " + "سؤال " * 6,
                "options": ["الف", "ب", "ج", "د"], "correct_answer": 1,
                "explanation": "توضیح " * 10}

    def test_practice_pdf_with_image(self):
        from qbank import generate_exam_pdf
        from qbank.query import ExamMeta
        content = generate_exam_pdf(
            [self._question()], ExamMeta(lesson="فیزیولوژی", topic="قلب"),
            mode="practice", question_images={"q1": self._png_reader()})
        assert content[:4] == b"%PDF"
        assert len(content) > 5000

    def test_exam_pdf_with_image(self):
        from qbank import generate_exam_pdf
        from qbank.query import ExamMeta
        content = generate_exam_pdf(
            [self._question()], ExamMeta(lesson="فیزیولوژی", topic="قلب"),
            mode="exam", question_images={"q1": self._png_reader()})
        assert content[:4] == b"%PDF"


class TestBotFilterWiring:
    """Static: فیلتر §۵.۴ در ربات سیم‌کشی شده است."""

    def _bot(self):
        return (ROOT / "questions.py").read_text(encoding="utf-8")

    def test_filter_callbacks_exist(self):
        bot = self._bot()
        for token in ("qf_year_set", "qf_src_tgl", "qf_start", "qf_back",
                      "cxf_year_set", "cxf_src_tgl", "cxf_start", "cxf_back",
                      "_filter_menu", "_filter_year_menu", "_filter_src_menu",
                      "_filter_summary", "_distinct_exam_years"):
            assert token in bot, token

    def test_practice_threads_filters(self):
        bot = self._bot()
        assert "exam_year_from=picked_year" in bot
        assert "content_source=quiz.get('content_source')" in bot

    def test_custom_exam_threads_filters(self):
        bot = self._bot()
        assert "exam_year_from=cx.get('exam_year')" in bot
        assert "content_source=cx.get('content_source')" in bot

    def test_review_card_shows_year_source(self):
        bot = self._bot()
        assert "q.get('exam_year')" in bot
        assert "content_source_label_fa" in bot
