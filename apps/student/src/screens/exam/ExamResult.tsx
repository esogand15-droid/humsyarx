import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { AppBar, Button, Card, Chip } from '../../components';
import { ErrorBlock, LoadingBlock } from '../../components/AccessStates';
import { Icon } from '../../icons';
import { fa } from '../../lib/library';
import { OPTION_LETTERS, accuracyTone, mockExam, type MockReview } from '../../lib/exam';

/** کارنامه + بازبینی.
 *
 *  اعداد از خودِ سند آزمون می‌آیند (`answered`, `correct`, `percentage`).
 *  بازبینی فقط برای آزمون تمام‌شده در دسترس است؛ سرور برای آزمون فعال
 *  ۴۰۹ می‌دهد، پس این صفحه هرگز پاسخ‌های صحیح آزمون جاری را لو نمی‌دهد.
 */
export function ExamResult() {
  const { sid = '' } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<MockReview | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error' | 'active'>('loading');

  const load = useCallback(async () => {
    setState('loading');
    try {
      const res = await mockExam.review(sid);
      setData(res);
      setState('ready');
    } catch (err) {
      const code = (err as { code?: string })?.code ?? '';
      // آزمون هنوز تمام نشده → برگرد به اجرای آزمون
      if (code === 'exam_still_active') setState('active');
      else setState('error');
    }
  }, [sid]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (state === 'active') navigate(`/exam/run/${sid}`, { replace: true });
  }, [state, sid, navigate]);

  const pct = data ? Math.round(data.percentage) : 0;
  const tone = accuracyTone(pct);

  return (
    <>
      <AppBar title="کارنامه" sub={data?.exam_code ? `کد ${data.exam_code}` : 'نتیجهٔ آزمون'} back onBack={() => navigate('/exam')} />
      <div className="page">
        {state === 'loading' && <LoadingBlock rows={3} />}
        {state === 'error' && <ErrorBlock error={null} onRetry={() => void load()} />}

        {state === 'ready' && data && (
          <>
            <Card className="mt-16" style={{ textAlign: 'center' }}>
              <div className={`score score--${tone}`}>
                <span className="score__n num">{fa(pct)}</span>
                <span className="score__u">٪</span>
              </div>
              <p className="small mt-8">
                {fa(data.correct)} پاسخ درست از {fa(data.answered)} پاسخ
                {data.total > data.answered ? ` · ${fa(data.total - data.answered)} سؤال بی‌پاسخ` : ''}
              </p>
              <div className="row gap-8 mt-12" style={{ justifyContent: 'center', flexWrap: 'wrap' }}>
                <Chip variant="quiet">{data.lesson}{data.topic ? ` · ${data.topic}` : ''}</Chip>
                <Chip variant="quiet">{fa(data.total)} سؤال</Chip>
                {data.minutes > 0 && <Chip variant="quiet">{fa(data.minutes)} دقیقه</Chip>}
              </div>
            </Card>

            <div className="row gap-8 mt-16">
              <Button variant="primary" size="sm" onClick={() => navigate('/exam/setup', { replace: true })}>
                آزمون تازه
              </Button>
              <Button variant="ghost" size="sm" onClick={() => navigate('/exam/mock/history')}>
                آزمون‌های قبلی
              </Button>
            </div>

            <div className="section__head mt-16">
              <Icon name="i-check" size={16} />
              <span className="h3">بازبینی</span>
            </div>

            {data.review.length === 0 ? (
              <p className="small mt-8">پاسخی برای بازبینی ثبت نشده است.</p>
            ) : (
              <div className="mt-8" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {data.review.map((r, idx) => (
                  <article key={`${r.question_id}-${idx}`} className="q-card q-card--review">
                    <div className="row gap-8" style={{ alignItems: 'center' }}>
                      <span className="tiny num">سؤال {fa(idx + 1)}</span>
                      <span className="grow" />
                      <Chip variant={r.is_correct ? 'cyan' : 'quiet'} icon={r.is_correct ? 'i-check' : undefined}>
                        {r.is_correct ? 'درست' : 'غلط'}
                      </Chip>
                    </div>
                    {r.image_url && (
                      <img className="q-img mt-8" src={r.image_url} alt="تصویر سؤال" loading="lazy" />
                    )}
                    <p className="q-stem mt-8" style={{ fontSize: 14.5 }}>
                      {r.question ?? 'متن سؤال در دسترس نیست.'}
                    </p>
                    <p className="tiny mt-8">
                      پاسخ تو: <b>{OPTION_LETTERS[r.selected] ?? r.selected}</b>
                      {r.options?.[r.selected] ? ` — ${r.options[r.selected]}` : ''} · پاسخ درست:{' '}
                      <b>{OPTION_LETTERS[r.correct_answer] ?? r.correct_answer}</b>
                      {r.options?.[r.correct_answer] ? ` — ${r.options[r.correct_answer]}` : ''}
                    </p>
                    {r.explanation && <p className="tiny mt-8">{r.explanation}</p>}
                  </article>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
