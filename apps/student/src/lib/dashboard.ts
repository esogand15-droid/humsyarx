/* لایهٔ دادهٔ داشبورد (موج P2) — ویجت‌های خانه از /api/web/dashboard */
import { apiCall } from './api';

export interface DashboardUser {
  name: string;
  nickname?: string;
  display_name: string;
  intake: string;
  group: string;
  role: string;
}

export interface DashboardStats {
  total_answers: number;
  correct_answers: number;
  accuracy: number;
  streak_days: number;
  weak_topics: string[];
}

export interface UpcomingExam {
  id: string;
  lesson: string;
  date: string;
  time: string;
  days_left: number | null;
}

export interface DashboardPayload {
  user: DashboardUser;
  stats: DashboardStats;
  upcoming_exams: UpcomingExam[];
  open_tickets: number;
  prestige: Record<string, unknown>;
}

export interface WeeklyActivity {
  weekly: Array<{ day: string; count: number }>;
}

export interface LeaderboardItem {
  rank: number;
  name: string;
  correct: number;
  total: number;
  percent: number;
  is_me: boolean;
}

export interface LeaderboardPayload {
  leaderboard: LeaderboardItem[];
}

export const dashboard = {
  overview: () => apiCall<DashboardPayload>('/dashboard'),
  weekly: () => apiCall<WeeklyActivity>('/dashboard/weekly'),
  leaderboard: () => apiCall<LeaderboardPayload>('/dashboard/leaderboard'),
};
