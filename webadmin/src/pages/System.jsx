import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Stat, B, toast, Confirm, Switch } from '../ui.jsx';

const fa = (n) => Number(n ?? 0).toLocaleString('fa-IR');

// 🖥 سلامت سامانه + 💾 مدیریت پشتیبان‌گیری (🌊 موج Backup-Mgmt)
// همان بخش‌های منوی «پشتیبان‌گیری» ربات + وضعیت/کنترل بکاپ خودکار —
// همه از endpointهای موجود؛ هیچ متریک ساختگی نمایش داده نمی‌شود.
const SECTIONS = [
  ['all',          '💾', 'کامل — همه بخش‌ها', 'کل دیتابیس (توصیه می‌شود)'],
  ['users',        '👥', 'کاربران',           'اطلاعات ثبت‌نام‌شدگان'],
  ['content',      '📚', 'علوم پایه',         'درس‌ها، جلسات و محتوا'],
  ['refs',         '📖', 'رفرنس‌ها',          'کتاب‌ها و فایل‌های درسی'],
  ['qbank',        '🧪', 'بانک سؤال',         'سؤال‌ها و فایل‌ها'],
  ['subscription', '💳', 'اشتراک و پرداخت',   'پلن‌ها، رسیدها، کدهای تخفیف'],
  ['grades',       '📊', 'نمرات',             'نمرات ثبت‌شده'],
  ['access',       '🔐', 'دسترسی‌ها و تنظیمات', 'نقش‌ها، بلک‌لیست، ورودی‌ها'],
];

export default function System() {
  const [bs, setBs] = useState(null);
  const [st, setSt] = useState(null);          // تنظیمات ربات (وضعیت بکاپ خودکار)
  const [err, setErr] = useState('');
  const [confirm, setConfirm] = useState(null); // section در انتظار تأیید
  const [busySec, setBusySec] = useState('');
  const [autoBusy, setAutoBusy] = useState(false);
  const [excelBusy, setExcelBusy] = useState(false);

  const load = async () => {
    setErr('');
    try {
      const [b, s] = await Promise.all([api.botStatus(), api.settings().catch(() => null)]);
      setBs(b); setSt(s);
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);

  const doBackup = async (section) => {
    setBusySec(section);
    try {
      const r = await api.backup(section === 'all' ? undefined : section);
      toast(r.message || '💾 درخواست پشتیبان ثبت شد — فایل در گفت‌وگوی ربات می‌آید');
    } catch (e) { toast(errText(e), 'err'); }
    setBusySec('');
  };
  const doExcel = async () => {
    setExcelBusy(true);
    try {
      await api.exportExcel();
      toast('درخواست ثبت شد 📑 ربات فایل اکسل را در گفت‌وگوی شما می‌فرستد');
    } catch (e) { toast(errText(e), 'err'); }
    setExcelBusy(false);
  };
  // ⏰ کنترل بکاپ خودکار — همان کلیدهای backup:auto_settings ربات (PATCH دارای audit)
  const setAuto = async (patch) => {
    setAutoBusy(true);
    try {
      await api.patchSettings(patch);
      setSt(s => ({ ...s, ...patch }));
      toast('تنظیمات بکاپ خودکار ذخیره شد ✅');
    } catch (e) { toast(errText(e), 'err'); }
    setAutoBusy(false);
  };

  if (err) return <ErrorState error={err} onRetry={load} />;
  if (!bs) return <Loading rows={4} />;

  const health = v => v ? ['🟢', 'ok', 'سالم'] : ['🔴', 'bad', 'مشکل'];
  const bot = !!bs.bot_ok ?? !!bs.online ?? true;
  const auto = st || {};
  const lastRun = (auto.auto_backup_last_run || '').slice(0, 16).replace('T', ' ');

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

      {/* ── ⏰ بکاپ خودکار روزانه (داده واقعی settings؛ PATCH دارای audit) ── */}
      {st && (
        <div className="panel panel-pad" style={{ marginTop: 14 }}>
          <div className="row" style={{ flexWrap: 'wrap', gap: 10 }}>
            <div>
              <b>⏰ بکاپ خودکار روزانه</b>
              <div className="muted" style={{ marginTop: 4 }}>
                {auto.auto_backup_enabled
                  ? `فعال — هر روز ساعت ${fa(auto.auto_backup_hour)}:۰۰ به‌وقت تهران؛ فایل مستقیماً در گفت‌وگوی مالک ارسال می‌شود.`
                  : 'غیرفعال — بکاپ کامل روزانه‌ی خودکار ساخته نمی‌شود.'}
              </div>
              <div className="muted" style={{ marginTop: 3 }}>
                🕐 آخرین اجرا: <span className="code">{lastRun || 'هنوز اجرا نشده'}</span>
              </div>
            </div>
            <span className="spacer" />
            <label className="row" style={{ gap: 6 }}>
              <Switch on={!!auto.auto_backup_enabled} disabled={autoBusy}
                      onChange={v => setAuto({ auto_backup_enabled: v })} />
              <span className="muted">فعال</span>
            </label>
            <select className="inp" style={{ maxWidth: 110 }} disabled={autoBusy}
                    value={auto.auto_backup_hour ?? 3}
                    onChange={e => setAuto({ auto_backup_hour: Number(e.target.value) })}>
              {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{fa(h)}:۰۰</option>)}
            </select>
          </div>
        </div>
      )}

      {/* ── 💾 پشتیبان دستی بخش‌بندی‌شده — دقیقاً همان بخش‌های منوی ربات ── */}
      <div className="panel panel-pad" style={{ marginTop: 14 }}>
        <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
          <div><b>💾 پشتیبان‌گیری دستی</b>
            <div className="muted" style={{ marginTop: 4 }}>بخش موردنظر را انتخاب کنید — فایل JSON از طریق ربات در گفت‌وگوی شما می‌آید (در audit ثبت می‌شود).</div>
          </div>
          <span className="spacer" />
          <button className="btn" disabled={excelBusy} onClick={doExcel}>
            {excelBusy ? '⏳ …' : '📑 خروجی اکسل کامل'}
          </button>
        </div>
        <div className="grid g4" style={{ marginTop: 12 }}>
          {SECTIONS.map(([key, icon, label, hint]) => (
            <div key={key} className="panel panel-pad bk-sec" style={{ background: 'var(--bg)' }}>
              <div className="row">
                <span style={{ fontSize: 18 }}>{icon}</span>
                <b style={{ fontSize: 13 }}>{label}</b>
              </div>
              <div className="muted" style={{ marginTop: 4, minHeight: 30 }}>{hint}</div>
              <button className={`btn sm ${key === 'all' ? 'primary' : ''}`} style={{ marginTop: 8, width: '100%' }}
                      disabled={!!busySec}
                      onClick={() => setConfirm(key)}>
                {busySec === key ? '⏳ در حال ثبت…' : key === 'all' ? 'ساخت پشتیبان کامل' : 'پشتیبان این بخش'}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* 🛠🌊 موج Parity-Final — عملیات مالک: prestige/force-send/تست گروه‌های لاگ */}
      <OwnerOpsPanel />

      {confirm && (
        <Confirm text={`ساخت پشتیبان «${SECTIONS.find(s => s[0] === confirm)?.[2]}»؟ (عملیات حساس — فایل در گفت‌وگوی ربات می‌آید و در audit ثبت می‌شود)`}
                 onYes={async () => { const s = confirm; setConfirm(null); await doBackup(s); }}
                 onNo={() => setConfirm(null)} />
      )}
    </>
  );
}

/* ── 🛠 عملیات مالک — همان دکمه‌های پراکنده‌ی پنل ربات (admin:prestige_backfill / notif_force_send / test_log_groups) ── */
function OwnerOpsPanel() {
  const [confirm, setConfirm] = useState(null);   // 'prestige' | 'force'
  const [busy, setBusy] = useState('');
  const [prestigeRep, setPrestigeRep] = useState(null);
  const [logRes, setLogRes] = useState(null);

  const runPrestige = async () => {
    setBusy('prestige');
    try {
      const r = await api.prestigeBackfill();
      setPrestigeRep(r.report);
      toast('Backfill Prestige کامل شد 🏅');
    } catch (e) {
      const t = errText(e);
      if (e.status === 403) return;               // غیرمالک: پنل بی‌فایده — پنهانش کن
      toast(t, 'err');
    } finally { setBusy(''); }
  };
  const runForce = async () => {
    setBusy('force');
    try {
      const r = await api.forceResNotif();
      toast(r.message || '📨 درخواست ثبت شد');
    } catch (e) { toast(errText(e), 'err'); }
    finally { setBusy(''); }
  };
  const runLogTest = async () => {
    setBusy('logtest'); setLogRes(null);
    try { setLogRes((await api.logGroupsTest()).results || []); }
    catch (e) { toast(errText(e), 'err'); }
    finally { setBusy(''); }
  };
  const LOG_ST = { sent: ['ok', '✅ ارسال شد'], unset: ['', '⬜ تنظیم نشده'], error: ['bad', '❌ خطا'] };

  return (
    <div className="panel panel-pad" style={{ marginTop: 14 }}>
      <b>🛠 عملیات مالک</b>
      <div className="muted" style={{ marginTop: 4 }}>همان اکشن‌های پراکنده‌ی پنل ربات — idempotent یا دارای Confirm؛ همه در audit ثبت می‌شوند.</div>
      <div className="row" style={{ marginTop: 10, flexWrap: 'wrap', gap: 8 }}>
        <button className="btn" disabled={!!busy} onClick={() => setConfirm('prestige')}>
          {busy === 'prestige' ? '⏳ در حال محاسبه…' : '🏅 محاسبه‌ی Prestige (Backfill)'}
        </button>
        <button className="btn" disabled={!!busy} onClick={() => setConfirm('force')}>
          {busy === 'force' ? '⏳ …' : '📨 ارسال فوری اعلان منابع'}
        </button>
        <button className="btn" disabled={!!busy} onClick={runLogTest}>
          {busy === 'logtest' ? '⏳ …' : '🧪 تست اتصال گروه‌های لاگ'}
        </button>
      </div>
      {prestigeRep && (
        <div className="row" style={{ marginTop: 10, flexWrap: 'wrap', gap: 6 }}>
          <B kind="acc">👥 پیمایش: {fa(prestigeRep.scanned)}</B>
          <B kind="ok">✅ مهاجرت: {fa(prestigeRep.migrated)}</B>
          <B kind="acc">🏛 بنیان‌گذار: {fa(prestigeRep.founders)}</B>
          <B kind="acc">🏆 نشان: {fa(prestigeRep.firsts)}</B>
          <B kind={prestigeRep.errors ? 'bad' : 'ok'}>⚠️ خطا: {fa(prestigeRep.errors)}</B>
        </div>
      )}
      {logRes && (
        <div className="grid" style={{ gap: 6, marginTop: 10 }}>
          {logRes.map(r => (
            <div key={r.key} className="row" style={{ gap: 6 }}>
              <B kind={LOG_ST[r.status]?.[0] || ''}>{LOG_ST[r.status]?.[1] || r.status}</B>
              <span style={{ fontSize: 12.5 }}>{r.label}</span>
              {r.ms != null && <span className="muted">({fa(r.ms)}ms)</span>}
              {r.error && <span className="muted code" title={r.error}>{r.error.slice(0, 60)}</span>}
            </div>
          ))}
        </div>
      )}
      {confirm === 'prestige' && (
        <Confirm text="اجرای Backfill Prestige روی همه‌ی کاربران؟ (idempotent — چندبار اجرا اشکال ندارد؛ در audit با HIGH ثبت می‌شود)"
                 onYes={async () => { setConfirm(null); await runPrestige(); }}
                 onNo={() => setConfirm(null)} />
      )}
      {confirm === 'force' && (
        <Confirm text="ارسال فوری اعلان منابع جدید به همه‌ی کاربران دارای این اعلان؟ (خارج از نوبتِ بازه‌ی ۲۴/۴۸/۷۲ ساعته)"
                 onYes={async () => { setConfirm(null); await runForce(); }}
                 onNo={() => setConfirm(null)} />
      )}
    </div>
  );
}
