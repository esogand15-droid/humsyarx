import { Link } from 'react-router-dom';
import { AppBar, Brand, Card, IconButton, ListRow, Chip } from '../components';

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

      <div className="h3 mt-16">امروز چه کاری؟</div>
      <Card variant="flush" className="mt-8">
        <Link to="/exam">
          <ListRow
            icon="i-flask"
            title="تمرین سؤال"
            sub="از بانک سؤال، با پاسخ و توضیح"
            chevron
            onClick={() => {}}
          />
        </Link>
        <Link to="/library">
          <ListRow icon="i-book" title="کتابخانه" sub="جزوه، ویدیو و مرجع درسی" chevron onClick={() => {}} />
        </Link>
        <Link to="/me/notes">
          <ListRow icon="i-pen" title="دفتر من" sub="یادداشت‌های روی جزوه‌ها" chevron onClick={() => {}} />
        </Link>
      </Card>

      <Card variant="flush" className="mt-16">
        <Link to="/system"><ListRow icon="i-grid" title="سیستم طراحی" sub="توکن‌ها، اجزا و آیکون‌ها — مرجع زنده" chevron onClick={() => {}} /></Link>
        <Link to="/states"><ListRow icon="i-lock" title="وضعیت‌های سیستمی" sub="خطا، آفلاین، قفل و انقضای نشست" chevron onClick={() => {}} /></Link>
      </Card>
      </div>
    </>
  );
}
