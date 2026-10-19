import { useCallback, useEffect, useState } from 'react';

import { AppBar, Card, Chip, EmptyState, ListRow } from '../../components';
import { Icon } from '../../icons';
import { ErrorBlock, LoadingBlock, LockedBlock } from '../../components/AccessStates';
import { library } from '../../lib/library';
import { reader, readerPath } from '../../lib/reader';
import type { ContinueItem } from '../../lib/reader';
import { ProgressBar } from '../../components';
import type { LibraryState, SubjectItem, TermItem } from '../../lib/library';
import { fa } from '../../lib/library';

type Tab = 'lessons' | 'references';

/** کتابخانه — ریشهٔ دو شاخه: «درس‌ها» (منابع علوم پایه) و «مرجع».
    دو شاخه گیت مستقل دارند، پس وضعیت هر تب جدا خوانده می‌شود. */
const clock = (sec: number) => {
  const m = Math.floor(Math.max(0, sec) / 60);
  const s = Math.floor(Math.max(0, sec) % 60);
  return `${fa(m)}:${s < 10 ? '۰' : ''}${fa(s)}`;
};

export function LibraryScreen() {
  const [tab, setTab] = useState<Tab>('lessons');
  const [state, setState] = useState<LibraryState | null>(null);
  const [terms, setTerms] = useState<TermItem[] | null>(null);
  const [subjects, setSubjects] = useState<SubjectItem[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [recent, setRecent] = useState<ContinueItem[]>([]);

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
      reader
        .recent()
        .then((r) => setRecent(r.items))
        .catch(() => setRecent([]));

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
        {recent.length > 0 && (
          <Card variant="flush" className="mt-16">
            <div className="row gap-8" style={{ padding: '12px 16px 6px', alignItems: 'center' }}>
              <Icon name="i-bookmark" size={16} />
              <span className="h3">ادامهٔ مطالعه</span>
            </div>
            {recent.map((r) => (
              <div key={`${r.scope}:${r.id}`} style={{ padding: '4px 16px 10px' }}>
                <ListRow
                  icon={r.kind === 'audio' ? 'i-headphones' : r.kind === 'video' ? 'i-video' : 'i-doc'}
                  title={r.name}
                  sub={
                    r.total > 0
                      ? `صفحهٔ ${fa(r.page)} از ${fa(r.total)} · ${fa(r.percent)}٪`
                      : r.kind === 'pdf'
                        ? 'در حال خواندن'
                        : `ادامه از ${clock(r.position)}`
                  }
                  to={readerPath(r.scope, r.id)}
                  chevron
                />
                {r.total > 0 && <div role="progressbar" aria-valuenow={r.percent} aria-valuemin={0} aria-valuemax={100} aria-label={`پیشرفت ${r.name}`}>
                  <ProgressBar value={r.percent} thin />
                </div>}
              </div>
            ))}
          </Card>
        )}

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
