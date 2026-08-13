import React, { useEffect, useMemo, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, B, toast, Switch, NoPerm, Empty } from '../ui.jsx';

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
    </>
  );
}
