import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Stat } from '../ui.jsx';

// 🤖 مانیتورینگ هوشیار — مصرف/خطا/کاربران (از API ai-admin موجود)
export default function AiAdmin() {
  const [stats, setStats] = useState(null);
  const [cfg, setCfg] = useState(null);
  const [err, setErr] = useState('');

  const load = async () => {
    setErr('');
    try {
      setStats(await api.aiStats().catch(() => null));
      setCfg(await api.aiConfig().catch(() => null));
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);

  if (err) return <ErrorState error={err} onRetry={load} />;
  if (stats === null && cfg === null) return <Loading rows={4} />;

  return (
    <>
      <div className="h1">پنل هوشیار</div>
      <div className="sub">مصرف، پیکربندی مدل و سلامت سرویس پاسخ‌گویی</div>
      <div className="grid g4">
        {stats && Object.entries(stats).slice(0, 8).map(([k, v]) => (
          <Stat key={k} icon="🤖" label={k} value={typeof v === 'number' ? Number(v).toLocaleString('fa') : String(v)} tint="var(--acc)" />
        ))}
      </div>
      {cfg && (
        <div className="panel panel-pad" style={{ marginTop: 14 }}>
          <b>پیکربندی فعلی</b>
          <dl className="kv" style={{ marginTop: 10 }}>
            {Object.entries(cfg).filter(([k]) => !/key|token|secret/i.test(k)).slice(0, 12).map(([k, v]) => (
              <React.Fragment key={k}><dt>{k}</dt><dd>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd></React.Fragment>
            ))}
          </dl>
          <p className="muted">ویرایش پیکربندی از مینی‌اپ ادمین AI در دسترس است؛ این نما فقط‌خواندنی است تا قواعد کسب‌وکار تکثیر نشوند.</p>
        </div>
      )}
    </>
  );
}
