/* لایهٔ دادهٔ برنامهٔ هفتگی (موج P2) */
import { apiCall } from './api';

export interface ScheduleItem {
  id: string;
  type: 'class' | 'exam' | 'makeup';
  lesson: string;
  teacher: string;
  date: string;
  time: string;
  end_time: string;
  location: string;
  note: string;
  group: string;
  educational_group: string;
  course_code: string;
  term: string;
  days_left: number | null;
}

export interface SchedulePayload {
  items: ScheduleItem[];
}

export const schedule = {
  list: (days = 7) =>
    apiCall<SchedulePayload>(`/schedule?days=${days}`),
};
