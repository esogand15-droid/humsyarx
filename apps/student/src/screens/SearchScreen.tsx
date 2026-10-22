import { useCallback, useEffect, useRef, useState } from 'react';

import { AppBar, Card, EmptyState, SkeletonStack } from '../components';
import { Icon } from '../icons';
import { searchApi } from '../lib/search';
import type { SearchResultItem } from '../lib/search';
import { errorText } from '../lib/api';

const TYPE_ICONS: Record<string, string> = {
  resource: 'i-file-text',
  question: 'i-help-circle',
  faq: 'i-message-circle',
  schedule: 'i-calendar',
  subject: 'i-book',
  book: 'i-book-open',
};

const TYPE_LABELS: Record<string, string> = {
  resource: 'منبع',
  question: 'سؤال',
  faq: 'پرسش',
  schedule: 'برنامه',
  subject: 'مرجع',
  book: 'کتاب',
};

function ResultRow({ item }: { item: SearchResultItem }) {
  return (
    <div className="list__item" style={{ padding: '14px 16px' }}>
      <Icon name={TYPE_ICONS[item.type] as any || 'i-file-text'} size={20} className="lead" />
      <span className="grow">
        <span className="h3" style={{ display: 'block' }}>{item.title}</span>
        {item.subtitle && (
          <span className="small" style={{ display: 'block' }}>{item.subtitle}</span>
        )}
      </span>
      <span style={{ fontSize: 10, padding: '3px 8px', borderRadius: 999, background: 'var(--paper-3)', color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>
        {TYPE_LABELS[item.type] || item.type}
      </span>
    </div>
  );
}

/** جستجوی سراسری — در منابع، سؤالات، برنامه و مرجع */
export function SearchScreen() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [searched, setSearched] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const search = useCallback(async (q: string) => {
    if (!q.trim() || q.trim().length < 2) {
      setResults([]);
      setSearched(false);
      return;
    }
    setLoading(true);
    setError('');
    setSearched(true);
    try {
      const res = await searchApi.global(q.trim());
      const all: SearchResultItem[] = [];
      const map = res.results || {};
      Object.entries(map).forEach(([type, items]) => {
        if (Array.isArray(items)) {
          items.forEach((it: any) => {
            all.push({
              id: it.id || it._id || String(Math.random()),
              title: it.title || it.name || it.question || it.lesson || '—',
              type: type.replace(/s$/, '') as any,
              subtitle: it.subtitle || it.topic || it.teacher || (it.answer ? it.answer.slice(0, 60) : undefined),
            });
          });
        }
      });
      setResults(all);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const id = setTimeout(() => {
      if (query.trim().length >= 2) {
        void search(query);
      }
    }, 400);
    return () => clearTimeout(id);
  }, [query, search]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  return (
    <>
      <AppBar title="جستجو" sub="جستجوی سراسری در محتوا" />
      <div className="page">
        <div className="row gap-8" style={{ position: 'sticky', top: 0, zIndex: 5, background: 'var(--paper)', padding: '8px 0' }}>
          <div className="grow" style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-3)', pointerEvents: 'none' }}>
              <Icon name="i-search" size={18} />
            </span>
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="جستجو در منابع، سؤالات، برنامه…"
              style={{
                width: '100%',
                height: 46,
                padding: '0 42px 0 14px',
                borderRadius: 13,
                border: '1px solid var(--line)',
                background: 'var(--paper-2)',
                fontSize: 15,
                fontFamily: 'inherit',
                outline: 'none',
              }}
            />
            {query && (
              <button
                onClick={() => { setQuery(''); setResults([]); setSearched(false); inputRef.current?.focus(); }}
                style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 0, cursor: 'pointer', color: 'var(--ink-3)' }}
              >
                <Icon name="i-x" size={18} />
              </button>
            )}
          </div>
        </div>

        {loading && <div className="mt-8"><SkeletonStack rows={4} /></div>}

        {error && !loading && (
          <div className="mt-16" style={{ textAlign: 'center' }}>
            <p className="body">{error}</p>
            <button className="btn mt-8" onClick={() => search(query)}>تلاش دوباره</button>
          </div>
        )}

        {!loading && !error && searched && results.length === 0 && (
          <div className="mt-16">
            <EmptyState
              icon="i-search"
              title="نتیجه‌ای پیدا نشد"
              text={`برای «${query}» چیزی نداریم. کلمهٔ دیگری امتحان کن.`}
            />
          </div>
        )}

        {!loading && !error && results.length > 0 && (
          <>
            <div className="row row--between mt-8">
              <div className="small">{results.length} نتیجه</div>
            </div>
            <Card variant="flush" className="mt-8">
              {results.map((item) => (
                <ResultRow key={`${item.type}-${item.id}`} item={item} />
              ))}
            </Card>
          </>
        )}

        {!searched && !loading && (
          <div className="mt-24" style={{ textAlign: 'center', opacity: 0.5 }}>
            <Icon name="i-search" size={48} />
            <p className="body mt-12">برای جستجو چیزی بنویس</p>
          </div>
        )}
      </div>
    </>
  );
}
