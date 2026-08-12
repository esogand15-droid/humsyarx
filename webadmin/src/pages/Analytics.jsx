import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Stat } from '../ui.jsx';

// 📈 تحلیل‌ها — از endpoint تحلیل موجود (بدون ساخت داده‌ی جعلی)
export default function Analytics() {
  const [an, setAn] = useState(null);
  const [err, setErr] = useState('');

  const load = async () => {
    setErr('');
    try { setAn(await api.analytics()); } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);

  if (err) return <ErrorState error={err} onRetry={load} />;
  if (!an) return <Loading rows={6} />;

  const flat = Object.entries(an).filter(([, v]) => typeof v === 'number');
  const nested = Object.entries(an).filter(([, v]) => typeof v === 'object' && v !== null);

  return (
    <>
      <div className="h1">تحلیل‌های سامانه</div>
      <div className="sub">متحد از داده‌های واقعی answers/downloads/subscriptions</div>
      <div className="grid g4">
        {flat.map(([k, v]) => (
          <Stat key={k} icon="📊" label={k} value={Number(v).toLocaleString('fa')} tint="var(--acc)" />
        ))}
      </div>
      {nested.map(([k, obj]) => (
        <div key={k} className="panel panel-pad" style={{ marginTop: 14 }}>
          <b>{k}</b>
          <dl className="kv" style={{ marginTop: 8 }}>
            {Object.entries(obj).filter(([, v]) => typeof v !== 'object').slice(0, 16).map(([sk, sv]) => (
              <React.Fragment key={sk}>
                <dt>{sk}</dt>
                <dd>{typeof sv === 'number' ? Number(sv).toLocaleString('fa') : String(sv)}</dd>
              </React.Fragment>
            ))}
          </dl>
        </div>
      ))}
    </>
  );
}
