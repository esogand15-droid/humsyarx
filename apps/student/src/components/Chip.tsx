import type { ReactNode } from 'react';
import { Icon } from '../icons/Icon';
import type { IconName } from '../icons/sprite';

export interface ChipProps {
  children: ReactNode;
  variant?: 'amber' | 'brand' | 'cyan' | 'quiet' | 'danger';
  icon?: IconName;
}

/** چیپ — وضعیت با متن، نه فقط رنگ (دسترس‌پذیری). */
export function Chip({ children, variant = 'amber', icon }: ChipProps) {
  const cls = ['chip', variant !== 'amber' && `chip--${variant}`].filter(Boolean).join(' ');
  return (
    <span className={cls}>
      {icon && <Icon name={icon} size={13} />}
      {children}
    </span>
  );
}
