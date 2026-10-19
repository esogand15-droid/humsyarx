export interface SwitchProps {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}

/** کلید روشن/خاموش — نقش switch، برچسب برای فناوری کمکی. */
export function Switch({ checked, onChange, label }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className="switch"
      onClick={() => onChange(!checked)}
    />
  );
}
