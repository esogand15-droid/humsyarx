import React, { useEffect, useMemo, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, B, toast, Switch, NoPerm, Empty, Confirm } from '../ui.jsx';

const faN = (n) => Number(n ?? 0).toLocaleString('fa-IR');

const CATS = {
  general:  { icon: '⚙️', label: 'عمومی' },
  logs:     { icon: '📣', label: 'گروه‌های لاگ' },
  donation: { icon: '💙', label: 'حمایت مالی' },
  backup:   { icon: '💾', label: 'بکاپ' },
  notif:    { icon: '🔔', label: 'پیش‌فرض اعلان‌ها' },
};

// ⚙️🌊 WA2.3 — مرکز کنترل تنظیمات: مقدار فعلی + توضیح + آخرین تغییردهنده/زمان + ذخیره + audit
export default function Settings() {
  const [cats, setCats] = useState(null);
  const [cat, setCat] = useState('general');
  const [qs, setQs] = useState('');           // 🌊 موج Settings-Search
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [edited, setEdited] = useState({});   // key → value محلی

  const load = async () => {
    setErr('');
    try { setCats((await api.settingsCenter()).categories || []); }
    catch (e) {
      if (e.status === 403) setPermErr(true); else setErr(errText(e));
    }
  };
  useEffect(() => { load(); }, []);

  const cur = useMemo(() => (cats || []).find(c => c.key === cat), [cats, cat]);
  const valueOf = (it) => (it.key in edited ? edited[it.key] : it.value);

  const save = async (it) => {
    const v = valueOf(it);
    try {
      await api.patchSetting(it.key, v);
      toast(`«${it.label}» ذخیره شد ✅`);
      setEdited(x => { const y = { ...x }; delete y[it.key]; return y; });
      load();
    } catch (e) { toast(errText(e), 'err'); }
  };

  if (permErr) return <NoPerm text="تنظیمات سیستم نیازمند مجوز «تنظیمات سیستم» (settings.manage) است" />;
  if (err) return <ErrorState error={err} onRetry={load} />;
  if (!cats) return <Loading rows={5} />;

  // 🌊 جست‌وجوی سراسری: فیلتر همه‌ی دسته‌ها بر اساس عنوان/توضیح/کلید
  const q = qs.trim();
  const filteredCats = q
    ? cats.map(c => ({
        ...c,
        items: c.items.filter(it =>
          (it.label || '').includes(q) || (it.desc || '').includes(q) || it.key.includes(q)),
      })).filter(c => c.items.length)
    : null;

  return (
    <>
      <div className="h1">مرکز کنترل تنظیمات</div>
      <div className="sub">هر تغییر در audit ثبت می‌شود و با همان کلیدهای مشترک ربات/مینی‌اپ ذخیره می‌گردد</div>
      <div className="row" style={{ marginBottom: 10 }}>
        <input className="inp" style={{ flex: 1, maxWidth: 380 }}
               placeholder="🔎 جست‌وجو در تنظیمات (عنوان/توضیح/کلید)…"
               value={qs} onChange={e => setQs(e.target.value)} />
        {q && <B kind="acc">{filteredCats.reduce((a, c) => a + c.items.length, 0).toLocaleString('fa')} نتیجه در {filteredCats.length.toLocaleString('fa')} دسته</B>}
      </div>
      <div className="tabs">
        {cats.map(c => (
          <button key={c.key} className={`tab ${cat === c.key && !q ? 'on' : ''}`} onClick={() => { setCat(c.key); setQs(''); }}>
            {CATS[c.key]?.icon} {CATS[c.key]?.label || c.key}
            <span className="muted"> ({c.items.length.toLocaleString('fa')})</span>
          </button>
        ))}
      </div>
      {(filteredCats || (cur ? [cur] : [])).length === 0 ? <Empty text={q ? 'تنظیمی با این جست‌وجو نیست' : 'دسته‌ای نیست'} /> : (
        <div className="grid" style={{ gap: 10 }}>
          {(filteredCats || [cur]).map(cc => (
          <React.Fragment key={cc.key}>
          {q && <div className="h1" style={{ fontSize: 14, marginTop: 6 }}>{CATS[cc.key]?.icon} {CATS[cc.key]?.label || cc.key}</div>}
          {cc.items.map(it => (
            <div key={it.key} className="panel panel-pad">
              <div className="row" style={{ alignItems: 'flex-start' }}>
                <div style={{ flex: 1, minWidth: 220 }}>
                  <div className="row">
                    <b>{it.label}</b>
                    <span className="code" style={{ direction: 'ltr' }}>{it.key}</span>
                  </div>
                  <div className="muted" style={{ marginTop: 4, lineHeight: 1.7 }}>{it.desc}</div>
                  {(it.updated_by || it.updated_at) && (
                    <div className="muted" style={{ marginTop: 6 }}>
                      🕓 آخرین تغییر: {it.updated_by || '—'} · {it.updated_at || '—'}
                      <B kind="acc" >🧭 در audit ثبت شده</B>
                    </div>
                  )}
                </div>
                <div style={{ minWidth: 240, display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
                  {it.type === 'bool' && (
                    <Switch on={!!valueOf(it)}
                            onChange={v => { setEdited(x => ({ ...x, [it.key]: v })); }} />
                  )}
                  {it.type === 'text' && (
                    <textarea className="inp" rows={2} style={{ width: '100%' }}
                              value={valueOf(it) ?? ''}
                              onChange={e => setEdited(x => ({ ...x, [it.key]: e.target.value }))} />
                  )}
                  {(it.type === 'group' || it.type === 'link') && (
                    <input className="inp" style={{ width: '100%', direction: 'ltr' }}
                           placeholder={it.type === 'group' ? '-100…' : 'https://…'}
                           value={valueOf(it) ?? ''}
                           onChange={e => setEdited(x => ({ ...x, [it.key]: e.target.value }))} />
                  )}
                  {it.type === 'hour' && (
                    <input className="inp" type="number" min="0" max="23" style={{ width: 90 }}
                           value={valueOf(it) ?? ''}
                           onChange={e => setEdited(x => ({ ...x, [it.key]: e.target.value }))} />
                  )}
                  {it.type === 'readonly' && (
                    <B kind="acc">{it.value ? String(it.value).slice(0, 16).replace('T', ' ') : 'هنوز اجرا نشده'}</B>
                  )}
                  {it.type !== 'readonly' && (it.key in edited) && JSON.stringify(edited[it.key]) !== JSON.stringify(it.value) && (
                    <button className="btn primary sm" onClick={() => save(it)}>💾 ذخیره</button>
                  )}
                </div>
              </div>
            </div>
          ))}
          </React.Fragment>
          ))}
        </div>
      )}

      {/* 🔒🌊 موج ChannelLock — قفل اجباری عضویت کانال (سطح مالک؛ معادل admin:channel_lock ربات) */}
      <ChannelLockPanel />
    </>
  );
}

function ChannelLockPanel() {
  const [chs, setChs] = useState(null);
  const [cid, setCid] = useState('');
  const [ctitle, setCtitle] = useState('');
  const [clink, setClink] = useState('');
  const [busy, setBusy] = useState(false);
  const [delId, setDelId] = useState(null);
  const load = async () => {
    try { setChs((await api.channelLock()).channels || []); }
    catch { setChs(null); }                 // غیرمالک: پنل پنهان می‌ماند
  };
  useEffect(() => { load(); }, []);
  if (chs === null) return null;
  const add = async () => {
    setBusy(true);
    try {
      await api.channelLockAdd({ id: cid.trim(), title: ctitle.trim(), invite_link: clink.trim() });
      toast('کانال اجباری افزوده شد 🔒'); setCid(''); setCtitle(''); setClink(''); load();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const del = async (id) => {
    try { await api.channelLockDel(id); toast('کانال حذف شد 🗑'); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  return (
    <div className="panel panel-pad" style={{ marginTop: 16 }}>
      <div className="row"><b>🔒 قفل اجباری عضویت کانال</b><span className="spacer" />
        {chs.length
          ? <B kind="warn">{faN(chs.length)} کانال فعال — کاربران عادی باید عضو همه باشند</B>
          : <B kind="ok">قفل غیرفعال است</B>}</div>
      <div className="sub" style={{ marginTop: 4 }}>ربات باید ادمین کانال باشد تا عضویت را بررسی کند · حذف/افزودن در audit (WARNING) ثبت می‌شود</div>
      <div className="grid" style={{ gap: 6, marginTop: 10 }}>
        {chs.map(c => (
          <div key={c.id} className="row" style={{ padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 10 }}>
            <span>📣</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <b style={{ color: 'var(--txt)' }}>{c.title}</b>{' '}
              <span className="code muted">{c.id}</span>
              {c.invite_link && <div className="muted code" dir="ltr" style={{ fontSize: 11 }}>{c.invite_link}</div>}
            </div>
            <button className="btn sm danger" onClick={() => setDelId(c.id)}>🗑 حذف</button>
          </div>
        ))}
      </div>
      <div className="row" style={{ marginTop: 12, flexWrap: 'wrap', gap: 6 }}>
        <input className="inp" style={{ flex: 1, minWidth: 150 }} dir="ltr" placeholder="آیدی عددی کانال (با منفی) — مثل -1001234567890"
               value={cid} onChange={e => setCid(e.target.value)} />
        <input className="inp" style={{ flex: 1, minWidth: 120 }} placeholder="نام کانال"
               value={ctitle} onChange={e => setCtitle(e.target.value)} />
        <input className="inp" style={{ flex: 1, minWidth: 130 }} dir="ltr" placeholder="لینک دعوت (اختیاری)"
               value={clink} onChange={e => setClink(e.target.value)} />
        <button className="btn primary sm" disabled={busy || !cid.trim() || !ctitle.trim()} onClick={add}>
          {busy ? '⏳' : '➕ افزودن کانال'}
        </button>
      </div>
      {delId && (
        <Confirm danger
                 text={`حذف کانال «${chs.find(c => c.id === delId)?.title || delId}» از قفل اجباری؟ (کاربران دیگر موظف به عضویت در آن نیستند)`}
                 onYes={async () => { const id = delId; setDelId(null); await del(id); }}
                 onNo={() => setDelId(null)} />
      )}
    </div>
  );
}
