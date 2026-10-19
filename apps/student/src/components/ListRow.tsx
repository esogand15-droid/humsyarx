import type { ReactNode } from 'react';
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
  onClick,
}: ListRowProps) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      className={`list__item ${danger ? 'list__item--danger' : ''}`.trim()}
      onClick={onClick}
      type={onClick ? 'button' : undefined}
    >
      {icon && <Icon name={icon} size={20} className="lead" />}
      <span className="grow">
        <span className="h3" style={{ display: 'block' }}>
          {title}
        </span>
        {sub && <span className="small" style={{ display: 'block' }}>{sub}</span>}
        {meta && <span className="list__meta num">{meta}</span>}
      </span>
      {trailing}
      {chevron && <Icon name="i-chevron" size={16} />}
    </Tag>
  );
}
