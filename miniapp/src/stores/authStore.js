import { create } from 'zustand';
import api from '../lib/api';
import { getTgUser, isTelegram } from '../lib/telegram';
import { IS_PWA } from '../lib/appMode';

/* 📲 در نسخهٔ نصب‌شدنی وب، «نبودِ تلگرام» خطا نیست: کاربر با کد
   یک‌بارمصرف (که ربات در تلگرام می‌فرستد) وارد می‌شود و نشست کوکی
   برقرار می‌ماند. تنها حالتی که واقعاً خطاست، «نشست نداریم». */
async function webSessionActive() {
  try {
    const { data } = await api.get('/api/web-auth/session');
    return Boolean(data?.authenticated);
  } catch (_) {
    return false;
  }
}

export const useAuthStore = create((set, get) => ({
  user: null,
  tgUser: null,
  loading: true,
  error: null,

  init: async () => {
    const tgUser = getTgUser();

    set({
      tgUser,
      loading: true,
      error: null,
    });

    // خارج از محیط تلگرام، initData معتبر وجود ندارد.
    // در PWA: اگر نشست وب داریم ادامه می‌دهیم، وگرنه صفحهٔ ورود.
    // 📲 در نسخهٔ نصب‌شدنی، تلگرام اصلاً مرجع نیست — حتی اگر شیء
    // global آن لود شده باشد؛ همیشه مسیر «نشست وب» تصمیم می‌گیرد.
    if (IS_PWA || !isTelegram) {
      if (IS_PWA) {
        const active = await webSessionActive();
        if (!active) {
          set({ loading: false, error: 'web_login_required' });
          return;
        }
      } else {
        set({ loading: false, error: 'telegram_required' });
        return;
      }
    }

    try {
      const response = await api.get('/api/profile');

      set({
        user: response.data?.user || null,
        loading: false,
        error: null,
      });
    } catch (error) {
      const detail = error.response?.data?.detail;

      /* 🧯 فقط رشتهً‌ رشته! detail در خطاهای
         422 لیست/آبجکت است و اگر به AuthError
         برسد، رندرش کرش می‌کند (صفحه‌ی تاریک) */
      set({
        loading: false,

        error:
          typeof detail === 'string'
            ? detail

          : error.response
            ? 'error'
            : 'network_error',
      });
    }
  },

  refresh: async () => {
    try {
      const response = await api.get('/api/profile');
      const user = response.data?.user || null;

      set({ user });

      return user;
    } catch (_) {
      return null;
    }
  },

  /* 📲 پس از ورود موفق با کد، اپ را دوباره بالا بیاور */
  loggedIn: async () => {
    set({ loading: true, error: null });
    try {
      const response = await api.get('/api/profile');
      set({
        user: response.data?.user || null,
        loading: false,
        error: null,
      });
    } catch (error) {
      const detail = error.response?.data?.detail;
      set({
        loading: false,
        error: typeof detail === 'string' ? detail : 'error',
      });
    }
  },

  /* 📲 خروج از نسخهٔ وب (نشست کوکی سمت سرور هم باطل می‌شود) */
  logoutWeb: async () => {
    try {
      await api.post('/api/web-auth/logout');
    } catch (_) {
      /* حتی اگر شبکه نبود، سمت کلاینت خارج می‌شویم */
    }
    set({ user: null, loading: false, error: 'web_login_required' });
  },

  /* تغییر وضعیت احراز هویت وسط نشست
     (مثل تعلیق کاربر توسط مدیر در حین استفاده) —
     api.js این رویدادها را روی window دیسپچ می‌کند */
  forceError: (code) =>
    set({
      user: null,
      loading: false,
      error: code,
    }),
}));
