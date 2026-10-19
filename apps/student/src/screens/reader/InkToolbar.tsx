import { Icon } from '../../icons';
import { type InkTool } from '../../lib/ink';
import type { InkStatus } from './InkLayer';

export const INK_COLORS = ['#1B1712', '#1740B8', '#B3453F', '#0A8794', '#B4701F'];
export const INK_WIDTHS = [0.0018, 0.0035, 0.006] as const;

interface Props {
  tool: InkTool | 'eraser' | null;
  setTool: (t: InkTool | 'eraser' | null) => void;
  color: string;
  setColor: (c: string) => void;
  widthIndex: number;
  setWidthIndex: (i: number) => void;
  undo: () => void;
  redo: () => void;
  clear: () => void;
  count: number;
  status: InkStatus;
  canUndo: boolean;
  canRedo: boolean;
  onOpenNotebook: () => void;
}

const STATUS_TEXT: Record<InkStatus, string> = {
  idle: '',
  saving: 'در حال ذخیره…',
  saved: 'ذخیره شد',
  pending: 'در انتظار اتصال',
};

/** نوار ابزار قلم — دکمه‌های واقعی، نه آیکن‌های اختراعی.
    هر ابزار `aria-pressed` دارد، پس با صفحه‌کلید و اسکرین‌ریدر هم وضعیتش معلوم است. */
export function InkToolbar({
  tool,
  setTool,
  color,
  setColor,
  widthIndex,
  setWidthIndex,
  undo,
  redo,
  clear,
  count,
  status,
  canUndo,
  canRedo,
  onOpenNotebook,
}: Props) {
  const drawing = tool === 'pen' || tool === 'highlighter';
  return (
    <div className="ink-bar" role="toolbar" aria-label="ابزار حاشیه‌نویسی">
      <div className="ink-bar__row">
        <button
          type="button"
          className={`ink-btn${tool === 'pen' ? ' is-on' : ''}`}
          aria-pressed={tool === 'pen'}
          onClick={() => setTool(tool === 'pen' ? null : 'pen')}
          title="قلم"
        >
          <Icon name="i-pen" size={16} />
          <span className="ink-btn__t">قلم</span>
        </button>
        <button
          type="button"
          className={`ink-btn${tool === 'highlighter' ? ' is-on' : ''}`}
          aria-pressed={tool === 'highlighter'}
          onClick={() => setTool(tool === 'highlighter' ? null : 'highlighter')}
          title="هایلایت"
        >
          <Icon name="i-highlighter" size={16} />
          <span className="ink-btn__t">هایلایت</span>
        </button>
        <button
          type="button"
          className={`ink-btn${tool === 'eraser' ? ' is-on' : ''}`}
          aria-pressed={tool === 'eraser'}
          onClick={() => setTool(tool === 'eraser' ? null : 'eraser')}
          title="پاک‌کن"
        >
          <Icon name="i-eraser" size={16} />
          <span className="ink-btn__t">پاک‌کن</span>
        </button>

        <span className="grow" />

        <button
          type="button"
          className="ink-btn ink-btn--icon"
          onClick={onOpenNotebook}
          aria-label="دفتر این فایل" 
          title="دفتر"
        >
          <Icon name="i-layers" size={16} />
          <span className="ink-btn__t ink-btn__t--word">دفتر</span>
        </button>
      </div>

      {drawing && (
        <div className="ink-bar__row ink-bar__row--sub">
          {INK_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              className={`ink-dot${color === c ? ' is-on' : ''}`}
              style={{ background: c }}
              aria-label={`رنگ ${c}`}
              aria-pressed={color === c}
              onClick={() => setColor(c)}
            />
          ))}
          <span className="ink-sep" aria-hidden="true" />
          {INK_WIDTHS.map((w, i) => (
            <button
              key={w}
              type="button"
              className={`ink-w${widthIndex === i ? ' is-on' : ''}`}
              aria-label={['ضخامت نازک', 'ضخامت متوسط', 'ضخامت پهن'][i]}
              aria-pressed={widthIndex === i}
              onClick={() => setWidthIndex(i)}
            >
              <i style={{ width: 4 + i * 4, height: 4 + i * 4 }} />
            </button>
          ))}
        </div>
      )}

      <div className="ink-bar__row ink-bar__row--sub">
        <button type="button" className="ink-link" onClick={undo} disabled={!canUndo}>
          بازگردانی
        </button>
        <button type="button" className="ink-link" onClick={redo} disabled={!canRedo}>
          دوباره
        </button>
        <button
          type="button"
          className="ink-link"
          onClick={clear}
          disabled={count === 0}
        >
          پاک‌کردن این صفحه
        </button>
        <span className="grow" />
        <span className="ink-status" aria-live="polite">
          {STATUS_TEXT[status]}
        </span>
      </div>
    </div>
  );
}
