import { useEffect, useState } from 'react';

import { fa } from '../../lib/library';
import { ink, type InkSummaryPage, type Scope } from '../../lib/ink';

interface Props {
  scope: Scope;
  id: string;
  page: number;
  open: boolean;
  onClose: () => void;
  onJump: (page: number) => void;
  /** هر بار که خطی ذخیره می‌شود، پنل تازه شود */
  refreshKey: number;
}

/** دفتر این فایل — جای دیگری برای «کجا نوشته‌ام؟»
 *
 *  روی دسکتاپ/تبلت کنار صفحه می‌نشیند و روی گوشی از پایین باز می‌شود؛
 *  در هر دو حالت یک کامپوننت است، چیدمان را CSS تعیین می‌کند.
 */
export function NotebookPanel({ scope, id, page, open, onClose, onJump, refreshKey }: Props) {
  const [pages, setPages] = useState<InkSummaryPage[]>([]);
  const [total, setTotal] = useState(0);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setState('loading');
    (async () => {
      try {
        const res = await ink.summary(scope, id);
        if (cancelled) return;
        setPages(res.pages ?? []);
        setTotal(res.total ?? 0);
        setState('ready');
      } catch {
        if (!cancelled) setState('error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [scope, id, open, refreshKey]);

  if (!open) return null;

  return (
    <aside className="notebook" aria-label="دفتر این فایل">
      <div className="notebook__head">
        <span className="h3">دفتر</span>
        <button type="button" className="iconbtn" onClick={onClose} aria-label="بستن دفتر">
          <span aria-hidden="true" className="zoom-glyph">×</span>
        </button>
      </div>

      {state === 'loading' && <p className="small">در حال خواندن دفتر…</p>}

      {state === 'error' && (
        <p className="small" role="alert">
          دفتر باز نشد. اتصال را بررسی کن؛ خطوط ذخیره‌شده از بین نرفته‌اند.
        </p>
      )}

      {state === 'ready' && pages.length === 0 && (
        <div className="notebook__empty">
          <p className="small">هنوز چیزی ننوشته‌ای.</p>
          <p className="tiny mt-8">
            قلم را از نوار پایین انتخاب کن و روی صفحه بکش. خطوط با همان ضخامت واقعی روی
            هر دستگاهی دوباره رسم می‌شوند.
          </p>
        </div>
      )}

      {state === 'ready' && pages.length > 0 && (
        <>
          <p className="tiny">
            {fa(pages.length)} صفحه · {fa(total)} خط
          </p>
          <ul className="notebook__list">
            {pages.map((p) => (
              <li key={p.page}>
                <button
                  type="button"
                  className={`notebook__item${p.page === page ? ' is-on' : ''}`}
                  onClick={() => onJump(p.page)}
                  aria-current={p.page === page ? 'page' : undefined}
                >
                  <span className="notebook__num num">صفحهٔ {fa(p.page)}</span>
                  <span className="tiny">{fa(p.count)} خط</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  );
}
