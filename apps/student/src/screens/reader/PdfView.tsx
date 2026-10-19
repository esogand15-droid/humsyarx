import { useCallback, useEffect, useRef, useState } from 'react';
import * as pdfjs from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

import { IconButton } from '../../components';
import { Icon } from '../../icons';
import { fa } from '../../lib/library';
import type { InkTool, Scope } from '../../lib/ink';
import { InkLayer, type InkApi, type InkStatus } from './InkLayer';
import { INK_COLORS, INK_WIDTHS, InkToolbar } from './InkToolbar';
import { NotebookPanel } from './NotebookPanel';

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

interface Props {
  scope: Scope;
  id: string;
  url: string;
  /** صفحهٔ ذخیره‌شده برای شروع */
  startPage: number;
  onProgress: (page: number, total: number) => void;
  /** اگر لینک امضاشده منقضی شد، یک بار آدرس تازه بگیر */
  onExpired: () => Promise<string | null>;
}

/** نمایش PDF با رندر روی canvas — بدون iframe و بدون افزونهٔ مرورگر.
   چرا canvas: نمایشگر بومی مرورگر در موبایل اغلب دانلود می‌کند یا
   کنترل ندارد؛ این‌جا پیمایش، بزرگ‌نمایی و پیشرفت یکدست است.

   حاشیه‌نویسی (P4): یک canvas دوم دقیقاً روی صفحه می‌نشیند. خطوط
   نرمال‌شده‌اند، پس با زوم و چرخش دستگاه جابه‌جا نمی‌شوند و همان
   چیزی که روی آیپد نوشته شده، روی گوشی هم سر جای خودش است. */
export function PdfView({ scope, id, url, startPage, onProgress, onExpired }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const docRef = useRef<pdfjs.PDFDocumentProxy | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inkApi = useRef<InkApi | null>(null);
  // کالبک والد در ref: اگر در deps باشد، هر رندر والد یک رندر دوبارهٔ صفحه
  // می‌سازد و pdf.js خطای «same canvas during multiple render» می‌دهد.
  const progressRef = useRef(onProgress);
  progressRef.current = onProgress;
  const taskRef = useRef<{ cancel: () => void } | null>(null);

  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [renderTick, setRenderTick] = useState(0);
  const [size, setSize] = useState({ w: 0, h: 0 });

  // ── قلم ──
  const [tool, setTool] = useState<InkTool | 'eraser' | null>(null);
  const [color, setColor] = useState(INK_COLORS[1]);
  const [widthIndex, setWidthIndex] = useState(1);
  const [status, setStatus] = useState<InkStatus>('idle');
  const [inkCount, setInkCount] = useState(0);
  const [history, setHistory] = useState({ undo: 0, redo: 0 });
  // دفتر پیش‌فرض بسته است: صفحهٔ خواندن تمام عرض را می‌گیرد تا کاربر خودش بازش کند
  const [notebookOpen, setNotebookOpen] = useState(false);
  const [notebookKey, setNotebookKey] = useState(0);

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
        // عرض از خودِ ناحیهٔ اسکرول گرفته می‌شود، نه از کل ریدر؛ وگرنه
        // وقتی دفتر روی تبلت باز می‌شود، صفحه از کادر بیرون می‌زند.
        const containerWidth = (scrollRef.current?.clientWidth ?? wrapRef.current?.clientWidth ?? 360) - 24;
        const base = p.getViewport({ scale: 1 });
        const fit = containerWidth / base.width;
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const viewport = p.getViewport({ scale: fit * zoom * dpr });

        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        const cssW = Math.floor(viewport.width / dpr);
        const cssH = Math.floor(viewport.height / dpr);
        canvas.style.width = `${cssW}px`;
        canvas.style.height = `${cssH}px`;
        setSize({ w: cssW, h: cssH });

        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        // اگر رندر قبلی هنوز در جریان است، اول لغو شود
        try {
          taskRef.current?.cancel();
        } catch {
          /* رندر قبلی تمام شده بود */
        }
        const task = p.render({ canvasContext: ctx, viewport });
        taskRef.current = task as unknown as { cancel: () => void };
        await task.promise;
        if (!cancelled) progressRef.current(page, doc.numPages);
      } catch (err) {
        // لغو عمدی (تغییر سریع صفحه) خطا نیست
        if (cancelled) return;
        if ((err as { name?: string })?.name === 'RenderingCancelledException') return;
        setError('صفحهٔ جاری رندر نشد. یک صفحهٔ دیگر را امتحان کن.');
      }
    })();

    return () => {
      cancelled = true;
      try {
        taskRef.current?.cancel();
      } catch {
        /* تمام شده */
      }
    };
  }, [page, zoom, loading, renderTick]);

  // کلیدهای صفحه‌کلید — خواندن و نوشتن با کیبورد، نه فقط با لمس
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'textarea') return;
      if (e.key === 'ArrowLeft' || e.key === 'PageDown') setPage((v) => Math.min(total || 1, v + 1));
      if (e.key === 'ArrowRight' || e.key === 'PageUp') setPage((v) => Math.max(1, v - 1));
      if (e.key === '+' || e.key === '=') setZoom((z) => Math.min(2.5, z + 0.2));
      if (e.key === '-') setZoom((z) => Math.max(0.6, z - 0.2));
      // میان‌برهای قلم — روی کیبورد لپ‌تاپ هم می‌شود حاشیه نوشت
      if (e.key === 'p' || e.key === 'P') setTool((t) => (t === 'pen' ? null : 'pen'));
      if (e.key === 'h' || e.key === 'H') setTool((t) => (t === 'highlighter' ? null : 'highlighter'));
      if (e.key === 'e' || e.key === 'E') setTool((t) => (t === 'eraser' ? null : 'eraser'));
      if (e.key === 'Escape') setTool(null);
      if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {
        e.preventDefault();
        if (e.shiftKey) inkApi.current?.redo();
        else inkApi.current?.undo();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [total]);

  // هر تغییر اندازهٔ ناحیهٔ نمایش (چرخش دستگاه، باز/بسته شدن دفتر) → فیت دوباره
  useEffect(() => {
    const onResize = () => setRenderTick((v) => v + 1);
    window.addEventListener('resize', onResize);
    const el = scrollRef.current;
    let ro: ResizeObserver | undefined;
    if (el && typeof ResizeObserver !== 'undefined') {
      let last = el.clientWidth;
      ro = new ResizeObserver(() => {
        // فقط وقتی عرض واقعاً تغییر کرد؛ وگرنه حلقهٔ رندر می‌سازد
        if (Math.abs(el.clientWidth - last) > 2) {
          last = el.clientWidth;
          setRenderTick((v) => v + 1);
        }
      });
      ro.observe(el);
    }
    return () => {
      window.removeEventListener('resize', onResize);
      ro?.disconnect();
    };
  }, []);

  const onInkCount = useCallback((n: number) => setInkCount(n), []);
  const onInkHistory = useCallback((h: { undo: number; redo: number }) => setHistory(h), []);
  const onInkStatus = useCallback((s: InkStatus) => setStatus(s), []);
  const onInkChanged = useCallback(() => setNotebookKey((k) => k + 1), []);

  const goTo = (target: number) => setPage(Math.min(Math.max(1, target), total || 1));

  return (
    <div className="reader reader--ink" ref={wrapRef}>
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
        <div className="reader__stage">
          <div className="reader__canvas" ref={scrollRef}>
            <div className="pdf-page">
              <canvas ref={canvasRef} className="reader__page" aria-label={`صفحهٔ ${page} از ${total}`} />
              {size.w > 0 && (
                <InkLayer
                  key={`${scope}:${id}:${page}`}
                  ref={inkApi}
                  scope={scope}
                  id={id}
                  page={page}
                  width={size.w}
                  height={size.h}
                  tool={tool}
                  color={color}
                  strokeWidth={INK_WIDTHS[widthIndex]}
                  onCount={onInkCount}
                  onHistory={onInkHistory}
                  onStatus={onInkStatus}
                  onChanged={onInkChanged}
                />
              )}
            </div>
          </div>

          <NotebookPanel
            scope={scope}
            id={id}
            page={page}
            open={notebookOpen}
            onClose={() => setNotebookOpen(false)}
            onJump={(p) => {
              goTo(p);
              if (window.innerWidth < 900) setNotebookOpen(false);
            }}
            refreshKey={notebookKey}
          />
        </div>
      )}

      {!error && !loading && (
        <>
          <InkToolbar
            tool={tool}
            setTool={setTool}
            color={color}
            setColor={setColor}
            widthIndex={widthIndex}
            setWidthIndex={setWidthIndex}
            undo={() => inkApi.current?.undo()}
            redo={() => inkApi.current?.redo()}
            clear={() => inkApi.current?.clear()}
            count={inkCount}
            status={status}
            canUndo={history.undo > 0}
            canRedo={history.redo > 0}
            onOpenNotebook={() => setNotebookOpen((v) => !v)}
          />

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
        </>
      )}
    </div>
  );
}
