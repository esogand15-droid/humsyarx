import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { AppBar, Card, Chip, EmptyState, ListRow } from '../../components';
import { ErrorBlock, LoadingBlock } from '../../components/AccessStates';
import { Icon } from '../../icons';
import { fa } from '../../lib/library';
import { accuracyTone, exam, type LessonItem, type StatsPayload, type TopicItem } from '../../lib/exam';

/** تمرین — انتخاب درس و مبحث، بعد شروع.
 *
 *  عددها همه از سرور می‌آیند (`/exam/stats`, شمار سؤال هر درس). هیچ
 *  درصد یا آمار ساختگی روی صفحه نمی‌نشیند.
 */
export function ExamHome() {
  const navigate = useNavigate();
  const [lessons, setLessons] = useState<LessonItem[]>([]);
  const [stats, setStats] = useState<StatsPayload | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<unknown>(null);

  // درس انتخاب‌شده و مبحث‌هایش
  const [picked, setPicked] = useState<LessonItem | null>(null);
  const [topics, setTopics] = useState<TopicItem[]>([]);
  const [topicsLoading, setTopicsLoading] = useState(false);

  const load = useCallback(async () => {
    setState('loading');
    setError(null);
    try {
      const [less, st] = await Promise.all([
        exam.lessons(),
        exam.stats().catch(() => null),
      ]);
      setLessons(less.lessons ?? []);
      setStats(st);
      setState('ready');
    } catch (err) {
      setError(err);
      setState('error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const pick = async (lesson: LessonItem) => {
    if (picked?.id === lesson.id) {
      setPicked(null);
      setTopics([]);
      return;
    }
    setPicked(lesson);
    setTopics([]);
    setTopicsLoading(true);
    try {
      const res = await exam.topics(lesson.id);
      setTopics(res.topics ?? []);
    } catch {
      setTopics([]);
    } finally {
      setTopicsLoading(false);
    }
  };

  const start = (topic?: TopicItem) => {
    if (!picked) {
      navigate('/exam/practice');
      return;
    }
    const params = new URLSearchParams({ lesson: picked.name, lessonId: picked.id });
    if (topic) {
      params.set('topic', topic.name);
      params.set('topicId', topic.id);
    }
    navigate(`/exam/practice?${params.toString()}`);
  };

  const accuracy = stats?.accuracy ?? 0;

  return (
    <>
      <AppBar title="تمرین" sub="بانک سؤال" back onBack={() => navigate(-1)} />
      <div className="page">
        {state === 'loading' && <LoadingBlock rows={3} />}
        {state === 'error' && <ErrorBlock error={error} onRetry={() => void load()} />}

        {state === 'ready' && (
          <>
            {/* آمار واقعی — فقط اگر کاربر قبلاً پاسخی داده باشد */}
            {stats && stats.attempts > 0 ? (
              <Card className="mt-16">
                <div className="row gap-8" style={{ alignItems: 'baseline' }}>
                  <span className="h2 num">{fa(Math.round(accuracy))}٪</span>
                  <span className="small">درست از {fa(stats.attempts)} پاسخ</span>
                  <span className="grow" />
                  <Chip variant={accuracyTone(accuracy) === 'good' ? 'cyan' : 'quiet'}>
                    {fa(stats.solved_unique)} سؤال یکتا
                  </Chip>
                </div>
                <div
                  className="mt-8"
                  role="progressbar"
                  aria-valuenow={Math.round(accuracy)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label="درصد پاسخ‌های درست"
                >
                  <div className="bar">
                    <i style={{ width: `${Math.round(accuracy)}%` }} />
                  </div>
                </div>
                {stats.weak_topics.length > 0 && (
                  <p className="tiny mt-8">
                    نقطهٔ ضعف شناخته‌شده: {stats.weak_topics.slice(0, 2).map((t) => t.topic || t.lesson).join(' · ')}
                  </p>
                )}
              </Card>
            ) : (
              <Card variant="quiet" className="mt-16">
                <p className="small">
                  هنوز سؤالی پاسخ نداده‌ای. با «شروع تمرین» اولین سؤال می‌آید؛ آمار همین‌جا ساخته می‌شود.
                </p>
              </Card>
            )}

            <div className="row gap-8 mt-16">
              <button type="button" className="btn btn--primary grow" onClick={() => start()}>
                شروع تمرین آزاد
              </button>
            </div>
            {!picked && (
              <p className="tiny mt-8">
                تمرین آزاد از همهٔ درس‌های مجاز تو سؤال می‌آورد. برای محدودکردن، یک درس را انتخاب کن.
              </p>
            )}

            <div className="section__head row gap-8 mt-16" style={{ alignItems: 'center' }}>
              <Icon name="i-grid" size={16} />
              <span className="h3">درس‌ها</span>
              <span className="grow" />
              <span className="tiny">{fa(lessons.length)} درس</span>
            </div>

            {lessons.length === 0 ? (
              <EmptyState
                icon="i-doc"
                title="سؤالی برای ورودی تو ثبت نشده"
                text="بانک سؤال بر پایهٔ ورودی تحصیلی و اشتراک فعال سرو می‌شود. اگر تازه عضو شده‌ای، بعد از تأیید ورودی سؤال‌ها همین‌جا می‌آیند."
              />
            ) : (
              <Card variant="flush" className="mt-8">
                {lessons.map((l) => (
                  <div key={l.id}>
                    <ListRow
                      icon="i-flask"
                      title={l.name}
                      sub={`${fa(l.count)} سؤال${l.term ? ` · ${l.term}` : ''}`}
                      chevron={picked?.id !== l.id}
                      onClick={() => void pick(l)}
                    />
                    {picked?.id === l.id && (
                      <div className="lesson-open">
                        {topicsLoading && <p className="small">در حال خواندن مبحث‌ها…</p>}
                        {!topicsLoading && topics.length === 0 && (
                          <p className="small">این درس مبحث‌بندی ندارد؛ کل درس تمرین می‌شود.</p>
                        )}
                        {!topicsLoading && topics.length > 0 && (
                          <>
                            <div className="row gap-8" style={{ flexWrap: 'wrap' }}>
                              {topics.map((t) => (
                                <button
                                  key={t.id}
                                  type="button"
                                  className="chip-btn"
                                  onClick={() => start(t)}
                                >
                                  {t.name}
                                  <span className="tiny num"> · {fa(t.count)}</span>
                                </button>
                              ))}
                            </div>
                            <button type="button" className="btn btn--ghost btn--sm mt-12" onClick={() => start()}>
                              کل {l.name}
                            </button>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </Card>
            )}

            <Card variant="flush" className="mt-16">
              <Link to="/exam/history">
                <ListRow icon="i-clock" title="تاریخچهٔ پاسخ‌ها" sub="هر چه پاسخ داده‌ای، با پاسخ صحیح" chevron onClick={() => {}} />
              </Link>
            </Card>
          </>
        )}
      </div>
    </>
  );
}
