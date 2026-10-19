import { useState } from 'react';

import { AppBar, Brand, Card, Chip, ListRow, Switch } from '../components';
import { useSession } from '../lib/session';
import { useTheme } from '../lib/theme';

/** «من» — در P1 هویت واقعی و خروج کار می‌کند؛ بقیهٔ ردیف‌ها فاز بعدی‌اند (D-026). */
export function MeScreen() {
  const { mode, setMode } = useTheme();
  const { user, signOut } = useSession();
  const [leaving, setLeaving] = useState(false);

  const name = user?.name?.trim() || 'دانشجوی هامزیار';
  const code = user?.student_id?.trim() || '—';
  const handle = user?.username ? `@${user.username}` : '—';

  return (
    <>
      <AppBar title="هامزیار من" sub="حساب، دستگاه‌ها و ظاهر" />
      <div className="page">
        <Card className="mt-16" style={{ textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <Brand size="lg" />
          </div>
          <div className="h2 mt-12">{name}</div>
          <p className="small mt-8">
            {handle} · شمارهٔ دانشجویی {code}
          </p>
          <div className="row gap-8 mt-12" style={{ justifyContent: 'center', flexWrap: 'wrap' }}>
            <Chip variant="quiet">حساب تأییدشده</Chip>
            {user?.group ? <Chip variant="quiet">{user.group}</Chip> : null}
          </div>
        </Card>

        <Card variant="flush" className="mt-16">
          <div className="setrow" style={{ padding: '14px 16px' }}>
            <span className="grow">
              <span className="h3" style={{ display: 'block' }}>
                تم تاریک
              </span>
              <span className="small">روشن، تاریک یا هماهنگ با سیستم</span>
            </span>
            <Switch
              checked={mode === 'dark'}
              onChange={(v) => setMode(v ? 'dark' : 'light')}
              label="تم تاریک"
            />
          </div>
          <ListRow title="دفتر من" sub="یادداشت‌ها و خط‌کشیده‌ها" to="/me/notes" chevron />
          <ListRow title="کد حساب" sub="در فاز P6 — قابل تغییر توسط پشتیبانی" chevron onClick={() => {}} />
          <ListRow title="دستگاه‌های من" sub="در فاز P6" chevron onClick={() => {}} />
          <ListRow title="اشتراک" sub="در فاز P6" chevron onClick={() => {}} />
          <ListRow
            title={leaving ? 'در حال خروج…' : 'خروج از حساب'}
            danger
            onClick={() => {
              if (leaving) return;
              setLeaving(true);
              void signOut().finally(() => setLeaving(false));
            }}
          />
        </Card>

        <p className="tiny mt-16" style={{ textAlign: 'center' }}>
          ساخت P1 · سیستم طراحی مرکب v0.1.0
        </p>
      </div>
    </>
  );
}
