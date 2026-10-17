import React, { useEffect, useRef, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Empty, Stat, B, FaDateTime, PageHeader, Tabs, Switch, toast, NoPerm, Confirm, Modal, DiffViewer } from '../ui.jsx';
import { PersianDatePicker } from '../PersianDatePicker.jsx';

// 🤖🌊 W-Admin — مرکز فرماندهی هوشیار: KPI ساخت‌یافته + برترین‌ها + گزارش‌ها + دسترسی + پیکربندی
// (رفع نقص قبلی: داده‌ی خام tuple/comma دیگر به UI تخلیه نمی‌شود — سریالایزر سمت API)
const AI_TABS = [['overview', '📊 نمای کلی'], ['reports', '🚩 گزارش‌ها'], ['access', '🔐 دسترسی و سهمیه'], ['image', '🎨 تولید تصویر'], ['live', '🎙 تماس صوتی زنده'], ['personas', '🎭 Personaها'], ['config', '⚙️ پیکربندی']];

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
      {tab === 'live' && <AiLiveStudio cfg={cfg} me={me} onSaved={load} />}
      {tab === 'reports' && <AiReports />}
      {tab === 'access' && <AiAccess me={me} />}
      {tab === 'personas' && me?.is_owner && <AiPersonas />}
      {tab === 'config' && <AiConfig cfg={cfg} me={me} onSaved={load} />}
    </>
  );
}

/* ── 🚩 گزارش‌های کاربران از پاسخ هوشیار ── */
/* ⭐ م8 / م8.4 — استودیوی تولید تصویر گوگل + پیکربندی مستقیم مدل تصویر هوشیار:
   فقط مدل‌های رایگان/رسمی گوگل (Gemini) + تستِ واقعیِ ساخت تصویر +
   تنظیم مستقیم مدل ساخت عکس برای ربات و مینی‌اپ هوشیار. */
function AiImageStudio({ cfg, me, onSaved }) {
  const [models, setModels] = useState(null);
  const [meta, setMeta] = useState(null);   // aspect_ratios / image_sizes / current_model / ...
  const [probing, setProbing] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [model, setModel] = useState('');
  const [aspect, setAspect] = useState('1:1');
  const [size, setSize] = useState('1K');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);   // {image_b64, mime, elapsed_ms, model}
  const [err, setErr] = useState('');

  // تنظیمات فعال هوشیار (ربات + مینی‌اپ)
  const [botEnabled, setBotEnabled] = useState(true);
  const [botModel, setBotModel] = useState('gemini-3.1-flash-lite-image');
  const [botLimit, setBotLimit] = useState(5);
  const [botSize, setBotSize] = useState('1K');
  const [savingCfg, setSavingCfg] = useState(false);

  const loadModels = async (refresh = false) => {
    setErr('');
    try {
      const r = await api.aiImageModels(refresh);
      const list = r.models || [];
      setModels(list);
      setMeta(r);
      const activeMod = r.current_model || cfg?.image_model || 'gemini-3.1-flash-lite-image';
      setBotModel(activeMod);
      setBotEnabled(r.image_enabled !== undefined ? !!r.image_enabled : (cfg?.image_enabled !== false));
      setBotLimit(r.image_daily_limit ?? cfg?.image_daily_limit ?? 5);
      setBotSize(r.image_size || cfg?.image_size || '1K');
      if (!model) {
        const hasActive = list.some(x => x.id === activeMod);
        setModel(hasActive ? activeMod : (list[0]?.id || activeMod));
      }
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { loadModels(false); }, []);

  const saveBotImageConfig = async (overrideModel) => {
    const targetModel = typeof overrideModel === 'string' && overrideModel ? overrideModel : botModel;
    setSavingCfg(true);
    try {
      const r = await api.aiImageConfigSave({
        image_enabled: !!botEnabled,
        image_model: targetModel,
        image_daily_limit: Number(botLimit) || 0,
        image_size: botSize || '1K',
      });
      setBotModel(r.image_model);
      setModel(r.image_model);
      setMeta(x => ({ ...(x || {}), current_model: r.image_model, image_enabled: r.image_enabled, image_daily_limit: r.image_daily_limit, image_size: r.image_size }));
      toast(`مدل تصویر هوشیار روی «${r.image_model}» ذخیره شد ✅`);
      onSaved && onSaved();
    } catch (e) { toast(errText(e), 'err'); }
    setSavingCfg(false);
  };

  const probe = async () => {
    setProbing(true);
    try {
      const r = await api.aiModelsProbe('gemini', {
        kind: 'image',
        models: (models || []).map(m => m.id),
      });
      const okN = Number(r.ok_count || 0), total = Number(r.count || 0);
      toast(`تست واقعی ساخت تصویر: ${okN} از ${total} مدل گوگل سالم و فعال است ${okN > 0 ? '✅' : '⚠️'}`);
      await loadModels(false);
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
    m.health_ok === true ? (
      <span style={{ color: 'var(--c-ok, #2a2)', fontSize: 'var(--fs-caption)', fontWeight: 600 }}>
        🟢 سالم ({Number(m.health_ms || 1).toLocaleString('fa')}ms)
      </span>
    ) : m.health_ok === false ? (
      <span style={{ color: 'var(--c-bad, #d24)', fontSize: 'var(--fs-caption)' }} title={m.health_error || ''}>
        🔴 خطا{m.health_error ? `: ${m.health_error.slice(0, 55)}` : ''}
      </span>
    ) : (
      <span className="muted" style={{ fontSize: 'var(--fs-caption)' }}>⚪ تست‌نشده</span>
    )
  );

  const activeBotModel = meta?.current_model || cfg?.image_model || botModel;

  return (
    <>
      <div className="panel panel-pad" style={{ marginBottom: 14 }}>
        <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <b>⚙️ پیکربندی ساخت تصویر در هوشیار (ربات تلگرام و مینی‌اپ)</b>
          <B kind={botEnabled ? 'ok' : 'warn'}>
            {botEnabled ? `فعال · مدل فعلی: ${activeBotModel}` : 'ساخت تصویر غیرفعال است'}
          </B>
        </div>
        <div className="muted" style={{ marginTop: 6, fontSize: 'var(--fs-caption)' }}>
          مدل انتخاب‌شده در این بخش، مدلِ پیش‌فرض هوشیار برای ساخت تصویر کاربران در ربات و مینی‌اپ است (با استفاده از کلیدهای گوگل Gemini ثبت‌شده در بخش پیکربندی).
        </div>
        <div className="grid g2" style={{ gap: 10, marginTop: 12 }}>
          <label className="fld">
            <span>وضعیت ساخت تصویر برای کاربران</span>
            <div className="row" style={{ marginTop: 6 }}>
              <Switch on={!!botEnabled} onChange={setBotEnabled} />
              <span>{botEnabled ? 'فعال — کاربران می‌توانند تصویر بسازند' : 'غیرفعال'}</span>
            </div>
          </label>
          <label className="fld">
            <span>مدل ساخت تصویر هوشیار (گوگل Gemini)</span>
            <select className="inp" style={{ direction: 'ltr' }} value={botModel} onChange={e => setBotModel(e.target.value)}>
              {(models || [{ id: 'gemini-3.1-flash-lite-image', label: '⚡ gemini-3.1-flash-lite-image' }]).map(m => (
                <option key={m.id} value={m.id}>
                  {m.health_ok === true ? '🟢 ' : m.health_ok === false ? '🔴 ' : ''}{m.id}{m.free ? ' [رایگان]' : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="fld">
            <span>سهمیه روزانه هر کاربر (تصویر در روز)</span>
            <input className="inp" type="number" min="0" max="500" value={botLimit} onChange={e => setBotLimit(e.target.value)} />
          </label>
          <label className="fld">
            <span>رزولوشن پیش‌فرض هوشیار</span>
            <select className="inp" value={botSize} onChange={e => setBotSize(e.target.value)}>
              {(meta?.image_sizes || ['1K', '2K', '4K']).map(s => (
                <option key={s} value={s}>{s === '1K' ? '1K (پیش‌فرض؛ سازگار با همه مدل‌های رایگان گوگل)' : s}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn primary" disabled={savingCfg || !botModel} onClick={() => saveBotImageConfig()}>
            {savingCfg ? '⏳ در حال ذخیره…' : '💾 ذخیره تنظیمات تصویر هوشیار'}
          </button>
        </div>
      </div>

      <div className="panel panel-pad">
        <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <b>🎨 مدل‌های تولید تصویر گوگل (Gemini) — تست واقعی و انتخاب</b>
          <span className="row">
            <button className="btn sm" onClick={() => loadModels(true)}>🔄 تازه‌سازی</button>
            <button className="btn sm" disabled={probing} onClick={probe}>{probing ? '⏳ در حال تست واقعی ساخت عکس…' : '🧪 تست زنده‌بودن (واقعی)'}</button>
          </span>
        </div>
        <div className="muted" style={{ marginTop: 6, fontSize: 'var(--fs-caption)' }}>
          فقط مدل‌های تصویر گوگل نمایش داده می‌شوند. دکمه «🧪 تست زنده‌بودن» یک تصویر واقعی آزمایشی با هر مدل می‌سازد تا دقیقاً مشخص شود کدام مدل روی کلید شما فعال و رایگان است.
        </div>
        {err && <div className="muted" style={{ color: 'var(--c-bad, #d24)', marginTop: 8 }}>{err}</div>}
        <div style={{ marginTop: 10, maxHeight: 300, overflowY: 'auto' }}>
          {models === null ? <span className="muted">…</span> : !models.length ? (
            <div className="muted">مدلی یافت نشد — ابتدا کلید API گوگل ثبت کن و «تازه‌سازی» را بزن.</div>
          ) : models.map(m => (
            <div key={m.id} className="row" style={{ justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--c-line, #eee)', gap: 8, flexWrap: 'wrap' }}>
              <label className="row" style={{ gap: 8, cursor: 'pointer', flex: 1, minWidth: 220 }}>
                <input type="radio" name="img-model" checked={model === m.id} onChange={() => setModel(m.id)} />
                <span className="code" style={{ direction: 'ltr', fontWeight: 600 }}>{m.id}</span>
                {m.label && m.label !== m.id && <span className="muted" style={{ fontSize: 'var(--fs-caption)' }}>{m.label.replace(m.id, '').trim()}</span>}
                {m.free && <B kind="ok">رایگان</B>}
                {activeBotModel === m.id && <B kind="info">⭐ فعال در هوشیار</B>}
              </label>
              <span className="row" style={{ gap: 8 }}>
                <HBadge m={m} />
                {activeBotModel !== m.id && (
                  <button className="btn sm" disabled={savingCfg} onClick={() => saveBotImageConfig(m.id)} title="تنظیم این مدل به عنوان مدل ساخت تصویر هوشیار">
                    تنظیم برای هوشیار
                  </button>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel panel-pad" style={{ marginTop: 14 }}>
        <b>🖌 تست و ساخت تصویر در پنل (Playground)</b>
        <div className="grid" style={{ gap: 10, marginTop: 12 }}>
          <label className="fld"><span>توضیح تصویر (پرامپت)</span>
            <textarea className="inp" rows={3} style={{ resize: 'vertical' }} value={prompt}
                      placeholder="مثلاً: نمودار آموزشی رنگی از چرخه‌ی خون با برچسب فارسی"
                      onChange={e => setPrompt(e.target.value)} /></label>
          <div className="row">
            <label className="fld" style={{ flex: 1 }}><span>مدل تست در پنل</span>
              <select className="inp" style={{ direction: 'ltr' }} value={model} onChange={e => setModel(e.target.value)}>
                {(models || []).map(m => <option key={m.id} value={m.id}>{m.id}</option>)}
              </select></label>
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
            <span className="muted">با کلیدهای فال‌بک گوگل (م7) — اگر یکی لیمیت خورد، خودکار کلید بعدی</span>
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

/* ⭐ م9 / م9.5 — استودیوی تماس صوتی زنده با هوشیار (Google Gemini Live API / BidiGenerateContent):
   مدیریت هر ۴ مدل رسمی Live گوگل + تست زنده‌بودن WebSocket + اتاق تست تماس صوتی زنده در پنل وب
   مجهز به موتور صوتی AudioWorkletProcessor + انتقال باینری مستقیم ArrayBuffer + درون‌یابی مکعبی ۴ نقطه‌ای */
const ADMIN_LIVE_WORKLET_CODE = `
class HumsyarAdminLiveAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    const sr = sampleRate || 48000;
    this.sr = sr;
    this.cap = Math.max(48000 * 30, Math.floor(sr * 45));
    this.ring = new Float32Array(this.cap);
    this.readPos = 0;
    this.writePos = 0;
    this.avail = 0;
    this.hasHist = false;
    this.sm2 = 0;
    this.sm1 = 0;
    this.s0 = 0;
    this.resamplePhase = 0;
    this.playing = false;
    this.prebuffering = true;
    this.turnComplete = false;
    this.targetPrebufSec = 0.115;
    this.firstBufTime = 0;
    this.lastOut = 0;
    this.fadeInTotal = Math.max(32, Math.floor(sr * 0.003));
    this.fadeInRem = 0;
    this.fadeStartSample = 0;
    this.clearFadeRem = 0;
    this.clearFadeTotal = Math.max(64, Math.floor(sr * 0.004));
    this.duckGain = 1.0;

    this.hpPrevX = 0;
    this.hpPrevY = 0;
    this.hpAlpha = Math.exp((-2 * Math.PI * 25) / sr);
    this.decimRatio = sr / 16000;
    this.decimAcc = 0;
    this.decimSum = 0;
    this.decimCount = 0;
    this.micOut = new Int16Array(640);
    this.micIdx = 0;
    this.micVoiceFrames = 0;
    this.echoTailSamples = 0;
    this.telemetrySamples = 0;

    this.port.onmessage = (ev) => {
      const d = ev.data;
      if (!d) return;
      if (d.type === 'pcm24k' && d.buffer) {
        this._pushPcm24k(new Int16Array(d.buffer));
      } else if (d.type === 'clear') {
        this.readPos = 0;
        this.writePos = 0;
        this.avail = 0;
        this.playing = false;
        this.prebuffering = true;
        this.turnComplete = false;
        this.hasHist = false;
        this.echoTailSamples = 0;
        this.fadeStartSample = this.lastOut;
        this.clearFadeRem = this.clearFadeTotal;
      } else if (d.type === 'turn_complete') {
        this.turnComplete = true;
      }
    };
  }

  _writeSample(v) {
    if (this.avail >= this.cap) {
      this.readPos = (this.readPos + 1) % this.cap;
      this.avail -= 1;
    }
    this.ring[this.writePos] = v;
    this.writePos = (this.writePos + 1) % this.cap;
    this.avail += 1;
  }

  _pushPcm24k(i16) {
    const n = i16.length;
    if (!n) return;
    if (this.avail === 0) this.firstBufTime = currentTime;
    this.turnComplete = false;
    this.echoTailSamples = Math.floor(this.sr * 0.85);
    if (!this.hasHist) {
      const f0 = i16[0] / 32768.0;
      this.sm2 = f0; this.sm1 = f0; this.s0 = f0;
      this.resamplePhase = 0;
      this.hasHist = true;
    }
    if (this.sr === 48000) {
      let sm2 = this.sm2, sm1 = this.sm1, s0 = this.s0;
      for (let i = 0; i < n; i++) {
        const sp1 = i16[i] / 32768.0;
        let mid = (-0.0625 * sm2) + (0.5625 * sm1) + (0.5625 * s0) - (0.0625 * sp1);
        if (mid > 1.0) mid = 1.0; else if (mid < -1.0) mid = -1.0;
        this._writeSample(mid);
        this._writeSample(sp1);
        sm2 = sm1; sm1 = s0; s0 = sp1;
      }
      this.sm2 = sm2; this.sm1 = sm1; this.s0 = s0;
      return;
    }
    if (this.sr === 24000) {
      for (let i = 0; i < n; i++) this._writeSample(i16[i] / 32768.0);
      return;
    }
    const step = 24000 / this.sr;
    let phase = this.resamplePhase, sm2 = this.sm2, sm1 = this.sm1, s0 = this.s0;
    for (let i = 0; i < n; i++) {
      const sp1 = i16[i] / 32768.0;
      while (phase <= 1.0) {
        const t = phase;
        const c0 = s0, c1 = 0.5 * (sp1 - sm1);
        const c2 = sm1 - 2.5 * s0 + 2.0 * sp1 - 0.5 * sm2;
        const c3 = 0.5 * (sp1 - sm2) + 1.5 * (s0 - sm1);
        let y = ((c3 * t + c2) * t + c1) * t + c0;
        if (y > 1.0) y = 1.0; else if (y < -1.0) y = -1.0;
        this._writeSample(y);
        phase += step;
      }
      phase -= 1.0;
      sm2 = sm1; sm1 = s0; s0 = sp1;
    }
    this.resamplePhase = phase; this.sm2 = sm2; this.sm1 = sm1; this.s0 = s0;
  }

  process(inputs, outputs) {
    const outChan = outputs[0] && outputs[0][0];
    const inChan = inputs[0] && inputs[0][0];
    const len = outChan ? outChan.length : 128;

    if (this.playing || this.avail > 0) {
      this.echoTailSamples = Math.floor(this.sr * 0.85);
    } else if (this.echoTailSamples > 0) {
      this.echoTailSamples = Math.max(0, this.echoTailSamples - len);
    }
    const echoGuardActive = this.playing || this.avail > 0 || this.echoTailSamples > 0;

    if (inChan && inChan.length) {
      if (echoGuardActive) {
        this.hpPrevX = 0; this.hpPrevY = 0;
        this.decimSum = 0; this.decimCount = 0;
        this.micVoiceFrames = 0;
        for (let i = 0; i < inChan.length; i++) {
          this.decimAcc += 1;
          if (this.decimAcc >= this.decimRatio) {
            this.decimAcc -= this.decimRatio;
            this.micOut[this.micIdx++] = 0;
            if (this.micIdx >= 640) {
              const copy = new Int16Array(this.micOut);
              this.port.postMessage({ type: 'mic_pcm16', buffer: copy.buffer }, [copy.buffer]);
              this.micIdx = 0;
            }
          }
        }
      } else {
        let prevX = this.hpPrevX, prevY = this.hpPrevY;
        const alpha = this.hpAlpha;
        let frameSq = 0;

        for (let i = 0; i < inChan.length; i++) {
          const x = inChan[i];
          const y = alpha * (prevY + x - prevX);
          prevX = x; prevY = y;
          frameSq += y * y;
          this.decimSum += y;
          this.decimCount += 1;
          this.decimAcc += 1;
          if (this.decimAcc >= this.decimRatio) {
            this.decimAcc -= this.decimRatio;
            const avg = this.decimCount > 0 ? (this.decimSum / this.decimCount) : y;
            this.decimSum = 0; this.decimCount = 0;
            const s = avg > 1.0 ? 1.0 : (avg < -1.0 ? -1.0 : avg);
            this.micOut[this.micIdx++] = s < 0 ? (s * 0x8000) : (s * 0x7fff);
            if (this.micIdx >= 640) {
              const copy = new Int16Array(this.micOut);
              this.port.postMessage({ type: 'mic_pcm16', buffer: copy.buffer }, [copy.buffer]);
              this.micIdx = 0;
            }
          }
        }
        this.hpPrevX = prevX; this.hpPrevY = prevY;
        const fRms = Math.sqrt(frameSq / inChan.length);
        if (fRms > 0.045) this.micVoiceFrames = Math.min(25, this.micVoiceFrames + 1);
        else this.micVoiceFrames = Math.max(0, this.micVoiceFrames - 1);
      }
    }

    this.duckGain = 1.0;

    if (outChan) {
      if (this.clearFadeRem > 0) {
        for (let i = 0; i < len; i++) {
          if (this.clearFadeRem > 0) {
            const prog = 1.0 - (this.clearFadeRem / this.clearFadeTotal);
            outChan[i] = this.fadeStartSample * 0.5 * (1.0 + Math.cos(Math.PI * prog));
            this.lastOut = outChan[i];
            this.clearFadeRem -= 1;
          } else {
            outChan[i] = 0; this.lastOut = 0;
          }
        }
      } else {
        if (!this.playing) {
          const targetSamples = Math.floor(this.sr * this.targetPrebufSec);
          const waited = this.avail > 0 ? (currentTime - this.firstBufTime) : 0;
          if (this.avail >= targetSamples || (this.turnComplete && this.avail > 0) || (this.avail > 0 && waited >= 0.145)) {
            this.playing = true;
            this.prebuffering = false;
            this.fadeStartSample = this.lastOut;
            this.fadeInRem = this.fadeInTotal;
          }
        }
        if (this.playing) {
          for (let i = 0; i < len; i++) {
            if (this.avail > 0) {
              let s = this.ring[this.readPos] * this.duckGain;
              this.readPos = (this.readPos + 1) % this.cap;
              this.avail -= 1;
              if (this.fadeInRem > 0) {
                const prog = 1.0 - (this.fadeInRem / this.fadeInTotal);
                const w = 0.5 * (1.0 - Math.cos(Math.PI * prog));
                s = this.fadeStartSample * (1.0 - w) + s * w;
                this.fadeInRem -= 1;
              }
              outChan[i] = s;
              this.lastOut = s;
            } else {
              const rem = len - i;
              const startS = this.lastOut;
              for (let k = 0; k < rem; k++) {
                const w = 0.5 * (1.0 + Math.cos(Math.PI * ((k + 1) / rem)));
                outChan[i + k] = startS * w;
              }
              this.lastOut = 0;
              this.playing = false;
              this.prebuffering = true;
              if (!this.turnComplete) {
                this.targetPrebufSec = Math.min(0.220, this.targetPrebufSec + 0.025);
              } else {
                this.targetPrebufSec = Math.max(0.105, this.targetPrebufSec - 0.008);
                this.turnComplete = false;
                this.hasHist = false;
              }
              break;
            }
          }
        } else {
          for (let i = 0; i < len; i++) {
            if (Math.abs(this.lastOut) > 0.0001) {
              this.lastOut *= 0.85;
              outChan[i] = this.lastOut;
            } else {
              this.lastOut = 0;
              outChan[i] = 0;
            }
          }
        }
      }
    }

    this.telemetrySamples += len;
    if (this.telemetrySamples >= Math.floor(this.sr * 0.08)) {
      this.telemetrySamples = 0;
      this.port.postMessage({ type: 'state', playing: this.playing });
    }
    return true;
  }
}
registerProcessor('humsyar-admin-live-audio-processor', HumsyarAdminLiveAudioProcessor);
`;

let _adminWorkletBlobUrl = null;
function getAdminLiveWorkletBlobUrl() {
  if (!_adminWorkletBlobUrl) {
    _adminWorkletBlobUrl = URL.createObjectURL(
      new Blob([ADMIN_LIVE_WORKLET_CODE], { type: 'application/javascript' }),
    );
  }
  return _adminWorkletBlobUrl;
}

function AiLiveStudio({ cfg, me, onSaved }) {
  const [models, setModels] = useState(null);
  const [meta, setMeta] = useState(null);
  const [probing, setProbing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  // تنظیمات فعال ربات/مینی‌اپ
  const [liveEnabled, setLiveEnabled] = useState(true);
  const [liveModel, setLiveModel] = useState('gemini-3.8-live');
  const [liveVoice, setLiveVoice] = useState('Sulafat');
  const [liveThinking, setLiveThinking] = useState('low');
  const [liveDailyMin, setLiveDailyMin] = useState(15);
  const [liveMaxSec, setLiveMaxSec] = useState(300);
  const [liveTargetLang, setLiveTargetLang] = useState('fa');
  const [liveTemperature, setLiveTemperature] = useState(0.85);
  const [voiceSystemPrompt, setVoiceSystemPrompt] = useState('');
  const [defaultVoicePrompt, setDefaultVoicePrompt] = useState('');

  // اتاق تست زنده در مرورگر ادمین (صدا + ویدیو دوربین / اشتراک صفحه)
  const [callState, setCallState] = useState('idle'); // idle | connecting | listening | speaking | error
  const [callErr, setCallErr] = useState('');
  const [videoOn, setVideoOn] = useState(false);
  const [userSub, setUserSub] = useState('');
  const [aiSub, setAiSub] = useState('');
  const [turns, setTurns] = useState([]);
  const [testText, setTestText] = useState('');
  const wsRef = useRef(null);
  const streamRef = useRef(null);
  const videoStreamRef = useRef(null);
  const videoElRef = useRef(null);
  const videoTimerRef = useRef(null);
  const capCtxRef = useRef(null);
  const procRef = useRef(null);
  const workletNodeRef = useRef(null);
  const workletLoadedCtxRef = useRef(null);
  const playCtxRef = useRef(null);
  const playGainRef = useRef(null);
  const nextTimeRef = useRef(0);
  const sourcesRef = useRef([]);
  const pendingPcmQueueRef = useRef([]);
  const pendingSamplesCountRef = useRef(0);
  const isPrebufferingRef = useRef(true);
  const flushTimerRef = useRef(null);
  const prevSampleRef = useRef(0);

  const loadLiveMeta = async (refresh = false) => {
    setErr('');
    try {
      const r = await api.aiLiveModels(refresh);
      setModels(r.models || []);
      setMeta(r);
      setLiveEnabled(r.live_enabled !== undefined ? !!r.live_enabled : (cfg?.live_enabled !== false));
      setLiveModel(r.current_model || cfg?.live_model || 'gemini-3.8-live');
      setLiveVoice(r.live_voice || cfg?.live_voice || 'Sulafat');
      setLiveThinking(r.live_thinking_level || cfg?.live_thinking_level || 'low');
      setLiveDailyMin(r.live_daily_minutes ?? cfg?.live_daily_minutes ?? 15);
      setLiveMaxSec(r.live_max_session_sec ?? cfg?.live_max_session_sec ?? 300);
      setLiveTargetLang(r.live_target_language || cfg?.live_target_language || 'fa');
      setLiveTemperature(r.live_temperature ?? cfg?.live_temperature ?? 0.85);
      setVoiceSystemPrompt(r.voice_system_prompt || cfg?.voice_system_prompt || '');
      setDefaultVoicePrompt(r.default_voice_system_prompt || cfg?.default_voice_system_prompt || '');
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { loadLiveMeta(false); }, []);

  const saveLiveCfg = async (overrideModel) => {
    const targetMod = typeof overrideModel === 'string' && overrideModel ? overrideModel : liveModel;
    setSaving(true);
    try {
      const r = await api.aiLiveConfigSave({
        live_enabled: !!liveEnabled,
        live_model: targetMod,
        live_voice: liveVoice || 'Sulafat',
        live_thinking_level: liveThinking || 'low',
        live_daily_minutes: Number(liveDailyMin) || 0,
        live_max_session_sec: Number(liveMaxSec) || 300,
        live_target_language: liveTargetLang || 'fa',
        live_temperature: Number(liveTemperature) || 0.85,
        voice_system_prompt: voiceSystemPrompt || '',
      });
      setLiveModel(r.live_model);
      setMeta(x => ({ ...(x || {}), current_model: r.live_model, live_enabled: r.live_enabled }));
      toast(`پیکربندی تماس صوتی زنده روی «${r.live_model}» ذخیره شد ✅`);
      onSaved && onSaved();
    } catch (e) { toast(errText(e), 'err'); }
    setSaving(false);
  };

  const probeLive = async () => {
    setProbing(true);
    try {
      const r = await api.aiModelsProbe('gemini', {
        kind: 'live',
        models: (models || []).map(m => m.id),
      });
      const okN = Number(r.ok_count || 0), total = Number(r.count || 0);
      toast(`تست WebSocket Gemini Live: ${okN} از ${total} مدل آماده و فعال است ${okN > 0 ? '✅' : '⚠️'}`);
      await loadLiveMeta(false);
    } catch (e) { toast(errText(e), 'err'); }
    setProbing(false);
  };

  const ensurePlayCtx = () => {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!playCtxRef.current || playCtxRef.current.state === 'closed') {
      try {
        playCtxRef.current = new AC({ latencyHint: 'interactive' });
      } catch (_) {
        playCtxRef.current = new AC();
      }
      playGainRef.current = null;
    }
    const ctx = playCtxRef.current;
    if (ctx.state === 'suspended') ctx.resume().catch(() => {});
    if (!playGainRef.current) {
      const g = ctx.createGain();
      g.gain.value = 1.0;
      g.connect(ctx.destination);
      playGainRef.current = g;
    }
    return ctx;
  };

  const warmUpPlayCtx = () => {
    try {
      const ctx = ensurePlayCtx();
      const silent = ctx.createBuffer(1, 128, ctx.sampleRate || 48000);
      const s = ctx.createBufferSource();
      s.buffer = silent;
      s.connect(ctx.destination);
      s.start(0);
    } catch (_) {}
  };

  const stopPlayback = () => {
    if (workletNodeRef.current) {
      try { workletNodeRef.current.port.postMessage({ type: 'clear' }); } catch (_) {}
    }
    if (flushTimerRef.current) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    pendingPcmQueueRef.current = [];
    pendingSamplesCountRef.current = 0;
    isPrebufferingRef.current = true;
    prevSampleRef.current = 0;
    const ctx = playCtxRef.current;
    const g = playGainRef.current;
    if (ctx && g && ctx.state === 'running') {
      try {
        const now = ctx.currentTime;
        g.gain.cancelScheduledValues(now);
        g.gain.setValueAtTime(g.gain.value, now);
        g.gain.linearRampToValueAtTime(0.0001, now + 0.012);
        g.gain.setValueAtTime(1.0, now + 0.016);
      } catch (_) {}
    }
    for (const s of sourcesRef.current) { try { s.stop(); } catch (_) {} }
    sourcesRef.current = [];
    nextTimeRef.current = 0;
  };

  const stopVideo = () => {
    if (videoTimerRef.current) { window.clearInterval(videoTimerRef.current); videoTimerRef.current = null; }
    if (videoStreamRef.current) {
      for (const t of videoStreamRef.current.getTracks()) { try { t.stop(); } catch (_) {} }
      videoStreamRef.current = null;
    }
    if (videoElRef.current) videoElRef.current.srcObject = null;
    setVideoOn(false);
  };

  const startVideo = async (mode = 'camera') => {
    stopVideo();
    try {
      const vStream = mode === 'screen' && navigator.mediaDevices.getDisplayMedia
        ? await navigator.mediaDevices.getDisplayMedia({ video: { width: { ideal: 800 }, height: { ideal: 600 } }, audio: false })
        : await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
      videoStreamRef.current = vStream;
      setVideoOn(true);
      if (videoElRef.current) {
        videoElRef.current.srcObject = vStream;
        videoElRef.current.play().catch(() => {});
      }
      const canvas = document.createElement('canvas');
      const ctx2d = canvas.getContext('2d');
      videoTimerRef.current = window.setInterval(() => {
        const vid = videoElRef.current;
        if (!vid || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        if (!vid.videoWidth || !vid.videoHeight) return;
        const scale = Math.min(1, 640 / Math.max(vid.videoWidth, vid.videoHeight));
        canvas.width = Math.round(vid.videoWidth * scale);
        canvas.height = Math.round(vid.videoHeight * scale);
        ctx2d.drawImage(vid, 0, 0, canvas.width, canvas.height);
        const b64 = (canvas.toDataURL('image/jpeg', 0.65).split(',')[1]) || '';
        if (b64) {
          wsRef.current.send(JSON.stringify({ type: 'video', data: b64, mimeType: 'image/jpeg' }));
        }
      }, 1000);
    } catch (_) {
      toast('دسترسی به دوربین/صفحه‌نمایش داده نشد', 'err');
    }
  };

  useEffect(() => {
    if (videoOn && videoElRef.current && videoStreamRef.current) {
      videoElRef.current.srcObject = videoStreamRef.current;
      videoElRef.current.play().catch(() => {});
    }
  }, [videoOn]);

  const stopTestCall = () => {
    stopPlayback();
    stopVideo();
    if (workletNodeRef.current) {
      try {
        workletNodeRef.current.port.onmessage = null;
        workletNodeRef.current.disconnect();
      } catch (_) {}
      workletNodeRef.current = null;
    }
    if (procRef.current) { try { procRef.current.disconnect(); } catch (_) {} procRef.current = null; }
    if (capCtxRef.current && capCtxRef.current !== playCtxRef.current) {
      try { capCtxRef.current.close(); } catch (_) {}
    }
    capCtxRef.current = null;
    if (streamRef.current) { for (const t of streamRef.current.getTracks()) { try { t.stop(); } catch (_) {} } streamRef.current = null; }
    if (wsRef.current) { try { wsRef.current.close(); } catch (_) {} wsRef.current = null; }
    setCallState('idle');
  };
  useEffect(() => () => stopTestCall(), []);

  const flushPendingPcm = (forceFlush = false) => {
    if (flushTimerRef.current && forceFlush) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    if (!pendingPcmQueueRef.current.length) return;
    if (isPrebufferingRef.current && !forceFlush && pendingSamplesCountRef.current < 3360) {
      return;
    }
    if (flushTimerRef.current) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }

    let total = 0;
    for (let i = 0; i < pendingPcmQueueRef.current.length; i++) total += pendingPcmQueueRef.current[i].length;
    const merged24k = new Float32Array(total);
    let off = 0;
    for (let i = 0; i < pendingPcmQueueRef.current.length; i++) {
      merged24k.set(pendingPcmQueueRef.current[i], off);
      off += pendingPcmQueueRef.current[i].length;
    }
    pendingPcmQueueRef.current = [];
    pendingSamplesCountRef.current = 0;
    if (!merged24k.length) return;

    try {
      const ctx = ensurePlayCtx();
      const now = ctx.currentTime;
      const wasUnderrun = !nextTimeRef.current || nextTimeRef.current <= now + 0.004;
      const applyFadeIn = isPrebufferingRef.current || wasUnderrun;
      isPrebufferingRef.current = false;

      let prev = prevSampleRef.current || 0;
      let bufSamples;
      let bufRate = 24000;
      if (ctx.sampleRate === 48000) {
        bufRate = 48000;
        bufSamples = new Float32Array(merged24k.length * 2);
        let sm2 = prev, sm1 = prev, s0 = merged24k[0];
        for (let i = 0; i < merged24k.length; i++) {
          const sp1 = merged24k[i];
          let mid = (-0.0625 * sm2) + (0.5625 * sm1) + (0.5625 * s0) - (0.0625 * sp1);
          if (mid > 1.0) mid = 1.0; else if (mid < -1.0) mid = -1.0;
          bufSamples[2 * i] = mid;
          bufSamples[2 * i + 1] = sp1;
          sm2 = sm1; sm1 = s0; s0 = sp1;
        }
        if (applyFadeIn) {
          const ramp = Math.min(bufSamples.length, 144);
          for (let i = 0; i < ramp; i++) {
            bufSamples[i] *= 0.5 * (1 - Math.cos((Math.PI * (i + 1)) / ramp));
          }
        }
        prevSampleRef.current = s0;
      } else {
        bufSamples = merged24k;
        if (applyFadeIn) {
          const ramp = Math.min(bufSamples.length, 72);
          for (let i = 0; i < ramp; i++) {
            bufSamples[i] *= 0.5 * (1 - Math.cos((Math.PI * (i + 1)) / ramp));
          }
        } else if (bufSamples.length >= 4) {
          bufSamples[0] = 0.5 * (prev + bufSamples[0]);
        }
        prevSampleRef.current = bufSamples[bufSamples.length - 1] || 0;
      }

      const buf = ctx.createBuffer(1, bufSamples.length, bufRate);
      buf.getChannelData(0).set(bufSamples);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(playGainRef.current || ctx.destination);
      const startAt = wasUnderrun ? now + 0.045 : Math.max(now + 0.008, nextTimeRef.current);
      nextTimeRef.current = startAt + buf.duration;
      sourcesRef.current.push(src);
      setCallState(prevSt => (prevSt === 'speaking' ? prevSt : 'speaking'));
      src.onended = () => {
        sourcesRef.current = sourcesRef.current.filter(x => x !== src);
        if (!sourcesRef.current.length && !pendingSamplesCountRef.current) {
          isPrebufferingRef.current = true;
          prevSampleRef.current = 0;
          setCallState(prevSt => (prevSt === 'speaking' ? 'listening' : prevSt));
        }
      };
      src.start(startAt);
    } catch (_) {}
  };

  const playPcm24k = (rawOrB64) => {
    try {
      let ab;
      if (rawOrB64 instanceof ArrayBuffer) {
        ab = rawOrB64;
      } else {
        const bin = atob(rawOrB64);
        const len = bin.length - (bin.length % 2);
        if (len <= 0) return;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) bytes[i] = bin.charCodeAt(i);
        ab = bytes.buffer;
      }
      if (!ab || ab.byteLength < 2) return;

      if (workletNodeRef.current) {
        workletNodeRef.current.port.postMessage({ type: 'pcm24k', buffer: ab }, [ab]);
        setCallState(prevSt => (prevSt === 'speaking' ? prevSt : 'speaking'));
        return;
      }

      const i16 = new Int16Array(ab, 0, Math.floor(ab.byteLength / 2));
      const f32 = new Float32Array(i16.length);
      for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768.0;

      const ctx = ensurePlayCtx();
      if (!nextTimeRef.current || nextTimeRef.current <= ctx.currentTime + 0.004) {
        isPrebufferingRef.current = true;
      }
      pendingPcmQueueRef.current.push(f32);
      pendingSamplesCountRef.current += f32.length;

      if (isPrebufferingRef.current) {
        if (pendingSamplesCountRef.current >= 3360) {
          flushPendingPcm(true);
        } else if (!flushTimerRef.current) {
          flushTimerRef.current = window.setTimeout(() => {
            flushTimerRef.current = null;
            flushPendingPcm(true);
          }, 110);
        }
      } else {
        flushPendingPcm(true);
      }
    } catch (_) {}
  };

  const startTestCall = async (withVideoMode = '') => {
    setCallErr(''); setUserSub(''); setAiSub(''); setTurns([]);
    warmUpPlayCtx();

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (_) {
      setCallState('error');
      setCallErr('دسترسی به میکروفون در مرورگر داده نشد.');
      return;
    }
    warmUpPlayCtx();
    streamRef.current = stream;
    setCallState('connecting');
    if (withVideoMode) {
      startVideo(withVideoMode);
    }
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const qs = new URLSearchParams({
      model: liveModel,
      voice: liveVoice,
      thinking_level: liveThinking,
      target_language: liveTargetLang,
      binary: '1',
    });
    const ws = new WebSocket(`${proto}//${window.location.host}/api/ai/live/ws?${qs.toString()}`);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onmessage = async (ev) => {
      if (ev.data instanceof ArrayBuffer) {
        playPcm24k(ev.data);
        return;
      }
      let msg;
      try { msg = JSON.parse(ev.data); } catch (_) { return; }
      if (msg.type === 'ready') {
        setCallState('listening');
        toast(`اتصال زنده به ${msg.model} برقرار شد — صحبت کنید 🎙`);
        const capCtx = ensurePlayCtx();
        capCtxRef.current = capCtx;
        const src = capCtx.createMediaStreamSource(stream);

        if (capCtx.audioWorklet && typeof window.AudioWorkletNode !== 'undefined') {
          try {
            if (workletLoadedCtxRef.current !== capCtx) {
              await capCtx.audioWorklet.addModule(getAdminLiveWorkletBlobUrl());
              workletLoadedCtxRef.current = capCtx;
            }
            const wNode = new window.AudioWorkletNode(capCtx, 'humsyar-admin-live-audio-processor', {
              numberOfInputs: 1,
              numberOfOutputs: 1,
              outputChannelCount: [1],
            });
            wNode.port.onmessage = (wEv) => {
              const d = wEv.data;
              if (!d) return;
              if (d.type === 'mic_pcm16' && d.buffer) {
                if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                  wsRef.current.send(d.buffer);
                }
              } else if (d.type === 'state') {
                setCallState(prevSt => (d.playing ? 'speaking' : (prevSt === 'speaking' ? 'listening' : prevSt)));
              }
            };
            src.connect(wNode);
            wNode.connect(playGainRef.current || capCtx.destination);
            workletNodeRef.current = wNode;
            return;
          } catch (wErr) {
            console.warn('[AiAdmin worklet fallback]', wErr);
          }
        }

        const proc = capCtx.createScriptProcessor(2048, 1, 1);
        const silentGain = capCtx.createGain();
        silentGain.gain.value = 0;
        procRef.current = proc;
        proc.onaudioprocess = (ae) => {
          if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
          const raw = ae.inputBuffer.getChannelData(0);
          const ratio = capCtx.sampleRate / 16000;
          const outLen = Math.round(raw.length / ratio);
          const pcm = new Int16Array(outLen);
          for (let i = 0; i < outLen; i++) {
            const start = Math.floor(i * ratio);
            const end = Math.min(raw.length, Math.floor((i + 1) * ratio));
            let sum = 0, cnt = 0;
            for (let j = start; j < end; j++) { sum += raw[j]; cnt++; }
            const avg = cnt > 0 ? sum / cnt : (raw[start] || 0);
            const s = Math.max(-1, Math.min(1, avg));
            pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          wsRef.current.send(pcm.buffer);
        };
        src.connect(proc);
        proc.connect(silentGain);
        silentGain.connect(capCtx.destination);
      } else if (msg.type === 'audio' && msg.data) {
        playPcm24k(msg.data);
      } else if (msg.type === 'interrupted') {
        stopPlayback();
        setCallState('listening');
      } else if (msg.type === 'input_transcript' && msg.text) {
        setUserSub(p => `${p} ${msg.text}`.trim());
      } else if (msg.type === 'user_transcript_override' && msg.text) {
        setTurns(prev => {
          if (!prev.length) return [{ r: 'شما', t: msg.text }];
          const copy = [...prev];
          for (let i = copy.length - 1; i >= 0; i--) {
            if (copy[i].r === 'شما') { copy[i] = { ...copy[i], t: msg.text }; return copy; }
          }
          copy.splice(copy.length - 1, 0, { r: 'شما', t: msg.text });
          return copy.slice(-10);
        });
      } else if ((msg.type === 'output_transcript' || msg.type === 'text') && msg.text) {
        setAiSub(p => `${p} ${msg.text}`.trim());
      } else if (msg.type === 'turn_state' && (msg.turn_complete || msg.interaction_status === 'IDLE')) {
        if (workletNodeRef.current) {
          try { workletNodeRef.current.port.postMessage({ type: 'turn_complete' }); } catch (_) {}
        } else {
          flushPendingPcm(true);
        }
        setUserSub(u => {
          setAiSub(a => {
            if (u || a) {
              setTurns(prev => [...prev.slice(-10), ...(u ? [{ r: 'شما', t: u }] : []), ...(a ? [{ r: 'هوشیار', t: a }] : [])]);
            }
            return '';
          });
          return '';
        });
      } else if (msg.type === 'error') {
        setCallErr(msg.message || 'خطا در نشست زنده');
        stopTestCall();
        setCallState('error');
      }
    };
    ws.onerror = () => { setCallErr('خطا در اتصال WebSocket'); stopTestCall(); setCallState('error'); };
    ws.onclose = () => { stopTestCall(); };
  };

  const HBadge = ({ m }) => (
    m.health_ok === true ? (
      <span style={{ color: 'var(--c-ok, #2a2)', fontSize: 'var(--fs-caption)', fontWeight: 600 }}>
        🟢 سالم ({Number(m.health_ms || 1).toLocaleString('fa')}ms)
      </span>
    ) : m.health_ok === false ? (
      <span style={{ color: 'var(--c-bad, #d24)', fontSize: 'var(--fs-caption)' }} title={m.health_error || ''}>
        🔴 خطا{m.health_error ? `: ${m.health_error.slice(0, 55)}` : ''}
      </span>
    ) : (
      <span className="muted" style={{ fontSize: 'var(--fs-caption)' }}>⚪ تست‌نشده</span>
    )
  );

  const activeBotModel = meta?.current_model || cfg?.live_model || liveModel;

  return (
    <>
      <div className="panel panel-pad" style={{ marginBottom: 14 }}>
        <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <b>🎙 پیکربندی تماس صوتی زنده با هوشیار (Google Gemini Live API)</b>
          <B kind={liveEnabled ? 'ok' : 'warn'}>
            {liveEnabled ? `فعال · مدل فعلی: ${activeBotModel}` : 'تماس صوتی زنده غیرفعال است'}
          </B>
        </div>
        <div className="muted" style={{ marginTop: 6, fontSize: 'var(--fs-caption)' }}>
          پشتیبانی کامل از پروتکل WebSocket دوطرفه <code>BidiGenerateContent</code> گوگل با صدای زنده فارسی، پریدن وسط حرف (Barge-in) و دسترسی زنده به ابزارهای دانشجویی هامزیار.
        </div>

        <div className="grid g2" style={{ gap: 10, marginTop: 12 }}>
          <label className="fld">
            <span>وضعیت تماس صوتی زنده برای کاربران (مینی‌اپ و ربات/گروه)</span>
            <div className="row" style={{ marginTop: 6 }}>
              <Switch on={!!liveEnabled} onChange={setLiveEnabled} />
              <span>{liveEnabled ? 'فعال — کاربران می‌توانند تماس صوتی زنده برقرار کنند' : 'غیرفعال'}</span>
            </div>
          </label>

          <label className="fld">
            <span>مدل تماس صوتی زنده (Gemini Live)</span>
            <select className="inp" style={{ direction: 'ltr' }} value={liveModel} onChange={e => setLiveModel(e.target.value)}>
              {(models || [
                { id: 'gemini-3.8-live', label: '⚡ gemini-3.8-live (پیش‌فرض کم‌تأخیر)' },
                { id: 'gemini-3.8-live-extended-thinking', label: '🧠 gemini-3.8-live-extended-thinking (استدلال عمیق)' },
                { id: 'gemini-3.1-flash-live-preview', label: '🚀 gemini-3.1-flash-live-preview (سریع و اقتصادی)' },
                { id: 'gemini-3.5-live-translate-preview', label: '🌐 gemini-3.5-live-translate-preview (مترجم صوت‌به‌صوت)' },
              ]).map(m => (
                <option key={m.id} value={m.id}>
                  {m.health_ok === true ? '🟢 ' : m.health_ok === false ? '🔴 ' : ''}{m.id} — {m.label}
                </option>
              ))}
            </select>
          </label>

          <label className="fld">
            <span>🗣 صدای هوشیار در تماس زنده</span>
            <select className="inp" value={liveVoice} onChange={e => setLiveVoice(e.target.value)}>
              {(meta?.voices || [{ id: 'Sulafat', label: 'Sulafat — گرم (پیشنهادی)' }]).map(v => (
                <option key={v.id} value={v.id}>{v.label}</option>
              ))}
            </select>
          </label>

          <label className="fld">
            <span>🧠 سطح تفکر (مخصوص مدل‌های Extended Thinking / 3.1 Flash Live)</span>
            <select className="inp" value={liveThinking} onChange={e => setLiveThinking(e.target.value)}>
              <option value="minimal">minimal (کمترین تأخیر — فقط ۳.۱)</option>
              <option value="low">low (پیشنهادی برای مکالمه روان)</option>
              <option value="medium">medium (متعادل)</option>
              <option value="high">high (تحلیل عمیق علمی و بالینی)</option>
            </select>
          </label>

          <label className="fld">
            <span>⏱ سهمیه روزانه هر کاربر (دقیقه در روز؛ ۰ = نامحدود)</span>
            <input className="inp" type="number" min="0" max="600" value={liveDailyMin} onChange={e => setLiveDailyMin(e.target.value)} />
          </label>

          <label className="fld">
            <span>⏳ حداکثر زمان هر نشست تماس (ثانیه)</span>
            <input className="inp" type="number" min="30" max="3600" value={liveMaxSec} onChange={e => setLiveMaxSec(e.target.value)} />
          </label>

          <label className="fld">
            <span>🌐 زبان مقصد ترجمه پیش‌فرض (برای مدل gemini-3.5-live-translate-preview)</span>
            <select className="inp" value={liveTargetLang} onChange={e => setLiveTargetLang(e.target.value)}>
              {(meta?.translate_languages || [{ code: 'fa', label: 'فارسی (fa)' }]).map(l => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>
          </label>

          <label className="fld">
            <span>🌡 دمای لحن صوتی (Temperature — پیشنهادی: 0.85 برای لحن صمیمی و بااحساس)</span>
            <input className="inp" type="number" step="0.05" min="0.1" max="1.5" value={liveTemperature} onChange={e => setLiveTemperature(e.target.value)} />
          </label>
        </div>

        <div className="grid" style={{ gap: 8, marginTop: 14 }}>
          <label className="fld">
            <span className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
              <span>💬 پرامپت سیستمی اختصاصی ویس‌چت زنده و پاسخ‌های صوتی (مستقل از چت متنی)</span>
              {defaultVoicePrompt && (
                <button type="button" className="btn sm" onClick={() => { setVoiceSystemPrompt(defaultVoicePrompt); toast('پرامپت پیش‌فرض صمیمی بارگذاری شد — برای ثبت نهایی دکمه ذخیره را بزنید'); }}>
                  🔄 بازگردانی به پرامپت صمیمی پیش‌فرض
                </button>
              )}
            </span>
            <textarea className="inp" rows={10} style={{ resize: 'vertical', marginTop: 6, lineHeight: 1.7 }}
                      placeholder="پرامپت لحن صمیمی و محاوره‌ای ویس‌چت زنده…"
                      value={voiceSystemPrompt} onChange={e => setVoiceSystemPrompt(e.target.value)} />
          </label>
          <div className="muted" style={{ fontSize: 'var(--fs-caption)' }}>
            این پرامپت فقط برای ویس‌چت زنده و پاسخ‌های صوتی استفاده می‌شود و چت متنی هوشیار را تغییر نمی‌دهد.
          </div>
        </div>

        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn primary" disabled={saving || !liveModel} onClick={() => saveLiveCfg()}>
            {saving ? '⏳ در حال ذخیره…' : '💾 ذخیره تنظیمات تماس صوتی زنده هوشیار'}
          </button>
        </div>
      </div>

      {/* جدول مدل‌های Live گوگل + تست WebSocket */}
      <div className="panel panel-pad" style={{ marginBottom: 14 }}>
        <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <b>📋 مدل‌های رسمی تماس صوتی زنده گوگل (Gemini Live API)</b>
          <div className="row" style={{ gap: 6 }}>
            <button className="btn sm" onClick={() => loadLiveMeta(true)}>🔄 تازه‌سازی</button>
            <button className="btn sm primary" disabled={probing || !models?.length} onClick={probeLive}>
              {probing ? '⏳ تست اتصال WebSocket…' : '🧪 تست زنده‌بودن مدل‌های Live'}
            </button>
          </div>
        </div>
        {err && <div style={{ color: 'var(--c-bad, #d24)', marginTop: 8 }}>{err}</div>}
        {models === null ? <Loading rows={2} /> : (
          <div style={{ marginTop: 10 }}>
            {models.map(m => {
              const isCurrent = m.id === activeBotModel;
              return (
                <div key={m.id} className="row" style={{
                  justifyContent: 'space-between', padding: '7px 8px',
                  borderBottom: '1px solid var(--c-line, #eee)',
                  background: isCurrent ? 'rgba(59,130,246,0.08)' : (m.id === liveModel ? 'var(--c-bg2, #f6f8fa)' : 'transparent'),
                  borderRadius: 6, flexWrap: 'wrap', gap: 8,
                }}>
                  <span className="row" style={{ gap: 8 }}>
                    <input type="radio" name="live_model" checked={m.id === liveModel} onChange={() => setLiveModel(m.id)} />
                    <span className="code" style={{ direction: 'ltr', fontWeight: isCurrent ? 700 : 400 }}>{m.id}</span>
                    {isCurrent && <B kind="acc">🤖 فعال در هوشیار</B>}
                    <span className="muted" style={{ fontSize: 'var(--fs-caption)' }}>{m.label}</span>
                  </span>
                  <span className="row" style={{ gap: 8 }}>
                    <HBadge m={m} />
                    {!isCurrent && (
                      <button className="btn sm" disabled={saving} onClick={() => saveLiveCfg(m.id)}>
                        🤖 تنظیم برای هوشیار
                      </button>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* اتاق تست تماس صوتی و ویدیویی زنده برای ادمین */}
      <div className="panel panel-pad">
        <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <b>🎧📹 اتاق تست تماس صوتی و ویدیویی زنده (مستقیم از مرورگر ادمین)</b>
          <B kind={callState === 'listening' || callState === 'speaking' ? 'ok' : callState === 'error' ? 'bad' : ''}>
            {callState === 'idle' ? 'آماده تست' : callState === 'connecting' ? 'در حال اتصال…' : callState === 'speaking' ? '🔊 هوشیار در حال صحبت…' : callState === 'listening' ? '🟢 در حال گوش دادن…' : 'خطا'}
          </B>
        </div>
        <div className="muted" style={{ marginTop: 6, fontSize: 'var(--fs-caption)' }}>
          با زدن دکمه‌های زیر، اتصال WebSocket به مدل انتخابی (<code>{liveModel}</code>) با صدای <code>{liveVoice}</code> برقرار می‌شود و می‌توانید زنده (صوتی یا ویدیویی + صوتی) با هوشیار مکالمه کنید.
        </div>
        {callErr && <div style={{ color: 'var(--c-bad, #d24)', marginTop: 8 }}>{callErr}</div>}

        {videoOn && (
          <div style={{ marginTop: 12, maxWidth: 360, borderRadius: 10, overflow: 'hidden', border: '2px solid var(--acc)' }}>
            <video ref={videoElRef} autoPlay playsInline muted style={{ width: '100%', display: 'block', background: '#000', maxHeight: 240 }} />
          </div>
        )}

        <div className="row" style={{ marginTop: 12, gap: 10, flexWrap: 'wrap' }}>
          {callState === 'idle' || callState === 'error' ? (
            <>
              <button className="btn primary" onClick={() => startTestCall('')}>🎙 شروع تست تماس صوتی زنده</button>
              {!liveModel.includes('translate') && (
                <>
                  <button className="btn" onClick={() => startTestCall('camera')}>📹 تست تماس ویدیویی + صوتی (دوربین)</button>
                  <button className="btn" onClick={() => startTestCall('screen')}>🖥 تست با اشتراک صفحه‌نمایش</button>
                </>
              )}
            </>
          ) : (
            <>
              <button className="btn danger" onClick={stopTestCall}>📴 پایان تماس آزمایشی</button>
              {!liveModel.includes('translate') && (
                <button className="btn" onClick={() => (videoOn ? stopVideo() : startVideo('camera'))}>
                  {videoOn ? '📹 بستن ویدیو' : '📷 روشن کردن دوربین'}
                </button>
              )}
            </>
          )}
          {(callState === 'listening' || callState === 'speaking') && !liveModel.includes('translate') && (
            <>
              <input className="inp" style={{ flex: 1, minWidth: 220 }} placeholder="ارسال پیام متنی در نشست زنده…"
                     value={testText} onChange={e => setTestText(e.target.value)}
                     onKeyDown={e => {
                       if (e.key === 'Enter' && testText.trim() && wsRef.current?.readyState === WebSocket.OPEN) {
                         wsRef.current.send(JSON.stringify({ type: 'text', text: testText.trim() }));
                         setTurns(p => [...p, { r: 'شما', t: testText.trim() }]);
                         setTestText('');
                       }
                     }} />
            </>
          )}
        </div>
        {(userSub || aiSub || turns.length > 0) && (
          <div style={{ marginTop: 12, padding: 10, borderRadius: 8, background: 'var(--c-bg2, #f6f8fa)', display: 'grid', gap: 6 }}>
            {turns.map((x, idx) => (
              <div key={idx} style={{ fontSize: 13 }}><b>{x.r}: </b><span>{x.t}</span></div>
            ))}
            {userSub && <div style={{ fontSize: 13, color: 'var(--acc)' }}><b>شما (زنده…): </b>{userSub}</div>}
            {aiSub && <div style={{ fontSize: 13, color: 'var(--ok)' }}><b>هوشیار (زنده…): </b>{aiSub}</div>}
          </div>
        )}
      </div>

      {/* 📞 م9.2 — دستیار ویس‌چت گروه تلگرام (Userbot / MTProto) */}
      <VcAssistantPanel />
    </>
  );
}

function _toAsciiDigits(s) {
  return String(s || '').replace(/[۰-۹٠-٩]/g, d => {
    const code = d.charCodeAt(0);
    if (code >= 0x06F0 && code <= 0x06F9) return String(code - 0x06F0);
    if (code >= 0x0660 && code <= 0x0669) return String(code - 0x0660);
    return d;
  });
}

/* 📞 م9.2 / م9.3 — پنل مدیریت و ویزارد اتصال «اکانت دستیار ویس‌چت گروه تلگرام» (Pyrogram + PyTgCalls) */
function VcAssistantPanel() {
  const [st, setSt] = useState(null);
  const [apiId, setApiId] = useState('');
  const [apiHash, setApiHash] = useState('');
  const [phone, setPhone] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState('');
  const [twoFaPass, setTwoFaPass] = useState('');
  const [needs2Fa, setNeeds2Fa] = useState(false);
  const [manualSession, setManualSession] = useState('');
  const [showManual, setShowManual] = useState(false);
  const [groupChatId, setGroupChatId] = useState('');
  const [busy, setBusy] = useState(false);
  const [panelErr, setPanelErr] = useState('');

  const load = async () => {
    try {
      const r = await api.aiVcAssistantStatus();
      setSt(r);
      if (r.api_id && !apiId) setApiId(String(r.api_id));
    } catch (_) {}
  };
  useEffect(() => { load(); }, []);

  const sendCode = async () => {
    setBusy(true);
    setPanelErr('');
    try {
      const r = await api.aiVcAssistantSendCode({
        api_id: apiId ? Number(_toAsciiDigits(apiId)) : (st?.api_id ? Number(st.api_id) : null),
        api_hash: apiHash.trim(),
        phone: _toAsciiDigits(phone).trim(),
      });
      setOtpSent(true);
      setNeeds2Fa(false);
      toast(r.message || 'کد تایید به تلگرام ارسال شد ✅');
      await load();
    } catch (e) {
      const msg = errText(e);
      setPanelErr(msg);
      toast(msg, 'err');
    }
    setBusy(false);
  };

  const verifyCode = async () => {
    setBusy(true);
    setPanelErr('');
    try {
      const r = await api.aiVcAssistantVerifyCode({
        code: _toAsciiDigits(otpCode).trim(),
        password: twoFaPass,
      });
      if (r.needs_2fa) {
        setNeeds2Fa(true);
        setPanelErr(r.message || 'رمز تایید دو مرحله‌ای (2FA) را وارد کنید.');
        toast(r.message, 'err');
      } else {
        toast(r.message || 'اکانت دستیار متصل شد ✅');
        setOtpSent(false); setNeeds2Fa(false); setOtpCode(''); setTwoFaPass('');
        await load();
      }
    } catch (e) {
      const msg = errText(e);
      setPanelErr(msg);
      toast(msg, 'err');
    }
    setBusy(false);
  };

  const saveManual = async () => {
    setBusy(true);
    setPanelErr('');
    try {
      await api.aiVcAssistantSave({
        api_id: apiId ? Number(_toAsciiDigits(apiId)) : undefined,
        api_hash: apiHash.trim() || undefined,
        session_string: manualSession.trim() || undefined,
      });
      setManualSession('');
      toast('مشخصات دستیار ویس‌چت گروه ذخیره شد ✅');
      await load();
    } catch (e) {
      const msg = errText(e);
      setPanelErr(msg);
      toast(msg, 'err');
    }
    setBusy(false);
  };

  const joinGroup = async () => {
    if (!groupChatId.trim()) return;
    setBusy(true);
    setPanelErr('');
    try {
      const r = await api.aiVcAssistantJoin({ chat_id: _toAsciiDigits(groupChatId).trim() });
      toast(`هوشیار وارد ویس‌چت گروه ${r.title || r.chat_id} شد 🎙`);
      await load();
    } catch (e) {
      const msg = errText(e);
      setPanelErr(msg);
      toast(msg, 'err');
    }
    setBusy(false);
  };

  const leaveGroup = async (cid) => {
    setBusy(true);
    setPanelErr('');
    try {
      await api.aiVcAssistantLeave({ chat_id: cid });
      toast('هوشیار از ویس‌چت گروه خارج شد 📴');
      await load();
    } catch (e) {
      const msg = errText(e);
      setPanelErr(msg);
      toast(msg, 'err');
    }
    setBusy(false);
  };

  const canSendCode = !busy && Boolean(apiId || st?.api_id) && Boolean(apiHash.trim() || st?.has_api_hash) && Boolean(phone.trim());

  return (
    <div className="panel panel-pad" style={{ marginTop: 14 }}>
      <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <b>📞 دستیار ویس‌چت گروه تلگرام (ورود مستقیم هوشیار به Group Voice Chat)</b>
        <B kind={st?.configured ? 'ok' : 'warn'}>
          {st?.configured
            ? `متصل${st?.assistant?.username ? ` (@${st.assistant.username})` : (st?.assistant?.first_name ? ` (${st.assistant.first_name})` : '')}`
            : 'نیازمند تنظیم اکانت دستیار'}
        </B>
      </div>
      <div className="muted" style={{ marginTop: 6, fontSize: 'var(--fs-caption)' }}>
        چون تلگرام به ربات‌های عادی اجازه ورود مستقیم به ویس‌چت گروهی (<code>phone.JoinGroupCall</code>) را نمی‌دهد، یک اکانت تلگرام دستیار با <code>API_ID</code> و <code>API_HASH</code> (از <a href="https://my.telegram.org" target="_blank" rel="noreferrer">my.telegram.org</a>) متصل کنید تا وقتی در گروه ویس‌چت باز می‌شود یا دستور <code>/joinlive</code> زده می‌شود، هوشیار مستقیم وارد ویس‌چت گروه شود و با بچه‌ها زنده صحبت کند.
      </div>

      {panelErr && (
        <div style={{ marginTop: 10, padding: '8px 12px', borderRadius: 8, background: 'rgba(220,38,38,0.08)', border: '1px solid var(--c-bad, #d24)', color: 'var(--c-bad, #d24)', fontSize: 13 }}>
          ⚠️ {panelErr}
        </div>
      )}

      {/* گام ۱ و ۲: ویزارد لاگین مستقیم با کد تلگرام */}
      <div className="grid g3" style={{ gap: 10, marginTop: 12 }}>
        <label className="fld">
          <span>۱. Telegram API_ID (از my.telegram.org)</span>
          <input className="inp" dir="ltr" placeholder="مثلاً 12345678" value={apiId} onChange={e => setApiId(_toAsciiDigits(e.target.value).replace(/\D/g, ''))} />
        </label>
        <label className="fld">
          <span>۲. Telegram API_HASH {st?.has_api_hash && <B kind="ok">ذخیره شده</B>}</span>
          <input className="inp" type="password" dir="ltr" placeholder={st?.has_api_hash ? 'ذخیره شده (فقط در صورت تغییر پر کنید)…' : '32 کاراکتر هگزادسیمال…'} value={apiHash} onChange={e => setApiHash(e.target.value)} />
        </label>
        <label className="fld">
          <span>۳. شماره موبایل اکانت دستیار (با پیش‌شماره یا 09)</span>
          <input className="inp" dir="ltr" placeholder="+98912... یا 0912..." value={phone} onChange={e => setPhone(_toAsciiDigits(e.target.value))} />
        </label>
      </div>

      <div className="row" style={{ marginTop: 10, gap: 8, flexWrap: 'wrap' }}>
        <button className="btn primary sm" disabled={!canSendCode} onClick={sendCode}>
          📲 ارسال کد تایید تلگرام (ساخت خودکار Session)
        </button>
        <button className="btn sm" onClick={() => setShowManual(v => !v)}>
          {showManual ? '▲ بستن ورود دستی Session' : '🔑 وارد کردن دستی Session String پایروگرام'}
        </button>
      </div>

      {otpSent && (
        <div style={{ marginTop: 12, padding: 12, borderRadius: 10, border: '1px solid var(--acc)', background: 'rgba(59,130,246,0.06)' }}>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <input className="inp" dir="ltr" placeholder="کد ۵ رقمی تلگرام…" value={otpCode} onChange={e => setOtpCode(_toAsciiDigits(e.target.value))} />
            <input className="inp" type="password" dir="ltr"
                   style={needs2Fa ? { borderColor: 'var(--c-bad, #d24)' } : undefined}
                   placeholder={needs2Fa ? '⚠️ رمز تایید دو مرحله‌ای (2FA) الزامی…' : 'رمز دو مرحله‌ای (2FA) — در صورت فعال بودن'}
                   value={twoFaPass} onChange={e => setTwoFaPass(e.target.value)} />
            <button className="btn primary sm" disabled={busy || (!otpCode.trim() && !needs2Fa)} onClick={verifyCode}>
              ✅ تایید و اتصال اکانت دستیار
            </button>
          </div>
        </div>
      )}

      {showManual && (
        <div style={{ marginTop: 12, padding: 12, borderRadius: 10, border: '1px solid var(--c-line, #ddd)' }}>
          <div className="muted" style={{ marginBottom: 6, fontSize: 'var(--fs-caption)' }}>
            اگر از قبل <code>session_string</code> پایروگرام دارید، اینجا وارد کنید (به‌صورت رمزنگاری‌شده با Fernet در دیتابیس ذخیره می‌شود):
          </div>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <input className="inp" style={{ flex: 1, direction: 'ltr' }} placeholder="Pyrogram Session String..." value={manualSession} onChange={e => setManualSession(e.target.value)} />
            <button className="btn primary sm" disabled={busy} onClick={saveManual}>💾 ذخیره مشخصات</button>
          </div>
        </div>
      )}

      {/* ورود دستی به ویس‌چت یک گروه از پنل وب + لیست ویس‌چت‌های فعال */}
      {st?.configured && (
        <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--c-line, #eee)' }}>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <input className="inp" dir="ltr" style={{ minWidth: 220 }} placeholder="Chat ID گروه (مثلاً -1001234567890)"
                   value={groupChatId} onChange={e => setGroupChatId(e.target.value)} />
            <button className="btn primary sm" disabled={busy || !groupChatId.trim()} onClick={joinGroup}>
              📞 ورود هوشیار به ویس‌چت این گروه
            </button>
          </div>
          {(st.active_calls || []).length > 0 && (
            <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
              {st.active_calls.map(c => (
                <div key={c.chat_id} className="row" style={{ justifyContent: 'space-between', padding: '6px 10px', borderRadius: 8, background: 'var(--c-bg2, #f6f8fa)' }}>
                  <span>🎙 <b>{c.title}</b> (<code dir="ltr">{c.chat_id}</code>) · مدل: <code>{c.model}</code> · ⏱ {c.elapsed_sec}s</span>
                  <button className="btn danger sm" disabled={busy} onClick={() => leaveGroup(c.chat_id)}>📴 خروج</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
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
  /* ⭐ م8 — صداهای TTS + تستِ سلامتِ مدل‌های گفتگو + کاتالوگ تصویر گوگل */
  const [tts, setTts] = useState(null);         // {voices, models, modes}
  const [imgMeta, setImgMeta] = useState(null); // {models, current_model, ...}
  const [probeBusy, setProbeBusy] = useState(false);
  useEffect(() => {
    api.aiTtsVoices().then(setTts).catch(() => {});
    api.aiImageModels().then(setImgMeta).catch(() => {});
  }, []);
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
        system_prompt: f.system_prompt,
        voice_system_prompt: f.voice_system_prompt || '',
        disabled_message: f.disabled_message || '',
        image_enabled: f.image_enabled !== false,
        image_provider: 'gemini',
        image_model: (f.image_model || 'gemini-3.1-flash-lite-image').trim(),
        image_daily_limit: Number(f.image_daily_limit ?? 5),
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
          {/* ⭐ م8.4 — پیکربندی ساخت تصویر هوشیار (مدل‌های گوگل Gemini) */}
          <label className="fld"><span>🎨 ساخت تصویر در هوشیار</span>
            <div className="row" style={{ marginTop: 4 }}>
              <Switch on={f.image_enabled !== false} onChange={v => set('image_enabled', v)} />
              <span>{f.image_enabled !== false ? 'فعال برای کاربران' : 'غیرفعال'}</span>
            </div>
          </label>
          <label className="fld"><span>🤖 مدل ساخت تصویر هوشیار (گوگل Gemini)</span>
            <select className="inp" style={{ direction: 'ltr' }}
                    value={f.image_model || 'gemini-3.1-flash-lite-image'}
                    onChange={e => set('image_model', e.target.value)}>
              {(imgMeta?.models || [
                { id: 'gemini-3.1-flash-lite-image', label: '⚡ gemini-3.1-flash-lite-image', free: true },
                { id: 'gemini-2.5-flash-image', label: '🍌 gemini-2.5-flash-image', free: true },
                { id: 'gemini-nano-banana-2.1', label: '🍌 gemini-nano-banana-2.1', free: true },
              ]).map(m => (
                <option key={m.id} value={m.id}>
                  {m.health_ok === true ? '🟢 ' : m.health_ok === false ? '🔴 ' : ''}{m.id}{m.free ? ' [رایگان]' : ''}
                </option>
              ))}
            </select></label>
          <label className="fld"><span>🎯 سهمیه روزانه ساخت تصویر (هر کاربر)</span>
            <input className="inp" type="number" min="0" max="500" value={f.image_daily_limit ?? 5}
                   onChange={e => set('image_daily_limit', e.target.value)} /></label>
          <label className="fld"><span>🖼 رزولوشن پیش‌فرض تصویر</span>
            <select className="inp" value={f.image_size || '1K'} onChange={e => set('image_size', e.target.value)}>
              <option value="1K">1K (سریع/ارزان — سازگار با همه مدل‌های رایگان گوگل)</option>
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
        <b>پیام و پرامپت‌ها (متنی و صوتی)</b>
        <div className="grid" style={{ gap: 10, marginTop: 12 }}>
          <label className="fld"><span>📝 پرامپت چت متنی (Text System Prompt — ۲۰ تا ۲۰هزار کاراکتر)</span>
            <textarea className="inp" rows={6} style={{ resize: 'vertical' }} value={f.system_prompt}
                      onChange={e => set('system_prompt', e.target.value)} /></label>
          <label className="fld">
            <span className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
              <span>🎙 پرامپت ویس‌چت زنده و پاسخ صوتی (Voice System Prompt — لحن صمیمی و محاوره‌ای)</span>
              {cfg.default_voice_system_prompt && (
                <button type="button" className="btn sm" onClick={() => set('voice_system_prompt', cfg.default_voice_system_prompt)}>
                  🔄 بازگردانی به پیش‌فرض صمیمی
                </button>
              )}
            </span>
            <textarea className="inp" rows={7} style={{ resize: 'vertical' }} value={f.voice_system_prompt || ''}
                      onChange={e => set('voice_system_prompt', e.target.value)} /></label>
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
