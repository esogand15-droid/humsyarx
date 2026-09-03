import React, { useCallback, useEffect, useState } from 'react';
import { api, errText } from './api.js';
import { Loading, ErrorState, FaDateTime, SectionHeader, B } from './ui.jsx';

// 🩺 مرکز سلامت سامانه
//
// مصرف‌کننده‌ی `/api/health/deep` — این endpoint از قبل در backend وجود
// داشت و هیچ‌جای پنل صدا زده نمی‌شد (endpoint یتیم). هیچ متریک تازه‌ای
// اینجا اختراع نمی‌شود؛ فقط همان چیزی که سرور واقعاً می‌دهد نمایش داده
// می‌شود. هر فیلدی که سرور نفرستد «—» می‌ماند، نه صفرِ گمراه‌کننده.

const fa = (n) => (n === null || n === undefined || n === '')
  ? '—'
  : Number(n).toLocaleString('fa-IR');

// وضعیت → رنگ توکنی. هیچ hex خامی؛ فقط توکن‌های موجود.
const TONE = {
  ok:       { tint: 'var(--ok, #16a34a)',   icon: '🟢', label: 'سالم' },
  degraded: { tint: 'var(--warn, #d97706)', icon: '🟡', label: 'نیمه‌فعال' },
  down:     { tint: 'var(--bad, #dc2626)',  icon: '🔴', label: 'خطا' },
  unknown:  { tint: 'var(--muted, #64748b)', icon: '⚪️', label: 'نامشخص' },
};

function toneOf(state) {
  if (state === true || state === 'ok' || state === 'ready') return TONE.ok;
  if (state === false || state === 'down') return TONE.down;
  if (state === 'degraded' || state === 'not_ready') return TONE.degraded;
  return TONE.unknown;
}

function uptimeText(seconds) {
  const s = Number(seconds);
  if (!Number.isFinite(s) || s < 0) return '—';
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${fa(d)} روز و ${fa(h)} ساعت`;
  if (h) return `${fa(h)} ساعت و ${fa(m)} دقیقه`;
  if (m) return `${fa(m)} دقیقه`;
  return `${fa(Math.floor(s))} ثانیه`;
}

function HealthCard({ icon, title, state, lines = [], error }) {
  const tone = toneOf(state);
  return (
    <div
      style={{
        border: '1px solid var(--bd, #e2e8f0)',
        borderRadius: 'var(--r2, 12px)',
        padding: 'var(--sp3, 14px)',
        background: 'var(--card, #fff)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--sp1, 6px)',
        borderInlineStartWidth: 4,
        borderInlineStartColor: tone.tint,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp1, 6px)' }}>
        <span aria-hidden="true">{icon}</span>
        <strong style={{ fontSize: 'var(--fs2, 14px)' }}>{title}</strong>
        <span style={{ marginInlineStart: 'auto', fontSize: 'var(--fs1, 12px)', color: tone.tint }}>
          {tone.icon} {tone.label}
        </span>
      </div>
      {lines.filter(Boolean).map(([k, v]) => (
        <div
          key={k}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: 'var(--fs1, 12px)',
            color: 'var(--fg2, #475569)',
          }}
        >
          <span>{k}</span>
          <span style={{ fontVariantNumeric: 'tabular-nums' }}>{v}</span>
        </div>
      ))}
      {error ? (
        <div
          role="status"
          style={{
            fontSize: 'var(--fs1, 12px)',
            color: 'var(--bad, #dc2626)',
            wordBreak: 'break-word',
          }}
        >
          {error}
        </div>
      ) : null}
    </div>
  );
}

export default function HealthCenter() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [at, setAt] = useState(null);

  const load = useCallback(async () => {
    setBusy(true);
    setErr('');
    try {
      const r = await api.healthDeep();
      setData(r);
      setAt(new Date().toISOString());
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (err && !data) return <ErrorState error={err} onRetry={load} />;
  if (!data) return <Loading rows={3} variant="cards" label="در حال سنجش سلامت" />;

  const bot = data.bot || {};
  const hb = bot.heartbeat || {};
  const mongo = data.mongo || {};
  const boot = data.bootstrap || {};
  const routes = data.routes || {};
  const miniapp = data.miniapp || {};
  const webadmin = data.webadmin || {};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp3, 14px)' }}>
      <SectionHeader
        title="🩺 سلامت سامانه"
        description="دیاگنوستیک عمیق — هر بخش مستقل سنجیده می‌شود و خطای یکی بقیه را متوقف نمی‌کند."
        actions={
          <button type="button" className="btn" onClick={load} disabled={busy}>
            {busy ? 'در حال بررسی…' : '🔄 بررسی مجدد'}
          </button>
        }
      />

      <div style={{ display: 'flex', gap: 'var(--sp2, 10px)', flexWrap: 'wrap', alignItems: 'center' }}>
        <B kind={data.status === 'ok' ? 'ok' : 'warn'}>
          وضعیت کلی: {toneOf(data.status).label}
        </B>
        <span style={{ fontSize: 'var(--fs1, 12px)', color: 'var(--fg2, #475569)' }}>
          نسخه {data.version || '—'} • آپ‌تایم {uptimeText(data.uptime_s)}
        </span>
        {at ? (
          <span style={{ marginInlineStart: 'auto', fontSize: 'var(--fs1, 12px)', color: 'var(--fg2, #475569)' }}>
            آخرین بررسی: <FaDateTime value={at} />
          </span>
        ) : null}
      </div>

      {err ? (
        <div role="alert" style={{ fontSize: 'var(--fs1, 12px)', color: 'var(--bad, #dc2626)' }}>
          بروزرسانی ناموفق بود ({err}) — داده‌های نمایش‌داده‌شده مربوط به بررسی قبلی است.
        </div>
      ) : null}

      <div
        style={{
          display: 'grid',
          gap: 'var(--sp2, 10px)',
          gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
        }}
      >
        <HealthCard
          icon="⚙️"
          title="API"
          state={data.api?.ok}
          lines={[['شناسه فرایند', fa(data.api?.pid)]]}
        />

        <HealthCard
          icon="🗄"
          title="MongoDB"
          state={mongo.ok}
          error={mongo.error}
          lines={[['تأخیر پینگ', mongo.ping_ms == null ? '—' : `${fa(mongo.ping_ms)} ms`]]}
        />

        <HealthCard
          icon="🤖"
          title="ربات تلگرام"
          state={bot.process_ok}
          error={bot.note}
          lines={[
            ['شناسه فرایند', fa(bot.process_pid)],
            ['ضربان دیده‌شده', hb.seen ? 'بله' : 'خیر'],
            hb.at ? ['آخرین ضربان', <FaDateTime key="hb" value={hb.at} />] : null,
          ]}
        />

        <HealthCard
          icon="🚀"
          title="راه‌اندازی"
          state={boot.ready}
          lines={Object.entries(boot)
            .filter(([k]) => k !== 'ready')
            .slice(0, 4)
            .map(([k, v]) => [k, typeof v === 'boolean' ? (v ? 'بله' : 'خیر') : String(v ?? '—')])}
        />

        <HealthCard
          icon="📱"
          title="Mini App"
          state={miniapp.built}
          lines={Object.entries(miniapp)
            .filter(([k]) => k !== 'built')
            .slice(0, 3)
            .map(([k, v]) => [k, typeof v === 'boolean' ? (v ? 'بله' : 'خیر') : String(v ?? '—')])}
        />

        <HealthCard
          icon="🖥"
          title="وب‌ادمین"
          state={webadmin.built}
          lines={Object.entries(webadmin)
            .filter(([k]) => k !== 'built')
            .slice(0, 3)
            .map(([k, v]) => [k, typeof v === 'boolean' ? (v ? 'بله' : 'خیر') : String(v ?? '—')])}
        />

        <HealthCard
          icon="🧭"
          title="فهرست مسیرها"
          state={routes.routes_match_baseline}
          lines={[
            ['عملیات OpenAPI', fa(routes.openapi_operations)],
            ['شیء مسیر زیر /api', fa(routes.api_route_objects)],
            ['خط‌مبنا', fa(routes.baseline_expected)],
          ]}
          error={
            routes.routes_match_baseline === false
              ? 'تعداد عملیات با خط‌مبنا نمی‌خواند — یا API عمداً تغییر کرده (خط‌مبنا را به‌روز کنید) یا مسیری ناخواسته اضافه/حذف شده است.'
              : ''
          }
        />
      </div>
    </div>
  );
}
