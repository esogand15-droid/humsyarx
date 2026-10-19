import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { IconButton } from './IconButton';

export interface AppBarProps {
  title: string;
  sub?: string;
  back?: boolean;
  actions?: ReactNode;
  onBack?: () => void;
}

/** نوار بالای صفحه — چسبان، با خط زیرین؛ بدون سایه. */
export function AppBar({ title, sub, back = false, actions, onBack }: AppBarProps) {
  const navigate = useNavigate();
  return (
    <header className="appbar">
      {back && <IconButton icon="i-chevron-r" label="بازگشت" onClick={onBack ?? (() => navigate(-1))} />}
      <div className="grow">
        <div className="appbar__title">{title}</div>
        {sub && <div className="appbar__sub">{sub}</div>}
      </div>
      {actions}
    </header>
  );
}
