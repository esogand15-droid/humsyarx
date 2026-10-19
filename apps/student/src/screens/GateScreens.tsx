import { Brand, Button, Card, Chip } from '../components';
import { Icon } from '../icons';
import type { IconName } from '../icons/sprite';
import { useSession } from '../lib/session';

/* سه صفحهٔ «قبل از اپ» — منطبق با واژگان وضعیت در design/16:
   loading / pending_approval / suspended.
   هیچ‌کدام بن‌بست نیستند: هر کدام حداقل یک اقدام واقعی دارند. */

function StopPage({
  icon,
  eyebrow,
  title,
  body,
  steps,
  tone,
}: {
  icon: IconName;
  eyebrow: string;
  title: string;
  body: string;
  steps?: string[];
  tone: 'warn' | 'danger';
}) {
  const { refresh, signOut, config } = useSession();
  const support = config?.support_url;

  return (
    <div className="auth">
      <div className="auth__head">
        <Brand size="lg" />
        <div className="mt-16">
          <Chip variant={tone === 'danger' ? 'danger' : 'amber'} icon={icon}>
            {eyebrow}
          </Chip>
        </div>
        <h1 className="h1 mt-12">{title}</h1>
        <p className="body mt-8">{body}</p>
      </div>

      {steps && steps.length > 0 && (
        <Card variant="quiet" className="mt-16">
          <ol className="steps">
            {steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </Card>
      )}

      <div className="auth__form">
        <Button block onClick={() => void refresh()}>
          بررسی دوبارهٔ وضعیت
        </Button>
        {support ? (
          <a className="btn btn--ghost btn--block" href={support} target="_blank" rel="noreferrer">
            <Icon name="i-chat" size={18} />
            گفتگو با پشتیبانی در تلگرام
          </a>
        ) : (
          <p className="tiny" style={{ textAlign: 'center' }}>
            برای پیگیری، از همان ربات هامزیار در تلگرام پیام بده.
          </p>
        )}
        <button type="button" className="linkbtn" onClick={() => void signOut()}>
          خروج از حساب
        </button>
      </div>
    </div>
  );
}

export function PendingScreen() {
  return (
    <StopPage
      icon="i-clock"
      eyebrow="در انتظار تأیید"
      title="حسابت هنوز تأیید نشده"
      body="ثبت‌نام تو انجام شده، ولی دسترسی به محتوا بعد از تأیید باز می‌شود. این کار از ربات هامزیار انجام می‌شود و معمولاً چند ساعت طول می‌کشد."
      steps={[
        'در ربات هامزیار، مشخصات خودت را کامل کن.',
        'اگر شمارهٔ دانشجویی خواسته شده، واردش کن.',
        'بعد از تأیید، همین صفحه را دوباره بررسی کن.',
      ]}
      tone="warn"
    />
  );
}

export function BlockedScreen() {
  return (
    <StopPage
      icon="i-lock"
      eyebrow="دسترسی بسته"
      title="دسترسی این حساب موقتاً متوقف شده"
      body="ورود تو درست بود، اما دسترسی به محتوا برای این حساب بسته است. اگر فکر می‌کنی اشتباهی رخ داده، از مسیر پشتیبانی پیگیری کن."
      steps={[
        'اگر اشتراکت تازه تمام شده، بعد از تمدید دسترسی خودکار برمی‌گردد.',
        'برای بررسی، کد حساب خودت را به پشتیبانی بده.',
      ]}
      tone="danger"
    />
  );
}

export function SplashScreen() {
  return (
    <div className="auth auth--splash" aria-busy="true">
      <Brand size="lg" />
      <p className="small mt-16">در حال بررسی وضعیت حساب…</p>
    </div>
  );
}
