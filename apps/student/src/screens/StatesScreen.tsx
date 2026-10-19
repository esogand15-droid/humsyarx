import { AppBar, Button, Card, Chip } from '../components';
import { Icon } from '../icons';
import type { IconName } from '../icons/sprite';

interface StateSpec {
  id: string;
  title: string;
  icon: IconName;
  message: string;
  action: string;
  code: string;
  tone: 'neutral' | 'warn' | 'danger';
}

/** نگاشت «کد خطای واقعی ← وضعیت UI» — design/16 §۳. یک مرجع، نه پیام‌های پراکنده. */
const STATES: StateSpec[] = [
  { id: 'offline', title: 'اتصال قطع است', icon: 'i-arch', code: 'offline', tone: 'warn',
    message: 'محتوایی که قبلاً دیده‌ای در دسترس است؛ جزوهٔ هامزیار در حالت آفلاین خوانده نمی‌شود.', action: 'تلاش دوباره' },
  { id: 'expired', title: 'برای ادامه وارد شو', icon: 'i-lock', code: '401 login_required', tone: 'neutral',
    message: 'نشست شما منقضی شده است. بعد از ورود، به همین صفحه برمی‌گردید.', action: 'ورود با کد کاربری' },
  { id: 'pending', title: 'حساب در انتظار تأیید', icon: 'i-clock', code: '403 pending_approval', tone: 'warn',
    message: 'حساب شما ساخته شده ولی هنوز تأیید نشده است. تأیید از ربات هامزیار انجام می‌شود.', action: 'راهنمای تأیید' },
  { id: 'suspended', title: 'دسترسی حساب بسته است', icon: 'i-lock', code: '403 suspended', tone: 'danger',
    message: 'دسترسی این حساب موقتاً متوقف شده است. برای بررسی با پشتیبانی در تماس باشید.', action: 'پشتیبانی' },
  { id: 'locked', title: 'این جزوه برای مشترکین است', icon: 'i-book', code: '402 feature_disabled', tone: 'neutral',
    message: 'جزوه‌های تیم هامزیار فقط داخل برنامه و برای اشتراک فعال خوانده می‌شوند.', action: 'مشاهدهٔ پلن‌ها' },
  { id: 'notfound', title: 'این صفحه پیدا نشد', icon: 'i-search', code: '404', tone: 'neutral',
    message: 'ممکن است محتوا جابه‌جا شده یا برای ورودی تحصیلی شما نباشد.', action: 'بازگشت به کتابخانه' },
  { id: 'error', title: 'مشکلی پیش آمد', icon: 'i-arch', code: '500', tone: 'danger',
    message: 'خطا ثبت شد. اگر تکرار شد، کد پیگیری را به پشتیبانی بدهید.', action: 'تلاش دوباره' },
  { id: 'policy', title: 'موقتاً ممکن نیست', icon: 'i-clock', code: '503 policy_unavailable', tone: 'warn',
    message: 'سیستم دسترسی در دسترس نیست. چند لحظه بعد دوباره تلاش کنید.', action: 'تلاش دوباره' },
];

const TONE: Record<StateSpec['tone'], 'quiet' | 'amber' | 'danger'> = {
  neutral: 'quiet',
  warn: 'amber',
  danger: 'danger',
};

/** پیش‌نمایش وضعیت‌های سیستمی — همان چیزی که در P1 پیاده می‌شود. */
export function StatesScreen() {
  return (
    <>
      <AppBar title="وضعیت‌های سیستمی" sub="طراحی، نه اتفاق" back />
      <div className="page">
      <p className="small" style={{ marginTop: 14 }}>
        هر کد خطای واقعی سرور یک وضعیت مشخص در رابط دارد؛ هیچ صفحه‌ای پیام اختصاصی نمی‌سازد.
      </p>
      <div className="stack gap-12 mt-16">
        {STATES.map((s) => (
          <Card key={s.id}>
            <div className="row gap-8" style={{ justifyContent: 'space-between' }}>
              <Chip variant={TONE[s.tone]}>{s.code}</Chip>
              <Icon name={s.icon} size={22} />
            </div>
            <div className="h3 mt-8">{s.title}</div>
            <p className="small mt-8">{s.message}</p>
            <Button variant="ghost" size="sm" className="mt-12">{s.action}</Button>
          </Card>
        ))}
      </div>
      </div>
    </>
  );
}
