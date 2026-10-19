/* لایهٔ دادهٔ ریدر (موج P3).
   آدرسِ فایل، امضاشده و کوتاه‌عمر است (۱۰ دقیقه) و از سرور خودمان
   عبور می‌کند؛ توکن تلگرام هرگز به مرورگر نمی‌رسد. */
import { apiCall } from './api';

export type Scope = 'res' | 'ref';
export type Kind = 'pdf' | 'video' | 'audio' | 'image' | 'other';

export interface ViewInfo {
  id: string;
  name: string;
  mime: string;
  size: number;
  kind: Kind;
  available: boolean;
  reason?: string;
  url?: string;
  expires_in?: number;
}

export interface Progress {
  page: number;
  total: number;
  position: number;
  updated_at: string | null;
}

export interface ContinueItem {
  scope: Scope;
  id: string;
  name: string;
  kind: Kind;
  page: number;
  total: number;
  position: number;
  percent: number;
  updated_at: string;
}

export const reader = {
  viewUrl: (scope: Scope, id: string) =>
    apiCall<ViewInfo>(`/library/view-url/${scope}/${encodeURIComponent(id)}`),

  progress: (scope: Scope, id: string) =>
    apiCall<Progress>(`/library/progress/${scope}/${encodeURIComponent(id)}`),

  save: (scope: Scope, id: string, body: { page: number; total: number; position: number; kind: Kind }) =>
    apiCall<{ ok: boolean }>(`/library/progress/${scope}/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  recent: () => apiCall<{ items: ContinueItem[] }>('/library/continue'),
};

/** نشانی ریدر برای یک فایل — یک‌جا، تا لینک‌ها از هم جدا نشوند. */
export function readerPath(scope: Scope, id: string): string {
  return `/read/${scope}/${encodeURIComponent(id)}`;
}
