import { useCallback, useEffect, useRef, useState } from 'react';
import * as pdfjs from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

import { IconButton } from '../../components';
import { Icon } from '../../icons';
import { fa } from '../../lib/library';

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

interface Props {
  url: string;
  /** صفحهٔ ذخیره‌شده برای شروع */
  startPage: number;
  onProgress: (page: number, total: number) => void;
  /** اگر لینک امضاشده منقضی شد، یک بار آدرس تازه بگیر */
  onExpired: () => Promise<string | null>;
}

/** نمایش PDF با رندر روی canvas — بدون iframe و بدون افزونهٔ مرورگر.
   چرا canvas: نمایشگر بومی مرورگر در موبایل اغلب دانلود می‌کند یا
   کنترل ندارد؛ این‌جا پیمایش، بزرگ‌نمایی و پیشرفت یکدست است. */
export function PdfView({ url, startPage, onProgress, onExpired }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const docRef = useRef<pdfjs.PDFDocumentProxy | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [renderTick, setRenderTick] = useState(0);

  const open = useCallback(
    async (target: string, jumpTo: number) => {
      setLoading(true);
      setError('');
      try {
        const doc = await pdfjs.getDocument({ url: target, isEvalSupported: false }).promise;
        docRef.current = doc;
        setTotal(doc.numPages);
        const first = Math.min(Math.max(1, jumpTo || 1), doc.numPages);
        setPage(first);
        setLoading(false);
      } catch {
        // لینک ۱۰ دقیقه‌ای منقضی شده یا شبکه قطع شده → یک بار تازه‌سازی
        try {
          const fresh = await onExpired();
          if (fresh) {
            const doc = await pdfjs.getDocument({ url: fresh, isEvalSupported: false }).promise;
            docRef.current = doc;
            setTotal(doc.numPages);
            setPage(Math.min(Math.max(1, jumpTo || 1), doc.numPages));
            setLoading(false);
            return;
          }
        } catch {
          /* پایین‌تر پیام می‌دهیم */
        }
        setLoading(false);
        setError('این فایل باز نشد. ممکن است لینک منقضی شده باشد؛ صفحه را دوباره باز کن.');
      }
    },
    [onExpired],
  );

  useEffect(() => {
    void open(url, startPage);
    return () => {
      docRef.current?.destroy().catch(() => undefined);
      docRef.current = null;
    };
  }, [url]); // eslint-disable-line react-hooks/exhaustive-deps

  // رندر صفحهٔ جاری
  useEffect(() => {
    const doc = docRef.current;
    const canvas = canvasRef.current;
    if (!doc || !canvas || loading) return;
    let cancelled = false;

    (async () => {
      try {
        const p = await doc.getPage(page);
        if (cancelled) return;
        const containerWidth = (wrapRef.current?.clientWidth ?? 360) - 24;
        const base = p.getViewport({ scale: 1 });
        const fit = containerWidth / base.width;
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const viewport = p.getViewport({ scale: fit * zoom * dpr });

        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        canvas.style.width = `${Math.floor(viewport.width / dpr)}px`;
        canvas.style.height = `${Math.floor(viewport.height / dpr)}px`;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        await p.render({ canvasContext: ctx, viewport }).promise;
        if (!cancelled) onProgress(page, doc.numPages);
      } catch {
        if (!cancelled) setError('صفحهٔ جاری رندر نشد. یک صفحهٔ دیگر را امتحان کن.');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [page, zoom, loading, renderTick, onProgress]);

  // کلیدهای صفحه‌کلید — خواندن با کیبورد، نه فقط با لمس
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft' || e.key === 'PageDown') setPage((v) => Math.min(total || 1, v + 1));
      if (e.key === 'ArrowRight' || e.key === 'PageUp') setPage((v) => Math.max(1, v - 1));
      if (e.key === '+' || e.key === '=') setZoom((z) => Math.min(2.5, z + 0.2));
      if (e.key === '-') setZoom((z) => Math.max(0.6, z - 0.2));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [total]);

  // چرخش اندازهٔ صفحه: دوباره رندر کن (فیت عرض)
  useEffect(() => {
    const onResize = () => setRenderTick((v) => v + 1);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  return (
    <div className="reader" ref={wrapRef}>
      {loading && (
        <div className="reader__center" aria-busy="true">
          <span className="small">در حال باز کردن فایل…</span>
        </div>
      )}

      {error && (
        <div className="reader__center">
          <Icon name="i-arch" size={30} />
          <p className="small mt-8" style={{ maxWidth: 300 }}>
            {error}
          </p>
        </div>
      )}

      {!error && (
        <div className="reader__canvas">
          <canvas ref={canvasRef} className="reader__page" aria-label={`صفحهٔ ${page} از ${total}`} />
        </div>
      )}

      {!error && !loading && (
        <div className="reader__bar" role="toolbar" aria-label="پیمایش فایل">
          <IconButton
            icon="i-chevron-r"
            label="صفحهٔ قبل"
            onClick={() => setPage((v) => Math.max(1, v - 1))}
          />
          <span className="reader__counter num" dir="ltr" aria-live="polite">
            {fa(page)} / {fa(total)}
          </span>
          <IconButton
            icon="i-chevron"
            label="صفحهٔ بعد"
            onClick={() => setPage((v) => Math.min(total || 1, v + 1))}
          />
          <span className="grow" />
          <button
            type="button"
            className="iconbtn"
            aria-label="کوچک‌نمایی"
            onClick={() => setZoom((z) => Math.max(0.6, z - 0.2))}
          >
            <span aria-hidden="true" className="zoom-glyph">−</span>
          </button>
          <span className="tiny num" style={{ minWidth: 40, textAlign: 'center' }} aria-live="polite">
            {fa(Math.round(zoom * 100))}٪
          </span>
          <button
            type="button"
            className="iconbtn"
            aria-label="بزرگ‌نمایی"
            onClick={() => setZoom((z) => Math.min(2.5, z + 0.2))}
          >
            <span aria-hidden="true" className="zoom-glyph">+</span>
          </button>
        </div>
      )}
    </div>
  );
}
