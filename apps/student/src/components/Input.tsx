import type { InputHTMLAttributes } from 'react';
import { useId } from 'react';

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label?: string;
  error?: string;
  code?: boolean;
}

/** فیلد — برچسب همیشه دیده می‌شود؛ خطا با متن، نه فقط رنگ. */
export function Input({ label, error, code = false, className = '', ...rest }: InputProps) {
  const id = useId();
  return (
    <div className={`field ${error ? 'field--error' : ''}`.trim()}>
      {label && <label htmlFor={id}>{label}</label>}
      <input
        id={id}
        className={`input ${code ? 'input--code' : ''} ${className}`.trim()}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-err` : undefined}
        {...rest}
      />
      {error && (
        <span className="field__err" id={`${id}-err`} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
