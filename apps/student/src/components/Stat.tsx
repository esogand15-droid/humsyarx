/** آمار — عدد باید از دادهٔ واقعی بیاید، وگرنه نمایش داده نمی‌شود (D-022). */
export function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="stat">
      <span className="stat__v num">{value}</span>
      <span className="stat__l">{label}</span>
    </div>
  );
}
