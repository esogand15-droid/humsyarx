import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { AppBar, Button, Chip, EmptyState } from '../../components';
import { ErrorBlock, LoadingBlock } from '../../components/AccessStates';
import { Icon } from '../../icons';
import { fa } from '../../lib/library';
import {
  OPTION_LETTERS,
  exam,
  type AnswerPayload,
  type NextPayload,
  type Question,
} from '../../lib/exam';

/** تمرین یک‌سؤالی.
 *
 *  قرارداد مهم: **پاسخ صحیح قبل از پاسخ‌دادن در مرورگر نیست.** کلید
 *  درست فقط از `/exam/answer` می‌آید. انتخاب کاربر تا لحظهٔ ثبت، فقط
 *  در حافظهٔ همین صفحه است (پس با رفرش، انتخاب نیمه‌کاره از بین می‌رود —
 *  همان رفتاری که مینی‌اپ دارد و از ثبت پاسخ بدون قصد جلوگیری می‌کند).
 */
export function PracticeScreen() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const lesson = params.get('lesson') ?? undefined;
  const topic = params.get('topic') ?? undefined;

  const [data, setData] = useState<NextPayload | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<unknown>(null);

  const [selected, setSelected] = useState<number | null>(null);
  const [result, setResult] = useState<AnswerPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [answered, setAnswered] = useState(0); // شمار پاسخ‌های همین نشست
  const inFlight = useRef(false);

  const load = useCallback(async () => {
    setState('loading');
    setError(null);
    setSelected(null);
    setResult(null);
    try {
      const res = await exam.next(lesson, topic);
      setData(res);
      setState('ready');
    } catch (err) {
      setError(err);
      setState('error');
    }
  }, [lesson, topic]);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = async () => {
    const q: Question | null = data?.question ?? null;
    if (!q || selected === null || result || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      const res = await exam.answer(q.id, selected);
      setResult(res);
      setAnswered((n) => n + 1);
    } catch (err) {
      // خطای شبکه: انتخاب کاربر حفظ می‌شود تا دوباره بزند
      setError(err);
      setState('error');
    } finally {
      setBusy(false);
      inFlight.current = false;
    }
  };

  const next = () => void load();

  // کیبورد: ۱..۴ انتخاب، Enter ثبت/بعدی
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!data?.question) return;
      const n = ['1', '2', '3', '4'].indexOf(e.key);
      if (n >= 0 && !result) {
        e.preventDefault();
        setSelected(n);
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        if (result) next();
        else void submit();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const q = data?.question ?? null;
  const progress = data?.progress;
  const scopeLabel = [lesson, topic].filter(Boolean).join(' · ') || 'تمرین آزاد';

  return (
    <>
      <AppBar
        title={scopeLabel}
        sub={
          progress
            ? `${fa(progress.solved_unique)} از ${fa(progress.total)} سؤال حل شده`
            : 'در حال آماده‌سازی'
        }
        back
        onBack={() => navigate(-1)}
      />

      <div className="page">
        {state === 'loading' && <LoadingBlock rows={3} />}
        {state === 'error' && <ErrorBlock error={error} onRetry={() => void load()} />}

        {state === 'ready' && !q && (
          <EmptyState
            icon="i-check"
            title="این بخش را تمام کردی"
            text={
              progress && progress.total > 0
                ? `همهٔ ${fa(progress.total)} سؤال این محدوده را پاسخ داده‌ای. برای ادامه، درس یا مبحث دیگری انتخاب کن.`
                : 'در این محدوده سؤالی برای ورودی و اشتراک فعلی تو ثبت نشده است.'
            }
            action={
              <Button variant="primary" size="sm" onClick={() => navigate('/exam')}>
                انتخاب درس دیگر
              </Button>
            }
          />
        )}

        {state === 'ready' && q && (
          <>
            {progress && progress.total > 0 && (
              <div
                className="mt-12"
                role="progressbar"
                aria-valuenow={progress.solved_unique}
                aria-valuemin={0}
                aria-valuemax={progress.total}
                aria-label="پیشرفت در این محدوده"
              >
                <div className="bar">
                  <i style={{ width: `${Math.round((100 * progress.solved_unique) / progress.total)}%` }} />
                </div>
              </div>
            )}

            <article className="q-card mt-16">
              <div className="row gap-8" style={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <Chip variant="quiet">{q.difficulty_label || 'متوسط'}</Chip>
                {q.topic && <Chip variant="quiet">{q.topic}</Chip>}
                {q.exam_session_label && <Chip variant="quiet">{q.exam_session_label}</Chip>}
                <span className="grow" />
                {answered > 0 && <span className="tiny">این نشست: {fa(answered)} پاسخ</span>}
              </div>

              {q.image_url && (
                <img className="q-img mt-12" src={q.image_url} alt={q.image.alt_text || 'تصویر سؤال'} loading="lazy" />
              )}

              <p className="q-stem mt-12">{q.question}</p>

              <ul className="q-options" role="radiogroup" aria-label="گزینه‌ها">
                {q.options.map((opt, i) => {
                  const isPicked = selected === i;
                  const isRight = result && result.correct_answer === i;
                  const isWrongPick = result && isPicked && !result.is_correct;
                  return (
                    <li key={i}>
                      <button
                        type="button"
                        role="radio"
                        aria-checked={isPicked}
                        className={`q-opt${isPicked ? ' is-picked' : ''}${isRight ? ' is-right' : ''}${
                          isWrongPick ? ' is-wrong' : ''
                        }`}
                        onClick={() => !result && setSelected(i)}
                        disabled={!!result}
                      >
                        <span className="q-opt__l" aria-hidden="true">
                          {OPTION_LETTERS[i] ?? i + 1}
                        </span>
                        <span className="q-opt__t">{opt}</span>
                        {isRight && <Icon name="i-check" size={16} />}
                      </button>
                    </li>
                  );
                })}
              </ul>

              {result && (
                <div className={`q-feedback ${result.is_correct ? 'is-ok' : 'is-no'}`} role="status">
                  <p className="h3">
                    {result.is_correct ? 'درست بود' : `پاسخ درست: ${OPTION_LETTERS[result.correct_answer] ?? ''}`}
                  </p>
                  {result.explanation ? (
                    <p className="small mt-8">{result.explanation}</p>
                  ) : (
                    <p className="small mt-8">برای این سؤال توضیحی ثبت نشده است.</p>
                  )}
                </div>
              )}

              <div className="row gap-8 mt-16">
                {!result ? (
                  <Button
                    variant="primary"
                    onClick={() => void submit()}
                    disabled={selected === null || busy}
                    aria-busy={busy}
                  >
                    {busy ? 'در حال ثبت…' : 'ثبت پاسخ'}
                  </Button>
                ) : (
                  <Button variant="primary" onClick={next}>
                    سؤال بعدی
                  </Button>
                )}
                <span className="grow" />
                <span className="tiny">با کلیدهای ۱ تا ۴ انتخاب، Enter ثبت</span>
              </div>
            </article>
          </>
        )}
      </div>
    </>
  );
}
