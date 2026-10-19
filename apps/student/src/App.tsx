import { Route, Routes, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import { Shell } from './layout/Shell';
import { HomeScreen } from './screens/HomeScreen';
import { MeScreen } from './screens/MeScreen';
import { Placeholder } from './screens/Placeholder';
import { StatesScreen } from './screens/StatesScreen';
import { SystemScreen } from './screens/SystemScreen';

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.querySelector('.content')?.scrollTo({ top: 0 });
  }, [pathname]);
  return null;
}

export function App() {
  return (
    <Shell>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<HomeScreen />} />
        <Route
          path="/library"
          element={
            <Placeholder
              title="کتابخانه"
              sub="جزوه‌ها، منابع و کتاب مرجع"
              phase="P2"
              icon="i-book"
              note="کتابخانه به دادهٔ واقعی ترم/درس/جلسه و به وضعیت دسترسی کاربر وصل می‌شود."
            />
          }
        />
        <Route
          path="/search"
          element={
            <Placeholder
              title="جستجو"
              sub="جستجوی سراسری"
              phase="P2"
              icon="i-search"
              note="نتایج جستجو باید به دامنهٔ دید کاربر احترام بگذارد؛ محتوای بیرون از دامنه هرگز برنمی‌گردد."
            />
          }
        />
        <Route
          path="/schedule"
          element={
            <Placeholder
              title="برنامه"
              sub="برنامهٔ هفتگی"
              phase="P7"
              icon="i-calendar"
              note="تقویم شمسی و جلسات از مسیر موجود برنامه خوانده می‌شود."
            />
          }
        />
        <Route path="/me" element={<MeScreen />} />
        <Route path="/system" element={<SystemScreen />} />
        <Route path="/states" element={<StatesScreen />} />
        <Route
          path="*"
          element={
            <Placeholder
              title="پیدا نشد"
              sub="مسیر نامعتبر"
              phase="—"
              icon="i-search"
              note="این مسیر وجود ندارد. از تب پایین به یکی از پنج ناحیه برگردید."
            />
          }
        />
      </Routes>
    </Shell>
  );
}
