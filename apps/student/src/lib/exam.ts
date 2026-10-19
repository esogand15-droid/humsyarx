/** ❓ لایهٔ دادهٔ بانک سؤال — فقط همین‌جا مسیر شبکه‌ای نوشته می‌شود.
 *
 *  قرارداد سرور (موج P5، همه روی هندلرهای موجود ربات/مینی‌اپ):
 *    lessons  → {lessons: [{id,name,term,count}]}
 *    topics   → {lesson_id, topics: [{id,name,count}]}
 *    next     → {question, progress:{total,solved_unique,remaining,exhausted}, ai_available}
 *    answer   → {is_correct, correct_answer, explanation, question, prestige}
 *    stats    → {attempts, solved_unique, correct, wrong, accuracy, weak_topics, topics}
 *    history  → {answers: [...], total, limit, has_more, next_cursor}
 */
import { apiCall } from './api';

export interface LessonItem {
  id: string;
  name: string;
  term: string;
  count: number;
}

export interface TopicItem {
  id: string;
  name: string;
  count: number;
}

export interface Question {
  id: string;
  lesson_id: string;
  topic_id: string;
  lesson: string;
  topic: string;
  difficulty: string;
  difficulty_label: string;
  question: string;
  options: string[];
  source: string;
  exam_year: string | null;
  exam_session_label: string | null;
  content_source: string;
  content_source_label_fa: string;
  image: { has_image: boolean; pending_upload: boolean; alt_text: string };
  image_url: string | null;
}

export interface Progress {
  total: number;
  solved_unique: number;
  remaining: number;
  exhausted: boolean;
}

export interface NextPayload {
  question: Question | null;
  progress: Progress;
  ai_available: boolean;
  message?: string;
}

export interface AnswerPayload {
  is_correct: boolean;
  correct_answer: number;
  explanation: string;
  question: Question;
  prestige?: unknown;
}

export interface TopicStat {
  lesson_id: string;
  topic_id: string;
  lesson: string;
  topic: string;
  attempts: number;
  correct: number;
  accuracy: number;
  weak: boolean;
}

export interface StatsPayload {
  attempts: number;
  solved_unique: number;
  correct: number;
  wrong: number;
  accuracy: number;
  weak_topics: TopicStat[];
  topics: TopicStat[];
}

export interface HistoryItem {
  id: string;
  question_id: string;
  lesson: string;
  topic: string;
  question: string;
  selected: number;
  correct_answer: number;
  is_correct: boolean;
  answered_at: string;
}

export interface HistoryPayload {
  answers: HistoryItem[];
  total: number | null;
  has_more: boolean;
  next_cursor: string | null;
}

const q = (v?: string | null) => (v ? `?${v}` : '');

export const exam = {
  lessons: () => apiCall<{ lessons: LessonItem[] }>('/exam/lessons'),

  topics: (lesson: string) =>
    apiCall<{ lesson_id: string; topics: TopicItem[] }>(`/exam/topics/${encodeURIComponent(lesson)}`),

  next: (lesson?: string, topic?: string) =>
    apiCall<NextPayload>(
      `/exam/next${q(
        [lesson && `lesson=${encodeURIComponent(lesson)}`, topic && `topic=${encodeURIComponent(topic)}`]
          .filter(Boolean)
          .join('&'),
      )}`,
    ),

  answer: (question_id: string, selected: number) =>
    apiCall<AnswerPayload>('/exam/answer', {
      method: 'POST',
      body: JSON.stringify({ question_id, selected }),
    }),

  stats: () => apiCall<StatsPayload>('/exam/stats'),

  history: (limit = 20) => apiCall<HistoryPayload>(`/exam/history?limit=${limit}`),
};

/** گزینه‌ها با حروف فارسی — «الف/ب/ج/د» همان چیزی است که دانشجو در
    برگهٔ آزمون می‌بیند؛ شمارهٔ لاتین وسط متن فارسی خواندن را کند می‌کند. */
export const OPTION_LETTERS = ['الف', 'ب', 'ج', 'د'];

export const accuracyTone = (pct: number): 'good' | 'mid' | 'low' =>
  pct >= 75 ? 'good' : pct >= 50 ? 'mid' : 'low';

/* ─────────────────────────────────────────────────────────────
   P5.2 — آزمون زمان‌دار
   ───────────────────────────────────────────────────────────── */

export interface MockStartBody {
  lesson: string;
  topic?: string | null;
  lesson_id?: string | null;
  topic_id?: string | null;
  count: number;
  minutes: number;
  allow_smaller?: boolean;
}

export interface MockPreview {
  requested_count: number;
  available_count: number;
  can_start: boolean;
  max_count: number;
  minutes: number;
  output_mode: string;
  taxonomy: Record<string, string>;
}

export interface MockSummary {
  session_id: string;
  lesson: string;
  topic: string;
  status: 'active' | 'finished' | 'expired' | 'abandoned';
  total: number;
  answered: number;
  correct: number;
  percentage: number;
  current_index: number;
  minutes: number;
  deadline: string | null;
  started_at: string | null;
  finished_at: string | null;
  exam_code: string | null;
  requested_count: number;
  actual_count: number;
}

export interface MockNext {
  finished: boolean;
  /** فقط وقتی finished=false */
  question?: Question;
  progress?: number;
  total?: number;
  seconds_left?: number | null;
  session_id?: string;
  /* وقتی finished=true، خلاصهٔ آزمون با همین فیلدها می‌آید */
  answered?: number;
  correct?: number;
  percentage?: number;
  status?: string;
}

export interface MockAnswerResult {
  accepted: boolean;
  progress: number;
  total: number;
  finished: boolean;
  session_id: string;
  result?: { answered: number; correct: number; percentage: number };
}

export interface ReviewItem {
  question_id: string;
  selected: number;
  correct_answer: number;
  is_correct: boolean;
  answered_at: string;
  question?: string;
  options?: string[];
  topic?: string;
  explanation?: string;
  image_url?: string | null;
}

export interface MockReview extends MockSummary {
  review: ReviewItem[];
  total_questions: number;
}

/** زمان باقی‌مانده از سرور؛ شمارش محلی فقط نمایشی است. */
export const mockExam = {
  preview: (b: MockStartBody) =>
    apiCall<MockPreview>('/exam/mock/preview', { method: 'POST', body: JSON.stringify(b) }),

  start: (b: MockStartBody) =>
    apiCall<MockSummary>('/exam/mock/start', { method: 'POST', body: JSON.stringify(b) }),

  active: () => apiCall<{ exam: MockSummary | null }>('/exam/mock/active'),

  session: (sid: string) => apiCall<MockSummary>(`/exam/mock/${sid}`),

  next: (sid: string) => apiCall<MockNext>(`/exam/mock/${sid}/next`),

  answer: (sid: string, selected: number) =>
    apiCall<MockAnswerResult>(`/exam/mock/${sid}/answer`, {
      method: 'POST',
      body: JSON.stringify({ selected }),
    }),

  abandon: (sid: string) =>
    apiCall<{ ok: boolean }>(`/exam/mock/${sid}/abandon`, { method: 'POST' }),

  history: () => apiCall<{ exams: MockSummary[]; total: number }>('/exam/mock/history'),

  review: (sid: string) => apiCall<MockReview>(`/exam/mock/${sid}/review`),
};

/** ثانیه → «۱۲:۳۴» با رقم فارسی (همان قاعدهٔ کل محصول: رقم فارسی،
 *  چیدمان عددی چپ‌به‌راست تا ساعت مثل ساعت خوانده شود). */
export function clockFa(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  const fa2 = (n: number) =>
    String(n)
      .padStart(2, '0')
      .replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)]);
  return `${fa2(m)}:${fa2(r)}`;
}
