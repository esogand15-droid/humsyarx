import type { ButtonHTMLAttributes } from 'react';
import { Icon } from '../icons/Icon';
import type { IconName } from '../icons/sprite';

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: IconName;
  label: string;
  active?: boolean;
}

/** دکمهٔ آیکونی — ۳۸px ظاهری، ناحیهٔ لمس ۴۴px از طریق padding/خط نامرئی. */
export function IconButton({ icon, label, active = false, className = '', ...rest }: IconButtonProps) {
  return (
    <button
      type="button"
      className={`iconbtn ${className}`.trim()}
      aria-label={label}
      aria-pressed={active || undefined}
      title={label}
      {...rest}
    >
      <Icon name={icon} size={20} />
    </button>
  );
}
