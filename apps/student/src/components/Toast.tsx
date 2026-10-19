export interface ToastProps {
  message: string | null;
}

/** توست — کوتاه، پایین صفحه، بدون آیکون ایموجی. */
export function Toast({ message }: ToastProps) {
  if (!message) return null;
  return (
    <div className="toast" role="status" aria-live="polite">
      {message}
    </div>
  );
}
