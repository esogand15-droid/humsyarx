import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Empty, Stat, B, FaDateTime, PageHeader, Tabs, Switch, toast, NoPerm, Confirm, Modal, DiffViewer } from '../ui.jsx';
import { PersianDatePicker } from '../PersianDatePicker.jsx';

// 🤖🌊 W-Admin — مرکز فرماندهی هوشیار: KPI ساخت‌یافته + برترین‌ها + گزارش‌ها + دسترسی + پیکربندی
// (رفع نقص قبلی: داده‌ی خام tuple/comma دیگر به UI تخلیه نمی‌شود — سریالایزر سمت API)
const AI_TABS = [['overview', '📊 نمای کلی'], ['reports', '🚩 گزارش‌ها'], ['access', '🔐 دسترسی و سهمیه'], ['image', '🎨 تولید تصویر'], ['personas', '🎭 Personaها'], ['config', '⚙️ پیکربندی']];

export default function AiAdmin({ me }) {
  const [tab, setTab] = useState('overview');
  const [stats, setStats] = useState(null);
  const [cfg, setCfg] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);

  const load = async () => {
    setErr('');
    try {
      const [s, c] = await Promise.all([api.aiStats(), api.aiConfig()]);
      setStats(s); setCfg(c);
    } catch (e) {
      if (e.status === 403) setPermErr(true); else setErr(errText(e));
    }
  };
  useEffect(() => { load(); }, []);

  if (permErr) return <NoPerm text="مدیریت هوشیار نیازمند مجوز «مدیریت هوشیار» (ai.manage) است" />;
  if (err) return <ErrorState title="بارگذاری داده‌های هوشیار ناموفق بود" error={err} onRetry={load} />;
  if (stats === null && cfg === null) return <Loading rows={4} />;

  const kpis = stats ? [
    { icon: '💬', label: 'پرسش امروز', v: stats.total_today, tint: 'var(--acc)' },
    { icon: '👥', label: 'کاربران فعال امروز', v: stats.users_today, tint: 'var(--ok)' },
    { icon: '🪙', label: 'توکن امروز', v: stats.tokens_today, tint: 'var(--warn)' },
    { icon: '📈', label: 'کل پرسش‌ها', v: stats.total_alltime, tint: 'var(--purple)' },
    { icon: '🧑‍🎓', label: 'کل کاربران هوشیار', v: stats.users_alltime, tint: 'var(--teal)' },
    { icon: '🏦', label: 'کل توکن مصرفی', v: stats.tokens_alltime, tint: 'var(--acc2)' },
  ] : [];

  const TopList = ({ title, rows }) => (
    <div className="panel panel-pad">
      <b>{title}</b>
      {!rows?.length && <div className="muted" style={{ marginTop: 8 }}>داده‌ای نیست</div>}
      {(rows || []).map((r, i) => (
        <div key={r.user_id} className="minibar-row" style={{ marginTop: 8 }}>
          <B kind={i < 3 ? 'acc' : ''}>{Number(i + 1).toLocaleString('fa')}</B>
          <div style={{ minWidth: 0, flex: '0 0 44%' }}>
            <div style={{ color: 'var(--txt)', fontSize: 'var(--fs-body)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</div>
            <div className="muted code">#{r.user_id}</div>
          </div>
          <div className="minibar-track">
            <div className="minibar-fill" style={{ width: `${Math.max(3, Math.round(r.count * 100 / Math.max(1, rows[0]?.count || 1)))}%` }} />
          </div>
          <B kind="ok">{Number(r.count).toLocaleString('fa')}</B>
        </div>
      ))}
    </div>
  );

  return (
    <>
      <PageHeader title="مرکز فرماندهی هوشیار" description="مصرف، سلامت سرویس، گزارش کاربران، دسترسی و پیکربندی مدل"
        actions={cfg ? <><B kind={cfg.enabled ? 'ok' : 'bad'}>{cfg.enabled ? '● سرویس فعال' : '● سرویس غیرفعال'}</B><B>{cfg.provider} · {cfg.model}</B></> : null} />
      <Tabs items={AI_TABS.filter(([k]) => k !== 'personas' || me?.is_owner)} value={tab} onChange={setTab} label="بخش‌های هوشیار" />

      {tab === 'overview' && (
        <>
          {!stats ? <Empty icon="📭" text="آمار مصرف در دسترس نیست" /> : (
            <>
              <div className="grid g4">
                {kpis.map((c, i) => <Stat key={i} icon={c.icon} label={c.label}
                  value={Number(c.v ?? 0).toLocaleString('fa')} tint={c.tint} />)}
              </div>
              <div className="grid g2" style={{ marginTop: 14 }}>
                <TopList title="🏅 برترین کاربران امروز" rows={stats.top_today_users} />
                <TopList title="🏆 برترین کاربران همه‌ی زمان‌ها" rows={stats.top_alltime_users} />
              </div>
            </>
          )}
        </>
      )}

      {tab === 'image' && <AiImageStudio cfg={cfg} me={me} onSaved={load} />}
      {tab === 'reports' && <AiReports />}
      {tab === 'access' && <AiAccess me={me} />}
      {tab === 'personas' && me?.is_owner && <AiPersonas />}
      {tab === 'config' && <AiConfig cfg={cfg} me={me} onSaved={load} />}
    </>
  );
}

/* ── 🚩 گزارش‌های کاربران از پاسخ هوشیار ── */
/* ⭐ م8 — استودیوی تولید تصویر: مدل‌های زنده (auto-detect از API) با
   نشانِ سلامت/رایگان + تستِ زنده‌بودن + اجرای تولید از خود پنل. */
function AiImageStudio({ cfg, me, onSaved }) {
  const [models, setModels] = useState(null);
  const [meta, setMeta] = useState(null);   // aspect_ratios / image_sizes / error
  const [probing, setProbing] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [model, setModel] = useState('');
  const [aspect, setAspect] = useState('1:1');
  const [size, setSize] = useState('1K');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);   // {image_b64, mime, elapsed_ms, model}
  const [err, setErr] = useState('');

  const loadModels = async () => {
    setErr('');
    try {
      const r = await api.aiImageModels();
      setModels(r.models || []);
      setMeta(r);
      if (!model && r.models?.length) setModel(r.models[0].id);
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { loadModels(); }, []);

  const probe = async () => {
    setProbing(true);
    try {
      const r = await api.aiModelsProbe(meta?.provider || 'gemini', { kind: 'image' });
      const okN = Number(r.ok_count || 0), total = Number(r.count || 0);
      toast(`تست سلامت: ${okN} از ${total} مدلِ تصویر زنده است ${okN === total && total ? '✅' : ''}`);
      await loadModels();
    } catch (e) { toast(errText(e), 'err'); }
    setProbing(false);
  };

  const generate = async () => {
    setBusy(true); setErr(''); setResult(null);
    try {
      const r = await api.aiImageGenerate({ prompt, model, aspect_ratio: aspect, image_size: size });
      setResult(r);
      toast(`تصویر ساخته شد ✅ (${Number(r.elapsed_ms || 0).toLocaleString('fa')} ms)`);
    } catch (e) { setErr(errText(e)); toast(errText(e), 'err'); }
    setBusy(false);
  };

  const HBadge = ({ m }) => (
    m.health_ok === true ? <span style={{ color: 'var(--c-ok, #2a2)', fontSize: 'var(--fs-caption)' }}>🟢 {Number(m.health_ms || 0).toLocaleString('fa')}ms</span>
    : m.health_ok === false ? <span style={{ color: 'var(--c-bad, #d24)', fontSize: 'var(--fs-caption)' }}>🔴 مرده</span>
    : <span className="muted" style={{ fontSize: 'var(--fs-caption)' }}>⚪ تست‌نشده</span>
  );

  return (
    <>
      <div className="panel panel-pad">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <b>🎨 مدل‌های تولید تصویر — از API (خودکار، بدون لیست ثابت)</b>
          <span className="row">
            <button className="btn sm" onClick={loadModels}>🔄 تازه‌سازی</button>
            <button className="btn sm" disabled={probing} onClick={probe}>{probing ? '⏳ در حال تست…' : '🧪 تست زنده‌بودن'}</button>
          </span>
        </div>
        <div className="muted" style={{ marginTop: 6, fontSize: 'var(--fs-caption)' }}>
          ترتیب: زنده‌ترین و رایگان‌ترین مدل‌ها اول (پس از تستِ سلامت). «رایگان» یعنی سهمیه‌ی رایگانِ محدود — معیارِ نهایی، پاسخِ واقعیِ مدل در تست است.
        </div>
        {err && <div className="muted" style={{ color: 'var(--c-bad, #d24)', marginTop: 8 }}>{err}</div>}
        <div style={{ marginTop: 10, maxHeight: 260, overflowY: 'auto' }}>
          {models === null ? <span className="muted">…</span> : !models.length ? (
            <div className="muted">مدلی یافت نشد — ابتدا کلید API ثبت کن و «تازه‌سازی» را بزن.</div>
          ) : models.map(m => (
            <label key={m.id} className="row" style={{ justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--c-line, #eee)', cursor: 'pointer', gap: 8 }}>
              <span className="row" style={{ gap: 8 }}>
                <input type="radio" name="img-model" checked={model === m.id} onChange={() => setModel(m.id)} />
                <span className="code" style={{ direction: 'ltr' }}>{m.id}</span>
                {m.free && <B kind="ok">رایگان</B>}
              </span>
              <HBadge m={m} />
            </label>
          ))}
        </div>
      </div>

      <div className="panel panel-pad" style={{ marginTop: 14 }}>
        <b>🖌 ساخت تصویر</b>
        <div className="grid" style={{ gap: 10, marginTop: 12 }}>
          <label className="fld"><span>توضیح تصویر (پرامپت)</span>
            <textarea className="inp" rows={3} style={{ resize: 'vertical' }} value={prompt}
                      placeholder="مثلاً: نمودار آموزشی رنگی از چرخه‌ی خون با برچسب فارسی"
                      onChange={e => setPrompt(e.target.value)} /></label>
          <div className="row">
            <label className="fld" style={{ flex: 1 }}><span>نسبت تصویر</span>
              <select className="inp" value={aspect} onChange={e => setAspect(e.target.value)}>
                {(meta?.aspect_ratios || ['1:1']).map(a => <option key={a} value={a}>{a}</option>)}
              </select></label>
            <label className="fld" style={{ flex: 1 }}><span>رزولوشن</span>
              <select className="inp" value={size} onChange={e => setSize(e.target.value)}>
                {(meta?.image_sizes || ['1K']).map(s => <option key={s} value={s}>{s}</option>)}
              </select></label>
          </div>
          <div className="row">
            <button className="btn primary" disabled={busy || prompt.trim().length < 3 || !model}
                    onClick={generate}>{busy ? '⏳ در حال ساخت… (تا ~۶۰ ثانیه)' : '🎨 تولید تصویر'}</button>
            <span className="muted">با کلیدهای فال‌بک (م7) — اگر یکی لیمیت خورد، خودکار کلید بعدی</span>
          </div>
        </div>
        {result && (
          <div style={{ marginTop: 14 }}>
            <img src={`data:${result.mime};base64,${result.image_b64}`} alt="تصویر تولیدشده"
                 style={{ maxWidth: '100%', borderRadius: 8, border: '1px solid var(--c-line, #eee)' }} />
            <div className="row" style={{ marginTop: 8 }}>
              <a className="btn sm" href={`data:${result.mime};base64,${result.image_b64}`}
                 download={`houshyar-${Date.now()}.png`}>📥 دانلود</a>
              <span className="muted">{result.model} · {result.aspect_ratio} · {result.image_size} · {Number(result.elapsed_ms || 0).toLocaleString('fa')} ms</span>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function AiReports() {
  const [data, setData] = useState(null); const [err, setErr] = useState('');
  const [q, setQ] = useState(''); const [userId, setUserId] = useState('');
  const [dateFrom, setDateFrom] = useState(''); const [dateTo, setDateTo] = useState(''); const [page, setPage] = useState(1); const limit = 30;
  const params = { q, user_id: userId, date_from: dateFrom, date_to: dateTo, skip: (page - 1) * limit, limit };
  const load = async () => { setErr(''); try { setData(await api.aiReports(params)); } catch (e) { setErr(errText(e)); } };
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [q, userId, dateFrom, dateTo, page]);
  if (err) return <ErrorState title="بارگذاری گزارش‌های هوشیار ناموفق بود" error={err} onRetry={load} />;
  const items = data?.reports || [];
  return <>
    <div className="panel panel-pad row" style={{ marginBottom: 10, flexWrap: 'wrap' }}>
      <input className="inp" placeholder="جست‌وجو در نام، پرسش و پاسخ…" value={q} onChange={e => { setQ(e.target.value); setPage(1); }} />
      <input className="inp" dir="ltr" placeholder="User ID" value={userId} onChange={e => { setUserId(e.target.value.replace(/\D/g, '')); setPage(1); }} />
      <PersianDatePicker value={dateFrom} onChange={value => { setDateFrom(value); setPage(1); }} placeholder="از تاریخ شمسی" />
      <PersianDatePicker value={dateTo} onChange={value => { setDateTo(value); setPage(1); }} placeholder="تا تاریخ شمسی" />
      <button className="btn sm" title="خروجی CSV از گزارش‌های هوش مصنوعی با همین فیلترها" onClick={() => api.exportAiReports(params)}>📤 CSV</button>
      {data && <B>{Number(data.total || 0).toLocaleString('fa')} گزارش</B>}
    </div>
    {!data ? <Loading rows={3} /> : !items.length ? <Empty icon="🎉" text="گزارشی با این فیلترها ثبت نشده" /> : <div className="grid" style={{ gap: 8 }}>
      {items.map(r => <div key={r.id} className="panel panel-pad">
        <div className="row"><b>{r.name || '—'}</b><span className="code muted">#{r.user_id}</span><span className="spacer" /><FaDateTime value={r.created_at} /></div>
        <div style={{ marginTop: 8 }}><div className="muted">❓ پرسش</div><div>{r.question}</div></div>
        <div style={{ marginTop: 6 }}><div className="muted">🤖 پاسخ گزارش‌شده</div><div style={{ color: 'var(--txt2)' }}>{r.answer}</div></div>
      </div>)}
      <div className="row" style={{ justifyContent: 'center' }}><button className="btn sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>قبلی</button><B>{page.toLocaleString('fa')}</B><button className="btn sm" disabled={page * limit >= (data.total || 0)} onClick={() => setPage(p => p + 1)}>بعدی</button></div>
    </div>}
  </>;
}

/* ── 🔐 دسترسی: جست‌وجو + مسدود/رفع + صفرکردن سهمیه ── */
function AiAccess({ me }) {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState(null);
  const [banned, setBanned] = useState(null); const [bTotal, setBTotal] = useState(0);
  const [bq, setBq] = useState(''); const [bPage, setBPage] = useState(1); const bLimit = 30;
  const [err, setErr] = useState('');
  const [pending, setPending] = useState(null);
  const [profile, setProfile] = useState(null);

  const loadBanned = async () => {
    try { const r = await api.aiBanned({ q: bq, skip: (bPage - 1) * bLimit, limit: bLimit }); setBanned(r.users || []); setBTotal(r.total || 0); }
    catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { const t = setTimeout(loadBanned, 250); return () => clearTimeout(t); }, [bq, bPage]);

  const search = async () => {
    if (q.trim().length < 2) return toast('حداقل ۲ حرف', 'err');
    try { setHits((await api.aiUsers(q.trim())).users || []); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const act = async (fn, okMsg) => {
    try { await fn(); toast(okMsg); setHits(null); loadBanned(); }
    catch (e) { toast(errText(e), 'err'); }
  };

  if (err) return <ErrorState title="بارگذاری فهرست دسترسی ناموفق بود" error={err} onRetry={loadBanned} />;
  return (
    <>
      <div className="panel panel-pad row" style={{ marginBottom: 12 }}>
        <input className="inp" style={{ flex: 1, minWidth: 200 }} placeholder="🔎 نام/یوزرنیم/شماره…"
               value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && search()} />
        <button className="btn primary sm" onClick={search}>جست‌وجو</button>
      </div>
      {hits && (
        <div className="panel" style={{ marginBottom: 12 }}>
          {hits.length === 0 && <Empty icon="🔍" text="کاربری یافت نشد" />}
          {hits.map(u => (
            <div key={u.id} className="tree-row" style={{ padding: '9px 12px' }}>
              <span>👤</span>
              <b style={{ color: 'var(--txt)' }}>{u.name}</b>
              <span className="code muted">#{u.id}</span>
              {u.banned && <B kind="bad">مسدود از هوشیار</B>}
              <span className="spacer" />
              <button className={`btn sm ${u.banned ? 'ok' : 'danger'}`}
                      onClick={() => setPending({ fn: () => api.aiBan(u.id), msg: u.banned ? 'رفع مسدودیت شد ✅' : 'مسدود شد ⛔', text: `${u.banned ? 'رفع مسدودیت' : 'مسدودسازی'} دسترسی هوشیار برای «${u.name}»؟`, danger: !u.banned })}>
                {u.banned ? '✅ رفع مسدودیت' : '⛔ مسدود'}
              </button>
              <button className="btn sm" title="صفرکردن سهمیه‌ی امروز"
                      onClick={() => setPending({ fn: () => api.aiResetQuota(u.id), msg: 'سهمیه‌ی امروز صفر شد 🔄', text: `سهمیه امروز «${u.name}» از ${u.usage_today || 0} به صفر تغییر کند؟`, danger: true })}>🔄 سهمیه</button>
              {me?.is_owner && <button className="btn sm" onClick={async () => { try { setProfile(await api.aiProfile(u.id)); } catch (e) { toast(errText(e), 'err'); } }}>🧠 پروفایل</button>}
            </div>
          ))}
        </div>
      )}
      <div className="panel panel-pad">
        <div className="row"><b>⛔ مسدودشدگان از هوشیار</b><span className="spacer" /><B>{Number(bTotal).toLocaleString('fa')}</B></div>
        <input className="inp" style={{ width: '100%', marginTop: 8 }} placeholder="جست‌وجو در مسدودشدگان…" value={bq} onChange={e => { setBq(e.target.value); setBPage(1); }} />
        {!banned ? <Loading rows={2} /> : banned.length === 0 ? (
          <p className="muted" style={{ marginTop: 8 }}>هیچ کاربر مسدودی نیست 🕊</p>
        ) : (
          <div className="grid" style={{ gap: 6, marginTop: 10 }}>
            {banned.map(u => (
              <div key={u.id} className="row" style={{ padding: '7px 10px', border: '1px solid var(--line)', borderRadius: 10 }}>
                <span>⛔</span>
                <b style={{ color: 'var(--txt)' }}>{u.name}</b>
                <span className="code muted">#{u.id}</span>
                <span className="spacer" />
                <button className="btn sm ok" onClick={() => setPending({ fn: () => api.aiBan(u.id), msg: 'رفع مسدودیت شد ✅', text: `رفع مسدودیت هوشیار برای «${u.name}»؟` })}>✅ رفع مسدودیت</button>
              </div>
            ))}
          </div>
        )}
        {bTotal > bLimit && <div className="row" style={{ justifyContent: 'center', marginTop: 8 }}><button className="btn sm" disabled={bPage <= 1} onClick={() => setBPage(p => p - 1)}>قبلی</button><B>{bPage.toLocaleString('fa')}</B><button className="btn sm" disabled={bPage * bLimit >= bTotal} onClick={() => setBPage(p => p + 1)}>بعدی</button></div>}
      </div>
      {pending && <Confirm danger={pending.danger} text={pending.text}
        onNo={() => setPending(null)} onYes={async () => { const p = pending; setPending(null); await act(p.fn, p.msg); }} />}
      {profile && <Modal title={`🧠 پروفایل ماندگار — ${profile.user?.name || profile.user?.id}`} onClose={() => setProfile(null)}>
        <div className="muted">فقط profile notes و حافظه legacy نمایش داده می‌شود؛ گفتگوهای شخصی چندگانه در این scope نیستند.</div>
        {(profile.notes || []).length ? <ul>{profile.notes.map((n, i) => <li key={i}>{n}</li>)}</ul> : <Empty text="یادداشت ماندگاری ثبت نشده" />}
        <div className="row"><B>{profile.legacy_memory_present ? 'حافظه legacy موجود است' : 'حافظه legacy ندارد'}</B><span className="spacer" />
          <button className="btn danger" onClick={() => setPending({ fn: () => api.aiProfileClear(profile.user.id), msg: 'پروفایل و حافظه legacy پاک شد', text: 'Profile notes و حافظه legacy پاک شوند؟ این عملیات گفتگوهای چندگانه را حذف نمی‌کند.', danger: true })}>پاک‌سازی</button></div>
      </Modal>}
    </>
  );
}

function AiPersonas() {
  const [items, setItems] = useState(null); const [err, setErr] = useState('');
  const [create, setCreate] = useState(false); const [name, setName] = useState(''); const [prompt, setPrompt] = useState('');
  const [pending, setPending] = useState(null);
  const load = async () => { try { setItems((await api.aiPersonas()).personas || []); setErr(''); } catch (e) { setErr(errText(e)); } };
  useEffect(() => { load(); }, []);
  if (err) return <ErrorState error={err} onRetry={load} />;
  if (!items) return <Loading rows={4} />;
  const execute = async p => { try { await p.fn(); toast(p.ok); load(); } catch (e) { toast(errText(e), 'err'); } };
  return <>
    <div className="row" style={{ marginBottom: 10 }}><B>{items.length.toLocaleString('fa')} Persona</B><span className="spacer" /><button className="btn primary" onClick={() => { setName(''); setPrompt(''); setCreate(true); }}>➕ ذخیره Persona</button></div>
    {!items.length ? <Empty text="Persona ذخیره‌شده‌ای نیست" /> : <div className="grid g2">{items.map(p => <div className="panel panel-pad" key={p.name}>
      <div className="row"><b>{p.name}</b>{p.active && <B kind="ok">فعال</B>}<span className="spacer" /><button className="btn sm" disabled={p.active} onClick={() => setPending({ danger: true, text: `Persona «${p.name}» فعال شود؟ System Prompt فعلی با prompt این Persona جایگزین می‌شود.`, before: 'System Prompt فعلی', after: p.prompt, fn: () => api.aiPersonaActivate(p.name), ok: 'Persona فعال شد' })}>▶ فعال‌سازی</button><button className="btn sm danger" onClick={() => setPending({ danger: true, text: `Persona «${p.name}» حذف شود؟`, fn: () => api.aiPersonaDelete(p.name), ok: 'Persona حذف شد' })}>🗑</button></div>
      <div className="muted text-wrap" style={{ marginTop: 8 }}>{p.prompt}</div>
      <div className="muted">{p.created_at ? <>ساخته‌شده: <FaDateTime value={p.created_at} /></> : 'متادیتای ساخت برای رکورد قدیمی موجود نیست'}</div>
    </div>)}</div>}
    {create && <Modal title="ذخیره Persona" onClose={() => setCreate(false)}><input className="inp" style={{ width: '100%' }} placeholder="نام Persona" value={name} onChange={e => setName(e.target.value)} /><textarea className="inp" rows={8} style={{ width: '100%', marginTop: 8 }} placeholder="Prompt؛ خالی = System Prompt فعلی" value={prompt} onChange={e => setPrompt(e.target.value)} /><div className="row" style={{ marginTop: 10 }}><button className="btn primary" disabled={!name.trim() || (!!prompt && prompt.trim().length < 20)} onClick={async () => { try { await api.aiPersonaCreate({ name: name.trim(), prompt: prompt.trim() || null }); setCreate(false); toast('Persona ذخیره شد'); load(); } catch (e) { toast(errText(e), 'err'); } }}>ذخیره</button></div></Modal>}
    {pending && <Confirm danger={pending.danger} text={pending.text} onNo={() => setPending(null)} onYes={async () => { const p = pending; setPending(null); await execute(p); }}>{pending.after && <DiffViewer before={{ system_prompt: pending.before }} after={{ system_prompt: pending.after }} />}</Confirm>}
  </>;
}

/* ── ⚙️ پیکربندی مدل (PUT /config — همان guard و منطق مینی‌اپ) ── */
/* ⭐ م7 — کلیدهای فال‌بک: چند کلید برای هر provider؛ اگر یکی سهمیه/خطا
   بخورد، درخواست خودکار با کلید بعدیِ سالم ادامه می‌یابد. */
function KeysPanel({ provider, me, onSaved }) {
  const [keys, setKeys] = useState(null);
  const [err, setErr] = useState('');
  const [newKey, setNewKey] = useState('');
  const [testing, setTesting] = useState(false);

  const load = async () => {
    setErr('');
    try { setKeys(await api.aiKeys(provider)); }
    catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { setKeys(null); load(); }, [provider]);

  const add = async () => {
    const secret = newKey.trim();
    setNewKey('');
    try {
      const r = await api.aiKeyAdd(provider, secret);
      toast(`کلید فال‌بک اضافه شد — ${Number(r.count || 0).toLocaleString('fa')} کلید در صف ✅`);
      load(); onSaved && onSaved();
    } catch (e) { toast(errText(e), 'err'); }
  };
  const del = async (index) => {
    try { await api.aiKeyDel(provider, index); toast('کلید حذف شد'); load(); onSaved && onSaved(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const test = async () => {
    setTesting(true);
    try {
      const r = await api.aiKeysTest(provider);
      const ok = Number(r.ok_count || 0), total = Number(r.count || 0);
      if (total > 0 && ok === total) toast(`همه‌ی ${total} کلید سالم‌اند ✅`);
      else if (ok === 0) toast('هیچ کلیدی جواب نداد ❌', 'err');
      else toast(`${ok} از ${total} کلید سالم — بقیه در صف فال‌بک نمی‌مانند`, 'err');
      load();
    } catch (e) { toast(errText(e), 'err'); }
    setTesting(false);
  };

  const st = { active: ['🟢', 'var(--c-ok, #2a2)'], cooldown: ['🟡', 'var(--c-warn, #b80)'], failed: ['🔴', 'var(--c-bad, #d24)'] };
  return (
    <div className="panel panel-pad" style={{ marginTop: 14 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <b>🔑 کلیدهای فال‌بک ({provider})</b>
        <button className="btn sm" disabled={testing || !keys || !keys.count} onClick={test}>{testing ? '⏳ …' : '🧪 تست همه'}</button>
      </div>
      <div className="muted" style={{ marginTop: 6, fontSize: 'var(--fs-caption)' }}>
        به تعداد دلخواه کلید ذخیره کن؛ اگر یکی سهمیه گرفت (429) یا خطا خورد، همان درخواست خودکار با کلید بعدیِ سالم ادامه می‌یابد. ترتیب = اولویت. 🧪 «تست همه» تولیدِ واقعیِ ۱ توکن با همان مسیر چت است — «سالم» یعنی واقعاً می‌تواند جواب بدهد.
      </div>
      {err && <div className="muted" style={{ color: 'var(--c-bad, #d24)', marginTop: 8 }}>{err}</div>}
      <div style={{ marginTop: 10 }}>
        {keys === null ? <span className="muted">…</span> : !keys.count ? (
          <div className="muted">هنوز کلیدی برای این ارائه‌دهنده ثبت نشده — با «چرخش کلید» یا فرم زیر اضافه کن.</div>
        ) : (
          (keys.keys || []).map(k => (
            <div key={k.index} className="row" style={{ justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid var(--c-line, #eee)' }}>
              <span className="code" style={{ direction: 'ltr' }}>{k.index}. {k.masked}</span>
              <span className="row" style={{ gap: 8 }}>
                <span style={{ color: (st[k.status] || ['⚪', ''])[1], fontSize: 'var(--fs-caption)' }}>
                  {(st[k.status] || ['⚪', ''])[0]} {k.status === 'cooldown' ? `استراحت ${Math.ceil(k.cooldown_remaining)}ث` : k.status === 'failed' ? 'شکست خورده' : 'سالم'}
                  {k.last_error ? ` — ${k.last_error.slice(0, 60)}` : ''}
                </span>
                {me?.is_owner && <button className="btn sm danger" onClick={() => del(k.index)}>🗑</button>}
              </span>
            </div>
          ))
        )}
      </div>
      {me?.is_owner && (
        <div className="row" style={{ marginTop: 12 }}>
          <input className="inp" type="password" autoComplete="new-password" style={{ direction: 'ltr', flex: 1 }}
                 placeholder="کلید فال‌بک جدید…" value={newKey} onChange={e => setNewKey(e.target.value)} />
          <button className="btn" disabled={newKey.trim().length < 8} onClick={add}>➕ افزودن</button>
        </div>
      )}
    </div>
  );
}

function AiConfig({ cfg, me, onSaved }) {
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmSave, setConfirmSave] = useState(false);
  /* 🌊 W9 — کاتالوگ مرکزی مدل‌ها (بدون تایپ دستی) */
  const [cat, setCat] = useState(null);
  useEffect(() => { api.aiModels().then(setCat).catch(() => {}); }, []);
  /* 🔴 FIX-R1 (مورد ۷) — فهرست زنده‌ی مدل‌ها از ارائه‌دهنده (با همان
     کلید ذخیره‌شده) + دکمه‌ی تازه‌سازی. بدون provider → کاتالوگ ثابت. */
  const [live, setLive] = useState(null);       // {models:[], cached, fallback, error, fetched_at}
  const [liveBusy, setLiveBusy] = useState(false);
  /* ⭐ م8 — صداهای TTS + تستِ سلامتِ مدل‌های گفتگو */
  const [tts, setTts] = useState(null);         // {voices, models, modes}
  const [probeBusy, setProbeBusy] = useState(false);
  useEffect(() => { api.aiTtsVoices().then(setTts).catch(() => {}); }, []);
  const probeChatModels = async () => {
    if (!f?.provider) return;
    setProbeBusy(true);
    try {
      const r = await api.aiModelsProbe(f.provider, { kind: 'chat' });
      const okN = Number(r.ok_count || 0), total = Number(r.count || 0);
      toast(`تست واقعی توکن: ${okN} از ${total} مدل زنده است — فهرست مرتب شد ${okN ? '✅' : '⚠️'}`);
      await loadLive(f.provider, true);
    } catch (e) { toast(errText(e), 'err'); }
    setProbeBusy(false);
  };
  const loadLive = async (provider, refresh = false) => {
    if (!provider) return;
    setLiveBusy(true);
    try {
      const r = await api.aiModels(provider, refresh);
      setLive(r && Array.isArray(r.models) ? r : { models: [], ...r });
    } catch (e) {
      setLive({ models: [], error: errText(e) });
    }
    setLiveBusy(false);
  };
  useEffect(() => { if (cfg?.provider) loadLive(cfg.provider, false); }, [cfg?.provider]);
  // با تغییر provider در فرم، فهرست زنده‌ی همان provider بار می‌شود
  useEffect(() => { if (f?.provider) loadLive(f.provider, false); }, [f?.provider]);
  const [keyOpen, setKeyOpen] = useState(false); const [apiKey, setApiKey] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [modelWarning, setModelWarning] = useState('');  // 🔴 FIX-R1 — هشدار مدلِ خارج از فهرست
  useEffect(() => { if (cfg) setF({ ...cfg }); }, [cfg]);
  if (!cfg) return <Empty icon="⚙️" text="پیکربندی در دسترس نیست" />;
  if (!f) return <Loading rows={3} />;

  const set = (k, v) => setF(x => ({ ...x, [k]: v }));

  /* 🔴 FIX-R1 (مورد ۷) — منبع مدل‌ها: فهرست زنده در اولویت است؛ اگر
     خطا داشت یا خالی بود، کاتالوگ ثابت. مدل سفارشی همیشه ممکن است. */
  const modelOptions = (live?.models?.length
    ? live.models
    : ((cat?.providers || []).find(p => p.id === f.provider)?.models)) || [];
  const liveIds = modelOptions.map(m => m.id);

  const save = async () => {
    setBusy(true);
    try {
      const r = await api.aiConfigUpdate({
        enabled: !!f.enabled, provider: f.provider, model: f.model.trim(),
        daily_limit: Number(f.daily_limit) || 0, thinking: f.thinking,
        system_prompt: f.system_prompt, disabled_message: f.disabled_message || '',
        voice_reply: f.voice_reply || 'voice', tts_voice: f.tts_voice || '',
        tts_model: f.tts_model || '', voice_reply_max_chars: Number(f.voice_reply_max_chars) || 500,
        voice_with_text: f.voice_with_text || 'off',
        image_size: f.image_size || '1K',
      });
      // 🔴 FIX-R1 (مورد ۷) — هشدار مدل: مدل انتخابی در فهرست واقعی
      // ارائه‌دهنده نیست (ممکن است حذف/غیرفعال شده باشد).
      setModelWarning(r?.model_warning || '');
      if (r?.model_warning) {
        toast('⚠️ ' + r.model_warning, 'err');
      } else {
        toast('پیکربندی ذخیره شد ✅');
      }
      onSaved();
    } catch (e) {
      // 🔴 FIX-R1 (مورد ۶) — خطای کلید/مدل با پیام فارسی سرور نمایش داده
      // می‌شود (422)؛ کلیدِ دارای کاراکتر غیرASCII از این به بعد سمت
      // سرور بلاک می‌شود و دیگر خطای 'ascii codec' در ربات رخ نمی‌دهد.
      toast(errText(e), 'err');
    }
    setBusy(false);
  };

  return (
    <>
    <div className="grid g2">
      <div className="panel panel-pad">
        <b>وضعیت سرویس</b>
        <div className="row" style={{ marginTop: 12 }}>
          <Switch on={!!f.enabled} onChange={v => set('enabled', v)} />
          <span>{f.enabled ? 'فعال — کاربران می‌توانند بپرسند' : 'غیرفعال — پیام disabled نمایش داده می‌شود'}</span>
        </div>
        <div className="grid" style={{ gap: 10, marginTop: 14 }}>
          <label className="fld"><span>ارائه‌دهنده</span>
            <select className="inp" value={f.provider} onChange={e => {
              const pid = e.target.value;
              const prov = (cat?.providers || []).find(p => p.id === pid);
              /* با تغییر provider، مدلِ فعلی احتمالاً نامعتبر است ⇒ پیش‌فرض همان provider */
              setF(x => ({ ...x, provider: pid, model: prov?.default_model || x.model }));
            }}>
              {(cat?.providers || [{ id: 'gemini', label: 'Gemini' }, { id: 'openrouter', label: 'OpenRouter' }])
                .map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select></label>
          <label className="fld"><span>
            مدل
            {/* 🔴 FIX-R1 (مورد ۷) — دکمه‌ی تازه‌سازی فهرست زنده + نشانگر کش */}
            <button className="btn sm" style={{ marginInlineStart: 8 }} disabled={liveBusy}
                    title="دریافت مجدد فهرست مدل‌ها از ارائه‌دهنده"
                    onClick={() => loadLive(f.provider, true)}>
              {liveBusy ? '⏳ …' : '🔄 تازه‌سازی'}
            </button>
            {/* ⭐ م8 — تستِ واقعیِ زنده‌بودن همه‌ی مدل‌ها (یک ورودی کوچک → یک خروجی) */}
            <button className="btn sm" style={{ marginInlineStart: 4 }} disabled={probeBusy}
                    title="ارسال درخواست آزمایشی به تک‌تک مدل‌ها؛ زنده‌ها از مرده‌ها جدا و رایگان‌هایِ زنده صدر فهرست می‌روند"
                    onClick={probeChatModels}>
              {probeBusy ? '⏳ تست…' : '🧪 تست زنده‌بودن'}
            </button>
            {live?.cached && <span className="muted" style={{ fontSize: 'var(--fs-caption)' }}> (کش سرور)</span>}
          </span>
            <select className="inp" style={{ direction: 'ltr' }}
                    value={f.model && liveIds.includes(f.model) ? f.model : (f.model ? '__custom' : (modelOptions[0]?.id || ''))}
                    onChange={e => set('model', e.target.value === '__custom' ? '' : e.target.value)}>
              {modelOptions.map(m => {
                const badge = m.health_ok === true ? '🟢 ' : (m.health_ok === false ? '🔴 ' : '');
                const free = m.free ? ' [رایگان]' : '';
                const ms = m.health_ms ? ` (${Number(m.health_ms).toLocaleString('fa')}ms)` : '';
                return <option key={m.id} value={m.id}>{badge}{m.label}{free}{ms}</option>;
              })}
              <option value="__custom">✏️ سفارشی (تایپ دستی)</option>
            </select>
            {f.model && !liveIds.includes(f.model) && (
              <>
                <input className="inp" style={{ direction: 'ltr', marginTop: 6 }}
                       placeholder="شناسه‌ی دقیق مدل" value={f.model}
                       onChange={e => set('model', e.target.value)} />
                {/* 🔴 FIX-R1 (مورد ۷) — مدل انتخابی خارج از فهرست واقعی است */}
                <div className="muted" style={{ marginTop: 4, color: 'var(--c-bad, #d24)', fontSize: 'var(--fs-caption)' }}>
                  ⚠️ این مدل در فهرست واقعی ارائه‌دهنده نیست — ممکن است حذف یا تغییر نام داده باشد.
                </div>
              </>
            )}
            {/* 🔴 FIX-R1 (مورد ۷) — پیام خطای فهرست زنده (کلید نامعتبر و…) */}
            {live?.error && (
              <div className="muted" style={{ marginTop: 4, fontSize: 'var(--fs-caption)' }}>
                ℹ️ فهرست زنده در دسترس نیست: {live.error} — کاتالوگ ثابت نمایش داده می‌شود.
              </div>
            )}
          </label>
          <label className="fld"><span>سهمیه‌ی روزانه‌ی هر کاربر</span>
            <input className="inp" type="number" min="0" max="1000" value={f.daily_limit}
                   onChange={e => set('daily_limit', e.target.value)} /></label>
          <label className="fld"><span>حالت تفکر</span>
            <select className="inp" value={f.thinking} onChange={e => set('thinking', e.target.value)}>
              <option value="auto">auto</option>
              <option value="high">high</option>
            </select></label>
          {/* ⭐ م8 — پاسخ صوتی (TTS فارسی — gemini-3.8-flash-lite-tts) */}
          <label className="fld"><span>🎤 پاسخ صوتی هوشیار (فارسی)</span>
            <select className="inp" value={f.voice_reply || 'voice'} onChange={e => set('voice_reply', e.target.value)}>
              <option value="voice">جوابِ ویس فقط با ویس — بدون تکرارِ متن (پیش‌فرض)</option>
              <option value="all">همه‌ی پاسخ‌ها صوتی هم باشند (متن می‌ماند)</option>
              <option value="off">خاموش</option>
            </select></label>
          <label className="fld"><span>🎧 همراهِ ویس، متنِ جواب هم ارسال شود؟</span>
            <select className="inp" value={f.voice_with_text || 'off'} onChange={e => set('voice_with_text', e.target.value)}>
              <option value="off">خاموش — فقط ویس (پیش‌فرض؛ بدون دوباره‌کاری)</option>
              <option value="on">روشن — ویس + متن (متن قبل از ویس تحویل می‌شود)</option>
            </select></label>
          <label className="fld"><span>🗣 صدای هوشیار</span>
            <select className="inp" value={f.tts_voice || 'Sulafat'} onChange={e => set('tts_voice', e.target.value)}>
              {(tts?.voices || [{ id: 'Sulafat', label: 'Sulafat — گرم' }]).map(v =>
                <option key={v.id} value={v.id}>{v.label}</option>)}
            </select></label>
          <label className="fld"><span>مدل گفتار (TTS)</span>
            <select className="inp" value={f.tts_model || 'gemini-3.8-flash-lite-tts'} onChange={e => set('tts_model', e.target.value)}>
              {(tts?.models || ['gemini-3.8-flash-lite-tts']).map(m =>
                <option key={m} value={m}>{m.includes('lite') ? '⚡ ' + m + ' (سریع/ارزان — پیشنهادی)' : '🎼 ' + m + ' (کیفیت استودیویی)'}</option>)}
            </select></label>
          <label className="fld"><span>حداکثر طول پاسخِ صوتی (نویسه)</span>
            <input className="inp" type="number" min="100" max="4000" value={f.voice_reply_max_chars ?? 500}
                   onChange={e => set('voice_reply_max_chars', e.target.value)} /></label>
          <label className="fld"><span>🖼 رزولوشن پیش‌فرض تصویر</span>
            <select className="inp" value={f.image_size || '1K'} onChange={e => set('image_size', e.target.value)}>
              <option value="1K">1K (سریع/ارزان)</option>
              <option value="2K">2K</option>
              <option value="4K">4K (فقط نانوبانانا 2.1)</option>
            </select></label>
          <div className="row">
            <B kind={cfg.has_api_key ? 'ok' : 'warn'}>{cfg.has_api_key ? '🔑 ●●●●●●●● · تنظیم شده' : '⚠️ کلید API ندارد'}</B>
            <span className="muted">Secret هرگز از API برگردانده نمی‌شود.</span>
            {me?.is_owner && <button className="btn sm" onClick={() => { setApiKey(''); setKeyOpen(true); }}>🔐 چرخش کلید</button>}
            {me?.is_owner && <button className="btn sm" onClick={async () => { try { setTestResult(await api.aiTest()); toast('اتصال هوشیار موفق بود ✅'); } catch (e) { toast(errText(e), 'err'); } }}>🧪 تست اتصال</button>}
          </div>
          {testResult && <div className="muted">پاسخ: {testResult.answer} · {Number(testResult.tokens || 0).toLocaleString('fa')} توکن · {Number(testResult.response_time_ms || 0).toLocaleString('fa')} ms · Request ID: <span className="code">{testResult.request_id}</span></div>}
          {/* ⭐ م7 — مدیریت کلیدهای فال‌بک برای provider فعلی */}
          <KeysPanel provider={f.provider || cfg.provider} me={me} onSaved={onSaved} />
          {/* 🔴 FIX-R1 (مورد ۷) — هشدار ذخیره‌شده‌ی مدل (پاسخ سرور) */}
          {modelWarning && <div style={{ color: 'var(--c-bad, #d24)', fontSize: 'var(--fs-caption)' }}>⚠️ {modelWarning}</div>}
        </div>
      </div>
      <div className="panel panel-pad">
        <b>پیام و پرامپت</b>
        <div className="grid" style={{ gap: 10, marginTop: 12 }}>
          <label className="fld"><span>System Prompt (۲۰ تا ۲۰هزار کاراکتر)</span>
            <textarea className="inp" rows={7} style={{ resize: 'vertical' }} value={f.system_prompt}
                      onChange={e => set('system_prompt', e.target.value)} /></label>
          <label className="fld"><span>پیام هنگام غیرفعال‌بودن سرویس</span>
            <input className="inp" value={f.disabled_message || ''}
                   onChange={e => set('disabled_message', e.target.value)} /></label>
          <div className="row">
            <button className="btn primary" disabled={busy || f.system_prompt.length < 20 || !f.model.trim()}
                    onClick={() => setConfirmSave(true)}>{busy ? '⏳ …' : '💾 بازبینی پیکربندی'}</button>
            <span className="muted">تغییرات در تنظیمات مشترک (`ai_*`) ثبت و در audit دیده می‌شود</span>
          </div>
        </div>
      </div>
    </div>
    {confirmSave && <Confirm danger text="پیکربندی فعال هوشیار برای همه کاربران تغییر می‌کند. اختلاف‌ها را بازبینی کنید." onNo={() => setConfirmSave(false)} onYes={async () => { setConfirmSave(false); await save(); }}>
      <DiffViewer before={{ enabled: cfg.enabled, provider: cfg.provider, model: cfg.model, daily_limit: cfg.daily_limit, thinking: cfg.thinking, system_prompt: cfg.system_prompt, disabled_message: cfg.disabled_message }} after={{ enabled: f.enabled, provider: f.provider, model: f.model, daily_limit: Number(f.daily_limit) || 0, thinking: f.thinking, system_prompt: f.system_prompt, disabled_message: f.disabled_message }} />
    </Confirm>}
    {keyOpen && <Modal title="🔐 چرخش API Key — فقط مالک" onClose={() => { setApiKey(''); setKeyOpen(false); }}>
      <input className="inp" type="password" autoComplete="new-password" style={{ width: '100%', direction: 'ltr' }} placeholder="کلید جدید…" value={apiKey} onChange={e => setApiKey(e.target.value)} />
      <div className="muted" style={{ marginTop: 8 }}>مقدار کلید هرگز نمایش، ذخیره در localStorage یا وارد audit نمی‌شود.</div>
      {/* 🔴 FIX-R1 (مورد ۶) — راهنمای صریح: کلید فقط ASCII بدون فاصله */}
      <div className="muted" style={{ marginTop: 4 }}>کلید را عیناً از سایت ارائه‌دهنده کپی کنید — کاراکترهای فارسی/فاصله‌ی اضافه باعث خطای رمزگذاری می‌شود و سمت سرور رد می‌شود.</div>
      <div className="row" style={{ marginTop: 12 }}><button className="btn danger" disabled={apiKey.trim().length < 8} onClick={async () => { const secret = apiKey; setApiKey(''); setKeyOpen(false); try { await api.aiKeyRotate(secret); toast('API Key با موفقیت چرخش یافت ✅'); onSaved(); } catch (e) { toast(errText(e), 'err'); } }}>تأیید و چرخش</button><button className="btn" onClick={() => { setApiKey(''); setKeyOpen(false); }}>انصراف</button></div>
    </Modal>}
    </>
  );
}
