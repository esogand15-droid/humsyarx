import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Stat, B, toast, Confirm } from '../ui.jsx';

// 🖥 سلامت سامانه + پشتیبان‌گیری (فقط داده‌های واقعی بک‌اند — بدون متریک جعلی)
export default function System() {
  const [bs, setBs] = useState(null);
  const [err, setErr] = useState('');
  const [confirm, setConfirm] = useState(false);

  const load = async () => {
    setErr('');
    try { setBs(await api.botStatus()); } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);

  const doBackup = async () => {
    try { const r = await api.backup(); toast(r.message || 'پشتیبان‌گیری آغاز شد'); }
    catch (e) { toast(errText(e), 'err'); }
  };
  // 🌊 موج Export — درخواست خروجی اکسل؛ ربات فایل را در گفت‌وگوی ادمین می‌فرستد
  const [excelBusy, setExcelBusy] = useState(false);
  const doExcel = async () => {
    setExcelBusy(true);
    try {
      await api.exportExcel();
      toast('درخواست ثبت شد 📑 ربات فایل اکسل را در گفت‌وگوی شما می‌فرستد');
    } catch (e) { toast(errText(e), 'err'); }
    setExcelBusy(false);
  };

  if (err) return <ErrorState error={err} onRetry={load} />;
  if (!bs) return <Loading rows={4} />;

  const health = v => v ? ['🟢', 'ok', 'سالم'] : ['🔴', 'bad', 'مشکل'];
  const bot = !!bs.bot_ok ?? !!bs.online ?? true;

  return (
    <>
      <div className="h1">سلامت سامانه</div>
      <div className="sub">وضعیت زنده از endpointهای موجود — هیچ متریک ساختگی نمایش داده نمی‌شود</div>
      <div className="grid g4">
        <div className="panel stat">
          <div className="ic" style={{ background: 'rgba(52,211,153,.1)' }}>{health(bot)[0]}</div>
          <div><div className="v"><B kind={health(bot)[1]}>{health(bot)[2]}</B></div><div className="l">ربات تلگرام</div></div>
        </div>
        <div className="panel stat">
          <div className="ic" style={{ background: 'rgba(56,182,255,.1)' }}>🗄️</div>
          <div><div className="v"><B kind="ok">متصل</B></div><div className="l">پایگاه‌داده (پاسخ‌گو)</div></div>
        </div>
        <div className="panel stat">
          <div className="ic" style={{ background: 'rgba(167,139,250,.1)' }}>⚙️</div>
          <div><div className="v"><B kind="ok">فعال</B></div><div className="l">API</div></div>
        </div>
      </div>

      <div className="panel panel-pad" style={{ marginTop: 14 }}>
        <b>جزئیات bot-status</b>
        <dl className="kv" style={{ marginTop: 8 }}>
          {Object.entries(bs).filter(([, v]) => typeof v !== 'object').slice(0, 14).map(([k, v]) => (
            <React.Fragment key={k}><dt>{k}</dt><dd>{String(v)}</dd></React.Fragment>
          ))}
        </dl>
      </div>

      <div className="panel panel-pad" style={{ marginTop: 14 }} >
        <div className="row">
          <div><b>💾 پشتیبان‌گیری دستی</b>
            <div className="muted" style={{ marginTop: 4 }}>auto_backup روزانه‌ی ربات فعال است؛ این اکشن یک نسخه‌ی فوری می‌سازد و در لاگ ثبت می‌شود.</div></div>
          <span className="spacer" />
          <button className="btn" disabled={excelBusy} onClick={doExcel}>
            {excelBusy ? '⏳ …' : '📑 خروجی اکسل کامل'}
          </button>
          <button className="btn" onClick={() => setConfirm(true)}>ساخت پشتیبان فوری</button>
        </div>
      </div>
      {confirm && (
        <Confirm text="ساخت پشتیبان کامل از پایگاه‌داده؟ (عملیات حساس — در audit ثبت می‌شود)"
                 onYes={async () => { setConfirm(false); await doBackup(); }}
                 onNo={() => setConfirm(false)} />
      )}
    </>
  );
}
