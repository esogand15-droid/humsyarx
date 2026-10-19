import { useCallback, useEffect, useState } from 'react';

import { AppBar, Card, Chip, EmptyState, ListRow } from '../../components';
import { ErrorBlock, LoadingBlock, LockedBlock } from '../../components/AccessStates';
import { library } from '../../lib/library';
import type { LibraryState, SubjectItem, TermItem } from '../../lib/library';
import { fa } from '../../lib/library';

type Tab = 'lessons' | 'references';

/** کتابخانه — ریشهٔ دو شاخه: «درس‌ها» (منابع علوم پایه) و «مرجع».
    دو شاخه گیت مستقل دارند، پس وضعیت هر تب جدا خوانده می‌شود. */
export function LibraryScreen() {
  const [tab, setTab] = useState<Tab>('lessons');
  const [state, setState] = useState<LibraryState | null>(null);
  const [terms, setTerms] = useState<TermItem[] | null>(null);
  const [subjects, setSubjects] = useState<SubjectItem[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const st = await library.state();
      setState(st);

      if (st.resources.allowed) {
        const t = await library.terms();
        setTerms(t.terms);
      } else {
        setTerms([]);
      }
      if (st.references.allowed) {
        const s = await library.subjects();
        setSubjects(s.subjects);
      } else {
        setSubjects([]);
      }
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const gate = state ? (tab === 'lessons' ? state.resources : state.references) : null;
  const rows = tab === 'lessons' ? terms : subjects;

  return (
    <>
      <AppBar title="کتابخانه" sub={state?.intake ? `ورودی ${state.intake}` : 'جزوه‌ها و منابع'} />
      <div className="page">
        <div className="seg mt-16" role="tablist" aria-label="بخش کتابخانه">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'lessons'}
            className={`seg__btn ${tab === 'lessons' ? 'is-on' : ''}`.trim()}
            onClick={() => setTab('lessons')}
          >
            درس‌ها
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'references'}
            className={`seg__btn ${tab === 'references' ? 'is-on' : ''}`.trim()}
            onClick={() => setTab('references')}
          >
            مرجع
          </button>
        </div>

        {loading && <LoadingBlock rows={4} />}

        {!loading && error != null && <ErrorBlock error={error} onRetry={() => void load()} />}

        {!loading && !error && gate && !gate.allowed && (
          <LockedBlock
            title={
              gate.code === 'policy_unavailable'
                ? 'سیستم دسترسی در دسترس نیست'
                : tab === 'lessons'
                  ? 'کتابخانهٔ درس‌ها برای مشترکین است'
                  : 'کتاب مرجع برای مشترکین است'
            }
            text={
              gate.code === 'policy_unavailable'
                ? 'چند لحظه بعد دوباره تلاش کن؛ این وضعیت موقتی است.'
                : 'با اشتراک فعال، همهٔ جزوه‌ها، ویدیوها و ویس‌های ترم خودت باز می‌شوند.'
            }
            code={gate.code ?? undefined}
          />
        )}

        {!loading && !error && gate?.allowed && rows && rows.length === 0 && (
          <EmptyState
            icon={tab === 'lessons' ? 'i-book' : 'i-layers'}
            title={tab === 'lessons' ? 'هنوز ترمی برای تو ثبت نشده' : 'هنوز موضوعی ثبت نشده'}
            text={
              tab === 'lessons'
                ? 'محتوا بر اساس ورودی تحصیلی دسته‌بندی می‌شود. اگر ورودی‌ات تازه ثبت شده، ممکن است محتوای آن هنوز منتشر نشده باشد.'
                : 'کتاب‌های مرجع هنوز برای ورودی تو منتشر نشده‌اند.'
            }
          />
        )}

        {!loading && !error && gate?.allowed && rows && rows.length > 0 && (
          <Card variant="flush" className="mt-16">
            {tab === 'lessons'
              ? (rows as TermItem[]).map((t) => (
                  <ListRow
                    key={t.name}
                    icon="i-calendar"
                    title={t.name}
                    sub={`${fa(t.lesson_count)} درس`}
                    to={`/library/term/${encodeURIComponent(t.name)}`}
                    chevron
                  />
                ))
              : (rows as SubjectItem[]).map((s) => (
                  <ListRow
                    key={s.id}
                    icon="i-layers"
                    title={s.name}
                    sub={`${fa(s.book_count)} کتاب`}
                    to={`/library/subject/${s.id}`}
                    chevron
                  />
                ))}
          </Card>
        )}

        {!loading && !error && (
          <p className="tiny mt-16" style={{ textAlign: 'center' }}>
            <Chip variant="quiet" icon="i-lock">
              محتوا فقط داخل هامزیار خوانده می‌شود
            </Chip>
          </p>
        )}
      </div>
    </>
  );
}
