/** نوار پیشرفت — بدون پرش؛ درصد با tabular-nums بیرون از آن نمایش داده می‌شود. */
export function ProgressBar({ value, thin = false }: { value: number; thin?: boolean }) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="bar" style={thin ? { height: 4 } : undefined} role="progressbar" aria-valuenow={v} aria-valuemin={0} aria-valuemax={100}>
      <i style={{ width: `${v}%` }} />
    </div>
  );
}
