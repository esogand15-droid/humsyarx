import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Stat, B, DiffViewer, PageHeader, StatusBadge, toast, Confirm, Switch } from '../ui.jsx';

const fa = (n) => Number(n ?? 0).toLocaleString('fa-IR');
const DETAIL_LABELS = {
  checked_at: 'زمان بررسی', bot_pid: 'شناسه فرایند ربات', bot_error: 'خطای ربات',
  db_ping_ms: 'تأخیر MongoDB (ms)', db_error: 'خطای پایگاه‌داده',
};

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

export default function System({ me }) {
  const [bs, setBs] = useState(null);
  const [st, setSt] = useState(null);          // تنظیمات ربات (وضعیت بکاپ خودکار)
  const [err, setErr] = useState('');
  const [confirm, setConfirm] = useState(null); // section در انتظار تأیید
  const [busySec, setBusySec] = useState('');
  const [autoBusy, setAutoBusy] = useState(false);
  const [excelBusy, setExcelBusy] = useState(false);

  const has = (p) => !!me?.is_owner || (me?.perms || []).includes(p);
  const canBackup = has('backup.manage');
  const canPrestige = has('prestige.manage');
  const canForce = has('notifications.manage');
  const canLogTest = has('settings.manage') || has('system.manage');

  const load = async () => {
    setErr('');
    try {
      const [b, s] = await Promise.all([api.botStatus(), canBackup ? api.settings() : Promise.resolve(null)]);
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

  const health = v => v === true ? ['🟢', 'ok', 'سالم'] : ['🔴', 'bad', 'مشکل'];
  const botOk = bs.bot_ok === true;
  const dbOk = bs.db_ok === true;
  const apiOk = bs.api_ok === true;
  const auto = st || {};
  const lastRun = (auto.auto_backup_last_run || '').slice(0, 16).replace('T', ' ');

  return (
    <>
      <PageHeader title="سلامت سامانه" description="وضعیت زنده Bot، API، MongoDB، صف اعلان و پشتیبان‌گیری؛ بدون متریک ساختگی"
        actions={<StatusBadge status={botOk && dbOk && apiOk ? 'healthy' : 'critical'} label={botOk && dbOk && apiOk ? 'سامانه سالم' : 'نیازمند بررسی'} />} />
      <div className="grid g4">
        <div className="panel stat">
          <div className="ic" style={{ background: 'rgba(52,211,153,.1)' }}>{health(botOk)[0]}</div>
          <div><div className="v"><B kind={health(botOk)[1]}>{health(botOk)[2]}</B></div>
            <div className="l">process ربات تلگرام{bs.bot_pid ? ` · PID ${bs.bot_pid}` : ''}</div></div>
        </div>
        <div className="panel stat">
          <div className="ic" style={{ background: 'rgba(56,182,255,.1)' }}>{health(dbOk)[0]}</div>
          <div><div className="v"><B kind={health(dbOk)[1]}>{health(dbOk)[2]}</B></div>
            <div className="l">پایگاه‌داده{bs.db_ping_ms != null ? ` · ${fa(bs.db_ping_ms)}ms` : ''}</div></div>
        </div>
        <div className="panel stat">
          <div className="ic" style={{ background: 'rgba(167,139,250,.1)' }}>{health(apiOk)[0]}</div>
          <div><div className="v"><B kind={health(apiOk)[1]}>{health(apiOk)[2]}</B></div>
            <div className="l">API{bs.sys?.uptime ? ` · ${bs.sys.uptime}` : ''}</div></div>
        </div>
        {bs.notifications && <Stat icon="🔔" label="پیام در صف ارسال" value={fa(bs.notifications.pending_queue)}
          hint={`${fa(bs.notifications.recent_failed_runs)} اجرای اخیر دارای خطا`} tint={bs.notifications.recent_failed_runs ? 'var(--warn)' : 'var(--ok)'} />}
        {bs.backup && <Stat icon="💾" label="پشتیبان‌گیری خودکار" value={bs.backup.enabled ? 'فعال' : 'غیرفعال'}
          hint={bs.backup.last_run ? `آخرین: ${String(bs.backup.last_run).slice(0, 16).replace('T', ' ')}` : 'هنوز اجرا نشده'} tint={bs.backup.enabled ? 'var(--ok)' : 'var(--warn)'} />}
      </div>

      <div className="panel panel-pad" style={{ marginTop: 14 }}>
        <b>جزئیات فنی سلامت</b>
        <dl className="kv" style={{ marginTop: 8 }}>
          {Object.entries(bs).filter(([k, v]) => typeof v !== 'object' && DETAIL_LABELS[k] && v !== '' && v != null).map(([k, v]) => (
            <React.Fragment key={k}><dt>{DETAIL_LABELS[k]}</dt><dd className={k.includes('pid') ? 'code' : ''}>{String(v)}</dd></React.Fragment>
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
      {canBackup && <div className="panel panel-pad" style={{ marginTop: 14 }}>
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
      </div>}

      {canPrestige && <PrestigeConfigPanel />}

      {/* 🛠 عملیات حساس با نمایش مبتنی بر permission */}
      <OwnerOpsPanel canPrestige={canPrestige} canForce={canForce} canLogTest={canLogTest} />

      {confirm && (
        <Confirm text={`ساخت پشتیبان «${SECTIONS.find(s => s[0] === confirm)?.[2]}»؟ (عملیات حساس — فایل در گفت‌وگوی ربات می‌آید و در audit ثبت می‌شود)`}
                 onYes={async () => { const s = confirm; setConfirm(null); await doBackup(s); }}
                 onNo={() => setConfirm(null)} />
      )}
    </>
  );
}

function PrestigeConfigPanel() {
  const [data, setData] = useState(null);
  const [values, setValues] = useState({});
  const [err, setErr] = useState('');
  const [confirmSave, setConfirmSave] = useState(false);
  const load = async () => {
    setErr('');
    try { const r = await api.prestigeConfig(); setData(r); setValues(r.effective || {}); }
    catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);
  if (err) return <div className="panel panel-pad" style={{ marginTop: 14 }}><ErrorState title="تنظیمات Prestige بارگذاری نشد" error={err} onRetry={load} /></div>;
  if (!data) return <div className="panel panel-pad" style={{ marginTop: 14 }}><Loading rows={4} /></div>;
  const changed = Object.keys(values).filter(k => Number(values[k]) !== Number(data.effective?.[k]));
  const save = async () => {
    setConfirmSave(false);
    const overrides = Object.fromEntries(Object.entries(values).filter(([k, v]) => Number(v) !== Number(data.defaults?.[k])));
    try { await api.prestigeConfigUpdate(overrides); toast('تنظیمات Prestige ذخیره شد ✅'); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const cs = data.challenge_stats || {};
  return <section className="panel panel-pad" style={{ marginTop: 14 }}>
    <div className="row"><div><b>🏅 تعادل زنده Prestige</b><div className="muted">اوررایدهای معتبر بدون redeploy؛ آستانه‌های Design Lock تغییر نمی‌کنند</div></div>
      <span className="spacer" />{data.updated_at && <B>آخرین تغییر: {String(data.updated_at).slice(0, 16).replace('T', ' ')}</B>}
      <button className="btn primary sm" disabled={!changed.length} onClick={() => setConfirmSave(true)}>بازبینی {fa(changed.length)} تغییر</button></div>
    {Object.keys(cs).length > 0 && <div className="row" style={{ marginTop: 10 }}>
      {cs.active != null && <B kind="acc">چالش فعال: {fa(cs.active)}</B>}
      {cs.completed != null && <B kind="ok">تکمیل‌شده: {fa(cs.completed)}</B>}
      {cs.failed != null && <B kind={cs.failed ? 'warn' : 'ok'}>ناموفق: {fa(cs.failed)}</B>}
    </div>}
    <div className="form-grid" style={{ marginTop: 12 }}>
      {Object.entries(data.meta || {}).map(([key, meta]) => <label className="fld" key={key}>
        <span>{meta.label}</span><input className="inp" type="number" min={meta.min} max={meta.max}
          value={values[key] ?? ''} onChange={e => setValues(v => ({ ...v, [key]: Number(e.target.value) }))} />
        <small className="field-help">بازه {fa(meta.min)} تا {fa(meta.max)} · پیش‌فرض {fa(data.defaults?.[key])}</small>
      </label>)}
    </div>
    {confirmSave && <Confirm onNo={() => setConfirmSave(false)} onYes={save}>
      <p className="muted" style={{ marginBottom: 10 }}>فقط اختلاف‌های زیر به‌عنوان override ذخیره می‌شوند.</p>
      <DiffViewer before={Object.fromEntries(changed.map(k => [data.meta[k]?.label || k, data.effective[k]]))}
        after={Object.fromEntries(changed.map(k => [data.meta[k]?.label || k, values[k]]))} />
    </Confirm>}
  </section>;
}

/* ── 🛠 عملیات مالک — همان دکمه‌های پراکنده‌ی پنل ربات (admin:prestige_backfill / notif_force_send / test_log_groups) ── */
function OwnerOpsPanel({ canPrestige, canForce, canLogTest }) {
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

  if (!canPrestige && !canForce && !canLogTest) return null;
  return (
    <div className="panel panel-pad" style={{ marginTop: 14 }}>
      <b>🛠 عملیات مالک</b>
      <div className="muted" style={{ marginTop: 4 }}>همان اکشن‌های پراکنده‌ی پنل ربات — idempotent یا دارای Confirm؛ همه در audit ثبت می‌شوند.</div>
      <div className="row" style={{ marginTop: 10, flexWrap: 'wrap', gap: 8 }}>
        {canPrestige && <button className="btn" disabled={!!busy} onClick={() => setConfirm('prestige')}>
          {busy === 'prestige' ? '⏳ در حال محاسبه…' : '🏅 محاسبه‌ی Prestige (Backfill)'}
        </button>}
        {canForce && <button className="btn" disabled={!!busy} onClick={() => setConfirm('force')}>
          {busy === 'force' ? '⏳ …' : '📨 ارسال فوری اعلان منابع'}
        </button>}
        {canLogTest && <button className="btn" disabled={!!busy} onClick={runLogTest}>
          {busy === 'logtest' ? '⏳ …' : '🧪 تست اتصال گروه‌های لاگ'}
        </button>}
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
