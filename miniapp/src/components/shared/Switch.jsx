// ── Switch — موج W2 Design Refactor
// سوییچ مشترک کل پروژه بر پایه‌ی کلاس‌های DS
// (.switch/.switch__nob/.switch--on/.switch--danger)
// تا امروز دو پیاده‌ی محلی MiniSwitch (32×18) تکراری
// بود؛ حالا یک کامپوننت استاندارد 46×27 با Touch Target
// و استایل یکسان همه‌جا. رفتار: aria-checked/disabled.

export default function Switch({
  on,
  onToggle,
  disabled = false,
  danger = false,
  color,
  label,
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label ||
        (on ? 'روشن' : 'خاموش')}
      disabled={disabled}
      className={
        'switch'
        + (on ? ' switch--on' : '')
        + (danger ? ' switch--danger' : '')
        + (on && color
          ? ' switch--custom'
          : '')
      }
      onClick={onToggle}
      style={{
        opacity: disabled ? .45 : 1,
        cursor: disabled
          ? 'default'
          : 'pointer',
        ...(on && color
          ? {
            background: color,
            borderColor: 'transparent',
          }
          : {}),
      }}
    >
      <span className="switch__nob" />
    </button>
  );
}
