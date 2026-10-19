import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { AppBar, Button, EmptyState } from '../../components';
import { ErrorBlock, LoadingBlock } from '../../components/AccessStates';
import { Icon } from '../../icons';
import { ink } from '../../lib/ink';
import { reader } from '../../lib/reader';
import type { Kind, Scope, ViewInfo } from '../../lib/reader';

// pdf.js حجم دارد؛ فقط وقتی وارد ریدر PDF می‌شویم بارگذاری می‌شود
const PdfView = lazy(() => import('./PdfView').then((m) => ({ default: m.PdfView })));
const MediaView = lazy(() => import('./MediaView').then((m) => ({ default: m.MediaView })));

/** ریدر — یک صفحه برای هر سه نوع محتوا (PDF / ویدیو-ویس / تصویر).
    آدرس فایل کوتاه‌عمر است، پس ذخیرهٔ پیشرفت و تازه‌سازی خودکار مهم است. */
export function ReaderScreen() {
  const { scope = 'res', id = '' } = useParams();
  const navigate = useNavigate();

  const [info, setInfo] = useState<ViewInfo | null>(null);
  const [url, setUrl] = useState('');
  const [startPage, setStartPage] = useState(1);
  const [startAt, setStartAt] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);

  const scopeTyped = (scope === 'ref' ? 'ref' : 'res') as Scope;
  const saveTimer = useRef<number | null>(null);
  const latest = useRef({ page: 1, total: 0, position: 0 });

  const persist = useCallback(
    (kind: Kind, patch: Partial<{ page: number; total: number; position: number }>) => {
      latest.current = { ...latest.current, ...patch };
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      // ذخیرهٔ تأخیری: پیمایش سریع نباید ده‌ها درخواست بسازد
      saveTimer.current = window.setTimeout(() => {
        void reader
          .save(scopeTyped, id, {
            page: latest.current.page,
            total: latest.current.total,
            position: latest.current.position,
            kind,
          })
          .then(() => {
            setSaved(true);
            window.setTimeout(() => setSaved(false), 1600);
          })
          .catch(() => undefined);
      }, 700);
    },
    [scopeTyped, id],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [view, prog] = await Promise.all([
        reader.viewUrl(scopeTyped, id),
        reader.progress(scopeTyped, id).catch(() => null),
      ]);
      setInfo(view);
      if (view.available && view.url) setUrl(view.url);
      if (prog) {
        latest.current = { page: prog.page || 1, total: prog.total || 0, position: prog.position || 0 };
        setStartPage(prog.page > 0 ? prog.page : 1);
        setStartAt(prog.position > 0 ? prog.position : 0);
      }
      // ?p=۴ از دفتر یادداشت‌ها → همان صفحه، حتی اگر پیشرفت جای دیگری باشد
      const jump = Number(new URLSearchParams(window.location.search).get('p'));
      if (jump > 0) {
        setStartPage(jump);
        latest.current = { ...latest.current, page: jump };
      }
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [scopeTyped, id]);

  useEffect(() => {
    void load();
    // هر خطی که آفلاین مانده بود، همین‌جا فرستاده می‌شود
    void ink.flush();
    return () => {
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
    };
  }, [load]);

  useEffect(() => {
    const onOnline = () => void ink.flush();
    window.addEventListener('online', onOnline);
    return () => window.removeEventListener('online', onOnline);
  }, []);


  /** لینک ۱۰ دقیقه‌ای تمام شده: آدرس تازه بگیر، همان‌جا بمان. */
  const refreshUrl = useCallback(async (): Promise<string | null> => {
    try {
      const view = await reader.viewUrl(scopeTyped, id);
      if (view.available && view.url) {
        setUrl(view.url);
        return view.url;
      }
    } catch {
      /* پایین‌تر پیام می‌دهد */
    }
    return null;
  }, [scopeTyped, id]);

  const kind: Kind = info?.kind ?? 'other';

  return (
    <>
      <AppBar
        title={info?.name ?? 'در حال باز کردن…'}
        sub={saved ? 'پیشرفت ذخیره شد' : 'خواندن داخل هامزیار'}
        back
        onBack={() => navigate(-1)}
      />

      {loading && (
        <div className="page">
          <LoadingBlock rows={2} />
        </div>
      )}

      {!loading && error != null && (
        <div className="page">
          <ErrorBlock error={error} onRetry={() => void load()} />
        </div>
      )}

      {!loading && !error && info && !info.available && (
        <div className="page">
          <EmptyState
            icon="i-lock"
            title="این فایل داخل برنامه خوانده نمی‌شود"
            text={
              info.reason === 'not_previewable'
                ? 'فرمت این فایل برای نمایش درون‌برنامه‌ای مناسب نیست (مثلاً پاورپوینت یا فایل فشرده). برای دیدنش باید از مسیر دریافت فایل استفاده کنی.'
                : 'این فایل در حال حاضر قابل نمایش نیست.'
            }
            action={
              <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
                بازگشت به فهرست
              </Button>
            }
          />
        </div>
      )}

      {!loading && !error && info && info.available && url && (
        <div className="reader-shell">
          <Suspense
            fallback={
              <div className="reader__center" aria-busy="true">
                <span className="small">در حال آماده‌سازی نمایشگر…</span>
              </div>
            }
          >
            {kind === 'pdf' ? (
              <PdfView
                scope={scopeTyped}
                id={id}
                url={url}
                startPage={startPage}
                onProgress={(page, total) => persist('pdf', { page, total })}
                onExpired={refreshUrl}
              />
            ) : kind === 'video' || kind === 'audio' || kind === 'image' ? (
              <MediaView
                url={url}
                kind={kind}
                name={info.name}
                size={info.size}
                startAt={startAt}
                onPosition={(seconds) => persist(kind, { position: seconds })}
              />
            ) : (
              <div className="page">
                <EmptyState
                  icon="i-doc"
                  title="نمایش این نوع فایل پشتیبانی نمی‌شود"
                  text="فقط PDF، ویدیو، صدا و تصویر داخل برنامه باز می‌شوند."
                />
              </div>
            )}
          </Suspense>

          <p className="reader__foot tiny">
            <Icon name="i-lock" size={13} /> این فایل فقط برای حساب تو و از سرور هامزیار سرو می‌شود؛
            لینکش پس از ۱۰ دقیقه باطل می‌شود.
          </p>
        </div>
      )}
    </>
  );
}
