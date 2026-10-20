import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Icon, type IconName } from './Icon';
import { fa, useProto } from '../lib/store';

/* ═══════════════════════════════════════════════════════════════════
   کامپوننت‌های مشترک — هر صفحه فقط از این‌ها استفاده می‌کند، پس
   «یک صفحهٔ خاص» نمی‌تواند ظاهر خودش را اختراع کند.
   ═══════════════════════════════════════════════════════════════════ */

export function SectionHead({
  title,
  hint,
  action,
  id,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  id?: string;
}) {
  return (
    <div className="section__head" id={id}>
      <h2>{title}</h2>
      {action}
      {hint && <span className="sm">{hint}</span>}
    </div>
  );
}

export function Chip({
  children,
  active,
  onClick,
  ai,
  ghost,
  title,
}: {
  children: ReactNode;
  active?: boolean;
  onClick?: () => void;
  ai?: boolean;
  ghost?: boolean;
  title?: string;
}) {
  const cls = `chip${ai ? ' chip--ai' : ''}${ghost ? ' chip--ghost' : ''}`;
  if (!onClick) return <span className={cls}>{children}</span>;
  return (
    <button type="button" className={cls} aria-pressed={!!active} onClick={onClick} title={title}>
      {children}
    </button>
  );
}

export function Badge({ children, tone, className }: { children: ReactNode; tone?: 'ok' | 'warn' | 'danger' | 'info' | 'locked'; className?: string }) {
  return <span className={`badge${tone ? ` badge--${tone}` : ''}${className ? ` ${className}` : ''}`}>{children}</span>;
}

export function Progress({ value, tone }: { value: number; tone?: 'ok' }) {
  return (
    <div className={`bar${tone === 'ok' ? ' bar--ok' : ''}`} role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <i style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  );
}

export function Ring({ value, size = 62, stroke = 5, label }: { value: number; size?: number; stroke?: number; label?: string }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="url(#ringGrad)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - (c * Math.min(100, value)) / 100}
          style={{ transition: 'stroke-dashoffset .5s var(--ease)' }}
        />
        <defs>
          <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--brand-600)" />
            <stop offset="100%" stopColor="var(--cyan-400)" />
          </linearGradient>
        </defs>
      </svg>
      <div className="ring__v">
        <b className="num">{fa(value)}٪</b>
        {label && <span>{label}</span>}
      </div>
    </div>
  );
}

export function Empty({
  icon = 'layers',
  title,
  text,
  action,
}: {
  icon?: IconName;
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty__ic">
        <Icon name={icon} size={22} />
      </div>
      <b>{title}</b>
      <p>{text}</p>
      {action}
    </div>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="col" style={{ gap: 10 }} aria-busy="true" aria-label="در حال بارگذاری">
      <div className="skel skel--title" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skel skel--row" />
      ))}
    </div>
  );
}

export function Note({
  tone,
  icon,
  children,
}: {
  tone?: 'warn' | 'danger' | 'ok' | 'ai';
  icon?: IconName;
  children: ReactNode;
}) {
  const ic: IconName = icon ?? (tone === 'danger' ? 'alert' : tone === 'ok' ? 'check' : tone === 'ai' ? 'sparkle' : 'info');
  return (
    <div className={`note${tone ? ` note--${tone}` : ''}`} role={tone === 'danger' ? 'alert' : undefined}>
      <Icon name={ic} size={16} style={{ marginTop: 3 }} />
      <div>{children}</div>
    </div>
  );
}

/* ── دیالوگ ──────────────────────────────────────────────────────── */
export function Dialog({
  open,
  title,
  children,
  actions,
  onClose,
  labelledBy = 'dlg-t',
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  actions: ReactNode;
  onClose: () => void;
  labelledBy?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const f = ref.current?.querySelector<HTMLElement>('button, [href], input, textarea');
    f?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby={labelledBy} ref={ref}>
        <div className="dialog__t" id={labelledBy}>
          {title}
        </div>
        <div className="sm muted">{children}</div>
        <div className="dialog__a">{actions}</div>
      </div>
    </div>
  );
}

/* ── کشوی کنار ───────────────────────────────────────────────────── */
export function Drawer({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="scrim" style={{ placeItems: 'stretch', padding: 0 }} onMouseDown={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title}>
        <div className="row">
          <b className="h3 grow">{title}</b>
          <button type="button" className="iconbtn" onClick={onClose} aria-label="بستن">
            <Icon name="close" />
          </button>
        </div>
        {children}
      </aside>
    </>
  );
}

/* ── توست‌ها ─────────────────────────────────────────────────────── */
export function Toasts() {
  const { toasts, dismiss } = useProto();
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast${t.tone === 'ok' ? ' toast--ok' : t.tone === 'err' ? ' toast--err' : ''}`}>
          <Icon
            name={t.tone === 'ok' ? 'check' : t.tone === 'err' ? 'alert' : 'info'}
            size={15}
            style={{ color: t.tone === 'ok' ? 'var(--ok)' : t.tone === 'err' ? 'var(--danger)' : 'var(--cyan-400)' }}
          />
          <span>{t.text}</span>
          <button type="button" className="iconbtn" style={{ width: 22, height: 22 }} onClick={() => dismiss(t.id)} aria-label="بستن">
            <Icon name="close" size={13} />
          </button>
        </div>
      ))}
    </div>
  );
}

/* ── ردیف منبع (فهرست مشترک) ─────────────────────────────────────── */
const KIND_ICON: Record<string, IconName> = { pdf: 'file', video: 'video', audio: 'audio', slide: 'slide' };
const KIND_LABEL: Record<string, string> = { pdf: 'جزوه', video: 'ویدیو', audio: 'صوت', slide: 'اسلاید' };

export function ResourceRow({
  title,
  meta,
  kind,
  locked,
  onClick,
  badge,
}: {
  title: string;
  meta: string[];
  kind: 'pdf' | 'video' | 'audio' | 'slide';
  locked?: boolean;
  onClick?: () => void;
  badge?: ReactNode;
}) {
  return (
    <button type="button" className="rrow" onClick={onClick} aria-label={`${KIND_LABEL[kind]} — ${title}${locked ? ' (قفل)' : ''}`}>
      <span className={`rrow__ic rrow__ic--${kind}`}>
        <Icon name={KIND_ICON[kind]} size={18} />
      </span>
      <span style={{ minWidth: 0 }}>
        <span className="rrow__t" style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {title}
        </span>
        <span className="rrow__m">
          {meta.map((m) => (
            <span key={m}>{m}</span>
          ))}
        </span>
      </span>
      {locked ? <Badge tone="locked">قفل</Badge> : badge ?? null}
      <span className="rrow__go" aria-hidden="true">
        <Icon name="back" size={16} />
      </span>
    </button>
  );
}

/* ── بازشدن تدریجی: در موبایل بخش ثانویه جمع می‌شود، در دسکتاپ/تبلت
   همیشه باز است (CSS با container query تصمیم می‌گیرد) ─────────────── */
export function Collapse({
  children,
  label,
  moreLabel = 'بیشتر',
  lessLabel = 'کمتر',
}: {
  children: ReactNode;
  label: string;
  moreLabel?: string;
  lessLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="collapse" data-open={open}>
      <div className="collapse__body">{children}</div>
      <button type="button" className="collapse__more btn btn--quiet btn--sm btn--block" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        {open ? lessLabel : moreLabel} {label}
      </button>
    </div>
  );
}
