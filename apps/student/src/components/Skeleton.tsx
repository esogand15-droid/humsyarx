/** اسکلت بارگذاری — بدون شیمر متحرک (بودجهٔ CPU، D-012). */
export function Skeleton({ variant = 'text', width }: { variant?: 'text' | 'card' | 'row'; width?: string }) {
  const cls = variant === 'card' ? 'skeleton skeleton--card' : variant === 'row' ? 'skeleton skeleton--row' : 'skeleton';
  return <div className={cls} style={width ? { width } : undefined} aria-hidden="true" />;
}

export function SkeletonStack({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skeleton-stack" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} variant={i === 0 ? 'card' : 'row'} />
      ))}
    </div>
  );
}
