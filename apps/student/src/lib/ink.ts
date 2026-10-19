/** 🖋 لایهٔ دادهٔ حاشیه‌نویسی.
 *
 *  قواعدی که عمداً این‌جاست و در کامپوننت‌ها تکرار نمی‌شود:
 *  - مختصات نرمال‌شده (۰..۱) → یک خط روی هر دستگاهی همان‌جا می‌نشیند.
 *  - ذخیره = جایگزینی کامل صفحه (idempotent) → تلاش دوباره، خط تکراری نمی‌سازد.
 *  - صف آفلاین در localStorage → در مترو هم می‌شود نوشت.
 */
import { apiCall } from './api';

export type Scope = 'res' | 'ref';
export type InkTool = 'pen' | 'highlighter';
export interface Stroke {
  tool: InkTool;
  color: string;
  /** کسری از عرض صفحه، نه پیکسل */
  width: number;
  /** [[x,y], …] نرمال‌شده */
  points: [number, number][];
}

export interface InkSummaryPage {
  page: number;
  count: number;
}

export interface NoteItem {
  scope: Scope;
  id: string;
  name: string;
  kind: string;
  pages: number;
  strokes: number;
  last_page: number;
  updated_at: string;
  available: boolean;
}

const QUEUE_KEY = 'hy_ink_queue_v1';

interface Pending {
  key: string;
  scope: Scope;
  id: string;
  page: number;
  strokes: Stroke[];
  at: number;
}

function readQueue(): Pending[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY);
    return raw ? (JSON.parse(raw) as Pending[]) : [];
  } catch {
    return [];
  }
}

function writeQueue(items: Pending[]) {
  try {
    if (items.length === 0) localStorage.removeItem(QUEUE_KEY);
    else localStorage.setItem(QUEUE_KEY, JSON.stringify(items));
  } catch {
    /* حافظهٔ مرورگر پر است — از صف صرف‌نظر می‌کنیم، خود ذخیرهٔ بعدی می‌آید */
  }
}

function enqueue(item: Pending) {
  const rest = readQueue().filter((q) => q.key !== item.key);
  rest.push(item);
  // سقف ۵۰ صفحهٔ در انتظار؛ قدیمی‌ترها دور ریخته می‌شوند تا حافظه نترکد
  writeQueue(rest.slice(-50));
}

export const inkPending = () => readQueue().length;

export const ink = {
  page: (scope: Scope, id: string, page: number) =>
    apiCall<{ strokes: Stroke[]; updated_at: string | null }>(
      `/ink/${scope}/${encodeURIComponent(id)}/${page}`,
    ),

  summary: (scope: Scope, id: string) =>
    apiCall<{ pages: InkSummaryPage[]; total: number }>(
      `/ink/summary/${scope}/${encodeURIComponent(id)}`,
    ),

  notes: () => apiCall<{ items: NoteItem[] }>('/ink/notes'),

  /** ذخیره با پشتیبانی آفلاین: اول صف، بعد شبکه. */
  save: async (scope: Scope, id: string, page: number, strokes: Stroke[]) => {
    const item: Pending = {
      key: `${scope}:${id}:${page}`,
      scope,
      id,
      page,
      strokes,
      at: Date.now(),
    };
    try {
      await apiCall<{ ok: boolean }>(`/ink/${scope}/${encodeURIComponent(id)}/${page}`, {
        method: 'PUT',
        body: JSON.stringify({ strokes }),
      });
      // ذخیرهٔ موفق، همان صفحه را از صف بیرون می‌کند
      writeQueue(readQueue().filter((q) => q.key !== item.key));
      return { ok: true, queued: false };
    } catch {
      enqueue(item);
      return { ok: false, queued: true };
    }
  },

  clearPage: async (scope: Scope, id: string, page: number) => {
    try {
      await apiCall<{ ok: boolean }>(`/ink/${scope}/${encodeURIComponent(id)}/${page}`, {
        method: 'DELETE',
      });
    } catch {
      /* پاک‌کردن آفلاین: به‌صورت «صفحهٔ خالی» در صف می‌نشیند */
    }
    writeQueue(readQueue().filter((q) => q.key !== `${scope}:${id}:${page}`));
  },

  /** فرستادن دوبارهٔ هر چیزی که آفلاین مانده بود. */
  flush: async () => {
    const items = readQueue();
    if (items.length === 0) return 0;
    let sent = 0;
    for (const it of items) {
      try {
        await apiCall<{ ok: boolean }>(`/ink/${it.scope}/${encodeURIComponent(it.id)}/${it.page}`, {
          method: 'PUT',
          body: JSON.stringify({ strokes: it.strokes }),
        });
        writeQueue(readQueue().filter((q) => q.key !== it.key));
        sent += 1;
      } catch {
        break; // شبکه هنوز نیست؛ بار بعد
      }
    }
    return sent;
  },
};
