import type { IconName } from './sprite';

/** آیکون — همه از اسپرایت واحد می‌آیند؛ رنگ از currentColor. */
export function Icon({
  name,
  size = 20,
  className,
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  return (
    <svg width={size} height={size} className={className} aria-hidden="true" focusable="false">
      <use href={`#${name}`} />
    </svg>
  );
}
