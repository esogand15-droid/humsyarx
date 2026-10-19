import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { AppBar, Button, Chip } from '../../components';
import { ErrorBlock, LoadingBlock } from '../../components/AccessStates';
import { ApiError } from '../../lib/api';
import { fa } from '../../lib/library';
import {
  OPTION_LETTERS,
  clockFa,
  mockExam,
  type MockNext,
  type MockSummary,
} from '../../lib/exam';

/** اجرای آزمون زمان‌دار.
 *
 *  سه قاعده که عمداً این‌جاست:
 *  ۱) مهلت **از سرور** می‌آید (`seconds_left`)؛ شمارش محلی فقط نمایشی است.
 *     وقتی به صفر رسید، از سرور وضعیت تازه پرسیده می‌شود، نه اینکه
 *     کلاینت خودش آزمون را ببندد.
 *  ۲) در میانهٔ آزمون پاسخ صحیح نمایش داده نمی‌شود؛ دکمهٔ «ثبت و بعدی»
 *     فقط می‌فرستد و جلو می‌رود.
 *  ۳) رفرش صفحه آزمون را از بین نمی‌برد؛ وضعیت از `/mock/{id}` می‌آید.
 */
export function MockRun() {
  const { sid = '' } = useParams();
  const navigate = useNavigate();

  const [summary, setSummary] = useState<MockSummary | null>(null);
  const [current, setCurrent] = useState<MockNext | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<unknown>(null);

  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [left, setLeft] = useState<number | null>(null);
  const [confirmLeave, setConfirmLeave] = useState(false);
  const sending = useRef(false);

  const goResult = useCallback(() => navigate(`/exam/result/${sid}`, { replace: true }), [navigate, sid]);

  const boot = useCallback(async () => {
    setState('loading');
    try {
      const [s, n] = await Promise.all([mockExam.session(sid), mockExam.next(sid)]);
      setSummary(s);
      if (n.finished) {
        goResult();
        return;
      }
      setCurrent(n);
      setLeft(typeof n.seconds_left === 'number' ? n.seconds_left : null);
      setState('ready');
    } catch (err) {
      setError(err);
      setState('error');
    }
  }, [sid, goResult]);

  useEffect(() => {
    void boot();
  }, [boot]);

  // شمارش معکوس نمایشی؛ هر ثانیه یک درجه. منبع حقیقت سرور است.
  useEffect(() => {
    if (left === null) return;
    if (left <= 0) {
      // مهلت تمام شد: وضعیت واقعی را از سرور بگیر
      void (async () => {
        try {
          const n = await mockExam.next(sid);
          if (n.finished) goResult();
        } catch {
          goResult();
        }
      })();
      return;
    }
    const t = window.setTimeout(() => setLeft((v) => (v === null ? null : v - 1)), 1000);
    return () => window.clearTimeout(t);
  }, [left, sid, goResult]);

  const pick = (i: number) => {
    if (busy) return;
    setSelected(i);
  };

  const submit = async () => {
    if (selected === null || busy || sending.current || !current?.question) return;
    sending.current = true;
    setBusy(true);
    try {
      const res = await mockExam.answer(sid, selected);
      setSelected(null);
      if (res.finished) {
        goResult();
        return;
      }
      const n = await mockExam.next(sid);
      if (n.finished) {
        goResult();
        return;
      }
      setCurrent(n);
      setLeft(typeof n.seconds_left === 'number' ? n.seconds_left : null);
    } catch (err) {
      // مهلت وسط ثبت پاسخ تمام شد → کارنامه، نه صفحهٔ خطا.
      if (err instanceof ApiError && (err.code === 'exam_not_active' || err.code === 'exam_still_active')) {
        goResult();
        return;
      }
      setError(err);
      setState('error');
    } finally {
      setBusy(false);
      sending.current = false;
    }
  };

  // کیبورد: ۱..۴ انتخاب، Enter ثبت
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (busy || !current?.question) return;
      const n = ['1', '2', '3', '4'].indexOf(e.key);
      if (n >= 0) {
        e.preventDefault();
        setSelected(n);
      }
      if (e.key === 'Enter' && selected !== null) {
        e.preventDefault();
        void submit();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const q = current?.question;
  const progress = current?.progress ?? 0;
  const total = current?.total ?? summary?.total ?? 0;
  const urgent = left !== null && left <= 60;

  return (
    <>
      <AppBar
        title={summary ? `${summary.lesson}${summary.topic ? ` · ${summary.topic}` : ''}` : 'آزمون'}
        sub={summary?.exam_code ? `کد ${summary.exam_code}` : 'در حال آماده‌سازی'}
        back
        onBack={() => setConfirmLeave(true)}
        actions={
          left !== null ? (
            <span className={`timer${urgent ? ' is-urgent' : ''}`} aria-live="off" dir="ltr">
              {clockFa(left)}
            </span>
          ) : undefined
        }
      />

      <div className="page">
        {state === 'loading' && <LoadingBlock rows={3} />}
        {state === 'error' && <ErrorBlock error={error} onRetry={() => void boot()} />}

        {state === 'ready' && q && (
          <>
            <div className="row gap-8 mt-12" style={{ alignItems: 'center' }}>
              <Chip variant="quiet">
                سؤال {fa(progress)} از {fa(total)}
              </Chip>
              <span className="grow" />
              <span className="tiny">پاسخ درستی نمایش داده نمی‌شود تا پایان آزمون</span>
            </div>

            <div
              className="mt-8"
              role="progressbar"
              aria-valuenow={progress}
              aria-valuemin={0}
              aria-valuemax={total}
              aria-label="پیشرفت آزمون"
            >
              <div className="bar">
                <i style={{ width: `${total ? Math.round((100 * (progress - 1)) / total) : 0}%` }} />
              </div>
            </div>

            <article className="q-card mt-16">
              {q.image_url && (
                <img className="q-img" src={q.image_url} alt={q.image.alt_text || 'تصویر سؤال'} loading="lazy" />
              )}
              <p className="q-stem mt-12">{q.question}</p>
              <ul className="q-options" role="radiogroup" aria-label="گزینه‌ها">
                {q.options.map((opt, i) => (
                  <li key={i}>
                    <button
                      type="button"
                      role="radio"
                      aria-checked={selected === i}
                      className={`q-opt${selected === i ? ' is-picked' : ''}`}
                      onClick={() => pick(i)}
                    >
                      <span className="q-opt__l" aria-hidden="true">
                        {OPTION_LETTERS[i] ?? i + 1}
                      </span>
                      <span className="q-opt__t">{opt}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <div className="row gap-8 mt-16">
                <Button variant="primary" onClick={() => void submit()} disabled={selected === null || busy} aria-busy={busy}>
                  {busy ? 'در حال ثبت…' : progress >= total ? 'ثبت و پایان آزمون' : 'ثبت و سؤال بعدی'}
                </Button>
                <span className="grow" />
                <span className="tiny">۱ تا ۴ انتخاب، Enter ثبت</span>
              </div>
            </article>
          </>
        )}
      </div>

      {confirmLeave && (
        <div className="sheet-scrim" role="dialog" aria-modal="true" aria-label="خروج از آزمون">
          <div className="sheet">
            <p className="h3">از آزمون بیرون بروی؟</p>
            <p className="small mt-8">
              آزمون ذخیره می‌شود و از «آزمون» می‌توانی ادامه بدهی. زمان، همچنان در حال گذشتن است.
            </p>
            <div className="row gap-8 mt-16">
              <Button variant="primary" size="sm" onClick={() => setConfirmLeave(false)}>
                ادامهٔ آزمون
              </Button>
              <Button variant="ghost" size="sm" onClick={() => navigate('/exam', { replace: true })}>
                خروج
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
