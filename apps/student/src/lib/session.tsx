import type { ReactNode } from 'react';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { api, ApiError } from './api';
import type { AccountState, AuthConfig, PublicUser } from './api';

/** وضعیت نشست در کل اپ — تنها منبع حقیقت برای گارد مسیرها. */
export type SessionStatus = AccountState | 'loading';

interface SessionValue {
  status: SessionStatus;
  user: PublicUser | null;
  /** true وقتی سرور جواب نداده؛ ورود هنوز قابل تلاش است، فقط هشدار نشان می‌دهیم. */
  offline: boolean;
  config: AuthConfig | null;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>('loading');
  const [user, setUser] = useState<PublicUser | null>(null);
  const [offline, setOffline] = useState(false);
  const [config, setConfig] = useState<AuthConfig | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await api.session();
      setOffline(false);
      setUser(res.user);
      setStatus(res.authenticated ? res.state : 'anonymous');
    } catch (err) {
      // سرور در دسترس نیست → کاربر را پشت صفحه‌ی خطای بن‌بست حبس نمی‌کنیم؛
      // فرم ورود می‌ماند و هشدار «اتصال برقرار نشد» کنارش می‌آید.
      setOffline(err instanceof ApiError ? err.offline : false);
      setUser(null);
      setStatus('anonymous');
    }
  }, []);

  useEffect(() => {
    void refresh();
    let alive = true;
    api
      .config()
      .then((c) => {
        if (alive) setConfig(c);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [refresh]);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // حتی اگر شبکه خطا داد، سمت کلاینت خارج می‌شویم؛ کوکی منقضی می‌ماند
    }
    setUser(null);
    setStatus('anonymous');
  }, []);

  const value = useMemo<SessionValue>(
    () => ({ status, user, offline, config, refresh, signOut }),
    [status, user, offline, config, refresh, signOut],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession باید داخل SessionProvider استفاده شود');
  return ctx;
}
