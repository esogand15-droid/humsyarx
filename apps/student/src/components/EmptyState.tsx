import type { ReactNode } from 'react';
import { Icon } from '../icons/Icon';
import type { IconName } from '../icons/sprite';

export interface EmptyStateProps {
  icon?: IconName;
  title: string;
  text?: string;
  action?: ReactNode;
}

/** حالت خالی — یک جملهٔ راهنما و حداکثر یک کنش. */
export function EmptyState({ icon = 'i-arch', title, text, action }: EmptyStateProps) {
  return (
    <div className="empty">
      <Icon name={icon} size={44} />
      <div className="h3" style={{ color: 'var(--ink-2)' }}>{title}</div>
      {text && <p className="small" style={{ marginTop: 6, maxWidth: 340, marginInline: 'auto' }}>{text}</p>}
      {action && <div style={{ marginTop: 14 }}>{action}</div>}
    </div>
  );
}
