import { Route, Routes, useLocation } from 'react-router-dom';
import { useEffect } from 'react';

import { Shell } from './layout/Shell';
import { LoginScreen } from './screens/LoginScreen';
import { BlockedScreen, PendingScreen, SplashScreen } from './screens/GateScreens';
import { HomeScreen } from './screens/HomeScreen';
import { LibraryScreen } from './screens/library/LibraryScreen';
import { ExamHome } from './screens/exam/ExamHome';
import { ExamResult } from './screens/exam/ExamResult';
import { ExamSetup, MockExamHistory } from './screens/exam/ExamSetup';
import { MockRun } from './screens/exam/MockRun';
import { HistoryScreen } from './screens/exam/HistoryScreen';
import { PracticeScreen } from './screens/exam/PracticeScreen';
import { NotesScreen } from './screens/notes/NotesScreen';
import { ReaderScreen } from './screens/reader/ReaderScreen';
import {
  BookScreen,
  LessonScreen,
  SessionScreen,
  SubjectScreen,
  TermScreen,
} from './screens/library/LibraryScreens';
import { MeScreen } from './screens/MeScreen';
import { Placeholder } from './screens/Placeholder';
import { StatesScreen } from './screens/StatesScreen';
import { SystemScreen } from './screens/SystemScreen';
import { useSession } from './lib/session';

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.querySelector('.content')?.scrollTo({ top: 0 });
  }, [pathname]);
  return null;
}

/** گارد — تنها جایی که «وضعیت حساب» به مسیر تبدیل می‌شود.
    سه وضعیت مستقل (نشست، تأیید، اشتراک) اینجا از هم جدا می‌مانند:
    این گارد فقط دو تای اول را می‌بیند؛ اشتراک در خود صفحه‌ها تصمیم می‌گیرد. */
function Gate({ children }: { children: React.ReactNode }) {
  const { status } = useSession();
  if (status === 'loading') return <SplashScreen />;
  if (status === 'pending_approval') return <PendingScreen />;
  if (status === 'suspended') return <BlockedScreen />;
  if (status !== 'active') return <LoginScreen />;
  return <>{children}</>;
}

/** صفحه‌های مرجع طراحی: بدون گارد، تا در بازبینی P0/P1 قابل دیدن باشند. */
const PUBLIC_PATHS = ['/system', '/states'];

/** پوسته بر اساس وضعیت واقعی نشست: تب‌بار فقط وقتی معنا دارد که
    کاربر وارد و تأییدشده باشد و در صفحه‌های مرجع نباشد. */
function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const { status } = useSession();
  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
  // ریدر فضای بیشتری می‌خواهد؛ تب‌بار پایین در آن پنهان می‌شود
  const immersive = pathname.startsWith('/read/');
  const variant = immersive ? 'reader' : status === 'active' && !isPublic ? 'default' : 'bare';
  return (
    <Shell tabs={status === 'active' && !isPublic && !immersive} variant={variant}>
      {children}
    </Shell>
  );
}

export function App() {
  return (
    <Layout>
      <ScrollToTop />
      <Routes>
        <Route
          path="/login"
          element={
            <Gate>
              <HomeScreen />
            </Gate>
          }
        />
        <Route path="/system" element={<SystemScreen />} />
        <Route path="/states" element={<StatesScreen />} />
        <Route
          path="/"
          element={
            <Gate>
              <HomeScreen />
            </Gate>
          }
        />
        <Route
          path="/library"
          element={
            <Gate>
              <LibraryScreen />
            </Gate>
          }
        />
        <Route path="/library/term/:term" element={<Gate><TermScreen /></Gate>} />
        <Route path="/library/lesson/:id" element={<Gate><LessonScreen /></Gate>} />
        <Route path="/library/session/:id" element={<Gate><SessionScreen /></Gate>} />
        <Route path="/library/subject/:id" element={<Gate><SubjectScreen /></Gate>} />
        <Route path="/library/book/:id" element={<Gate><BookScreen /></Gate>} />
        <Route path="/read/:scope/:id" element={<Gate><ReaderScreen /></Gate>} />
        <Route path="/me/notes" element={<Gate><NotesScreen /></Gate>} />
        <Route path="/exam" element={<Gate><ExamHome /></Gate>} />
        <Route path="/exam/practice" element={<Gate><PracticeScreen /></Gate>} />
        <Route path="/exam/history" element={<Gate><HistoryScreen /></Gate>} />
        <Route path="/exam/setup" element={<Gate><ExamSetup /></Gate>} />
        <Route path="/exam/mock/history" element={<Gate><MockExamHistory /></Gate>} />
        <Route path="/exam/run/:sid" element={<Gate><MockRun /></Gate>} />
        <Route path="/exam/result/:sid" element={<Gate><ExamResult /></Gate>} />
        <Route
          path="/search"
          element={
            <Gate>
              <Placeholder
                title="جستجو"
                sub="جستجوی سراسری"
                phase="P2"
                icon="i-search"
                note="نتایج جستجو باید به دامنهٔ دید کاربر احترام بگذارد؛ محتوای بیرون از دامنه هرگز برنمی‌گردد."
              />
            </Gate>
          }
        />
        <Route
          path="/schedule"
          element={
            <Gate>
              <Placeholder
                title="برنامه"
                sub="برنامهٔ هفتگی"
                phase="P7"
                icon="i-calendar"
                note="تقویم شمسی و جلسات از مسیر موجود برنامه خوانده می‌شود."
              />
            </Gate>
          }
        />
        <Route
          path="/me"
          element={
            <Gate>
              <MeScreen />
            </Gate>
          }
        />
        <Route
          path="*"
          element={
            <Gate>
              <Placeholder
                title="پیدا نشد"
                sub="مسیر نامعتبر"
                phase="—"
                icon="i-search"
                note="این مسیر وجود ندارد. از تب پایین به یکی از پنج ناحیه برگردید."
              />
            </Gate>
          }
        />
      </Routes>
    </Layout>
  );
}
