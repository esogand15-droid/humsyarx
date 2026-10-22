/* لایهٔ دادهٔ جستجوی سراسری (موج P2) */
import { apiCall } from './api';

export interface SearchResultItem {
  id: string;
  title: string;
  type: 'resource' | 'question' | 'faq' | 'schedule' | 'subject' | 'book';
  subtitle?: string;
  meta?: string;
}

export interface SearchPayload {
  results: {
    resources?: SearchResultItem[];
    questions?: SearchResultItem[];
    faqs?: SearchResultItem[];
    schedules?: SearchResultItem[];
    subjects?: SearchResultItem[];
    books?: SearchResultItem[];
  };
  query: string;
}

export const searchApi = {
  global: (q: string) =>
    apiCall<SearchPayload>(`/search?q=${encodeURIComponent(q)}`),
};
