import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { Icon } from '../icons/Icon';
import type { IconName } from '../icons/sprite';

export interface ListRowProps {
  title: string;
  sub?: string;
  meta?: string;
  icon?: IconName;
  trailing?: ReactNode;
  chevron?: boolean;
  danger?: boolean;
  /** مسیر مقصد. اگر داده شود، ردیف خودش یک لینک است — نه دکمه‌ای
      داخل لینک. (نesting دو عنصر تعاملی، کلیک را می‌بلعد و
      مرورگر هم آن را نامعتبر می‌داند.) */
  to?: string;
  onClick?: () => void;
}

/** ردیف لیست — یک کنش در هر ردیف؛ آخرین ردیف بدون خط پایین. */
export function ListRow({
  title,
  sub,
  meta,
  icon,
  trailing,
  chevron = false,
  danger = false,
  to,
  onClick,
}: ListRowProps) {
  const inner = (
    <>
      {icon && <Icon name={icon} size={20} className="lead" />}
      <span className="grow">
        <span className="h3" style={{ display: 'block' }}>
          {title}
        </span>
        {sub && (
          <span className="small" style={{ display: 'block' }}>
            {sub}
          </span>
        )}
        {meta && <span className="list__meta num">{meta}</span>}
      </span>
      {trailing}
      {chevron && <Icon name="i-chevron" size={16} />}
    </>
  );

  const cls = `list__item ${danger ? 'list__item--danger' : ''}`.trim();

  if (to) {
    return (
      <Link className={cls} to={to}>
        {inner}
      </Link>
    );
  }

  if (onClick) {
    return (
      <button className={cls} onClick={onClick} type="button">
        {inner}
      </button>
    );
  }

  return <div className={cls}>{inner}</div>;
}
