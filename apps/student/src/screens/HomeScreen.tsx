import { Link } from 'react-router-dom';
import { AppBar, Brand, Card, EmptyState, IconButton, ListRow, Chip } from '../components';

/** خانه — در P0 فقط پوسته و مسیرهای موجود؛ داده در P2 (داشبورد) می‌آید. */
export function HomeScreen() {
  return (
    <>
      <AppBar
        title="هامزیار"
        sub="همراه تو، از ترم یک تا پای تخته"
        actions={<IconButton icon="i-grid" label="سیستم طراحی" />}
      />
      <div className="page">
      <div className="row gap-12 mt-16" style={{ alignItems: 'center' }}>
        <Brand size="md" />
        <div className="grow">
          <div className="eyebrow">فاز P0 · اسکلت</div>
          <div className="h2">پوسته آماده است</div>
        </div>
        <Chip variant="cyan" icon="i-check">RTL و تم</Chip>
      </div>

      <EmptyState
        icon="i-home"
        title="داشبورد در فاز P2 ساخته می‌شود"
        text="تا آن زمان هیچ آمار یا کارت نمونه‌ای نمایش داده نمی‌شود؛ دادهٔ ساختگی می‌تواند به الزام تبدیل شود."
      />

      <Card variant="flush">
        <Link to="/system"><ListRow icon="i-grid" title="سیستم طراحی" sub="توکن‌ها، اجزا و آیکون‌ها — مرجع زنده" chevron onClick={() => {}} /></Link>
        <Link to="/states"><ListRow icon="i-lock" title="وضعیت‌های سیستمی" sub="خطا، آفلاین، قفل و انقضای نشست" chevron onClick={() => {}} /></Link>
      </Card>
      </div>
    </>
  );
}
