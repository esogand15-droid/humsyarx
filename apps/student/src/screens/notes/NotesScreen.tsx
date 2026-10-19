import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { AppBar, Card, EmptyState, ListRow } from '../../components';
import type { IconName } from '../../icons';
import { ErrorBlock, LoadingBlock } from '../../components/AccessStates';
import { fa } from '../../lib/library';
import { ink, type NoteItem } from '../../lib/ink';
import { readerPath } from '../../lib/reader';

const ICON: Record<string, IconName> = {
  pdf: 'i-doc',
  video: 'i-video',
  audio: 'i-headphones',
  image: 'i-doc',
};

/** دفتر من — فایل‌هایی که روی آن‌ها نوشته‌ام (`/me/notes`، SC-061).
 *
 *  عددها از خودِ استروک‌ها می‌آید (تعداد صفحه و خط)، نه تخمین درصد.
 *  اگر فایلی از دسترس خارج شده باشد، ردیف با برچسب «در دسترس نیست»
 *  می‌ماند تا یادداشت‌ها به‌کلی ناپدید نشوند.
 */
export function NotesScreen() {
  const navigate = useNavigate();
  const [items, setItems] = useState<NoteItem[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');

  const load = useCallback(async () => {
    setState('loading');
    try {
      const res = await ink.notes();
      setItems(res.items ?? []);
      setState('ready');
    } catch {
      setState('error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <AppBar title="دفتر من" sub="هر چیزی که روی آن نوشته‌ای" back onBack={() => navigate(-1)} />
      <div className="page">
        {state === 'loading' && <LoadingBlock rows={3} />}

        {state === 'error' && <ErrorBlock error={null} onRetry={() => void load()} />}

        {state === 'ready' && items.length === 0 && (
          <EmptyState
            icon="i-doc"
            title="هنوز یادداشتی نداری"
            text="داخل یک جزوه، قلم را از نوار پایین انتخاب کن؛ هر خطی که بکشی همین‌جا فهرست می‌شود و روی هر دستگاهی دوباره دیده می‌شود."
          />
        )}

        {state === 'ready' && items.length > 0 && (
          <Card variant="flush" className="mt-16">
            {items.map((n) => (
              <ListRow
                key={`${n.scope}:${n.id}`}
                icon={ICON[n.kind] ?? 'i-doc'}
                title={n.name}
                sub={
                  n.available
                    ? `${fa(n.pages)} صفحه · ${fa(n.strokes)} خط · آخرین صفحه ${fa(n.last_page)}`
                    : 'این فایل دیگر در دسترس نیست — یادداشت‌ها محفوظ‌اند'
                }
                to={n.available ? `${readerPath(n.scope, n.id)}?p=${n.last_page}` : undefined}
                chevron={n.available}
              />
            ))}
          </Card>
        )}
      </div>
    </>
  );
}
