import type { ButtonHTMLAttributes } from 'react';
import { Icon } from '../icons/Icon';
import type { IconName } from '../icons/sprite';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost' | 'ink';
  size?: 'md' | 'sm';
  block?: boolean;
  loading?: boolean;
  icon?: IconName;
}

/** دکمه — تنها جایی که رنگ برند روی سطح می‌نشیند (D-011). */
export function Button({
  variant = 'primary',
  size = 'md',
  block = false,
  loading = false,
  icon,
  children,
  className = '',
  disabled,
  ...rest
}: ButtonProps) {
  const cls = [
    'btn',
    variant === 'ghost' && 'btn--ghost',
    variant === 'ink' && 'btn--ink',
    size === 'sm' && 'btn--sm',
    block && 'btn--block',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button className={cls} aria-busy={loading || undefined} disabled={disabled} {...rest}>
      {loading ? (
        <span className="btn__spin" aria-hidden="true" />
      ) : icon ? (
        <Icon name={icon} size={18} />
      ) : null}
      {children}
    </button>
  );
}
