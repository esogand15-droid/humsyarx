import type { ReactNode } from 'react';

import { Button, Card, EmptyState, SkeletonStack } from '../components';
import { Icon } from '../icons';
import type { IconName } from '../icons/sprite';
import { ApiError, errorText } from '../lib/api';

/* حالت‌های مشترک کتابخانه — یک نگاشت، نه پیام‌های پراکنده در هر صفحه.
   همان جدول design/16: هر کد خطای واقعی یک وضعیت مشخص دارد. */

export function LoadingBlock({ rows = 4 }: { rows?: number }) {
  return (
    <div className="mt-16">
      <SkeletonStack rows={rows} />
    </div>
  );
}

interface ErrorBlockProps {
  error: unknown;
  onRetry?: () => void;
}

/** خطای بارگذاری: پیام بر اساس کد واقعی سرور، نه متن عمومی. */
export function ErrorBlock({ error, onRetry }: ErrorBlockProps) {
  const offline = error instanceof ApiError && error.offline;
  const icon: IconName = offline ? 'i-arch' : 'i-clock';

  return (
    <EmptyState
      icon={icon}
      title={offline ? 'اتصال به سرور برقرار نشد' : 'بارگذاری ممکن نشد'}
      text={errorText(error, 'مشکلی پیش آمد. دوباره تلاش کن.')}
      action={
        onRetry ? (
          <Button variant="ghost" size="sm" onClick={onRetry}>
            تلاش دوباره
          </Button>
        ) : undefined
      }
    />
  );
}

/** بن‌بست دسترسی: وقتی گیت اشتراک/دامنه جلوی بخش را گرفته است.
    بن‌بست نیست — یک اقدام واقعی دارد (بازگشت یا راهنمای فعال‌سازی). */
export function LockedBlock({
  title,
  text,
  action,
  code,
}: {
  title: string;
  text: string;
  action?: ReactNode;
  code?: string;
}) {
  return (
    <Card variant="quiet" className="mt-16" style={{ textAlign: 'center', padding: '26px 18px' }}>
      <div className="row" style={{ justifyContent: 'center' }}>
        <Icon name="i-lock" size={30} />
      </div>
      <div className="h3 mt-12">{title}</div>
      <p className="small mt-8" style={{ maxWidth: 340, marginInline: 'auto' }}>
        {text}
      </p>
      {code && (
        <p className="tiny mt-8" dir="ltr" style={{ opacity: 0.7 }}>
          {code}
        </p>
      )}
      {action && <div className="mt-16">{action}</div>}
    </Card>
  );
}
