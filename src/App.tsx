import { HashRouter, Route, Routes, useLocation } from 'react-router-dom';
import { useEffect, type ReactNode } from 'react';
import { Shell } from './components/Shell';
import { Home } from './screens/Home';
import { Library, ResourceDetail } from './screens/Library';
import { ExamHome, Practice, ExamRun, ExamResult } from './screens/Exam';
import { Hoshiar } from './screens/Hoshiar';
import { Plan } from './screens/Plan';
import { Profile, Settings, Subscription } from './screens/Me';
import { System } from './screens/System';
import { Handoff } from './screens/Handoff';
import { Notes } from './screens/Notes';
import { Capability } from './screens/Capability';

function ScrollTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    // پوسته خودش اسکرول می‌کند؛ پنجره دیگر اسکرول‌کننده نیست
    const main = document.getElementById('main');
    if (main) main.scrollTo({ top: 0 });
    window.scrollTo({ top: 0 });
  }, [pathname]);
  return null;
}

/** قاب صفحه: انتقال کوتاه و یکسان؛ مسیرهای تودرتو از سمت inline وارد می‌شوند */
function Frame({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const nested = pathname.split('/').filter(Boolean).length > 1;
  return (
    <div key={pathname} className={`route${nested ? ' page-enter--push page-enter' : ' page-enter'}`}>
      {children}
    </div>
  );
}

export function App() {
  return (
    <HashRouter>
      <ScrollTop />
      <Shell>
        <Frame>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/library" element={<Library />} />
          <Route path="/library/:id" element={<ResourceDetail />} />
          <Route path="/exam" element={<ExamHome />} />
          <Route path="/exam/practice" element={<Practice />} />
          <Route path="/exam/run" element={<ExamRun />} />
          <Route path="/exam/result" element={<ExamResult />} />
          <Route path="/ai" element={<Hoshiar />} />
          <Route path="/notes" element={<Notes />} />
          <Route path="/notes/:id" element={<Notes />} />
          <Route path="/capability" element={<Capability />} />
          <Route path="/plan" element={<Plan />} />
          <Route path="/me" element={<Profile />} />
          <Route path="/me/subscription" element={<Subscription />} />
          <Route path="/me/settings" element={<Settings />} />
          <Route path="/system" element={<System />} />
          <Route path="/handoff" element={<Handoff />} />
          <Route path="*" element={<Home />} />
        </Routes>
        </Frame>
      </Shell>
    </HashRouter>
  );
}
