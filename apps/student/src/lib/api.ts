/* کلاینت API موج P1 — تنها جایی که مسیر شبکه‌ای نوشته می‌شود.
   همه‌ی درخواست‌ها same-origin هستند (`/api/web/...`)؛ پس نه CORS
   لازم است، نه کلید، نه آدرس هاردکدشده. کوکی نشست HttpOnly است و
   مرورگر خودش می‌فرستد؛ این لایه هیچ توکنی در JS نگه نمی‌دارد. */

const BASE = '/api/web';

export type AccountState =
  | 'anonymous'
  | 'active'
  | 'pending_approval'
  | 'suspended'
  | 'not_registered';

export interface PublicUser {
  id: number;
  name: string;
  username: string;
  student_id: string;
  group: string;
  intake: string;
  role: string;
  registered_at: string;
}

export interface SessionPayload {
  authenticated: boolean;
  state: AccountState;
  user: PublicUser | null;
}

export interface StartPayload {
  ok: boolean;
  challenge: string;
  channel: 'telegram';
  hint: string;
  resend_in: number;
  expires_in: number;
  debug_code?: string;
}

export interface VerifyPayload {
  ok: boolean;
  state: AccountState;
  user: PublicUser;
}

export interface AuthConfig {
  otp_length: number;
  otp_ttl_sec: number;
  resend_in: number;
  session_days: number;
  channels: string[];
  support_url: string | null;
}

/** خطای لایه‌ی شبکه: یا سرور کد خطا داده، یا اصلاً جوابی نیامده. */
export class ApiError extends Error {
  status: number;
  code: string;
  offline: boolean;
  /** کل بدنهٔ `detail` سرور — برای خطاهایی که دادهٔ همراه دارند.
   *  نمونه: `active_exam_exists` خودِ آزمون فعال را در `detail.exam`
   *  می‌فرستد تا صفحه بتواند «ادامه بده» پیشنهاد کند. */
  detail: Record<string, unknown> | null;

  constructor(code: string, status: number, offline = false, detail: Record<string, unknown> | null = null) {
    super(code);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.offline = offline;
    this.detail = detail;
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      ...init,
    });
  } catch {
    // قطعی شبکه یا نبودِ سرور — نه خطای اعتبارسنجی
    throw new ApiError('offline', 0, true);
  }

  let body: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      // پاسخ HTML (مثلاً صفحه‌ی 404 پروکسی) یعنی API اینجا نیست
      throw new ApiError('offline', res.status, true);
    }
  }

  if (!res.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    let code: string;
    let extra: Record<string, unknown> | null = null;
    if (typeof detail === 'string') {
      code = detail;
    } else if (detail && typeof detail === 'object' && 'code' in detail) {
      // گیت اشتراک: {code: "SUB_REQUIRED"|"feature_disabled"|..., message, feature}
      // آزمون: {code: "active_exam_exists", exam: {...}}
      code = String((detail as { code?: unknown }).code ?? `http_${res.status}`);
      extra = detail as Record<string, unknown>;
    } else {
      code = `http_${res.status}`;
    }
    throw new ApiError(code, res.status, false, extra);
  }
  return (body ?? {}) as T;
}

/** همان لایهٔ شبکه برای ماژول‌های دیگر (کتابخانه) — مسیر نسبی به /api/web. */
export const apiCall = call;

export const api = {
  session: () => call<SessionPayload>('/auth/session'),

  config: () => call<AuthConfig>('/auth/config'),

  start: (identifier: string) =>
    call<StartPayload>('/auth/start', {
      method: 'POST',
      body: JSON.stringify({ identifier }),
    }),

  verify: (challenge: string, code: string) =>
    call<VerifyPayload>('/auth/verify', {
      method: 'POST',
      body: JSON.stringify({ challenge, code }),
    }),

  logout: () => call<{ ok: boolean }>('/auth/logout', { method: 'POST' }),
};

/** پیام فارسی هر کد خطا — یک نگاشت واحد، نه متن پراکنده در کامپوننت‌ها. */
export const ERROR_TEXT: Record<string, string> = {
  offline: 'اتصال به سرور برقرار نشد. اینترنت را بررسی کن و دوباره تلاش کن.',
  identifier_invalid: 'شناسه معتبر نیست. یوزرنیم تلگرام یا شمارهٔ دانشجویی را وارد کن.',
  code_format: 'کد باید ۶ رقم باشد.',
  code_invalid: 'کد درست نیست. دوباره بررسی کن.',
  code_expired: 'این کد منقضی شده است. کد تازه بگیر.',
  too_many_attempts: 'تلاش‌های ناموفق زیاد شد. کد تازه بگیر.',
  rate_limited: 'درخواست‌ها زیاد شد. کمی بعد دوباره تلاش کن.',
  login_required: 'برای ادامه باید وارد شوی.',
  pending_approval: 'حساب تو هنوز تأیید نشده است.',
  suspended: 'دسترسی این حساب موقتاً بسته است.',
  not_registered: 'این حساب در هامزیار ثبت نشده است.',
  send_failed: 'ارسال کد ممکن نشد. کمی بعد دوباره تلاش کن.',
  SUB_REQUIRED: 'این بخش برای مشترکین هامزیار است.',
  subscription_required: 'این بخش برای مشترکین هامزیار است.',
  feature_disabled: 'این بخش موقتاً غیرفعال است.',
  policy_unavailable: 'سیستم دسترسی در دسترس نیست. کمی بعد دوباره تلاش کن.',
  not_in_scope: 'این محتوا برای ورودی تحصیلی تو نیست.',
  unknown_feature: 'این بخش در دسترس نیست.',
  forbidden: 'دسترسی به این بخش برای حساب تو باز نیست.',
  http_404: 'این محتوا پیدا نشد.',
  // ── بانک سؤال و آزمون (P5/P5.2) — همان کدهایی که دامنه برمی‌گرداند
  active_exam_exists: 'یک آزمون نیمه‌کاره داری؛ اول آن را ادامه بده یا رها کن.',
  exam_still_active: 'این آزمون هنوز تمام نشده است؛ کارنامه بعد از پایان می‌آید.',
  exam_not_found: 'این آزمون پیدا نشد.',
  exam_not_active: 'زمان این آزمون تمام شده است.',
  active_exam_not_found: 'آزمون فعالی برای رها کردن نیست.',
  answer_conflict: 'این پاسخ قبلاً ثبت شده است.',
  exam_capacity: 'برای این تعداد سؤال، ظرفیت بانک کافی نیست.',
  lesson_not_found: 'این درس در بانک سؤال پیدا نشد.',
  topic_not_found: 'این مبحث در بانک سؤال پیدا نشد.',
  ambiguous_lesson: 'درس انتخاب‌شده مبهم است؛ یکی از موارد پیشنهادی را انتخاب کن.',
  review_unavailable: 'بازبینی این آزمون فعلاً در دسترس نیست.',
  question_not_found: 'این سؤال پیدا نشد.',
};

export function errorText(err: unknown, fallback = 'مشکلی پیش آمد. دوباره تلاش کن.'): string {
  if (err instanceof ApiError) return ERROR_TEXT[err.code] ?? fallback;
  return fallback;
}
