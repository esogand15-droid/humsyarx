import { AppBar } from '../components/AppBar';
import { Card } from '../components/Card';
import { Chip } from '../components/Chip';
import { EmptyState } from '../components/EmptyState';
import type { IconName } from '../icons/sprite';

export interface PlaceholderProps {
  title: string;
  sub: string;
  phase: string;
  icon: IconName;
  note: string;
}

/**
 * صفحهٔ اسکلت — در P0 فقط پوسته و وضعیت خالی را تأیید می‌کند.
 * هیچ دادهٔ ساختگی نمایش داده نمی‌شود (D-022).
 */
export function Placeholder({ title, sub, phase, icon, note }: PlaceholderProps) {
  return (
    <>
      <AppBar title={title} sub={sub} />
      <div className="page">
      <EmptyState
        icon={icon}
        title="این صفحه هنوز محتوایی ندارد"
        text={note}
      />
      <Card variant="quiet" style={{ marginTop: 8 }}>
        <div className="row gap-8" style={{ justifyContent: 'space-between' }}>
          <span className="small">ساخته‌شدن در فاز</span>
          <Chip variant="brand">{phase}</Chip>
        </div>
        <p className="tiny" style={{ marginTop: 8 }}>
          تا آن فاز، هیچ عدد یا فهرست نمونه‌ای نمایش داده نمی‌شود تا دادهٔ ساختگی به الزام تبدیل نشود.
        </p>
      </Card>
      </div>
    </>
  );
}
