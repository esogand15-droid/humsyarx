import { IconButton } from './IconButton';
import type { IconName } from '../icons/sprite';

export type ReaderTool = 'pen' | 'highlighter' | 'eraser' | 'bookmark' | 'panel' | 'grid';

const TOOLS: { id: ReaderTool; icon: IconName; label: string }[] = [
  { id: 'pen', icon: 'i-pen', label: 'قلم' },
  { id: 'highlighter', icon: 'i-highlighter', label: 'هایلایت' },
  { id: 'eraser', icon: 'i-eraser', label: 'پاک‌کن' },
  { id: 'bookmark', icon: 'i-bookmark', label: 'نشانک' },
  { id: 'panel', icon: 'i-layers', label: 'پنل‌ها' },
  { id: 'grid', icon: 'i-grid', label: 'فهرست صفحه‌ها' },
];

/** نوار ابزار ریدر — انتخاب‌شده با aria-pressed و رنگ، نه فقط شکل. */
export function ReaderToolbar({
  active,
  onSelect,
}: {
  active: ReaderTool | null;
  onSelect: (t: ReaderTool) => void;
}) {
  return (
    <div className="rtool" role="toolbar" aria-label="ابزارهای مطالعه">
      {TOOLS.map((t, i) => (
        <span key={t.id} style={{ display: 'contents' }}>
          {i === 4 && <span className="sep" aria-hidden="true" />}
          <IconButton
            icon={t.icon}
            label={t.label}
            active={active === t.id}
            onClick={() => onSelect(t.id)}
          />
        </span>
      ))}
    </div>
  );
}
