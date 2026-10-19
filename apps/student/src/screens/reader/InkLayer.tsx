import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';

import { ink, type InkTool, type Scope, type Stroke } from '../../lib/ink';

export interface InkApi {
  undo: () => void;
  redo: () => void;
  clear: () => void;
  count: () => number;
}

export type InkStatus = 'idle' | 'saving' | 'saved' | 'pending';

interface Props {
  scope: Scope;
  id: string;
  page: number;
  /** اندازهٔ نمایشی صفحه (CSS px) — خطوط نسبت به همین کادر رسم می‌شوند */
  width: number;
  height: number;
  /** ابزار فعال؛ `null` یعنی فقط خواندن (لمس روی صفحه نقاشی نمی‌کند) */
  tool: InkTool | 'eraser' | null;
  color: string;
  /** ضخامت پایه به‌صورت کسری از عرض صفحه */
  strokeWidth: number;
  onCount: (n: number) => void;
  /** برای فعال/غیرفعال کردن دکمه‌های بازگردانی — عدد واقعی، نه حدس */
  onHistory: (s: { undo: number; redo: number }) => void;
  onStatus: (s: InkStatus) => void;
  /** یک بار پس از تغییر، پنل دفتر را به‌روز کن */
  onChanged?: () => void;
}

const SAVE_DELAY = 900;

/** کف دست را نادیده بگیر: اگر در این نشست قلم دیده شده، لمس انگشت نقاشی نمی‌کند. */
let penSeen = false;

/** لایهٔ حاشیه‌نویسی — یک canvas روی صفحهٔ PDF.
 *
 *  چرا canvas و نه SVG: با هزاران نقطه، SVG در موبایل کند می‌شود؛
 *  canvas با یک مسیر پیوسته بدون DOM اضافه رسم می‌کند.
 *  مختصات ذخیره‌شده نرمال‌شده است، پس زوم و چرخش دستگاه خط را جابه‌جا نمی‌کند.
 */
export const InkLayer = forwardRef<InkApi, Props>(function InkLayer(
  { scope, id, page, width, height, tool, color, strokeWidth, onCount, onHistory, onStatus, onChanged },
  ref,
) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  // کال‌بک‌های والد در ref نگه داشته می‌شوند. اگر در deps افکت‌ها باشند،
  // هر رندر والد یک بارگذاری تازه می‌سازد و حلقهٔ بی‌پایان درخواست می‌شود.
  const cbs = useRef({ onCount, onHistory, onStatus, onChanged });
  cbs.current = { onCount, onHistory, onStatus, onChanged };
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const strokesRef = useRef<Stroke[]>([]);
  const past = useRef<Stroke[][]>([]);
  const future = useRef<Stroke[][]>([]);
  const drawing = useRef<Stroke | null>(null);
  const saveTimer = useRef<number | undefined>(undefined);
  const dirty = useRef(false);
  const loaded = useRef(false);
  const [ready, setReady] = useState(false);

  const commit = useCallback(
    (next: Stroke[], opts: { history?: boolean } = { history: true }) => {
      if (opts.history !== false) {
        past.current.push(strokesRef.current);
        if (past.current.length > 40) past.current.shift();
        future.current = [];
      }
      strokesRef.current = next;
      setStrokes(next);
      cbs.current.onCount(next.length);
      cbs.current.onHistory({ undo: past.current.length, redo: future.current.length });
      dirty.current = true;
    },
    [],
  );

  // ── بارگذاری خطوط صفحه ───────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    loaded.current = false;
    setReady(false);
    past.current = [];
    future.current = [];
    (async () => {
      let list: Stroke[] = [];
      try {
        const res = await ink.page(scope, id, page);
        list = res.strokes ?? [];
      } catch {
        // آفلاین: اگر نسخهٔ منتظرِ ارسال برای همین صفحه داریم، همان را نشان بده
        list = [];
      }
      if (cancelled) return;
      strokesRef.current = list;
      setStrokes(list);
      cbs.current.onCount(list.length);
      cbs.current.onHistory({ undo: 0, redo: 0 });
      loaded.current = true;
      setReady(true);
      cbs.current.onStatus('idle');
    })();
    return () => {
      cancelled = true;
    };
  }, [scope, id, page]);

  // ── ذخیرهٔ دسته‌ای (debounce) ────────────────────────────────
  const flushSave = useCallback(async () => {
    if (!dirty.current) return;
    dirty.current = false;
    cbs.current.onStatus('saving');
    const res = await ink.save(scope, id, page, strokesRef.current);
    cbs.current.onStatus(res.ok ? 'saved' : 'pending');
    if (res.ok) cbs.current.onChanged?.();
  }, [scope, id, page]);

  useEffect(() => {
    if (!dirty.current) return;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => void flushSave(), SAVE_DELAY);
    return () => window.clearTimeout(saveTimer.current);
  }, [strokes, flushSave]);

  // خروج از صفحه = ذخیرهٔ فوری، نه از دست رفتن خط
  useEffect(() => {
    return () => {
      window.clearTimeout(saveTimer.current);
      if (dirty.current) {
        dirty.current = false;
        void ink.save(scope, id, page, strokesRef.current);
      }
    };
  }, [scope, id, page]);

  // ── رسم ─────────────────────────────────────────────────────
  const paint = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !width || !height) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    for (const s of strokesRef.current) {
      if (s.points.length === 0) continue;
      ctx.beginPath();
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.strokeStyle = s.color;
      ctx.lineWidth = Math.max(1, s.width * width);
      ctx.globalAlpha = s.tool === 'highlighter' ? 0.34 : 1;
      const [x0, y0] = s.points[0];
      ctx.moveTo(x0 * width, y0 * height);
      if (s.points.length === 1) {
        ctx.lineTo(x0 * width + 0.1, y0 * height);
      }
      for (let i = 1; i < s.points.length; i += 1) {
        const [x, y] = s.points[i];
        ctx.lineTo(x * width, y * height);
      }
      ctx.stroke();
    }

    // خطِ در حال کشیدن، تا لحظهٔ رها کردن هم دیده شود
    const live = drawing.current;
    if (live && live.points.length > 0) {
      ctx.beginPath();
      ctx.strokeStyle = live.color;
      ctx.lineWidth = Math.max(1, live.width * width);
      ctx.globalAlpha = live.tool === 'highlighter' ? 0.34 : 1;
      const [lx, ly] = live.points[0];
      ctx.moveTo(lx * width, ly * height);
      for (let i = 1; i < live.points.length; i += 1) {
        const [x, y] = live.points[i];
        ctx.lineTo(x * width, y * height);
      }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }, [width, height]);

  useEffect(() => {
    paint();
  }, [paint, strokes, ready, width, height]);

  // ── ورودی ───────────────────────────────────────────────────
  const pos = (e: React.PointerEvent<HTMLCanvasElement>): [number, number] => {
    const rect = e.currentTarget.getBoundingClientRect();
    return [
      Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)),
      Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height)),
    ];
  };

  const hitStroke = (x: number, y: number): number => {
    const r = 0.014; // شعاع برخورد پاک‌کن، نسبت به عرض صفحه
    const list = strokesRef.current;
    for (let i = list.length - 1; i >= 0; i -= 1) {
      const pts = list[i].points;
      for (let j = 0; j < pts.length; j += 1) {
        const [px, py] = pts[j];
        const dx = (px - x) * (width / Math.max(height, 1));
        const dy = py - y;
        if (Math.hypot(dx, dy) < r) return i;
      }
    }
    return -1;
  };

  const onDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!tool) return;
    if (e.pointerType === 'pen') penSeen = true;
    if (penSeen && e.pointerType === 'touch') return; // کف دست
    if (e.pointerType === 'touch') e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    const [x, y] = pos(e);

    if (tool === 'eraser') {
      const i = hitStroke(x, y);
      if (i >= 0) commit(strokesRef.current.filter((_, k) => k !== i));
      return;
    }
    // فشار قلم: میانگین در طول خط، به‌صورت یک ضریب روی ضخامت
    const pressure = e.pointerType === 'pen' ? Math.min(1.4, 0.6 + e.pressure) : 1;
    drawing.current = {
      tool,
      color,
      width: strokeWidth * pressure,
      points: [[x, y]],
    };
    paint();
  };

  const onMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!tool) return;
    if (penSeen && e.pointerType === 'touch') return;
    const [x, y] = pos(e);

    if (tool === 'eraser') {
      if (e.buttons !== 1) return;
      const i = hitStroke(x, y);
      if (i >= 0) commit(strokesRef.current.filter((_, k) => k !== i));
      return;
    }
    const live = drawing.current;
    if (!live) return;
    const last = live.points[live.points.length - 1];
    if (Math.abs(last[0] - x) < 0.0015 && Math.abs(last[1] - y) < 0.0015) return;
    live.points.push([x, y]);
    paint();
  };

  const onUp = () => {
    const live = drawing.current;
    if (!live) return;
    drawing.current = null;
    if (live.points.length < 2) {
      // یک نقطه تنها هم یک خط است (نقطه‌گذاری)، ولی خط تکراری نمی‌سازیم
      live.points.push([live.points[0][0] + 0.0005, live.points[0][1]]);
    }
    commit([...strokesRef.current, live]);
    paint();
  };

  useImperativeHandle(ref, () => ({
    undo: () => {
      const prev = past.current.pop();
      if (!prev) return;
      future.current.push(strokesRef.current);
      strokesRef.current = prev;
      setStrokes(prev);
      cbs.current.onCount(prev.length);
      cbs.current.onHistory({ undo: past.current.length, redo: future.current.length });
      dirty.current = true;
      paint();
    },
    redo: () => {
      const next = future.current.pop();
      if (!next) return;
      past.current.push(strokesRef.current);
      strokesRef.current = next;
      setStrokes(next);
      cbs.current.onCount(next.length);
      cbs.current.onHistory({ undo: past.current.length, redo: future.current.length });
      dirty.current = true;
      paint();
    },
    clear: () => {
      if (strokesRef.current.length === 0) return;
      past.current.push(strokesRef.current);
      future.current = [];
      strokesRef.current = [];
      setStrokes([]);
      cbs.current.onCount(0);
      cbs.current.onHistory({ undo: past.current.length, redo: future.current.length });
      dirty.current = true;
      paint();
    },
    count: () => strokesRef.current.length,
  }));

  return (
    <canvas
      ref={canvasRef}
      className={`ink-canvas${tool ? ' ink-canvas--active' : ''}`}
      style={{ width, height, touchAction: tool ? 'none' : 'auto' }}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
      aria-label={
        tool
          ? 'سطح حاشیه‌نویسی روی صفحه؛ با قلم یا ماوس خط بکش'
          : 'حاشیه‌نویسی‌های این صفحه'
      }
      role="img"
    />
  );
});
