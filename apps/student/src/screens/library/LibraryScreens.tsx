import { useCallback } from 'react';
import { useParams } from 'react-router-dom';

import { AppBar, Card, Chip, EmptyState, ListRow } from '../../components';
import { ErrorBlock, LoadingBlock } from '../../components/AccessStates';
import { Icon } from '../../icons';
import { fileLabel, humanSize, library } from '../../lib/library';
import type { BookItem, ContentFile, LessonItem, ReferenceFile, SessionItem } from '../../lib/library';
import { fa } from '../../lib/library';
import { useAsync } from '../../lib/useAsync';

/* سه سطح کتابخانه (ترم → درس → جلسه → فایل) و دو سطح مرجع
   (موضوع → کتاب → فایل). هر صفحه همان سه حالت بارگذاری/خطا/خالی را دارد. */

function Shell({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <>
      <AppBar title={title} sub={sub} back />
      <div className="page">{children}</div>
    </>
  );
}

/* ─────────────── ۱) درس‌های یک ترم ─────────────── */
export function TermScreen() {
  const { term = '' } = useParams();
  const run = useCallback(() => library.lessons(term), [term]);
  const { data, error, loading, reload } = useAsync(run, [term]);

  return (
    <Shell title={term || 'ترم'} sub="درس‌های این ترم">
      {loading && <LoadingBlock />}
      {!loading && error != null && <ErrorBlock error={error} onRetry={reload} />}
      {!loading && !error && data && data.lessons.length === 0 && (
        <EmptyState icon="i-book" title="درسی در این ترم نیست" text="شاید محتوای این ترم هنوز منتشر نشده است." />
      )}
      {!loading && !error && data && data.lessons.length > 0 && (
        <Card variant="flush" className="mt-16">
          {data.lessons.map((l: LessonItem) => (
            <ListRow
              key={l._id}
              icon="i-book"
              title={l.name}
              sub={[l.teacher, `${fa(l.session_count)} جلسه`].filter(Boolean).join(' · ')}
              to={`/library/lesson/${l._id}`}
              chevron
            />
          ))}
        </Card>
      )}
    </Shell>
  );
}

/* ─────────────── ۲) جلسه‌های یک درس ─────────────── */
export function LessonScreen() {
  const { id = '' } = useParams();
  const run = useCallback(() => library.sessions(id), [id]);
  const { data, error, loading, reload } = useAsync(run, [id]);

  return (
    <Shell title="جلسه‌ها" sub="ویدیو، جزوه و ویس هر جلسه">
      {loading && <LoadingBlock />}
      {!loading && error != null && <ErrorBlock error={error} onRetry={reload} />}
      {!loading && !error && data && data.sessions.length === 0 && (
        <EmptyState icon="i-video" title="جلسه‌ای ثبت نشده" text="برای این درس هنوز جلسه‌ای منتشر نشده است." />
      )}
      {!loading && !error && data && data.sessions.length > 0 && (
        <Card variant="flush" className="mt-16">
          {data.sessions.map((s: SessionItem) => (
            <ListRow
              key={s._id}
              icon="i-play"
              title={`جلسهٔ ${fa(s.number)} — ${s.topic}`}
              sub={[s.teacher, `${fa(s.file_count)} فایل`].filter(Boolean).join(' · ')}
              to={`/library/session/${s._id}`}
              chevron
            />
          ))}
        </Card>
      )}
    </Shell>
  );
}

/* ─────────────── ۳) فایل‌های یک جلسه ─────────────── */
export function SessionScreen() {
  const { id = '' } = useParams();
  const run = useCallback(() => library.files(id), [id]);
  const { data, error, loading, reload } = useAsync(run, [id]);

  const iconFor = (kind: string) => {
    if (kind === 'video') return 'i-video' as const;
    if (kind === 'voice') return 'i-headphones' as const;
    if (kind === 'pdf' || kind === 'ppt') return 'i-doc' as const;
    if (kind === 'test') return 'i-flask' as const;
    return 'i-doc' as const;
  };

  return (
    <Shell title="فایل‌های جلسه" sub="نوع، حجم و منبع">
      {loading && <LoadingBlock />}
      {!loading && error != null && <ErrorBlock error={error} onRetry={reload} />}
      {!loading && !error && data && data.files.length === 0 && (
        <EmptyState icon="i-doc" title="فایلی برای این جلسه نیست" text="ممکن است فایل‌ها در حال آماده‌سازی باشند." />
      )}
      {!loading && !error && data && data.files.length > 0 && (
        <>
          <Card variant="flush" className="mt-16">
            {data.files.map((f: ContentFile) => (
              <ListRow
                key={f.id}
                icon={iconFor(f.type)}
                title={f.name}
                sub={[fileLabel(f.type), humanSize(f.size)].filter(Boolean).join(' · ')}
                meta={f.downloads > 0 ? `${fa(f.downloads)} بار دریافت شده` : undefined}
                trailing={f.preview ? <Chip variant="quiet">پیش‌نمایش</Chip> : undefined}
              />
            ))}
          </Card>
          <p className="notice notice--quiet mt-16" role="note">
            خواندن و پخش داخل هامزیار در فاز P3 فعال می‌شود؛ تا آن زمان این فهرست فقط برای شناخت
            محتوای هر جلسه است. لینک مستقیم فایل عمداً ساخته نمی‌شود.
          </p>
        </>
      )}
    </Shell>
  );
}

/* ─────────────── ۴) کتاب‌های یک موضوع مرجع ─────────────── */
export function SubjectScreen() {
  const { id = '' } = useParams();
  const run = useCallback(() => library.books(id), [id]);
  const { data, error, loading, reload } = useAsync(run, [id]);

  return (
    <Shell title={data?.subject.name ?? 'موضوع'} sub="کتاب‌های این موضوع">
      {loading && <LoadingBlock />}
      {!loading && error != null && <ErrorBlock error={error} onRetry={reload} />}
      {!loading && !error && data && data.books.length === 0 && (
        <EmptyState icon="i-layers" title="کتابی ثبت نشده" text="برای این موضوع هنوز کتابی منتشر نشده است." />
      )}
      {!loading && !error && data && data.books.length > 0 && (
        <Card variant="flush" className="mt-16">
          {data.books.map((b: BookItem) => (
            <ListRow
              key={b.id}
              icon="i-book"
              title={b.name}
              sub={[
                b.fa_count ? `${fa(b.fa_count)} جلد فارسی` : '',
                b.en_count ? `${fa(b.en_count)} جلد انگلیسی` : '',
              ]
                .filter(Boolean)
                .join(' · ')}
              to={`/library/book/${b.id}`}
              chevron
            />
          ))}
        </Card>
      )}
    </Shell>
  );
}

/* ─────────────── ۵) فایل‌های یک کتاب مرجع ─────────────── */
function RefRow({ f }: { f: ReferenceFile }) {
  return (
    <ListRow
      icon="i-doc"
      title={f.description || `جلد ${fa(f.volume)}`}
      sub={[f.lang === 'fa' ? 'فارسی' : 'انگلیسی', `جلد ${fa(f.volume)}`, humanSize(f.size)]
        .filter(Boolean)
        .join(' · ')}
      trailing={f.preview ? <Chip variant="quiet">پیش‌نمایش</Chip> : undefined}
    />
  );
}

export function BookScreen() {
  const { id = '' } = useParams();
  const run = useCallback(() => library.bookFiles(id), [id]);
  const { data, error, loading, reload } = useAsync(run, [id]);

  return (
    <Shell title={data?.book.name ?? 'کتاب'} sub="جلدهای فارسی و انگلیسی">
      {loading && <LoadingBlock />}
      {!loading && error != null && <ErrorBlock error={error} onRetry={reload} />}
      {!loading && !error && data && data.fa_files.length + data.en_files.length === 0 && (
        <EmptyState icon="i-doc" title="فایلی برای این کتاب نیست" text="جلدها هنوز بارگذاری نشده‌اند." />
      )}

      {!loading && !error && data && data.fa_files.length > 0 && (
        <>
          <div className="row gap-8 mt-16" style={{ alignItems: 'center' }}>
            <Icon name="i-doc" size={16} />
            <span className="h3">فارسی</span>
          </div>
          <Card variant="flush" className="mt-8">
            {data.fa_files.map((f) => (
              <RefRow key={f.id} f={f} />
            ))}
          </Card>
        </>
      )}

      {!loading && !error && data && data.en_files.length > 0 && (
        <>
          <div className="row gap-8 mt-20" style={{ alignItems: 'center' }}>
            <Icon name="i-doc" size={16} />
            <span className="h3">انگلیسی</span>
          </div>
          <Card variant="flush" className="mt-8">
            {data.en_files.map((f) => (
              <RefRow key={f.id} f={f} />
            ))}
          </Card>
        </>
      )}

      {!loading && !error && (
        <p className="notice notice--quiet mt-16" role="note">
          خواندن کتاب مرجع داخل اپ در فاز P3 فعال می‌شود.
        </p>
      )}
    </Shell>
  );
}
