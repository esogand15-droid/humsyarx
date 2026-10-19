import { useEffect, type ReactNode } from 'react';
import { IconButton } from './IconButton';

export interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

/** شیت پایین‌کشیدنی — بستن با Esc و کلیک روی پرده. */
export function Sheet({ open, onClose, title, children }: SheetProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <>
      <div className="sheet-scrim" onClick={onClose} aria-hidden="true" />
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title}>
        <div className="sheet__grip" aria-hidden="true" />
        <div className="sheet__head">
          <span className="h2">{title}</span>
          <IconButton icon="i-chevron" label="بستن" onClick={onClose} />
        </div>
        {children}
      </div>
    </>
  );
}
