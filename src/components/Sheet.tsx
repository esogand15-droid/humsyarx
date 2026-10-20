import { useEffect, useRef, type ReactNode } from 'react';
import { Icon } from './Icon';

/* ═══════════════════════════════════════════════════════════════════
   Sheet — یک کامپوننت برای دو فرم‌فاکتور:
   • ≤۸۶۰px  → شیت پایین با grip و ناحیهٔ امن
   • >۸۶۰px  → دیالوگ مرکزی
   Escape، کلیک روی پرده و بازگشت فوکوس همه پیاده‌سازی شده‌اند.
   ═══════════════════════════════════════════════════════════════════ */

export function Sheet({
  open,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const box = useRef<HTMLDivElement | null>(null);
  const restore = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restore.current = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'Tab' && box.current) {
        const items = box.current.querySelectorAll<HTMLElement>('button, [href], input, textarea, [tabindex]:not([tabindex="-1"])');
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    const t = window.setTimeout(() => box.current?.querySelector<HTMLElement>('button, input, textarea')?.focus(), 40);
    return () => {
      document.removeEventListener('keydown', onKey);
      window.clearTimeout(t);
      restore.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="sheet-scrim" onClick={onClose} role="presentation" />
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} ref={box}>
        <div className="sheet__grip" />
        <div className="row" style={{ marginBottom: 'var(--s-3)' }}>
          <h2 className="h3 grow">{title}</h2>
          <button type="button" className="iconbtn" onClick={onClose} aria-label="بستن">
            <Icon name="close" size={16} />
          </button>
        </div>
        {children}
        {footer && <div className="row" style={{ marginTop: 'var(--s-4)', gap: 'var(--s-2)' }}>{footer}</div>}
      </div>
    </>
  );
}
