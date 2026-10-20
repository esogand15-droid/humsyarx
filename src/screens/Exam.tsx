import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Icon } from '../components/Icon';
import { Badge, Chip, Dialog, Empty, Note, Progress, Ring, SectionHead, Skeleton } from '../components/ui';
import { PageTitle } from '../components/Shell';
import { clock, fa, useProto } from '../lib/store';
import { examConfig, examHistory, lessons, questions, type Question } from '../data/demo';

const LETTERS = ['الف', 'ب', 'ج', 'د'];

/* ═══════════════════════════════════════════════════════════════════
   SC-030 — بانک سؤال (کشف)
   یک صفحهٔ «شروع کار»، نه داشبورد: انتخاب محدوده، آمار واقعی، دو مسیر
   (تمرین آزاد / آزمون زمان‌دار) و تاریخچهٔ آزمون‌ها.
   ═══════════════════════════════════════════════════════════════════ */
export function ExamHome() {
  const navigate = useNavigate();
  const [lesson, setLesson] = useState('همه');
  const [topic, setTopic] = useState<string | null>(null);

  const topics = useMemo(() => {
    const src = questions.filter((q) => lesson === 'همه' || q.lesson === lesson);
    const map = new Map<string, number>();
    src.forEach((q) => map.set(q.topic, (map.get(q.topic) ?? 0) + 1));
    return [...map.entries()];
  }, [lesson]);

  const scoped = questions.filter(
    (q) => (lesson === 'همه' || q.lesson === lesson) && (!topic || q.topic === topic),
  );

  return (
    <div className="page">
      <PageTitle
        title="بانک سؤال"
        sub="تمرین آزاد با بازخورد فوری، یا آزمون زمان‌دار بدون افشای پاسخ"
        actions={
          <div className="row" style={{ gap: 8 }}>
            <Badge tone="info">
              <Icon name="question" size={12} /> {fa(176)} سؤال در دسترس
            </Badge>
            <Badge tone="ok">پلن تو: نامحدود</Badge>
          </div>
        }
      />

      <div className="home-grid">
        <div>
          {/* انتخاب محدوده */}
          <section className="panel panel--pad">
            <div className="row" style={{ marginBottom: 12 }}>
              <b className="h3">۱. محدودهٔ تمرین</b>
              <span className="grow" />
              <span className="xs muted-2">همه از سرور می‌آید</span>
            </div>
            <div className="filters">
              <Chip active={lesson === 'همه'} onClick={() => { setLesson('همه'); setTopic(null); }}>
                همهٔ درس‌ها
              </Chip>
              {lessons.map((l) => (
                <Chip key={l.id} active={lesson === l.name} onClick={() => { setLesson(l.name); setTopic(null); }}>
                  {l.name} <span className="num muted-2">· {fa(l.questions)}</span>
                </Chip>
              ))}
            </div>

            <div className="filters" style={{ marginTop: 14 }}>
              <span className="xs muted-2" style={{ marginInlineEnd: 4 }}>
                مبحث:
              </span>
              <Chip active={!topic} onClick={() => setTopic(null)}>
                همهٔ مباحث
              </Chip>
              {topics.map(([t, n]) => (
                <Chip key={t} active={topic === t} onClick={() => setTopic(t)}>
                  {t} <span className="num muted-2">· {fa(n)}</span>
                </Chip>
              ))}
            </div>

            <div className="trace" />

            <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
              <button type="button" className="btn btn--primary" onClick={() => navigate('/exam/practice')}>
                <Icon name="play" size={15} fill />
                شروع تمرین آزاد
              </button>
              <button type="button" className="btn btn--ghost" onClick={() => navigate('/exam/run')}>
                <Icon name="clock" size={15} />
                آزمون زمان‌دار
              </button>
              <span className="grow" />
              <span className="xs muted-2">
                {fa(scoped.length)} سؤال در این محدوده
              </span>
            </div>
          </section>

          {/* تاریخچه */}
          <SectionHead title="آزمون‌های قبلی" hint="آخرین ۴ آزمون" />
          <div className="panel panel--flush">
            {examHistory.map((e) => (
              <button key={e.id} type="button" className="rrow" onClick={() => navigate('/exam/result')}>
                <span
                  className="rrow__ic"
                  style={{
                    color: e.pct >= 75 ? 'var(--ok)' : e.pct >= 55 ? 'var(--warn)' : 'var(--danger)',
                    background: e.pct >= 75 ? 'var(--ok-soft)' : e.pct >= 55 ? 'var(--warn-soft)' : 'var(--danger-soft)',
                    borderColor: 'transparent',
                  }}
                >
                  <b className="num" style={{ fontSize: 12 }}>
                    {fa(e.pct)}
                  </b>
                </span>
                <span style={{ minWidth: 0 }}>
                  <span className="rrow__t">
                    {e.lesson} · {e.topic}
                  </span>
                  <span className="rrow__m">
                    <span>{e.date}</span>
                    <span className="num">
                      {fa(e.correct)} از {fa(e.total)} درست
                    </span>
                  </span>
                </span>
                <Badge tone={e.status === 'تمام‌شده' ? 'ok' : undefined}>{e.status}</Badge>
                <span className="rrow__go" aria-hidden="true">
                  <Icon name="back" size={16} />
                </span>
              </button>
            ))}
          </div>
        </div>

        <aside style={{ display: 'grid', gap: 16 }}>
          <section className="panel panel--pad">
            <b className="h3">وضعیت تمرین تو</b>
            <div className="row" style={{ gap: 16, marginTop: 14 }}>
              <Ring value={77} label="دقت کل" />
              <div style={{ display: 'grid', gap: 10 }}>
                <div className="stat">
                  <span className="stat__v num">{fa(412)}</span>
                  <span className="stat__l">سؤال پاسخ‌داده</span>
                </div>
                <div className="stat">
                  <span className="stat__v num" style={{ color: 'var(--ok)' }}>
                    {fa(318)}
                  </span>
                  <span className="stat__l">پاسخ درست</span>
                </div>
              </div>
            </div>
            <div className="trace" />
            <div className="xs muted-2" style={{ marginBottom: 8 }}>
              نقاط ضعف این هفته
            </div>
            {[
              ['ایمونولوژی — ایمنی هومورال', 48],
              ['بیوشیمی — متابولیسم', 61],
            ].map(([t, v]) => (
              <div key={String(t)} style={{ marginBottom: 10 }}>
                <div className="row" style={{ justifyContent: 'space-between', marginBottom: 4 }}>
                  <span className="xs">{t}</span>
                  <span className="xs num muted-2">{fa(Number(v))}٪</span>
                </div>
                <Progress value={Number(v)} />
              </div>
            ))}
            <button type="button" className="btn btn--ghost btn--sm btn--block" style={{ marginTop: 6 }} onClick={() => navigate('/exam/practice')}>
              تمرین از نقاط ضعف
            </button>
          </section>

          <Note tone="ai" icon="sparkle">
            <b>هوشیار از همین‌جا سؤال می‌سازد.</b> بعد از هر آزمون، تحلیل پاسخ‌ها و پیشنهاد مرور در صفحهٔ
            کارنامه می‌آید.
          </Note>
        </aside>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   SC-031 — تمرین آزاد: یک سؤال، بازخورد فوری، توضیح، بعدی
   ═══════════════════════════════════════════════════════════════════ */
export function Practice() {
  const navigate = useNavigate();
  const { toast } = useProto();
  const [idx, setIdx] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [state, setState] = useState<'ready' | 'loading' | 'exhausted' | 'error' | 'locked'>('ready');
  const [map, setMap] = useState<Record<string, 'ok' | 'bad'>>({});
  const [showDlg, setShowDlg] = useState(false);
  const q: Question | undefined = questions[idx];

  const submit = useCallback(() => {
    if (picked === null || !q) return;
    setSubmitted(true);
    setMap((m) => ({ ...m, [q.id]: picked === q.answer ? 'ok' : 'bad' }));
  }, [picked, q]);

  const next = useCallback(() => {
    if (idx + 1 >= questions.length) {
      setState('exhausted');
      return;
    }
    setIdx((i) => i + 1);
    setPicked(null);
    setSubmitted(false);
  }, [idx]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (state !== 'ready') return;
      if (['1', '2', '3', '4'].includes(e.key)) setPicked(Number(e.key) - 1);
      if (e.key === 'Enter') submitted ? next() : submit();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [state, submitted, submit, next]);

  const correct = q ? picked === q.answer : false;

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 14, gap: 8 }}>
        <button type="button" className="btn btn--quiet btn--sm" onClick={() => navigate('/exam')}>
          <Icon name="forward" size={15} />
          بانک سؤال
        </button>
        <span className="grow" />
        <div className="seg" role="group" aria-label="حالت نمایش">
          <button type="button" aria-pressed onClick={() => setState('ready')}>
            تمرین
          </button>
          <button type="button" aria-pressed={false} onClick={() => navigate('/exam/run')}>
            آزمون
          </button>
        </div>
        <button type="button" className="iconbtn" onClick={() => setShowDlg(true)} aria-label="گزارش مشکل سؤال">
          <Icon name="flag" size={16} />
        </button>
      </div>

      {state === 'loading' ? (
        <div className="exam-shell">
          <div className="panel panel--pad">
            <Skeleton rows={4} />
          </div>
        </div>
      ) : state === 'locked' ? (
        <div className="panel">
          <Empty
            icon="lock"
            title="بانک سؤال در پلن فعلی تو بسته است"
            text="این بخش برای مشترکین فعال باز می‌شود. بررسی دسترسی سمت سرور انجام می‌شود."
            action={
              <Link to="/me/subscription" className="btn btn--accent btn--sm">
                مشاهدهٔ پلن‌ها
              </Link>
            }
          />
        </div>
      ) : state === 'error' ? (
        <div className="panel panel--pad">
          <Note tone="danger">
            <b>سؤال بارگذاری نشد.</b> اتصال به سرور برقرار نشد. پاسخ‌های ثبت‌شده از بین نمی‌روند؛ دوباره
            تلاش کن.
          </Note>
          <div className="row" style={{ marginTop: 12 }}>
            <button type="button" className="btn btn--primary btn--sm" onClick={() => setState('ready')}>
              <Icon name="refresh" size={14} /> تلاش دوباره
            </button>
          </div>
        </div>
      ) : state === 'exhausted' ? (
        <div className="panel">
          <Empty
            icon="check"
            title="این محدوده را تمام کردی"
            text={`همهٔ ${fa(questions.length)} سؤال انتخاب‌شده پاسخ داده شد. برای ادامه، مبحث دیگری انتخاب کن یا آزمون زمان‌دار بده.`}
            action={
              <div className="row" style={{ gap: 8 }}>
                <button
                  type="button"
                  className="btn btn--primary btn--sm"
                  onClick={() => {
                    setIdx(0);
                    setPicked(null);
                    setSubmitted(false);
                    setState('ready');
                  }}
                >
                  شروع دوباره
                </button>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => navigate('/exam')}>
                  انتخاب مبحث دیگر
                </button>
              </div>
            }
          />
        </div>
      ) : q ? (
        <div className="exam-shell">
          <div>
            <div className="qcard">
              <div className="qmeta">
                <Chip ghost>{q.lesson}</Chip>
                <Chip ghost>{q.topic}</Chip>
                <Badge tone={q.difficulty === 'سخت' ? 'danger' : q.difficulty === 'متوسط' ? 'warn' : 'ok'}>{q.difficulty}</Badge>
                <span className="grow" />
                <span className="xs muted-2">
                  سؤال <span className="num">{fa(idx + 1)}</span> از <span className="num">{fa(questions.length)}</span>
                </span>
              </div>

              <p className="qstem">{q.stem}</p>

              <div className="qopts" role="radiogroup" aria-label="گزینه‌ها">
                {q.options.map((o, i) => {
                  const isPicked = picked === i;
                  const isAnswer = i === q.answer;
                  let cls = 'qopt';
                  if (submitted && isAnswer) cls += ' qopt--ok';
                  else if (submitted && isPicked && !isAnswer) cls += ' qopt--bad';
                  return (
                    <button
                      key={i}
                      type="button"
                      role="radio"
                      aria-checked={isPicked}
                      className={cls}
                      disabled={submitted}
                      onClick={() => setPicked(i)}
                    >
                      <span className="qopt__l" aria-hidden="true">
                        {LETTERS[i]}
                      </span>
                      <span>{o}</span>
                    </button>
                  );
                })}
              </div>

              {submitted && (
                <div className="explain">
                  <div className="explain__t">
                    <Icon name={correct ? 'check' : 'alert'} size={14} style={{ color: correct ? 'var(--ok)' : 'var(--danger)' }} />
                    {correct ? 'درست بود' : 'پاسخ درست مشخص شد'}
                    <span className="grow" />
                    <span>
                      منبع: {q.source} · <span className="num">{q.year}</span>
                    </span>
                  </div>
                  <p className="sm" style={{ lineHeight: 1.9 }}>
                    {q.explanation}
                  </p>
                </div>
              )}

              <div className="row" style={{ marginTop: 20, gap: 8, flexWrap: 'wrap' }}>
                {!submitted ? (
                  <button type="button" className="btn btn--primary" disabled={picked === null} onClick={submit}>
                    ثبت پاسخ
                    <span className="kbd">Enter</span>
                  </button>
                ) : (
                  <button type="button" className="btn btn--primary" onClick={next}>
                    سؤال بعدی
                    <Icon name="back" size={15} />
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => {
                    toast('سؤال به هوشیار ارجاع داده شد.', 'ok');
                    navigate('/ai');
                  }}
                >
                  <Icon name="sparkle" size={14} style={{ color: 'var(--cyan-400)' }} />
                  توضیح بیشتر از هوشیار
                </button>
                <span className="grow" />
                <span className="xs muted-2">۱ تا ۴ انتخاب · Enter ثبت</span>
              </div>
            </div>
          </div>

          {/* نقشهٔ سؤال‌ها */}
          <aside style={{ display: 'grid', gap: 16 }}>
            <section className="panel panel--pad">
              <div className="row" style={{ marginBottom: 12 }}>
                <b className="h3">نقشهٔ تمرین</b>
                <span className="grow" />
                <span className="xs muted-2 num">
                  {fa(Object.keys(map).length)}/{fa(questions.length)}
                </span>
              </div>
              <div className="qmap">
                {questions.map((qq, i) => (
                  <button
                    key={qq.id}
                    type="button"
                    data-s={map[qq.id] ?? (i === idx ? 'now' : undefined)}
                    aria-label={`سؤال ${fa(i + 1)}`}
                    onClick={() => {
                      setIdx(i);
                      setPicked(null);
                      setSubmitted(false);
                    }}
                  >
                    {fa(i + 1)}
                  </button>
                ))}
              </div>
              <div className="row xs muted-2" style={{ marginTop: 12, gap: 12, flexWrap: 'wrap' }}>
                <span className="row" style={{ gap: 4 }}>
                  <span className="dot" style={{ color: 'var(--ok)' }} /> درست
                </span>
                <span className="row" style={{ gap: 4 }}>
                  <span className="dot" style={{ color: 'var(--danger)' }} /> غلط
                </span>
                <span className="row" style={{ gap: 4 }}>
                  <span className="dot" style={{ color: 'var(--cyan-400)' }} /> جاری
                </span>
              </div>
            </section>

            <section className="panel panel--pad">
              <b className="h3">پیشرفت این محدوده</b>
              <div className="row" style={{ gap: 14, marginTop: 12 }}>
                <Ring value={Math.round((Object.keys(map).length / questions.length) * 100)} size={56} label="پاسخ‌داده" />
                <div className="sm muted">
                  {fa(Object.values(map).filter((v) => v === 'ok').length)} درست از{' '}
                  {fa(Object.keys(map).length)} پاسخ ثبت‌شده
                </div>
              </div>
            </section>

            <section className="panel panel--pad">
              <b className="h3">سرنخ مطالعه</b>
              <p className="xs muted" style={{ marginTop: 6, lineHeight: 1.85 }}>
                بعد از پاسخ، توضیح کامل و منبع سؤال (سال آزمون) همین‌جا می‌آید. اگر صورت سؤال مشکل داشت،
                از آیکن گزارش در نوار بالا استفاده کن.
              </p>
              <div className="trace" />
              <div className="xs muted-2" style={{ marginBottom: 8 }}>
                بازبینی حالت‌ها (ابزار طراحی)
              </div>
              <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setState('error')}>
                  <Icon name="alert" size={13} />
                  خطا
                </button>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setState('locked')}>
                  <Icon name="lock" size={13} />
                  قفل
                </button>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setState('loading')}>
                  <Icon name="refresh" size={13} />
                  بارگذاری
                </button>
              </div>
            </section>
          </aside>
        </div>
      ) : null}

      <Dialog
        open={showDlg}
        title="گزارش مشکل این سؤال"
        onClose={() => setShowDlg(false)}
        actions={
          <>
            <button
              type="button"
              className="btn btn--primary btn--sm"
              onClick={() => {
                setShowDlg(false);
                toast('گزارش ثبت شد؛ تیم محتوا بررسی می‌کند.', 'ok');
              }}
            >
              ارسال گزارش
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setShowDlg(false)}>
              انصراف
            </button>
          </>
        }
      >
        اگر صورت سؤال ناقص است، گزینهٔ درست اشتباه علامت خورده یا توضیح با منبع نمی‌خواند، همین‌جا بگو.
        گزارش مستقیم به تیم محتوا می‌رود.
      </Dialog>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   SC-032 — آزمون زمان‌دار
   مهلت از سرور می‌آید؛ شمارش محلی فقط نمایشی است. هیچ کلیدی در میانه
   آزمون نشان داده نمی‌شود.
   ═══════════════════════════════════════════════════════════════════ */
export function ExamRun() {
  const navigate = useNavigate();
  const [started, setStarted] = useState(false);
  const [minutes, setMinutes] = useState(20);
  const [count, setCount] = useState(20);
  const [left, setLeft] = useState(20 * 60);
  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [picked, setPicked] = useState<number | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [finished, setFinished] = useState(false);
  const tick = useRef<number | null>(null);

  const pool = questions.slice(0, Math.min(examConfig.availableCount, questions.length));
  const q = pool[idx];
  const urgent = left <= 60;

  useEffect(() => {
    if (!started || finished) return;
    tick.current = window.setInterval(() => {
      setLeft((v) => {
        if (v <= 1) {
          window.clearInterval(tick.current!);
          setFinished(true);
          return 0;
        }
        return v - 1;
      });
    }, 1000);
    return () => {
      if (tick.current) window.clearInterval(tick.current);
    };
  }, [started, finished]);

  const submit = () => {
    if (picked === null || !q) return;
    setAnswers((a) => ({ ...a, [q.id]: picked }));
    if (idx + 1 >= pool.length) {
      setFinished(true);
      return;
    }
    setIdx((i) => i + 1);
    setPicked(null);
  };

  if (!started) {
    return (
      <div className="page page--narrow">
        <PageTitle title="آزمون زمان‌دار" sub="آزمون از همان بانک سؤال ساخته می‌شود؛ مهلت و کارنامه سمت سرور است." />
        <div className="panel panel--pad">
          <div className="row" style={{ marginBottom: 14 }}>
            <Icon name="clock" size={17} style={{ color: 'var(--cyan-400)' }} />
            <b className="h3">تنظیم آزمون</b>
          </div>

          <div className="field" style={{ marginBottom: 16 }}>
            <span className="field__l">تعداد سؤال</span>
            <div className="filters">
              {examConfig.countOptions.map((c) => (
                <Chip key={c} active={count === c} onClick={() => setCount(c)}>
                  <span className="num">{fa(c)}</span> سؤال
                </Chip>
              ))}
            </div>
          </div>

          <div className="field" style={{ marginBottom: 16 }}>
            <span className="field__l">زمان</span>
            <div className="filters">
              {examConfig.minuteOptions.map((m) => (
                <Chip key={m} active={minutes === m} onClick={() => setMinutes(m)}>
                  {m === 0 ? 'بدون زمان' : `${fa(m)} دقیقه`}
                </Chip>
              ))}
            </div>
          </div>

          <Note icon="info">
            در این محدوده <b className="num">{fa(examConfig.availableCount)}</b> سؤال موجود است و آزمون با
            همان تعداد ساخته می‌شود.
          </Note>

          <div className="row" style={{ marginTop: 18, gap: 8 }}>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => {
                setStarted(true);
                setLeft((minutes || 10) * 60);
              }}
            >
              <Icon name="play" size={15} fill />
              شروع آزمون
            </button>
            <Link to="/exam" className="btn btn--ghost">
              بازگشت
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (finished) {
    return (
      <div className="page page--narrow">
        <div className="panel panel--pad" style={{ textAlign: 'center' }}>
          <div className="center" style={{ width: 54, height: 54, borderRadius: 16, background: 'var(--ok-soft)', color: 'var(--ok)', margin: '0 auto 14px' }}>
            <Icon name="check" size={24} />
          </div>
          <b className="h2">آزمون ثبت شد</b>
          <p className="sm muted" style={{ marginTop: 6 }}>
            {fa(Object.keys(answers).length)} پاسخ ثبت شد. کارنامه و بازبینی آماده است.
          </p>
          <div className="row" style={{ justifyContent: 'center', marginTop: 16, gap: 8 }}>
            <button type="button" className="btn btn--primary" onClick={() => navigate('/exam/result')}>
              مشاهدهٔ کارنامه
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => {
                setStarted(false);
                setFinished(false);
                setIdx(0);
                setAnswers({});
                setPicked(null);
              }}
            >
              آزمون تازه
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 14, gap: 10, flexWrap: 'wrap' }}>
        <button type="button" className="btn btn--quiet btn--sm" onClick={() => setConfirm(true)}>
          <Icon name="forward" size={15} />
          خروج
        </button>
        <div className="row" style={{ gap: 8 }}>
          <Chip ghost>فیزیولوژی</Chip>
          <Chip ghost>قلب</Chip>
        </div>
        <span className="grow" />
        <span className={`timer${urgent ? ' timer--urgent' : ''}`} dir="ltr" aria-live="off">
          <Icon name="clock" size={14} />
          <span className="num">{clock(left)}</span>
        </span>
        <Badge tone="info">
          سؤال <span className="num">{fa(idx + 1)}</span> از <span className="num">{fa(pool.length)}</span>
        </Badge>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Progress value={Math.round(((idx + (picked !== null ? 0.5 : 0)) / pool.length) * 100)} />
      </div>

      <div className="exam-shell">
        <div className="qcard">
          <div className="qmeta">
            <Badge tone={q.difficulty === 'سخت' ? 'danger' : q.difficulty === 'متوسط' ? 'warn' : 'ok'}>{q.difficulty}</Badge>
            <span className="xs muted-2">{q.topic}</span>
            <span className="grow" />
            <span className="xs muted-2">پاسخ درست تا پایان آزمون نمایش داده نمی‌شود</span>
          </div>
          <p className="qstem">{q.stem}</p>
          <div className="qopts" role="radiogroup" aria-label="گزینه‌ها">
            {q.options.map((o, i) => (
              <button
                key={i}
                type="button"
                role="radio"
                aria-checked={picked === i}
                className="qopt"
                onClick={() => setPicked(i)}
              >
                <span className="qopt__l" aria-hidden="true">
                  {LETTERS[i]}
                </span>
                <span>{o}</span>
              </button>
            ))}
          </div>
          <div className="row" style={{ marginTop: 20, gap: 8 }}>
            <button type="button" className="btn btn--primary" disabled={picked === null} onClick={submit}>
              {idx + 1 === pool.length ? 'ثبت و پایان آزمون' : 'ثبت و سؤال بعدی'}
              <Icon name="back" size={15} />
            </button>
            <span className="grow" />
            <span className="xs muted-2">{fa(Object.keys(answers).length)} پاسخ ثبت‌شده</span>
          </div>
        </div>

        <aside style={{ display: 'grid', gap: 16 }}>
          <section className="panel panel--pad">
            <b className="h3">وضعیت سؤال‌ها</b>
            <div className="qmap" style={{ marginTop: 12 }}>
              {pool.map((qq, i) => (
                <button key={qq.id} data-s={answers[qq.id] !== undefined ? 'ok' : i === idx ? 'now' : undefined} onClick={() => { setIdx(i); setPicked(null); }}>
                  {fa(i + 1)}
                </button>
              ))}
            </div>
            <p className="xs muted-2" style={{ marginTop: 10, lineHeight: 1.7 }}>
              با رفتن به سؤال بعد، پاسخ ثبت می‌شود و برگشت به آن ممکن نیست — مطابق رفتار آزمون در مینی‌اپ.
            </p>
          </section>
          <Note tone="warn" icon="clock">
            مهلت از سرور می‌آید. اگر مرورگر بسته شود، آزمون از بین نمی‌رود و مهلت همچنان می‌گذرد.
          </Note>
        </aside>
      </div>

      <Dialog
        open={confirm}
        title="از آزمون بیرون بروی؟"
        onClose={() => setConfirm(false)}
        actions={
          <>
            <button type="button" className="btn btn--primary btn--sm" onClick={() => setConfirm(false)}>
              ادامهٔ آزمون
            </button>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => {
                setConfirm(false);
                navigate('/exam');
              }}
            >
              خروج
            </button>
          </>
        }
      >
        آزمون ذخیره می‌شود و می‌توانی ادامه بدهی، اما زمان همچنان در حال گذشتن است.
      </Dialog>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   SC-033 — کارنامه و بازبینی
   ═══════════════════════════════════════════════════════════════════ */
export function ExamResult() {
  const navigate = useNavigate();
  const { toast } = useProto();
  const [only, setOnly] = useState<'all' | 'wrong'>('all');
  const reviewed = questions.slice(0, 5);
  const shown = only === 'all' ? reviewed : reviewed.filter((q) => q.id !== 'Q1');

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 14 }}>
        <button type="button" className="btn btn--quiet btn--sm" onClick={() => navigate('/exam')}>
          <Icon name="forward" size={15} />
          بانک سؤال
        </button>
        <span className="grow" />
        <Badge tone="ok">تمام‌شده</Badge>
      </div>

      <div className="home-grid">
        <div>
          <section className="panel panel--pad result-hero">
            <div className="result-hero__top">
              <Ring value={80} size={104} stroke={7} label="درصد کل" />
              <div className="result-hero__meta">
                <div>
                  <b className="h2">فیزیولوژی · قلب</b>
                  <p className="xs muted-2" style={{ marginTop: 4 }}>
                    ۲۶ مهر ۱۴۰۵ · ۲۰ سؤال · ۱۹ دقیقه
                  </p>
                </div>
                <div className="row result-stats" style={{ gap: 24 }}>
                  <div className="stat">
                    <span className="stat__v num" style={{ color: 'var(--ok)' }}>۱۶</span>
                    <span className="stat__l">درست</span>
                  </div>
                  <div className="stat">
                    <span className="stat__v num" style={{ color: 'var(--danger)' }}>۴</span>
                    <span className="stat__l">غلط</span>
                  </div>
                  <div className="stat">
                    <span className="stat__v num">۰</span>
                    <span className="stat__l">بی‌پاسخ</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="trace" />

            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <button type="button" className="btn btn--primary btn--sm" onClick={() => navigate('/exam/practice')}>
                <Icon name="refresh" size={14} />
                تمرین روی سؤال‌های غلط
              </button>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => {
                  toast('تحلیل آزمون در گفتگوی هوشیار آماده شد.', 'ok');
                  navigate('/ai');
                }}
              >
                <Icon name="sparkle" size={14} style={{ color: 'var(--cyan-400)' }} />
                تحلیل هوشیار
              </button>
              <button type="button" className="btn btn--quiet btn--sm" onClick={() => toast('خروجی PDF در پلن جامع فعال می‌شود.')}>
                <Icon name="download" size={14} />
                PDF
              </button>
            </div>
          </section>

          <SectionHead
            title="بازبینی سؤال‌به‌سؤال"
            action={
              <div className="seg" role="group" aria-label="فیلتر بازبینی">
                <button type="button" aria-pressed={only === 'all'} onClick={() => setOnly('all')}>
                  همه
                </button>
                <button type="button" aria-pressed={only === 'wrong'} onClick={() => setOnly('wrong')}>
                  فقط غلط‌ها
                </button>
              </div>
            }
          />

          <div className="review-list">
            {shown.map((q, i) => {
              const ok = q.id === 'Q1';
              return (
                <details key={q.id} className="panel panel--pad review-q" open={i === 0 || undefined}>
                  <summary className="review-q__sum">
                    <span className="avatar" style={{ width: 26, height: 26, borderRadius: 8, background: ok ? 'var(--ok-soft)' : 'var(--danger-soft)', color: ok ? 'var(--ok)' : 'var(--danger)', fontSize: 11 }}>
                      {fa(i + 1)}
                    </span>
                    <Badge tone={ok ? 'ok' : 'danger'}>{ok ? 'درست' : 'غلط'}</Badge>
                    <span className="xs muted-2">
                      {q.topic} · {q.difficulty}
                    </span>
                    <span className="review-q__peek">{q.stem}</span>
                    <span className="review-q__chev" aria-hidden="true">
                      <Icon name="chevron" size={15} />
                    </span>
                  </summary>
                  <div className="review-q__body">
                  <p className="sm" style={{ lineHeight: 1.9 }}>{q.stem}</p>
                  <div style={{ display: 'grid', gap: 6, marginTop: 10 }}>
                    {q.options.map((o, oi) => {
                      const isAns = oi === q.answer;
                      const mine = ok ? isAns : oi === (q.answer + 1) % 4;
                      if (!isAns && !mine) return null;
                      return (
                        <div
                          key={oi}
                          className="row"
                          style={{
                            gap: 8,
                            padding: '8px 10px',
                            borderRadius: 'var(--r-sm)',
                            background: isAns ? 'var(--ok-soft)' : 'var(--danger-soft)',
                            alignItems: 'flex-start',
                          }}
                        >
                          <Icon name={isAns ? 'check' : 'close'} size={14} style={{ color: isAns ? 'var(--ok)' : 'var(--danger)', marginTop: 3 }} />
                          <span className="sm">
                            {o}
                            <span className="xs muted-2" style={{ marginInlineStart: 8 }}>
                              {isAns ? 'پاسخ درست' : 'انتخاب تو'}
                            </span>
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  <div className="explain" style={{ marginTop: 12 }}>
                    <div className="explain__t">
                      <Icon name="info" size={13} />
                      توضیح
                    </div>
                    <p className="sm" style={{ lineHeight: 1.9 }}>{q.explanation}</p>
                  </div>
                  </div>
                </details>
              );
            })}
          </div>
        </div>

        <aside style={{ display: 'grid', gap: 16 }}>
          <section className="panel panel--pad">
            <b className="h3">تحلیل کوتاه</b>
            <div className="trace" />
            <div style={{ display: 'grid', gap: 12 }}>
              {[
                ['قلب و گردش خون', 82],
                ['تنفس', 64],
              ].map(([t, v]) => (
                <div key={String(t)}>
                  <div className="row" style={{ justifyContent: 'space-between', marginBottom: 4 }}>
                    <span className="xs">{t}</span>
                    <span className="xs num muted-2">{fa(Number(v))}٪</span>
                  </div>
                  <Progress value={Number(v)} tone="ok" />
                </div>
              ))}
            </div>
            <p className="xs muted-2" style={{ marginTop: 12, lineHeight: 1.7 }}>
              مقایسه با میانگین ۲۰ آزمون قبلی تو.
            </p>
          </section>

          <Note tone="ai" icon="sparkle">
            <b>پیشنهاد هوشیار:</b> ۱۰ سؤال تنفس و ۶ سؤال بیوشیمی برای فردا. با یک کلیک به برنامهٔ مطالعه اضافه
            می‌شود.
          </Note>
        </aside>
      </div>
    </div>
  );
}
