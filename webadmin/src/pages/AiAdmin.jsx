import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Empty, Stat, B, Switch, toast, NoPerm } from '../ui.jsx';

// 🤖🌊 W-Admin — مرکز فرماندهی هوشیار: KPI ساخت‌یافته + برترین‌ها + گزارش‌ها + دسترسی + پیکربندی
// (رفع نقص قبلی: داده‌ی خام tuple/comma دیگر به UI تخلیه نمی‌شود — سریالایزر سمت API)
const AI_TABS = [['overview', '📊 نمای کلی'], ['reports', '🚩 گزارش‌ها'], ['access', '🔐 دسترسی و سهمیه'], ['config', '⚙️ پیکربندی']];

export default function AiAdmin() {
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
            <div style={{ color: 'var(--txt)', fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</div>
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
      <div className="row">
        <div>
          <div className="h1">مرکز فرماندهی هوشیار</div>
          <div className="sub">مصرف، سلامت سرویس، گزارش‌های کاربران، دسترسی و پیکربندی مدل</div>
        </div>
        <span className="spacer" />
        {cfg && <B kind={cfg.enabled ? 'ok' : 'bad'}>{cfg.enabled ? '🟢 سرویس فعال' : '🔴 سرویس غیرفعال'}</B>}
        {cfg && <B>{cfg.provider} · {cfg.model}</B>}
      </div>

      <div className="tabs" style={{ marginBottom: 14 }}>
        {AI_TABS.map(([k, v]) => (
          <button key={k} className={`tab ${tab === k ? 'on' : ''}`} onClick={() => setTab(k)}>{v}</button>
        ))}
      </div>

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

      {tab === 'reports' && <AiReports />}
      {tab === 'access' && <AiAccess />}
      {tab === 'config' && <AiConfig cfg={cfg} onSaved={load} />}
    </>
  );
}

/* ── 🚩 گزارش‌های کاربران از پاسخ هوشیار ── */
function AiReports() {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState('');
  const load = async () => {
    try { setItems((await api.aiReports()).reports || []); }
    catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);
  if (err) return <ErrorState title="بارگذاری گزارش‌های هوشیار ناموفق بود" error={err} onRetry={load} />;
  if (!items) return <Loading rows={3} />;
  if (!items.length) return <Empty icon="🎉" text="گزارشی ثبت نشده" />;
  return (
    <div className="grid" style={{ gap: 8 }}>
      {items.map(r => (
        <div key={r.id} className="panel panel-pad">
          <div className="row">
            <b style={{ color: 'var(--txt)' }}>{r.name || '—'}</b>
            <span className="code muted">#{r.user_id}</span>
            <span className="spacer" />
            <span className="muted">{String(r.created_at || '').replace('T', ' ')}</span>
          </div>
          <div style={{ marginTop: 8 }}>
            <div className="muted">❓ پرسش</div>
            <div style={{ fontSize: 12.5 }}>{r.question}</div>
          </div>
          <div style={{ marginTop: 6 }}>
            <div className="muted">🤖 پاسخ (گزارش‌شده)</div>
            <div style={{ fontSize: 12.5, color: 'var(--txt2)' }}>{r.answer}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── 🔐 دسترسی: جست‌وجو + مسدود/رفع + صفرکردن سهمیه ── */
function AiAccess() {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState(null);
  const [banned, setBanned] = useState(null);
  const [err, setErr] = useState('');

  const loadBanned = async () => {
    try { setBanned((await api.aiBanned()).users || []); }
    catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { loadBanned(); }, []);

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
                      onClick={() => act(() => api.aiBan(u.id), u.banned ? 'رفع مسدودیت شد ✅' : 'مسدود شد ⛔')}>
                {u.banned ? '✅ رفع مسدودیت' : '⛔ مسدود'}
              </button>
              <button className="btn sm" title="صفرکردن سهمیه‌ی امروز"
                      onClick={() => act(() => api.aiResetQuota(u.id), 'سهمیه‌ی امروز صفر شد 🔄')}>🔄 سهمیه</button>
            </div>
          ))}
        </div>
      )}
      <div className="panel panel-pad">
        <b>⛔ مسدودشدگان از هوشیار</b>
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
                <button className="btn sm ok" onClick={() => act(() => api.aiBan(u.id), 'رفع مسدودیت شد ✅')}>✅ رفع مسدودیت</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

/* ── ⚙️ پیکربندی مدل (PUT /config — همان guard و منطق مینی‌اپ) ── */
function AiConfig({ cfg, onSaved }) {
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (cfg) setF({ ...cfg }); }, [cfg]);
  if (!cfg) return <Empty icon="⚙️" text="پیکربندی در دسترس نیست" />;
  if (!f) return <Loading rows={3} />;

  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  const save = async () => {
    setBusy(true);
    try {
      await api.aiConfigUpdate({
        enabled: !!f.enabled, provider: f.provider, model: f.model.trim(),
        daily_limit: Number(f.daily_limit) || 0, thinking: f.thinking,
        system_prompt: f.system_prompt, disabled_message: f.disabled_message || '',
      });
      toast('پیکربندی ذخیره شد ✅'); onSaved();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  return (
    <div className="grid g2">
      <div className="panel panel-pad">
        <b>وضعیت سرویس</b>
        <div className="row" style={{ marginTop: 12 }}>
          <Switch on={!!f.enabled} onChange={v => set('enabled', v)} />
          <span>{f.enabled ? 'فعال — کاربران می‌توانند بپرسند' : 'غیرفعال — پیام disabled نمایش داده می‌شود'}</span>
        </div>
        <div className="grid" style={{ gap: 10, marginTop: 14 }}>
          <label className="fld"><span>ارائه‌دهنده</span>
            <select className="inp" value={f.provider} onChange={e => set('provider', e.target.value)}>
              <option value="gemini">Gemini</option>
              <option value="openrouter">OpenRouter</option>
            </select></label>
          <label className="fld"><span>مدل</span>
            <input className="inp" style={{ direction: 'ltr' }} value={f.model} onChange={e => set('model', e.target.value)} /></label>
          <label className="fld"><span>سهمیه‌ی روزانه‌ی هر کاربر</span>
            <input className="inp" type="number" min="0" max="1000" value={f.daily_limit}
                   onChange={e => set('daily_limit', e.target.value)} /></label>
          <label className="fld"><span>حالت تفکر</span>
            <select className="inp" value={f.thinking} onChange={e => set('thinking', e.target.value)}>
              <option value="auto">auto</option>
              <option value="high">high</option>
            </select></label>
          <div className="row">
            <B kind={cfg.has_api_key ? 'ok' : 'warn'}>{cfg.has_api_key ? '🔑 کلید API تنظیم شده' : '⚠️ کلید API ندارد'}</B>
            <span className="muted">کلید هرگز به مرورگر ارسال نمی‌شود؛ تغییرش از مینی‌اپ ادمین</span>
          </div>
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
                    onClick={save}>{busy ? '⏳ …' : '💾 ذخیره‌ی پیکربندی'}</button>
            <span className="muted">تغییرات در تنظیمات مشترک (`ai_*`) ثبت و در audit دیده می‌شود</span>
          </div>
        </div>
      </div>
    </div>
  );
}
