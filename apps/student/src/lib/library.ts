/* لایهٔ دادهٔ کتابخانه (موج P2) — هر شکل داده دقیقاً همان چیزی است که
   هندلرهای موجود مینی‌اپ برمی‌گردانند؛ هیچ فیلدی این‌جا ساخته نمی‌شود. */
import { apiCall } from './api';

export interface TermItem {
  name: string;
  lesson_count: number;
}

export interface LessonItem {
  _id: string;
  name: string;
  teacher: string;
  term: string;
  session_count: number;
}

export interface SessionItem {
  _id: string;
  number: number;
  topic: string;
  teacher: string;
  file_count: number;
  logical_id: string;
}

export type FileKind = 'video' | 'ppt' | 'pdf' | 'note' | 'test' | 'voice' | 'file' | string;

export interface ContentFile {
  id: string;
  type: FileKind;
  name: string;
  description: string;
  downloads: number;
  mime: string;
  size: number;
  preview: boolean;
  lesson?: string;
  session?: string;
}

export interface SubjectItem {
  id: string;
  name: string;
  book_count: number;
}

export interface BookItem {
  id: string;
  name: string;
  fa_count: number;
  en_count: number;
}

export interface ReferenceFile {
  id: string;
  lang: 'fa' | 'en';
  volume: number;
  description: string;
  downloads: number;
  mime: string;
  size: number;
  preview: boolean;
}

export interface GateState {
  allowed: boolean;
  code: string | null;
  message: string;
  status?: number;
}

export interface LibraryState {
  resources: GateState;
  references: GateState;
  intake: string;
  group: string;
}

export const library = {
  state: () => apiCall<LibraryState>('/library/state'),

  terms: () => apiCall<{ terms: TermItem[] }>('/library/terms'),

  lessons: (term: string) =>
    apiCall<{ lessons: LessonItem[] }>(`/library/lessons/${encodeURIComponent(term)}`),

  sessions: (lessonId: string) =>
    apiCall<{ sessions: SessionItem[] }>(`/library/sessions/${encodeURIComponent(lessonId)}`),

  files: (sessionId: string) =>
    apiCall<{ files: ContentFile[] }>(`/library/files/${encodeURIComponent(sessionId)}`),

  search: (q: string) =>
    apiCall<{ results: ContentFile[] }>(`/library/search?q=${encodeURIComponent(q)}`),

  subjects: () => apiCall<{ subjects: SubjectItem[] }>('/library/subjects'),

  books: (subjectId: string) =>
    apiCall<{ subject: { id: string; name: string }; books: BookItem[] }>(
      `/library/books/${encodeURIComponent(subjectId)}`,
    ),

  bookFiles: (bookId: string) =>
    apiCall<{ book: { id: string; name: string }; fa_files: ReferenceFile[]; en_files: ReferenceFile[] }>(
      `/library/book-files/${encodeURIComponent(bookId)}`,
    ),
};

/** برچسب فارسی نوع فایل — همان واژگان ربات، یک‌جا. */
export const FILE_LABEL: Record<string, string> = {
  video: 'ویدیو کلاس',
  ppt: 'پاورپوینت',
  pdf: 'جزوه PDF',
  note: 'نکات',
  test: 'تست',
  voice: 'ویس استاد',
  file: 'فایل آموزشی',
};

export function fileLabel(kind: string): string {
  return FILE_LABEL[kind] ?? FILE_LABEL.file;
}

/** حجم خوانا — بدون اعشار الکی، بدون صفر پیشرو. */
export function humanSize(bytes: number): string {
  if (!bytes || bytes < 0) return '';
  const units = ['بایت', 'کیلوبایت', 'مگابایت', 'گیگابایت'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = value >= 10 || unit === 0 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded.toLocaleString('fa-IR')} ${units[unit]}`;
}

/** عدد فارسی بدون ارقام لاتین. */
export function fa(value: number): string {
  return Math.max(0, Math.trunc(value || 0)).toLocaleString('fa-IR');
}
