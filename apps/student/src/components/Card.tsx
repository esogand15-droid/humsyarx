import type { HTMLAttributes } from 'react';

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'plain' | 'rule' | 'quiet' | 'flush';
}

/** کارت — جداکنندهٔ ۱px، سایهٔ حداقلی. فقط چهار حالت. */
export function Card({ variant = 'plain', className = '', children, ...rest }: CardProps) {
  const cls = [
    'card',
    variant === 'rule' && 'card--rule',
    variant === 'quiet' && 'card--quiet',
    variant === 'flush' && 'card--flush',
    className,
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <div className={cls} {...rest}>
      {children}
    </div>
  );
}
