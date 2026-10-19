import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { AppBar, Button, Card, Chip, EmptyState } from '../../components';
import { ErrorBlock, LoadingBlock } from '../../components/AccessStates';
import { ApiError } from '../../lib/api';
import { fa } from '../../lib/library';
import { exam, mockExam, type LessonItem, type MockPreview, type MockSummary, type TopicItem } from '../../lib/exam';

const COUNTS = [10, 20, 30, 50];
const MINUTES = [0, 10, 15, 20, 30, 45, 60];

/** ساخت آزمون — درس، مبحث، تعداد، زمان.
 *
 *  تعداد پیش از شروع با سرور چک می‌شود (`/exam/mock/preview`) تا کاربر
 *  آزمون ۲۰ سؤالی نخواهد وقتی بانک ۷ سؤال دارد. عدد «موجود» از سرور است،
 *  نه حدس کلاینت.
 */
export function ExamSetup() {
  const navigate = useNavigate();
  const [lessons, setLessons] = useState<LessonItem[]>([]);
  const [pickedLesson, setPickedLesson] = useState<LessonItem | null>(null);
  const [topics, setTopics] = useState<TopicItem[]>([]);
  const [pickedTopic, setPickedTopic] = useState<TopicItem | null>(null);
  const [count, setCount] = useState(20);
  const [minutes, setMinutes] = useState(20);
  const [preview, setPreview] = useState<MockPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<MockSummary | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setState('loading');
    try {
      const [less, act] = await Promise.all([
        exam.lessons(),
        mockExam.active().catch(() => ({ exam: null })),
      ]);
      setLessons(less.lessons ?? []);
      setActive(act.exam ?? null);
      setState('ready');
    } catch (err) {
      setError(err);
      setState('error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // پیش‌نمایش ظرفیت — با هر تغییر انتخاب، از سرور
  useEffect(() => {
    let cancelled = false;
    if (!pickedLesson) {
      setPreview(null);
      return;
    }
    (async () => {
      try {
        const p = await mockExam.preview({
          lesson: pickedLesson.name,
          topic: pickedTopic?.name ?? null,
          lesson_id: pickedLesson.id,
          topic_id: pickedTopic?.id ?? null,
          count,
          minutes,
        });
        if (!cancelled) setPreview(p);
      } catch {
        if (!cancelled) setPreview(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pickedLesson, pickedTopic, count, minutes]);

  const pick = async (l: LessonItem) => {
    setPickedLesson(l);
    setPickedTopic(null);
    setTopics([]);
    try {
      const res = await exam.topics(l.id);
      setTopics(res.topics ?? []);
    } catch {
      setTopics([]);
    }
  };

  const start = async () => {
    if (!pickedLesson || busy) return;
    setBusy(true);
    try {
      const s = await mockExam.start({
        lesson: pickedLesson.name,
        topic: pickedTopic?.name ?? null,
        lesson_id: pickedLesson.id,
        topic_id: pickedTopic?.id ?? null,
        count,
        minutes,
        allow_smaller: true, // تعداد واقعی را سرور تعیین می‌کند و در پیش‌نمایش گفته
      });
      navigate(`/exam/run/${s.session_id}`, { replace: true });
    } catch (err) {
      // سرور گفت «آزمون فعال داری» (۴۰۹ + خودِ آزمون در detail.exam):
      // به‌جای خطای مبهم، همان کارت «ادامه / رها کردن» را نشان می‌دهیم.
      if (err instanceof ApiError && err.code === 'active_exam_exists') {
        const existing = (err.detail?.exam ?? null) as MockSummary | null;
        if (existing) {
          setActive(existing);
          setBusy(false);
          return;
        }
      }
      setError(err);
      setState('error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <AppBar title="آزمون" sub="زمان‌دار، بدون پاسخ در میانه" back onBack={() => navigate(-1)} />
      <div className="page">
        {state === 'loading' && <LoadingBlock rows={3} />}
        {state === 'error' && <ErrorBlock error={error} onRetry={() => void load()} />}

        {state === 'ready' && (
          <>
            {active && (
              <Card className="mt-16">
                <p className="h3">یک آزمون نیمه‌کاره داری</p>
                <p className="small mt-8">
                  {active.lesson}
                  {active.topic ? ` · ${active.topic}` : ''} — {fa(active.answered)} از {fa(active.total)} پاسخ
                </p>
                <div className="row gap-8 mt-12">
                  <Button variant="primary" size="sm" onClick={() => navigate(`/exam/run/${active.session_id}`)}>
                    ادامهٔ آزمون
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={async () => {
                      await mockExam.abandon(active.session_id).catch(() => undefined);
                      setActive(null);
                    }}
                  >
                    رها کردن
                  </Button>
                </div>
              </Card>
            )}

            {lessons.length === 0 ? (
              <EmptyState
                icon="i-doc"
                title="سؤالی برای ورودی تو ثبت نشده"
                text="آزمون از همان بانک سؤال تمرین ساخته می‌شود؛ وقتی سؤالی برای ورودی تو ثبت شود، همین‌جا می‌شود آزمون ساخت."
              />
            ) : (
              <>
                <div className="section__head mt-16">
                  <span className="h3">۱. درس</span>
                </div>
                <div className="row gap-8 mt-8" style={{ flexWrap: 'wrap' }}>
                  {lessons.map((l) => (
                    <button
                      key={l.id}
                      type="button"
                      className={`chip-btn${pickedLesson?.id === l.id ? ' is-on' : ''}`}
                      aria-pressed={pickedLesson?.id === l.id}
                      onClick={() => void pick(l)}
                    >
                      {l.name} <span className="tiny num">· {fa(l.count)}</span>
                    </button>
                  ))}
                </div>

                {topics.length > 0 && (
                  <>
                    <div className="section__head mt-16">
                      <span className="h3">۲. مبحث</span>
                      <span className="tiny">اختیاری</span>
                    </div>
                    <div className="row gap-8 mt-8" style={{ flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className={`chip-btn${!pickedTopic ? ' is-on' : ''}`}
                        aria-pressed={!pickedTopic}
                        onClick={() => setPickedTopic(null)}
                      >
                        همهٔ درس
                      </button>
                      {topics.map((t) => (
                        <button
                          key={t.id}
                          type="button"
                          className={`chip-btn${pickedTopic?.id === t.id ? ' is-on' : ''}`}
                          aria-pressed={pickedTopic?.id === t.id}
                          onClick={() => setPickedTopic(t)}
                        >
                          {t.name} <span className="tiny num">· {fa(t.count)}</span>
                        </button>
                      ))}
                    </div>
                  </>
                )}

                <div className="section__head mt-16">
                  <span className="h3">۳. تعداد سؤال</span>
                </div>
                <div className="row gap-8 mt-8" style={{ flexWrap: 'wrap' }}>
                  {COUNTS.map((c) => (
                    <button
                      key={c}
                      type="button"
                      className={`chip-btn${count === c ? ' is-on' : ''}`}
                      aria-pressed={count === c}
                      onClick={() => setCount(c)}
                    >
                      <span className="num">{fa(c)}</span>
                    </button>
                  ))}
                </div>

                <div className="section__head mt-16">
                  <span className="h3">۴. زمان</span>
                </div>
                <div className="row gap-8 mt-8" style={{ flexWrap: 'wrap' }}>
                  {MINUTES.map((m) => (
                    <button
                      key={m}
                      type="button"
                      className={`chip-btn${minutes === m ? ' is-on' : ''}`}
                      aria-pressed={minutes === m}
                      onClick={() => setMinutes(m)}
                    >
                      {m === 0 ? 'بدون زمان' : `${fa(m)} دقیقه`}
                    </button>
                  ))}
                </div>

                {pickedLesson && (
                  <Card variant="quiet" className="mt-16">
                    {preview ? (
                      <>
                        <p className="small">
                          در این محدوده <b className="num">{fa(preview.available_count)}</b> سؤال موجود است.
                          {preview.can_start
                            ? ` آزمون با ${fa(Math.min(count, preview.available_count))} سؤال ساخته می‌شود.`
                            : ` کمتر از ${fa(count)} انتخاب‌شده؛ آزمون با ${fa(preview.available_count)} سؤال ساخته می‌شود.`}
                        </p>
                        {preview.available_count === 0 && (
                          <p className="tiny mt-8">برای این مبحث هنوز سؤالی ثبت نشده؛ مبحث دیگری را امتحان کن.</p>
                        )}
                      </>
                    ) : (
                      <p className="small">در حال بررسی ظرفیت…</p>
                    )}
                  </Card>
                )}

                <div className="row gap-8 mt-16">
                  <Button
                    variant="primary"
                    onClick={() => void start()}
                    disabled={!pickedLesson || busy || (preview?.available_count ?? 0) === 0}
                    aria-busy={busy}
                  >
                    {busy ? 'در حال ساخت آزمون…' : 'شروع آزمون'}
                  </Button>
                </div>
                <p className="tiny mt-8">
                  در جریان آزمون پاسخ صحیح نمایش داده نمی‌شود؛ کارنامه و بازبینی بعد از پایان می‌آید.
                </p>
              </>
            )}

            <div className="row gap-8 mt-16">
              <Button variant="ghost" size="sm" onClick={() => navigate('/exam/mock/history')}>
                آزمون‌های قبلی
              </Button>
            </div>
          </>
        )}
      </div>
    </>
  );
}

/** فهرست آزمون‌های قبلی — از همان `history` دامنه، با همان گیت. */
export function MockExamHistory() {
  const navigate = useNavigate();
  const [items, setItems] = useState<MockSummary[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');

  useEffect(() => {
    (async () => {
      try {
        const res = await mockExam.history();
        setItems(res.exams ?? []);
        setState('ready');
      } catch {
        setState('error');
      }
    })();
  }, []);

  const label: Record<string, string> = {
    active: 'در جریان',
    finished: 'تمام‌شده',
    expired: 'زمان تمام',
    abandoned: 'رها‌شده',
  };

  return (
    <>
      <AppBar title="آزمون‌های قبلی" sub="کارنامه و بازبینی" back onBack={() => navigate(-1)} />
      <div className="page">
        {state === 'loading' && <LoadingBlock rows={3} />}
        {state === 'error' && <ErrorBlock error={null} onRetry={() => navigate(0)} />}
        {state === 'ready' && items.length === 0 && (
          <EmptyState icon="i-clock" title="هنوز آزمونی نداده‌ای" text="اولین آزمون را از صفحهٔ «آزمون» بساز." />
        )}
        {state === 'ready' && items.length > 0 && (
          <Card variant="flush" className="mt-16">
            {items.map((e) => (
              <button
                key={e.session_id}
                type="button"
                className="mock-row"
                onClick={() =>
                  navigate(e.status === 'active' ? `/exam/run/${e.session_id}` : `/exam/result/${e.session_id}`)
                }
              >
                <span className="grow" style={{ textAlign: 'start' }}>
                  <span className="h3" style={{ display: 'block' }}>
                    {e.lesson}
                    {e.topic ? ` · ${e.topic}` : ''}
                  </span>
                  <span className="tiny">
                    {fa(e.answered)} از {fa(e.total)} پاسخ
                    {e.status !== 'active' ? ` · ${fa(Math.round(e.percentage))}٪ درست` : ''}
                  </span>
                </span>
                <Chip variant={e.status === 'active' ? 'cyan' : 'quiet'}>{label[e.status] ?? e.status}</Chip>
              </button>
            ))}
          </Card>
        )}
      </div>
    </>
  );
}
