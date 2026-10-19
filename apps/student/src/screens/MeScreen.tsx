import { AppBar, Brand, Card, Chip, ListRow, Switch } from '../components';
import { useTheme } from '../lib/theme';

/** «من» — در P0 فقط تنظیم ظاهر کار می‌کند؛ بقیهٔ ردیف‌ها در P1 (D-026). */
export function MeScreen() {
  const { mode, setMode } = useTheme();

  return (
    <>
      <AppBar title="هامزیار من" sub="حساب، دستگاه‌ها و ظاهر" />
      <div className="page">
      <Card className="mt-16" style={{ textAlign: 'center' }}>
        <div style={{ display: 'flex', justifyContent: 'center' }}><Brand size="lg" /></div>
        <div className="h2 mt-12">حساب مهمان</div>
        <p className="small mt-8">ورود با کد کاربری در فاز P1 فعال می‌شود.</p>
        <div className="row gap-8 mt-12" style={{ justifyContent: 'center', flexWrap: 'wrap' }}>
          <Chip variant="quiet">بدون اشتراک</Chip>
          <Chip variant="quiet">۰ دستگاه</Chip>
        </div>
      </Card>

      <Card variant="flush" className="mt-16">
        <div className="setrow" style={{ padding: '14px 16px' }}>
          <span className="grow">
            <span className="h3" style={{ display: 'block' }}>تم تاریک</span>
            <span className="small">روشن، تاریک یا هماهنگ با سیستم</span>
          </span>
          <Switch
            checked={mode === 'dark'}
            onChange={(v) => setMode(v ? 'dark' : 'light')}
            label="تم تاریک"
          />
        </div>
        <ListRow title="کد کاربری" sub="در فاز P1" chevron onClick={() => {}} />
        <ListRow title="دستگاه‌های من" sub="در فاز P1" chevron onClick={() => {}} />
        <ListRow title="اشتراک" sub="در فاز P6" chevron onClick={() => {}} />
        <ListRow title="خروج از حساب" danger onClick={() => {}} />
      </Card>

      <p className="tiny mt-16" style={{ textAlign: 'center' }}>
        ساخت P0.2 · سیستم طراحی مرکب v0.1.0
      </p>
      </div>
    </>
  );
}
