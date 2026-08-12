import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Stat, B, Empty } from '../ui.jsx';

// 📚 نمای کلی محتوا — scope-aware (ورودی‌محور + سراسری) از API فعلی content_admin
export default function Content() {
  const [intakes, setIntakes] = useState([]);
  const [intake, setIntake] = useState('');
  const [ov, setOv] = useState(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    api.caIntakes().then(r => setIntakes(r.intakes || [])).catch(e => setErr(errText(e)));
  }, []);
  const load = async () => {
    setErr(''); setOv(null);
    try { setOv(await api.caOverview(intake || undefined)); }
    catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, [intake]);

  if (err) return <ErrorState error={err} onRetry={load} />;

  return (
    <>
      <div className="h1">مدیریت محتوا</div>
      <div className="sub">نمای scope-محور؛ ساختار کامل (درس/جلسه/فایل) در مینی‌اپ ادمین محتوا در دسترس است</div>
      <div className="row" style={{ marginBottom: 14 }}>
        <select className="inp" value={intake} onChange={e => setIntake(e.target.value)}>
          <option value="">🌐 سراسری (پایه)</option>
          {intakes.map(i => <option key={i.code || i} value={i.code || i}>🏷 {i.label || i.code || i}</option>)}
        </select>
        <B kind="acc">فقط خواندنی — ویرایش/آپلود موقتاً از طریق پنل محتوا در مینی‌اپ</B>
      </div>
      {!ov ? <Loading rows={4} /> : (
        <>
          <div className="grid g4">
            <Stat icon="🧪" label="سوالات در انتظار بازبینی" value={Number(ov.pending_questions ?? 0).toLocaleString('fa')} tint="var(--warn)" />
            <Stat icon="✅" label="سوالات تأییدشده" value={Number(ov.approved_questions ?? 0).toLocaleString('fa')} tint="var(--ok)" />
            <Stat icon="📚" label="فایل‌های ریسورس" value={Number(ov.total_resources ?? 0).toLocaleString('fa')} tint="var(--acc)" />
            <Stat icon="🏷" label="Scope فعلی" value={ov.intake || 'سراسری'} tint="var(--purple)" />
          </div>
          {ov.effective && (
            <div className="panel panel-pad" style={{ marginTop: 14 }}>
              <b>🍴 وضعیت مؤثر (fork-aware)</b>
              <div className="muted" style={{ marginTop: 6 }}>
                نمای مؤثر = پایه‌ی سراسری + overrideهای ورودی «{ov.intake || '—'}»
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}
