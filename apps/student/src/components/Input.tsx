import type { InputHTMLAttributes } from 'react';
import { forwardRef, useId } from 'react';

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label?: string;
  error?: string;
  code?: boolean;
}

/** فیلد — برچسب همیشه دیده می‌شود؛ خطا با متن، نه فقط رنگ.
    forwardRef لازم است تا صفحهٔ ورود بتواند فوکوس را روی فیلد کد ببرد. */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, code = false, className = '', 'aria-describedby': describedBy, ...rest },
  ref,
) {
  const id = useId();
  const help = [error ? `${id}-err` : '', describedBy ?? ''].filter(Boolean).join(' ') || undefined;
  return (
    <div className={`field ${error ? 'field--error' : ''}`.trim()}>
      {label && <label htmlFor={id}>{label}</label>}
      <input
        id={id}
        ref={ref}
        className={`input ${code ? 'input--code' : ''} ${className}`.trim()}
        aria-invalid={error ? true : undefined}
        aria-describedby={help}
        {...rest}
      />
      {error && (
        <span className="field__err" id={`${id}-err`} role="alert">
          {error}
        </span>
      )}
    </div>
  );
});
