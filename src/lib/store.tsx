import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

/* ═══════════════════════════════════════════════════════════════════
   وضعیت سراسری پروتوتایپ — فقط ظاهر (تم، عرض پیش‌نمایش، جهت بصری، توست)
   هیچ داده‌ای به سرور نمی‌رود؛ همه‌چیز محلی است.
   ═══════════════════════════════════════════════════════════════════ */

export type Theme = 'dark' | 'light';
export type PreviewWidth = 'desktop' | 'tablet' | 'mobile';
export type VisualDirection = 'intelligent' | 'quiet';

interface Toast { id: number; text: string; tone?: 'ok' | 'err' | 'info' }

interface Ctx {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  preview: PreviewWidth;
  setPreview: (v: PreviewWidth) => void;
  direction: VisualDirection;
  setDirection: (v: VisualDirection) => void;
  toasts: Toast[];
  toast: (text: string, tone?: Toast['tone']) => void;
  dismiss: (id: number) => void;
}

const C = createContext<Ctx | null>(null);

export function ProtoProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>('dark');
  const [preview, setPreview] = useState<PreviewWidth>('desktop');
  const [direction, setDirection] = useState<VisualDirection>('intelligent');
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    document.documentElement.dataset.preview = preview;
  }, [preview]);

  useEffect(() => {
    document.documentElement.dataset.vdir = direction;
  }, [direction]);

  const toast = useCallback((text: string, tone: Toast['tone'] = 'info') => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3600);
  }, []);

  const value = useMemo<Ctx>(
    () => ({
      theme,
      setTheme,
      toggleTheme: () => setTheme((t) => (t === 'dark' ? 'light' : 'dark')),
      preview,
      setPreview,
      direction,
      setDirection,
      toasts,
      toast,
      dismiss: (id: number) => setToasts((t) => t.filter((x) => x.id !== id)),
    }),
    [theme, preview, direction, toasts, toast],
  );

  return <C.Provider value={value}>{children}</C.Provider>;
}

export function useProto(): Ctx {
  const v = useContext(C);
  if (!v) throw new Error('useProto must be used inside ProtoProvider');
  return v;
}

/* ── ابزار اعداد فارسی ──────────────────────────────────────────── */
const FA = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
export function fa(n: number | string): string {
  return String(n).replace(/[0-9]/g, (d) => FA[Number(d)]);
}
export function clock(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  return `${fa(String(Math.floor(s / 60)).padStart(2, '0'))}:${fa(String(s % 60).padStart(2, '0'))}`;
}
export function pct(a: number, b: number): number {
  return b ? Math.round((a * 100) / b) : 0;
}
