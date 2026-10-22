import { useState } from 'react';
import { Link } from 'react-router-dom';

import { AppBar, Brand, Card, Chip, ListRow, Switch } from '../components';
import { Icon } from '../icons';
import { useSession } from '../lib/session';
import { useTheme } from '../lib/theme';

/** «من» — حساب کاربری، تنظیمات و خروج */
export function MeScreen() {
  const { mode, setMode } = useTheme();
  const { user, signOut } = useSession();
  const [leaving, setLeaving] = useState(false);
  const [copied, setCopied] = useState(false);

  const name = user?.name?.trim() || 'دانشجوی هامزیار';
  const code = user?.student_id?.trim() || '—';
  const handle = user?.username ? `@${user.username}` : '—';
  const group = user?.group || '';
  const intake = user?.intake || '';

  const copyCode = () => {
    if (code && code !== '—') {
      void navigator.clipboard.writeText(code).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      });
    }
  };

  return (
    <>
      <AppBar title="هامزیار من" sub="حساب، دستگاه‌ها و ظاهر" />
      <div className="page">
        {/* هویت */}
        <Card className="mt-8" style={{ textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <Brand size="lg" />
          </div>
          <div className="h2 mt-12">{name}</div>
          <p className="small mt-8">
            {handle} · شمارهٔ دانشجویی {code}
          </p>
          <div className="row gap-8 mt-12" style={{ justifyContent: 'center', flexWrap: 'wrap' }}>
            <Chip variant="quiet">حساب تأییدشده</Chip>
            {group ? <Chip variant="quiet">{group}</Chip> : null}
            {intake ? <Chip variant="quiet">{intake}</Chip> : null}
          </div>
        </Card>

        {/* کد کاربری */}
        <Card className="mt-12">
          <div className="row row--between">
            <div>
              <div className="h3">کد کاربری</div>
              <div className="small mt-4">برای ورود سریع و اشتراک‌گذاری</div>
            </div>
            <button
              className="btn btn--sm btn--ghost"
              onClick={copyCode}
              style={{ direction: 'ltr' }}
            >
              <Icon name={copied ? 'i-check' : 'i-copy'} size={16} />
              {copied ? 'کپی شد' : code}
            </button>
          </div>
        </Card>

        {/* ظاهر */}
        <Card variant="flush" className="mt-12">
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
        </Card>

        {/* دسترسی‌ها */}
        <Card variant="flush" className="mt-12">
          <Link to="/me/notes">
            <ListRow icon="i-pen" title="دفتر من" sub="یادداشت‌ها و خط‌کشیده‌ها" chevron />
          </Link>
          <ListRow icon="i-smartphone" title="دستگاه‌های من" sub="مدیریت دستگاه‌های متصل" chevron onClick={() => {}} />
          <ListRow icon="i-credit-card" title="اشتراک" sub="وضعیت و تمدید اشتراک" chevron onClick={() => {}} />
          <ListRow icon="i-bell" title="اعلان‌ها" sub="تنظیم اعلان‌های تلگرام" chevron onClick={() => {}} />
          <ListRow icon="i-shield" title="امنیت" sub="تغییر کد کاربری و خروج از همه دستگاه‌ها" chevron onClick={() => {}} />
        </Card>

        {/* پشتیبانی */}
        <Card variant="flush" className="mt-12">
          <ListRow icon="i-message-circle" title="پشتیبانی" sub="ارتباط با تیم هامزیار" chevron onClick={() => {}} />
          <ListRow icon="i-help-circle" title="راهنما و سوالات متداول" sub="آموزش استفاده از اپ" chevron onClick={() => {}} />
          <ListRow icon="i-info" title="دربارهٔ هامزیار" sub="نسخه ۲.۰ · ساخته‌شده با ❤️" chevron onClick={() => {}} />
        </Card>

        {/* خروج */}
        <Card variant="flush" className="mt-12">
          <ListRow
            icon="i-log-out"
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
          هامزیار v2.0 · دستیار هوشمند دانشجویان پزشکی
        </p>
      </div>
    </>
  );
}
