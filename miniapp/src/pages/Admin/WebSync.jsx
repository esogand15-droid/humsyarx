import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import api from '../../lib/api';
import Header from '../../components/layout/Header';
import PageError from '../../components/shared/PageError';
import EmptyState from '../../components/shared/EmptyState';
import { Spinner } from '../../components/shared/Loading';
import { faNum } from '../../lib/format';
import { haptic } from '../../lib/telegram';
import { useUIStore } from '../../stores/uiStore';

/* میزهای هم‌تراز با پنل وب.
   همان کلاینت مینی‌اپ (X-Init-Data) به /api/web-admin و /api/ring می‌زند.
   هیچ صفحه‌ی قدیمی اینجا جایگزین نمی‌شود. */

const fa = (value) => faNum(value ?? '');
const nfa = (value) => faNum(Number(value || 0).toLocaleString('en-US'));
const toman = (value) => `${nfa(value)} تومان`;

function when(value) {
  if (!value) return '—';
  return fa(String(value).replace('T', ' ').replace('+00:00', '').slice(0, 16));
}

export function apiError(error, fallback = 'انجام نشد.') {
  const status = error?.response?.status;
  const data = error?.response?.data;
  const detail = data?.detail ?? data?.message ?? data;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail === 'object') {
    if (typeof detail.message === 'string' && detail.message.trim()) return detail.message;
    if (typeof detail.msg === 'string' && detail.msg.trim()) return detail.msg;
  }
  if (status === 403) return 'این کار برای نقش شما مجاز نیست.';
  if (status === 404) return 'مورد پیدا نشد.';
  return fallback;
}

export function deskPath(go) {
  const raw = String(go || '');
  if (raw.includes('tab=reconcile') || raw.includes('tab=wallets')) return '/admin/finance';
  if (raw.includes('tab=import')) return '/admin/content/url-import';
  if (raw.includes('focus=dlq')) return '/admin/system?focus=dlq';
  const path = raw.split('?')[0];
  return {
    '/subscriptions': '/admin/subscription',
    '/tickets': '/admin/tickets',
    '/questions': '/admin/questions',
    '/users': '/admin/users',
    '/content': '/admin/content/reports',
    '/system': '/admin/system',
    '/operations': '/admin/operations',
  }[path] || '/admin';
}

function Desk({ title, subtitle, onRefresh, refreshing, children }) {
  return (
    <>
      <Header
        title={title}
        subtitle={subtitle}
        back
        backTo="/admin"
        onRefresh={onRefresh}
        refreshing={refreshing}
      />
      <main className="page">{children}</main>
    </>
  );
}

function Chips({ value, options, onChange }) {
  return (
    <div className="chip-row">
      {options.map((item) => (
        <button
          key={item.id}
          type="button"
          className={value === item.id ? 'chip chip--active' : 'chip'}
          onClick={() => {
            haptic('light');
            onChange(item.id);
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

function Kpis({ items }) {
  return (
    <div className="grid2" style={{ marginBottom: 12 }}>
      {items.map((item) => (
        <article key={item.label} className="card kpi">
          <span className="kpi__icon" style={{ background: item.soft || 'var(--soft-acc)' }}>
            {item.icon}
          </span>
          <b className="kpi__value">{item.value}</b>
          <span className="kpi__label">{item.label}</span>
        </article>
      ))}
    </div>
  );
}

function Armed({ label, confirmLabel = 'تأیید و انجام', danger = false, busy = false, onConfirm }) {
  const [armed, setArmed] = useState(false);
  if (!armed) {
    return (
      <button type="button" className={danger ? 'btn btn-d' : 'btn btn-g'} onClick={() => setArmed(true)}>
        {label}
      </button>
    );
  }
  return (
    <span style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
      <button type="button" className={danger ? 'btn btn-d' : 'btn btn-p'} disabled={busy} onClick={onConfirm}>
        {busy ? <Spinner size={14} /> : confirmLabel}
      </button>
      <button type="button" className="btn btn-dark" onClick={() => setArmed(false)}>انصراف</button>
    </span>
  );
}

function severityBadge(severity) {
  if (severity === 'critical' || severity === 'high') return 'badge b-red';
  if (severity === 'warning') return 'badge b-yel';
  if (severity === 'info') return 'badge b-gray';
  return 'badge b-acc';
}

function useToast() {
  return useUIStore((state) => state.toast);
}

function AttentionDesk() {
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [reason, setReason] = useState('');
  const [hours, setHours] = useState(24);
  const [openKey, setOpenKey] = useState('');

  const query = useQuery({
    queryKey: ['wa-attention'],
    queryFn: () => api.get('/api/web-admin/attention').then((r) => r.data),
  });
  const dismissed = useQuery({
    queryKey: ['wa-attention-dismissals'],
    queryFn: () => api.get('/api/web-admin/attention/dismissals').then((r) => r.data),
  });

  const dismiss = useMutation({
    mutationFn: (body) => api.post('/api/web-admin/attention/dismiss', body),
    onSuccess: () => {
      toast('هشدار تا مدت انتخاب‌شده کنار گذاشته شد.', 'success');
      setReason('');
      setOpenKey('');
      qc.invalidateQueries({ queryKey: ['wa-attention'] });
      qc.invalidateQueries({ queryKey: ['wa-attention-dismissals'] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });
  const restore = useMutation({
    mutationFn: (key) => api.post('/api/web-admin/attention/restore', { key }),
    onSuccess: () => {
      toast('هشدار برگشت.', 'success');
      qc.invalidateQueries({ queryKey: ['wa-attention'] });
      qc.invalidateQueries({ queryKey: ['wa-attention-dismissals'] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });

  const items = query.data?.items || [];
  const hot = items.filter((item) => Number(item.count) > 0);
  const calm = items.filter((item) => !Number(item.count));

  return (
    <Desk
      title="نیازمند اقدام"
      subtitle="همان صف پنل وب، داخل مینی‌اپ"
      onRefresh={() => { query.refetch(); dismissed.refetch(); }}
      refreshing={query.isRefetching}
    >
      {query.isLoading ? <Spinner /> : null}
      {query.isError ? <PageError text={apiError(query.error, 'صف اقدام دریافت نشد.')} onRetry={query.refetch} /> : null}
      {!query.isLoading && !query.isError ? (
        <>
          <p style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)', marginTop: 0 }}>
            فقط کارهایی دیده می‌شود که نقش شما اجازه دیدنشان را دارد. آخرین بررسی: {when(query.data?.checked_at)}
          </p>
          {hot.length === 0 ? (
            <EmptyState icon="🌿">الان صف خالی است. کار معوقی برای نقش شما نمانده.</EmptyState>
          ) : hot.map((item) => (
            <article key={item.key} className="card" style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <b style={{ flex: 1 }}>{item.icon} {item.label}</b>
                <span className={severityBadge(item.severity)}>{nfa(item.count)}</span>
              </div>
              <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)', marginTop: 6 }}>
                تازه‌ترین مورد: {when(item.timestamp)}
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                <button type="button" className="btn btn-p" onClick={() => navigate(deskPath(item.go))}>
                  برو به میز
                </button>
                <button type="button" className="btn btn-dark" onClick={() => setOpenKey(openKey === item.key ? '' : item.key)}>
                  کنار گذاشتن
                </button>
              </div>
              {openKey === item.key ? (
                <div style={{ marginTop: 10 }}>
                  <label className="fld-label">دلیل، حداقل ۳ حرف</label>
                  <input className="inp" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} />
                  <div className="chip-row" style={{ marginTop: 8 }}>
                    {[
                      [24, 'یک روز'],
                      [72, 'سه روز'],
                      [168, 'یک هفته'],
                      [0, 'دائم'],
                    ].map(([id, label]) => (
                      <button key={id} type="button" className={hours === id ? 'chip chip--active' : 'chip'} onClick={() => setHours(id)}>
                        {label}
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    className="btn btn-d"
                    disabled={reason.trim().length < 3 || dismiss.isPending}
                    onClick={() => dismiss.mutate({ key: item.key, reason: reason.trim(), dismiss_hours: hours })}
                  >
                    ثبت کنارگذاشتن
                  </button>
                </div>
              ) : null}
            </article>
          ))}
          {calm.length ? (
            <p style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
              آرام: {calm.map((item) => item.label).join(' · ')}
            </p>
          ) : null}
          {(dismissed.data?.items || []).length ? (
            <section>
              <h3 className="sec-title">کنار گذاشته‌شده‌ها</h3>
              {dismissed.data.items.map((item) => (
                <div key={item.key} className="card" style={{ marginBottom: 8 }}>
                  <b>{item.key}</b>
                  <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>{item.reason}</div>
                  <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>تا {when(item.dismissed_until)}</div>
                  <button type="button" className="btn btn-g" style={{ marginTop: 8 }} disabled={restore.isPending} onClick={() => restore.mutate(item.key)}>
                    برگرداندن
                  </button>
                </div>
              ))}
            </section>
          ) : null}
        </>
      ) : null}
    </Desk>
  );
}

function OperationsDesk() {
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState('work');
  const [kind, setKind] = useState('');
  const [repair, setRepair] = useState({ name: '', type: 'pdf', description: '' });

  const work = useQuery({
    queryKey: ['wa-my-work'],
    queryFn: () => api.get('/api/web-admin/operations/my-work').then((r) => r.data),
  });
  const alerts = useQuery({
    queryKey: ['wa-ops-alerts'],
    queryFn: () => api.get('/api/web-admin/operations/alerts').then((r) => r.data),
    enabled: tab === 'alerts',
  });
  const quality = useQuery({
    queryKey: ['wa-quality'],
    queryFn: () => api.get('/api/web-admin/operations/data-quality').then((r) => r.data),
    enabled: tab === 'quality',
  });
  const items = useQuery({
    queryKey: ['wa-quality-items', kind],
    queryFn: () => api.get(`/api/web-admin/operations/data-quality/${kind}`).then((r) => r.data),
    enabled: tab === 'quality' && Boolean(kind),
  });

  const fix = useMutation({
    mutationFn: (target) => api.post(`/api/web-admin/operations/data-quality/${target}/fix`, { kind: target, confirm: true }),
    onSuccess: () => {
      toast('اصلاح امن انجام شد.', 'success');
      qc.invalidateQueries({ queryKey: ['wa-quality'] });
      qc.invalidateQueries({ queryKey: ['wa-quality-items'] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });
  const repairMut = useMutation({
    mutationFn: ({ id, body }) => api.post(`/api/web-admin/operations/data-quality/files_missing_metadata/${id}/repair`, body),
    onSuccess: () => {
      toast('متادیتا ذخیره شد.', 'success');
      qc.invalidateQueries({ queryKey: ['wa-quality-items'] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });

  const active = tab === 'work' ? work : tab === 'alerts' ? alerts : quality;
  const fixable = new Set(quality.data?.fixable || []);

  return (
    <Desk title="میز عملیات" subtitle="کار من، هشدار و کیفیت داده" onRefresh={() => active.refetch()} refreshing={active.isRefetching}>
      <Chips
        value={tab}
        onChange={setTab}
        options={[
          { id: 'work', label: 'کار من' },
          { id: 'alerts', label: 'هشدارها' },
          { id: 'quality', label: 'کیفیت داده' },
        ]}
      />
      {active.isLoading ? <Spinner /> : null}
      {active.isError ? (
        <PageError
          text={apiError(active.error, 'میز عملیات باز نشد.')}
          detail={active.error?.response?.status === 403 ? 'کیفیت داده فقط با مجوز system.manage باز است.' : undefined}
          onRetry={active.refetch}
        />
      ) : null}

      {tab === 'work' && work.data ? (work.data.tasks || []).map((task) => (
        <button key={task.key} type="button" className="card card-tap" style={{ width: '100%', textAlign: 'right', marginBottom: 8 }} onClick={() => navigate(deskPath(task.go))}>
          <b>{task.icon} {task.label}</b>
          <div style={{ color: 'var(--txm)', marginTop: 4 }}>{task.empty ? 'خالی' : `${nfa(task.count)} مورد · کهنه‌ترین ${when(task.oldest_at)}`}</div>
        </button>
      )) : null}

      {tab === 'alerts' && alerts.data ? (
        (alerts.data.alerts || []).length === 0
          ? <EmptyState icon="🌿">هشدار بازی نیست.</EmptyState>
          : alerts.data.alerts.map((item) => (
            <button key={item.key} type="button" className="card card-tap" style={{ width: '100%', textAlign: 'right', marginBottom: 8 }} onClick={() => navigate(deskPath(item.go))}>
              <b>{item.icon} {item.label}</b>
              <span className={severityBadge(item.severity)} style={{ marginRight: 8 }}>{nfa(item.count)}</span>
            </button>
          ))
      ) : null}

      {tab === 'quality' && quality.data ? (
        <>
          <p style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
            فقط یتیم‌های بی‌والد و ارجاع نقش ناموجود اصلاح خودکار دارند. موارد هویتی و مالی دستی می‌مانند.
          </p>
          {(quality.data.items || []).map((item) => (
            <article key={item.kind} className="card" style={{ marginBottom: 8 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <b style={{ flex: 1 }}>{item.label}</b>
                <span className={severityBadge(item.severity)}>{item.available ? nfa(item.count) : '؟'}</span>
              </div>
              <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)', marginTop: 4 }}>{item.suggestion}</div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                <button type="button" className="btn btn-g" onClick={() => setKind(item.kind)}>نمونه‌ها</button>
                {fixable.has(item.kind) && Number(item.count) > 0 ? (
                  <Armed danger label="اصلاح امن" busy={fix.isPending} onConfirm={() => fix.mutate(item.kind)} />
                ) : null}
              </div>
            </article>
          ))}
          {kind && items.isLoading ? <Spinner /> : null}
          {kind && items.data ? (
            <section>
              <h3 className="sec-title">نمونه‌های {kind}</h3>
              {(items.data.items || []).length === 0 ? <EmptyState icon="✅">موردی نیست.</EmptyState> : null}
              {(items.data.items || []).map((row) => (
                <article key={row.id || row.technical} className="card" style={{ marginBottom: 8 }}>
                  <b>{row.title || row.reason}</b>
                  <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>{row.context}</div>
                  {kind === 'files_missing_metadata' ? (
                    <div style={{ marginTop: 8 }}>
                      <input className="inp" placeholder="نام" value={repair.name} onChange={(e) => setRepair({ ...repair, name: e.target.value })} />
                      <select className="inp" style={{ marginTop: 6 }} value={repair.type} onChange={(e) => setRepair({ ...repair, type: e.target.value })}>
                        {['video', 'ppt', 'pdf', 'note', 'test', 'voice'].map((type) => <option key={type} value={type}>{type}</option>)}
                      </select>
                      <input className="inp" style={{ marginTop: 6 }} placeholder="توضیح" value={repair.description} onChange={(e) => setRepair({ ...repair, description: e.target.value })} />
                      <button type="button" className="btn btn-p" style={{ marginTop: 8 }} disabled={repairMut.isPending} onClick={() => repairMut.mutate({ id: row.id, body: repair })}>
                        ذخیره متادیتا
                      </button>
                    </div>
                  ) : null}
                </article>
              ))}
            </section>
          ) : null}
        </>
      ) : null}
    </Desk>
  );
}

const Q_STATUS = [
  { id: 'pending', label: 'در انتظار' },
  { id: 'needs_changes', label: 'نیاز به اصلاح' },
  { id: 'approved', label: 'تأییدشده' },
  { id: 'rejected', label: 'ردشده' },
  { id: 'all', label: 'همه' },
];
const DIFF_FA = { easy: 'آسان', medium: 'متوسط', hard: 'سخت' };

function QuestionsDesk() {
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState('list');
  const [status, setStatus] = useState('pending');
  const [q, setQ] = useState('');
  const [applied, setApplied] = useState('');
  const [skip, setSkip] = useState(0);
  const [openId, setOpenId] = useState('');
  const [reason, setReason] = useState('');
  const [picked, setPicked] = useState([]);
  const [draft, setDraft] = useState(null);
  const limit = 20;

  const list = useQuery({
    queryKey: ['wa-questions', status, applied, skip],
    queryFn: () => api.get('/api/web-admin/questions', {
      params: { status, q: applied || undefined, skip, limit },
    }).then((r) => r.data),
    enabled: tab === 'list',
  });
  const health = useQuery({
    queryKey: ['wa-q-health'],
    queryFn: () => api.get('/api/web-admin/questions/health', { params: { limit: 8 } }).then((r) => r.data),
  });
  const detail = useQuery({
    queryKey: ['wa-q-360', openId],
    queryFn: () => api.get(`/api/web-admin/questions/${openId}/360`).then((r) => r.data),
    enabled: Boolean(openId),
  });

  const act = useMutation({
    mutationFn: async ({ kind, id, note }) => {
      if (kind === 'delete') {
        return api.delete(`/api/web-admin/questions/${id}`, { params: { reason: note || '' } });
      }
      return api.post(`/api/web-admin/questions/${id}/${kind}`, { reason: note || '' });
    },
    onSuccess: () => {
      toast('ثبت شد.', 'success');
      setReason('');
      qc.invalidateQueries({ queryKey: ['wa-questions'] });
      qc.invalidateQueries({ queryKey: ['wa-q-health'] });
      if (openId) qc.invalidateQueries({ queryKey: ['wa-q-360', openId] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });
  const bulk = useMutation({
    mutationFn: (body) => api.post('/api/web-admin/questions/bulk', body),
    onSuccess: (res) => {
      const data = res.data || {};
      toast(`${nfa(data.done || 0)} سؤال انجام شد.`, data.failed?.length ? 'error' : 'success');
      setPicked([]);
      qc.invalidateQueries({ queryKey: ['wa-questions'] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });
  const save = useMutation({
    mutationFn: ({ id, body }) => api.patch(`/api/web-admin/questions/${id}`, body),
    onSuccess: () => {
      toast('سؤال ذخیره شد.', 'success');
      qc.invalidateQueries({ queryKey: ['wa-questions'] });
      qc.invalidateQueries({ queryKey: ['wa-q-360', openId] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });

  const rows = list.data?.questions || [];
  const total = Number(list.data?.total || 0);

  function toggle(id) {
    setPicked((curr) => (curr.includes(id) ? curr.filter((item) => item !== id) : [...curr, id]));
  }

  return (
    <Desk title="بانک سؤال" subtitle="بازبینی ساختاریافته، جدا از صف ساده محتوا" onRefresh={() => { list.refetch(); health.refetch(); }} refreshing={list.isRefetching}>
      <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)', marginTop: 0, marginBottom: 8 }}>
        صف ساده قبلی سر جایش است.
        {' '}
        <button type="button" className="btn btn-g" onClick={() => navigate('/admin/content/questions')}>بررسی ساده</button>
      </div>
      <Chips
        value={tab}
        onChange={setTab}
        options={[{ id: 'list', label: 'فهرست' }, { id: 'health', label: 'سلامت' }]}
      />
      {health.data?.summary?.needs_review ? (
        <div className="card" style={{ marginBottom: 10 }}>
          {nfa(health.data.summary.needs_review)} سؤال علامت سلامت گرفته‌اند. بدترین‌ها در زبانه سلامت است.
        </div>
      ) : null}

      {tab === 'health' ? (
        health.isError ? <PageError text={apiError(health.error)} onRetry={health.refetch} /> : (
          (health.data?.items || []).length === 0
            ? <EmptyState icon="💚">سؤال بیماری در نمونه فعلی نیست.</EmptyState>
            : (health.data.items || []).map((item) => (
              <article key={item.id} className="card" style={{ marginBottom: 8 }}>
                <b>امتیاز بیماری {nfa(item.score)}</b>
                <div>{item.question}</div>
                <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
                  {(item.signals || []).map((sig) => sig.label).join(' · ') || 'سیگنال خاصی نیست'}
                </div>
                <button type="button" className="btn btn-g" style={{ marginTop: 8 }} onClick={() => { setDraft(null); setTab('list'); setOpenId(item.id); }}>
                  پرونده
                </button>
              </article>
            ))
        )
      ) : null}

      {tab === 'list' ? (
        <>
          <Chips value={status} onChange={(id) => { setStatus(id); setSkip(0); setPicked([]); }} options={Q_STATUS} />
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setApplied(q.trim());
              setSkip(0);
            }}
            style={{ display: 'flex', gap: 8, marginBottom: 8 }}
          >
            <input className="inp" placeholder="جست‌وجو در متن" value={q} onChange={(e) => setQ(e.target.value)} />
            <button type="submit" className="btn btn-p">جست‌وجو</button>
          </form>
          <input className="inp" style={{ marginBottom: 10 }} placeholder="دلیل رد یا اصلاح — حداقل ۳ حرف" value={reason} onChange={(e) => setReason(e.target.value)} />
          {list.isLoading ? <Spinner /> : null}
          {list.isError ? <PageError text={apiError(list.error, 'بانک سؤال باز نشد.')} onRetry={list.refetch} /> : null}
          {picked.length ? (
            <div className="card" style={{ marginBottom: 10 }}>
              <b>{nfa(picked.length)} انتخاب</b>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                <button type="button" className="btn btn-p" disabled={bulk.isPending} onClick={() => bulk.mutate({ action: 'approve', ids: picked, reason: '' })}>تأیید گروهی</button>
                <Armed
                  danger
                  label="رد گروهی"
                  busy={bulk.isPending}
                  onConfirm={() => {
                    if (reason.trim().length < 3) {
                      toast('برای رد، دلیل حداقل ۳ حرف لازم است.', 'error');
                      return;
                    }
                    bulk.mutate({ action: 'reject', ids: picked, reason: reason.trim() });
                  }}
                />
              </div>
              <input className="inp" style={{ marginTop: 8 }} placeholder="دلیل رد گروهی" value={reason} onChange={(e) => setReason(e.target.value)} />
            </div>
          ) : null}
          {rows.map((row) => (
            <article key={row.id} className="card" style={{ marginBottom: 8 }}>
              <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                <input type="checkbox" checked={picked.includes(row.id)} onChange={() => toggle(row.id)} />
                <span style={{ flex: 1 }}>
                  <b>{row.question || 'بدون متن'}</b>
                  <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)', marginTop: 4 }}>
                    {row.lesson || 'بدون درس'} · {row.topic || 'بدون موضوع'} · {DIFF_FA[row.difficulty] || row.difficulty || '—'}
                    {row.intake ? ` · ورودی ${row.intake}` : ''}
                    {row.reports ? ` · ${nfa(row.reports)} گزارش` : ''}
                  </div>
                </span>
              </label>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                <button type="button" className="btn btn-g" onClick={() => { setOpenId(openId === row.id ? '' : row.id); setDraft(null); }}>پرونده</button>
                {row.can_approve ? (
                  <button type="button" className="btn btn-p" disabled={act.isPending} onClick={() => act.mutate({ kind: 'approve', id: row.id })}>تأیید</button>
                ) : null}
                {row.can_reject ? (
                  <button type="button" className="btn btn-d" disabled={act.isPending || reason.trim().length < 3} onClick={() => act.mutate({ kind: 'reject', id: row.id, note: reason.trim() })}>رد</button>
                ) : null}
              </div>
              {openId === row.id ? (
                <QuestionFile
                  row={row}
                  detail={detail.data}
                  loading={detail.isLoading}
                  reason={reason}
                  setReason={setReason}
                  draft={draft}
                  setDraft={setDraft}
                  busy={act.isPending || save.isPending}
                  onAct={(kind) => act.mutate({ kind, id: row.id, note: reason.trim() })}
                  onSave={(body) => save.mutate({ id: row.id, body })}
                />
              ) : null}
            </article>
          ))}
          {openId && !rows.some((row) => row.id === openId) ? (
            <article className="card" style={{ marginBottom: 8 }}>
              <b>پرونده سؤال</b>
              <QuestionFile
                row={{ id: openId, can_edit: false, can_reject: false, can_delete: false, can_approve: false }}
                detail={detail.data}
                loading={detail.isLoading}
                reason={reason}
                setReason={setReason}
                draft={draft}
                setDraft={setDraft}
                busy={act.isPending || save.isPending}
                onAct={(kind) => act.mutate({ kind, id: openId, note: reason.trim() })}
                onSave={(body) => save.mutate({ id: openId, body })}
              />
            </article>
          ) : null}
          {!list.isLoading && rows.length === 0 && !list.isError ? <EmptyState icon="🧪">در این صافی سؤالی نیست.</EmptyState> : null}
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
            <button type="button" className="btn btn-dark" disabled={skip <= 0} onClick={() => setSkip(Math.max(0, skip - limit))}>قبلی</button>
            <span style={{ color: 'var(--txm)' }}>{nfa(Math.min(total, skip + 1))}–{nfa(Math.min(total, skip + rows.length))} از {nfa(total)}</span>
            <button type="button" className="btn btn-dark" disabled={skip + limit >= total} onClick={() => setSkip(skip + limit)}>بعدی</button>
          </div>
        </>
      ) : null}
    </Desk>
  );
}

function QuestionFile({ row, detail, loading, reason, setReason, draft, setDraft, busy, onAct, onSave }) {
  const q = detail?.question;
  const options = Array.isArray(q?.options) ? q.options : (Array.isArray(row.options) ? row.options : []);
  const correct = Number(q?.correct_answer ?? row.correct);
  useEffect(() => {
    if (q && !draft) {
      setDraft({
        question: q.question || '',
        explanation: q.explanation || '',
        lesson: q.lesson || '',
        topic: q.topic || '',
        difficulty: q.difficulty || 'medium',
        options: options.map(String),
        correct: Number.isFinite(correct) ? correct : 0,
      });
    }
  }, [q, draft, setDraft, options, correct]);

  return (
    <div style={{ marginTop: 10 }}>
      {loading ? <Spinner /> : null}
      {options.map((option, index) => (
        <div key={`${index}-${option}`} style={{ padding: '4px 0', fontWeight: index === correct ? 800 : 400 }}>
          {fa(index + 1)}. {option} {index === correct ? '✓' : ''}
        </div>
      ))}
      {q?.explanation ? <p style={{ color: 'var(--txm)' }}>{q.explanation}</p> : null}
      {detail?.health?.signals?.length ? (
        <p>{detail.health.signals.map((sig) => sig.label).join(' · ')}</p>
      ) : null}
      {detail?.reports ? (
        <p style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
          گزارش باز {nfa(detail.reports.open)} از {nfa(detail.reports.total)}
          {detail.reports.recent?.[0]?.reason ? ` · آخرین: ${detail.reports.recent[0].reason}` : ''}
        </p>
      ) : null}
      {detail?.exams ? (
        <p style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
          در آزمون: {nfa(detail.exams.attempts)} تلاش، {nfa(detail.exams.correct)} درست
        </p>
      ) : null}
      <input className="inp" placeholder="دلیل رد یا درخواست اصلاح" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
        {row.can_reject ? (
          <button type="button" className="btn btn-dark" disabled={busy || reason.trim().length < 3} onClick={() => onAct('needs-changes')}>نیاز به اصلاح</button>
        ) : null}
        {row.can_delete ? (
          <Armed danger label="حذف" busy={busy} onConfirm={() => onAct('delete')} />
        ) : null}
      </div>
      {row.can_edit && draft ? (
        <div style={{ marginTop: 10 }}>
          <label className="fld-label">ویرایش</label>
          <textarea className="inp" rows={3} value={draft.question} onChange={(e) => setDraft({ ...draft, question: e.target.value })} />
          <textarea className="inp" rows={2} style={{ marginTop: 6 }} placeholder="توضیح پاسخ" value={draft.explanation} onChange={(e) => setDraft({ ...draft, explanation: e.target.value })} />
          <button
            type="button"
            className="btn btn-p"
            style={{ marginTop: 8 }}
            disabled={busy}
            onClick={() => onSave({
              question: draft.question,
              explanation: draft.explanation,
              lesson: draft.lesson,
              topic: draft.topic,
              difficulty: draft.difficulty,
              options: draft.options,
              correct: draft.correct,
            })}
          >
            ذخیره ویرایش
          </button>
        </div>
      ) : null}
    </div>
  );
}

const ACCESS_FA = {
  free: 'رایگان',
  subscription: 'فقط اشتراک',
  admin_only: 'فقط مدیر',
  disabled: 'خاموش',
};
const QUOTA_FA = { none: 'بدون سهمیه', daily: 'روزانه', monthly: 'ماهانه' };

function FeaturesDesk() {
  const toast = useToast();
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['wa-features'],
    queryFn: () => api.get('/api/web-admin/features').then((r) => r.data),
  });
  const save = useMutation({
    mutationFn: ({ key, body }) => api.put(`/api/web-admin/features/${key}`, body),
    onSuccess: () => {
      toast('دسترسی ذخیره شد.', 'success');
      qc.invalidateQueries({ queryKey: ['wa-features'] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });
  const grouped = useMemo(() => {
    const map = {};
    (query.data?.items || []).forEach((item) => {
      const cat = item.category || 'سایر';
      map[cat] = map[cat] || [];
      map[cat].push(item);
    });
    return map;
  }, [query.data]);

  return (
    <Desk title="دسترسی قابلیت‌ها" subtitle="روشن/خاموش، اشتراک و سهمیه" onRefresh={query.refetch} refreshing={query.isRefetching}>
      {query.isLoading ? <Spinner /> : null}
      {query.isError ? <PageError text={apiError(query.error)} onRetry={query.refetch} /> : null}
      {Object.entries(grouped).map(([cat, items]) => (
        <section key={cat}>
          <h3 className="sec-title">{cat}</h3>
          {items.map((item) => (
            <FeatureCard key={item.key} item={item} busy={save.isPending} onSave={(body) => save.mutate({ key: item.key, body })} />
          ))}
        </section>
      ))}
    </Desk>
  );
}

function FeatureCard({ item, busy, onSave }) {
  const pol = item.policy || {};
  const [enabled, setEnabled] = useState(Boolean(pol.enabled));
  const [access, setAccess] = useState(pol.access || 'subscription');
  const [trial, setTrial] = useState(Boolean(pol.trial_allowed));
  const [quotaKind, setQuotaKind] = useState(pol.quota?.kind || 'none');
  const [quotaLimit, setQuotaLimit] = useState(pol.quota?.limit || 0);
  const [note, setNote] = useState(pol.note || '');
  useEffect(() => {
    setEnabled(Boolean(pol.enabled));
    setAccess(pol.access || 'subscription');
    setTrial(Boolean(pol.trial_allowed));
    setQuotaKind(pol.quota?.kind || 'none');
    setQuotaLimit(pol.quota?.limit || 0);
    setNote(pol.note || '');
  }, [item.key, pol.enabled, pol.access, pol.trial_allowed, pol.quota, pol.note]);

  return (
    <article className="card" style={{ marginBottom: 10 }}>
      <b>{item.label || item.key}</b>
      <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>{item.desc}</div>
      {!item.enforced ? <div className="badge b-yel" style={{ marginTop: 6 }}>هنوز در کد قفل نشده</div> : null}
      <label style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        فعال
      </label>
      <select className="inp" value={access} onChange={(e) => setAccess(e.target.value)}>
        {Object.entries(ACCESS_FA).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
      </select>
      <label style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <input type="checkbox" checked={trial} onChange={(e) => setTrial(e.target.checked)} />
        دوره آزمایشی مجاز است
      </label>
      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <select className="inp" value={quotaKind} onChange={(e) => setQuotaKind(e.target.value)}>
          {Object.entries(QUOTA_FA).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>
        <input className="inp" inputMode="numeric" value={quotaLimit} onChange={(e) => setQuotaLimit(e.target.value)} />
      </div>
      <input className="inp" style={{ marginTop: 8 }} placeholder="یادداشت برای مدیران" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
      <button
        type="button"
        className="btn btn-p"
        style={{ marginTop: 8 }}
        disabled={busy}
        onClick={() => onSave({
          enabled,
          access,
          trial_allowed: trial,
          quota_kind: quotaKind,
          quota_limit: Number(quotaLimit) || 0,
          note,
        })}
      >
        ذخیره
      </button>
    </article>
  );
}

const REF_STATUS = [
  { id: '', label: 'همه' },
  { id: 'flagged', label: 'مشکوک' },
  { id: 'counted', label: 'شمرده‌شده' },
  { id: 'capped', label: 'سقف‌خورده' },
  { id: 'rejected', label: 'ردشده' },
];
const REWARDS = [
  ['sub_days', 'روز اشتراک'],
  ['wallet', 'کیف پول'],
  ['discount', 'تخفیف درصدی'],
  ['xp', 'امتیاز'],
];

function GrowthDesk() {
  const toast = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState('stats');
  const [status, setStatus] = useState('flagged');
  const [form, setForm] = useState(null);

  const stats = useQuery({
    queryKey: ['wa-growth-stats'],
    queryFn: () => api.get('/api/web-admin/growth/stats').then((r) => r.data),
  });
  const config = useQuery({
    queryKey: ['wa-growth-config'],
    queryFn: () => api.get('/api/web-admin/growth/config').then((r) => r.data),
  });
  const refs = useQuery({
    queryKey: ['wa-growth-refs', status],
    queryFn: () => api.get('/api/web-admin/growth/referrals', { params: { status, limit: 30 } }).then((r) => r.data),
    enabled: tab === 'refs',
  });
  useEffect(() => {
    if (config.data && !form) setForm({ ref: config.data.ref, dun: config.data.dun });
  }, [config.data, form]);

  const review = useMutation({
    mutationFn: ({ id, approve }) => api.post(`/api/web-admin/growth/referrals/${id}/review`, { approve }),
    onSuccess: () => {
      toast('دعوت بازبینی شد.', 'success');
      qc.invalidateQueries({ queryKey: ['wa-growth-refs'] });
      qc.invalidateQueries({ queryKey: ['wa-growth-stats'] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });
  const save = useMutation({
    mutationFn: (body) => api.put('/api/web-admin/growth/config', body),
    onSuccess: (res) => {
      toast('تنظیم رشد ذخیره شد.', 'success');
      setForm({ ref: res.data.ref, dun: res.data.dun });
      qc.invalidateQueries({ queryKey: ['wa-growth-config'] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });

  const referral = stats.data?.referral || {};
  const dunning = stats.data?.dunning || {};

  return (
    <Desk title="رشد و دعوت" subtitle="ریفرال، جایزه و یادآوری پرداخت" onRefresh={() => { stats.refetch(); config.refetch(); }} refreshing={stats.isRefetching}>
      <Chips
        value={tab}
        onChange={setTab}
        options={[
          { id: 'stats', label: 'آمار' },
          { id: 'refs', label: 'دعوت‌ها' },
          { id: 'config', label: 'تنظیم' },
        ]}
      />
      {stats.isError ? <PageError text={apiError(stats.error)} onRetry={stats.refetch} /> : null}
      {tab === 'stats' && stats.data ? (
        <Kpis items={[
          { icon: '🎁', label: 'همه دعوت‌ها', value: nfa(referral.total) },
          { icon: '✅', label: 'شمرده‌شده', value: nfa(referral.counted) },
          { icon: '🚩', label: 'مشکوک', value: nfa(referral.flagged) },
          { icon: '🛒', label: 'اولین خرید', value: nfa(referral.first_buys) },
          { icon: '🔔', label: 'یادآوری ارسال‌شده', value: nfa(dunning.sent) },
          { icon: '👆', label: 'کلیک یادآوری', value: nfa(dunning.clicks) },
        ]} />
      ) : null}
      {tab === 'refs' ? (
        <>
          <Chips value={status} onChange={setStatus} options={REF_STATUS} />
          {refs.isLoading ? <Spinner /> : null}
          {(refs.data?.items || []).map((item) => (
            <article key={item.id} className="card" style={{ marginBottom: 8 }}>
              <b>{item.inviter_name || item.inviter_id} ← {item.invitee_name || item.invitee_id}</b>
              <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
                {item.status}{item.flag_reason ? ` · ${item.flag_reason}` : ''} · {when(item.created_at)}
              </div>
              {item.status === 'flagged' ? (
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <button type="button" className="btn btn-p" disabled={review.isPending} onClick={() => review.mutate({ id: item.id, approve: true })}>تأیید و جایزه</button>
                  <button type="button" className="btn btn-d" disabled={review.isPending} onClick={() => review.mutate({ id: item.id, approve: false })}>رد</button>
                </div>
              ) : null}
            </article>
          ))}
          {refs.data && !(refs.data.items || []).length ? <EmptyState icon="🎁">دعوتی در این وضعیت نیست.</EmptyState> : null}
        </>
      ) : null}
      {tab === 'config' && form ? (
        <article className="card">
          <label style={{ display: 'flex', gap: 8 }}>
            <input type="checkbox" checked={Boolean(form.ref?.enabled)} onChange={(e) => setForm({ ...form, ref: { ...form.ref, enabled: e.target.checked } })} />
            دعوت دوستان روشن باشد
          </label>
          <label className="fld-label">زمان جایزه</label>
          <select className="inp" value={form.ref?.timing || 'split'} onChange={(e) => setForm({ ...form, ref: { ...form.ref, timing: e.target.value } })}>
            <option value="on_register">با ثبت‌نام</option>
            <option value="on_first_buy">با اولین خرید</option>
            <option value="split">نصف‌نصف</option>
          </select>
          <label className="fld-label">سقف روزانه / ماهانه</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <input className="inp" inputMode="numeric" value={form.ref?.cap_daily ?? 0} onChange={(e) => setForm({ ...form, ref: { ...form.ref, cap_daily: Number(e.target.value) || 0 } })} />
            <input className="inp" inputMode="numeric" value={form.ref?.cap_monthly ?? 0} onChange={(e) => setForm({ ...form, ref: { ...form.ref, cap_monthly: Number(e.target.value) || 0 } })} />
          </div>
          {REWARDS.map(([key, label]) => {
            const one = form.ref?.rewards?.[key] || { on: false, amount: 0 };
            return (
              <div key={key} style={{ marginTop: 8 }}>
                <label style={{ display: 'flex', gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={Boolean(one.on)}
                    onChange={(e) => setForm({
                      ...form,
                      ref: { ...form.ref, rewards: { ...form.ref.rewards, [key]: { ...one, on: e.target.checked } } },
                    })}
                  />
                  {label}
                </label>
                <input
                  className="inp"
                  inputMode="numeric"
                  value={one.amount ?? 0}
                  onChange={(e) => setForm({
                    ...form,
                    ref: { ...form.ref, rewards: { ...form.ref.rewards, [key]: { ...one, amount: Number(e.target.value) || 0 } } },
                  })}
                />
              </div>
            );
          })}
          <label style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <input type="checkbox" checked={Boolean(form.dun?.enabled)} onChange={(e) => setForm({ ...form, dun: { ...form.dun, enabled: e.target.checked } })} />
            یادآوری پرداخت ناتمام
          </label>
          <label className="fld-label">گام اول و دوم یادآوری، به ثانیه</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <input className="inp" inputMode="numeric" value={form.dun?.step1_s ?? 60} onChange={(e) => setForm({ ...form, dun: { ...form.dun, step1_s: Number(e.target.value) || 60 } })} />
            <input className="inp" inputMode="numeric" value={form.dun?.step2_s ?? 60} onChange={(e) => setForm({ ...form, dun: { ...form.dun, step2_s: Number(e.target.value) || 60 } })} />
          </div>
          <label className="fld-label">ساعت سکوت، از / تا</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <input className="inp" inputMode="numeric" value={form.dun?.quiet_start ?? 0} onChange={(e) => setForm({ ...form, dun: { ...form.dun, quiet_start: Number(e.target.value) || 0 } })} />
            <input className="inp" inputMode="numeric" value={form.dun?.quiet_end ?? 0} onChange={(e) => setForm({ ...form, dun: { ...form.dun, quiet_end: Number(e.target.value) || 0 } })} />
          </div>
          <button
            type="button"
            className="btn btn-p"
            style={{ marginTop: 10 }}
            disabled={save.isPending}
            onClick={() => save.mutate({ ref: form.ref, dun: form.dun })}
          >
            ذخیره تنظیم رشد
          </button>
        </article>
      ) : null}
    </Desk>
  );
}

const RING_ACTIONS = [
  ['resolve', 'حل شد'],
  ['dismiss', 'بی‌اساس'],
  ['review', 'در حال بررسی'],
  ['warn', 'هشدار'],
  ['temp_ban', 'بن یک‌روزه'],
  ['perm_ban', 'بن دائم'],
];

function RingDesk() {
  const toast = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState('home');
  const [reportStatus, setReportStatus] = useState('pending');
  const [note, setNote] = useState('');
  const [ban, setBan] = useState({ user_id: '', kind: 'temporary', hours: 24, reason: '', scope: 'ring' });

  const overview = useQuery({
    queryKey: ['ring-overview'],
    queryFn: () => api.get('/api/ring/overview').then((r) => r.data),
  });
  const reports = useQuery({
    queryKey: ['ring-reports', reportStatus],
    queryFn: () => api.get('/api/ring/reports', { params: { status: reportStatus, page: 1, size: 25 } }).then((r) => r.data),
    enabled: tab === 'reports',
  });
  const queue = useQuery({
    queryKey: ['ring-queue'],
    queryFn: () => api.get('/api/ring/queue').then((r) => r.data),
    enabled: tab === 'live',
  });
  const sessions = useQuery({
    queryKey: ['ring-sessions'],
    queryFn: () => api.get('/api/ring/sessions', { params: { status: 'active', size: 25 } }).then((r) => r.data),
    enabled: tab === 'live',
  });
  const bans = useQuery({
    queryKey: ['ring-bans'],
    queryFn: () => api.get('/api/ring/bans').then((r) => r.data),
    enabled: tab === 'bans',
  });

  const refresh = () => qc.invalidateQueries({ queryKey: ['ring-overview'] });
  const stateMut = useMutation({
    mutationFn: (body) => api.post('/api/ring/state', body),
    onSuccess: () => { toast('وضعیت رینگ عوض شد.', 'success'); refresh(); },
    onError: (error) => toast(apiError(error), 'error'),
  });
  const review = useMutation({
    mutationFn: ({ id, action }) => api.post(`/api/ring/reports/${id}/review`, { action, note }),
    onSuccess: () => {
      toast('گزارش ثبت شد.', 'success');
      qc.invalidateQueries({ queryKey: ['ring-reports'] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });
  const endSession = useMutation({
    mutationFn: (sid) => api.post(`/api/ring/sessions/${sid}/end`, { reason: 'admin' }),
    onSuccess: () => { toast('گفت‌وگو بسته شد.', 'success'); qc.invalidateQueries({ queryKey: ['ring-sessions'] }); },
    onError: (error) => toast(apiError(error), 'error'),
  });
  const banMut = useMutation({
    mutationFn: (body) => api.post('/api/ring/bans', body),
    onSuccess: () => { toast('محدودیت ثبت شد.', 'success'); qc.invalidateQueries({ queryKey: ['ring-bans'] }); },
    onError: (error) => toast(apiError(error), 'error'),
  });
  const unban = useMutation({
    mutationFn: (uid) => api.delete(`/api/ring/bans/${uid}`),
    onSuccess: () => { toast('محدودیت برداشته شد.', 'success'); qc.invalidateQueries({ queryKey: ['ring-bans'] }); },
    onError: (error) => toast(apiError(error), 'error'),
  });

  const live = overview.data?.live || {};
  const state = overview.data?.state;

  return (
    <Desk title="رینگ گفت‌وگو" subtitle={overview.data?.state_label || 'وضعیت، صف، گزارش و بن'} onRefresh={overview.refetch} refreshing={overview.isRefetching}>
      {overview.isLoading ? <Spinner /> : null}
      {overview.isError ? <PageError text={apiError(overview.error, 'رینگ باز نشد.')} onRetry={overview.refetch} /> : null}
      {overview.data ? (
        <Kpis items={[
          { icon: '👥', label: 'پروفایل فعال', value: nfa(live.active_profiles) },
          { icon: '⏳', label: 'در صف', value: nfa(live.waiting) },
          { icon: '💬', label: 'گفت‌وگوی زنده', value: nfa(live.in_chat) },
          { icon: '🚩', label: 'گزارش باز', value: nfa(live.reports_pending) },
        ]} />
      ) : null}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        {['active', 'maintenance'].map((id) => (
          <button key={id} type="button" className={state === id ? 'btn btn-p' : 'btn btn-dark'} disabled={stateMut.isPending} onClick={() => stateMut.mutate({ state: id, disable_mode: 'soft' })}>
            {id === 'active' ? 'فعال' : 'نگهداری'}
          </button>
        ))}
        <Armed danger label="خاموش نرم" busy={stateMut.isPending} onConfirm={() => stateMut.mutate({ state: 'disabled', disable_mode: 'soft' })} />
        <Armed danger label="خاموش سخت" confirmLabel="بستن گفت‌وگوهای جاری" busy={stateMut.isPending} onConfirm={() => stateMut.mutate({ state: 'disabled', disable_mode: 'hard' })} />
      </div>
      <Chips
        value={tab}
        onChange={setTab}
        options={[
          { id: 'home', label: 'خلاصه' },
          { id: 'reports', label: 'گزارش‌ها' },
          { id: 'live', label: 'صف و گفت‌وگو' },
          { id: 'bans', label: 'محدودیت' },
        ]}
      />
      {tab === 'reports' ? (
        <>
          <Chips
            value={reportStatus}
            onChange={setReportStatus}
            options={[
              { id: 'pending', label: 'باز' },
              { id: 'reviewing', label: 'در بررسی' },
              { id: 'resolved', label: 'حل‌شده' },
              { id: 'dismissed', label: 'ردشده' },
              { id: 'action_taken', label: 'اقدام‌شده' },
            ]}
          />
          <input className="inp" placeholder="یادداشت بررسی" value={note} onChange={(e) => setNote(e.target.value)} />
          {(reports.data?.reports || []).map((rep) => {
            const id = rep.report_id ?? rep.id;
            return (
              <article key={id} className="card" style={{ marginTop: 8 }}>
                <b>گزارش {fa(id)} · {rep.reason || rep.status}</b>
                <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
                  گزارش‌شده: {fa(rep.reported_uid || rep.target_uid || '—')} · {when(rep.created_at)}
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                  {RING_ACTIONS.map(([action, label]) => (
                    <button key={action} type="button" className="btn btn-dark" disabled={review.isPending} onClick={() => review.mutate({ id, action })}>{label}</button>
                  ))}
                </div>
              </article>
            );
          })}
          {reports.data && !(reports.data.reports || []).length ? <EmptyState icon="🚩">گزارشی در این وضعیت نیست.</EmptyState> : null}
        </>
      ) : null}
      {tab === 'live' ? (
        <>
          <h3 className="sec-title">صف</h3>
          {(queue.data?.queue || []).map((row) => (
            <div key={`${row.uid}-${row.queued_at}`} className="card" style={{ marginBottom: 8 }}>
              {fa(row.anon || row.uid)} · {row.mode === 'fun' ? 'سرگرمی' : 'جدی'} · انتظار {nfa(row.wait_s || 0)} ثانیه
            </div>
          ))}
          {(queue.data?.queue || []).length === 0 ? <EmptyState icon="⏳">کسی در صف نیست.</EmptyState> : null}
          <h3 className="sec-title">گفت‌وگوهای زنده</h3>
          {(sessions.data?.sessions || []).map((row) => {
            const sid = row.session_id || row.id;
            return (
              <article key={sid} className="card" style={{ marginBottom: 8 }}>
                <b>{sid}</b>
                <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>{row.mode} · {when(row.created_at)}</div>
                <Armed danger label="بستن گفت‌وگو" busy={endSession.isPending} onConfirm={() => endSession.mutate(sid)} />
              </article>
            );
          })}
        </>
      ) : null}
      {tab === 'bans' ? (
        <>
          <article className="card" style={{ marginBottom: 10 }}>
            <label className="fld-label">شناسه کاربر</label>
            <input className="inp" inputMode="numeric" value={ban.user_id} onChange={(e) => setBan({ ...ban, user_id: e.target.value })} />
            <select className="inp" style={{ marginTop: 6 }} value={ban.kind} onChange={(e) => setBan({ ...ban, kind: e.target.value })}>
              <option value="warning">هشدار</option>
              <option value="temporary">موقت</option>
              <option value="permanent">دائم</option>
            </select>
            <input className="inp" style={{ marginTop: 6 }} inputMode="numeric" value={ban.hours} onChange={(e) => setBan({ ...ban, hours: e.target.value })} />
            <input className="inp" style={{ marginTop: 6 }} placeholder="دلیل" value={ban.reason} onChange={(e) => setBan({ ...ban, reason: e.target.value })} />
            <Armed
              danger
              label="ثبت محدودیت"
              busy={banMut.isPending}
              onConfirm={() => banMut.mutate({
                user_id: Number(ban.user_id),
                kind: ban.kind,
                hours: ban.kind === 'temporary' ? Number(ban.hours) || 24 : null,
                reason: ban.reason,
                scope: ban.scope,
              })}
            />
          </article>
          {(bans.data?.bans || []).map((row) => (
            <article key={`${row.user_id}-${row.created_at}`} className="card" style={{ marginBottom: 8 }}>
              <b>کاربر {fa(row.user_id)}</b>
              <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>{row.kind} · {row.reason || 'بدون دلیل'} · {when(row.until || row.created_at)}</div>
              <button type="button" className="btn btn-g" disabled={unban.isPending} onClick={() => unban.mutate(row.user_id)}>برداشتن</button>
            </article>
          ))}
        </>
      ) : null}
    </Desk>
  );
}

function SystemJobsDesk() {
  const [params] = useSearchParams();
  const toast = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState(params.get('focus') === 'dlq' ? 'dlq' : 'jobs');
  const [picked, setPicked] = useState([]);
  const jobs = useQuery({
    queryKey: ['wa-jobs'],
    queryFn: () => api.get('/api/web-admin/system/jobs').then((r) => r.data),
  });
  const dlq = useQuery({
    queryKey: ['wa-dlq'],
    queryFn: () => api.get('/api/web-admin/system/dlq').then((r) => r.data),
    enabled: tab === 'dlq',
  });
  const act = useMutation({
    mutationFn: ({ path, body }) => api.post(path, body),
    onSuccess: (res) => {
      const data = res.data || {};
      toast(`انجام شد: ${nfa(data.requeued || data.discarded || 0)}`, 'success');
      setPicked([]);
      qc.invalidateQueries({ queryKey: ['wa-dlq'] });
      qc.invalidateQueries({ queryKey: ['wa-jobs'] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });

  return (
    <Desk title="صف سیستم" subtitle="کارهای زمان‌بندی و پیام‌های نرسیده" onRefresh={jobs.refetch} refreshing={jobs.isRefetching}>
      <Chips value={tab} onChange={setTab} options={[{ id: 'jobs', label: 'کارها' }, { id: 'dlq', label: 'پیام مرده' }]} />
      {tab === 'jobs' && jobs.isLoading ? <Spinner /> : null}
      {tab === 'jobs' && jobs.isError ? <PageError text={apiError(jobs.error)} onRetry={jobs.refetch} /> : null}
      {tab === 'jobs' ? (jobs.data?.jobs || []).map((job) => (
        <article key={job.key} className="card" style={{ marginBottom: 8 }}>
          <b>{job.label}</b>
          <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
            {job.status}
            {job.pending != null ? ` · صف ${nfa(job.pending)}` : ''}
            {job.scheduled != null ? ` · زمان‌بندی ${nfa(job.scheduled)}` : ''}
            {job.dead != null ? ` · مرده ${nfa(job.dead)}` : ''}
            {job.failed != null ? ` · خطا ${nfa(job.failed)}` : ''}
            {job.last_run ? ` · ${when(job.last_run)}` : ''}
          </div>
        </article>
      )) : null}
      {tab === 'dlq' ? (
        <>
          <p style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
            این پیام‌ها بعد از چند تلاش نرسیده‌اند. بازپخش دوباره به صف ربات برمی‌گرداند؛ کنارگذاشتن حذف نمی‌کند.
          </p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" className="btn btn-p" disabled={!picked.length || act.isPending} onClick={() => act.mutate({ path: '/api/web-admin/system/dlq/requeue', body: { ids: picked } })}>بازپخش انتخاب‌ها</button>
            <Armed danger label="کنارگذاشتن انتخاب‌ها" busy={act.isPending} onConfirm={() => act.mutate({ path: '/api/web-admin/system/dlq/discard', body: { ids: picked } })} />
          </div>
          {dlq.isLoading ? <Spinner /> : null}
          {dlq.isError ? <PageError text={apiError(dlq.error)} onRetry={dlq.refetch} /> : null}
          {(dlq.data?.items || []).map((item) => (
            <label key={item.id} className="card" style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <input type="checkbox" checked={picked.includes(item.id)} onChange={() => setPicked((curr) => curr.includes(item.id) ? curr.filter((id) => id !== item.id) : [...curr, item.id])} />
              <span>
                <b>{item.text || 'بدون متن'}</b>
                <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
                  کاربر {fa(item.user_id)} · تلاش {nfa(item.attempts)} · {item.error || 'بدون خطا'}
                </div>
              </span>
            </label>
          ))}
          {dlq.data && !(dlq.data.items || []).length ? <EmptyState icon="📤">پیام مرده‌ای نیست.</EmptyState> : null}
        </>
      ) : null}
    </Desk>
  );
}

function FinanceDesk() {
  const toast = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState('home');
  const [q, setQ] = useState('');
  const [applied, setApplied] = useState('');
  const [uid, setUid] = useState(null);
  const [adjust, setAdjust] = useState({ amount: '', reason: '' });

  const finance = useQuery({
    queryKey: ['wa-finance'],
    queryFn: () => api.get('/api/web-admin/subscription/finance').then((r) => r.data),
  });
  const recon = useQuery({
    queryKey: ['wa-reconcile'],
    queryFn: () => api.get('/api/web-admin/subscription/reconcile').then((r) => r.data),
    enabled: tab === 'recon',
  });
  const wallets = useQuery({
    queryKey: ['wa-wallets', applied],
    queryFn: () => api.get('/api/web-admin/wallets', { params: { q: applied, limit: 30 } }).then((r) => r.data),
    enabled: tab === 'wallets',
  });
  const wallet = useQuery({
    queryKey: ['wa-wallet', uid],
    queryFn: () => api.get(`/api/web-admin/wallets/${uid}`).then((r) => r.data),
    enabled: tab === 'wallets' && Boolean(uid),
  });

  const run = useMutation({
    mutationFn: ({ url, body }) => api.post(url, body),
    onSuccess: () => {
      toast('اقدام مالی ثبت شد.', 'success');
      qc.invalidateQueries({ queryKey: ['wa-reconcile'] });
      qc.invalidateQueries({ queryKey: ['wa-finance'] });
      qc.invalidateQueries({ queryKey: ['wa-wallet'] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });

  const daily = finance.data?.daily || [];
  const maxDaily = Math.max(1, ...daily.map((row) => Number(row.total) || 0));
  const walletStats = finance.data?.wallet || {};

  function reconAction(item, action, extra = {}) {
    if (action.key === 'go') return;
    if (action.key === 'activate') {
      run.mutate({ url: `/api/web-admin/subscription/reconcile/${item.payment_id}/activate`, body: { confirm: true } });
    } else if (action.key === 'finalize_topup') {
      run.mutate({ url: `/api/web-admin/subscription/reconcile/${item.payment_id}/finalize-topup`, body: { confirm: true } });
    } else if (action.key === 'recredit') {
      run.mutate({
        url: '/api/web-admin/subscription/reconcile/wallet-recredit',
        body: { payment_id: action.payment_id || item.payment_id, confirm: true },
      });
    } else if (action.key === 'resync') {
      run.mutate({ url: `/api/web-admin/wallets/${item.user_id}/resync`, body: { confirm: true } });
    } else if (action.key === 'resolve_tx') {
      run.mutate({
        url: `/api/web-admin/wallet-tx/${action.tx_id || item.technical}/resolve`,
        body: { action: extra.resolve || 'complete', confirm: true },
      });
    }
  }

  return (
    <Desk title="مرکز مالی" subtitle="درآمد، مغایرت و کیف پول؛ بررسی رسید همچنان در اشتراک است" onRefresh={finance.refetch} refreshing={finance.isRefetching}>
      <Chips
        value={tab}
        onChange={setTab}
        options={[
          { id: 'home', label: 'خلاصه' },
          { id: 'recon', label: 'مغایرت' },
          { id: 'wallets', label: 'کیف پول' },
        ]}
      />
      {finance.isLoading ? <Spinner /> : null}
      {finance.isError ? <PageError text={apiError(finance.error)} onRetry={finance.refetch} /> : null}
      {tab === 'home' && finance.data ? (
        <>
          <Kpis items={[
            { icon: '💰', label: 'درآمد تأییدشده', value: toman(finance.data.revenue_total) },
            { icon: '📅', label: 'هفت روز', value: toman(finance.data.revenue_week) },
            { icon: '↩️', label: 'بازگشت وجه', value: toman(finance.data.revenue_refunded) },
            { icon: '👛', label: 'موجودی کیف‌ها', value: toman(walletStats.balance) },
          ]} />
          <article className="card">
            <b>روند ۱۴ روز</b>
            {daily.map((row) => (
              <div key={row.day} className="hbar">
                <span>{fa(String(row.day).slice(5))}</span>
                <div className="hbar__track">
                  <div className="hbar__fill" style={{ width: `${Math.round((Number(row.total) || 0) * 100 / maxDaily)}%` }} />
                </div>
                <span className="hbar__count">{nfa(Math.round((Number(row.total) || 0) / 1000))}</span>
              </div>
            ))}
            <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>اعداد نمودار به هزار تومان است.</div>
          </article>
          {(finance.data.refunds || []).slice(0, 8).map((row) => (
            <div key={row.payment_id} className="card" style={{ marginTop: 8 }}>
              بازگشت {toman(row.amount)} · کاربر {fa(row.user_id)} · {row.reason || 'بدون دلیل'}
            </div>
          ))}
        </>
      ) : null}
      {tab === 'recon' ? (
        recon.isLoading ? <Spinner /> : recon.isError ? <PageError text={apiError(recon.error)} onRetry={recon.refetch} /> : (
          <>
            <p style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
              {nfa(recon.data?.summary?.total || 0)} مورد · امروز {nfa(recon.data?.summary?.resolved_today || 0)} رفع شده
            </p>
            {(recon.data?.items || []).length === 0 ? <EmptyState icon="✅">مغایرت بازی نیست.</EmptyState> : null}
            {(recon.data?.items || []).map((item, index) => (
              <article key={`${item.type}-${item.payment_id || item.user_id}-${index}`} className="card" style={{ marginBottom: 8 }}>
                <span className={severityBadge(item.severity)}>{item.label}</span>
                <p>{item.summary}</p>
                <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>{toman(item.amount)} · {when(item.at)}</div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                  {(item.actions || []).filter((action) => action.key !== 'go').map((action) => (
                    action.key === 'resolve_tx' ? (
                      <span key={action.key} style={{ display: 'inline-flex', gap: 6 }}>
                        <Armed label="اعمال تراکنش" busy={run.isPending} onConfirm={() => reconAction(item, action, { resolve: 'complete' })} />
                        <Armed danger label="لغو تراکنش" busy={run.isPending} onConfirm={() => reconAction(item, action, { resolve: 'cancel' })} />
                      </span>
                    ) : (
                      <Armed key={action.key} danger label={action.label} busy={run.isPending} onConfirm={() => reconAction(item, action)} />
                    )
                  ))}
                </div>
              </article>
            ))}
          </>
        )
      ) : null}
      {tab === 'wallets' ? (
        <>
          <form onSubmit={(e) => { e.preventDefault(); setApplied(q.trim()); }} style={{ display: 'flex', gap: 8 }}>
            <input className="inp" placeholder="نام، شماره دانشجویی یا شناسه" value={q} onChange={(e) => setQ(e.target.value)} />
            <button className="btn btn-p" type="submit">جست‌وجو</button>
          </form>
          {(wallets.data?.items || []).map((row) => (
            <button key={row.user_id} type="button" className="card card-tap" style={{ width: '100%', textAlign: 'right', marginTop: 8 }} onClick={() => setUid(row.user_id)}>
              <b>{row.user_name || `کاربر ${fa(row.user_id)}`}</b>
              <div>{toman(row.balance)}</div>
            </button>
          ))}
          {uid && wallet.data ? (
            <article className="card" style={{ marginTop: 10 }}>
              <b>{wallet.data.summary?.user_name || fa(uid)}</b>
              <div>موجودی {toman(wallet.data.summary?.balance)}</div>
              {(wallet.data.transactions || []).slice(0, 12).map((tx) => (
                <div key={tx.id} style={{ fontSize: 'var(--fs-cap)', color: 'var(--txm)', marginTop: 4 }}>
                  {tx.label || tx.type} · {tx.direction === 'debit' ? '−' : '+'}{toman(tx.amount)} · {tx.status} · {when(tx.at)}
                </div>
              ))}
              <Armed danger label="هم‌تراز با دفتر" busy={run.isPending} onConfirm={() => run.mutate({ url: `/api/web-admin/wallets/${uid}/resync`, body: { confirm: true } })} />
              <label className="fld-label">تنظیم دستی؛ مثبت یعنی افزایش</label>
              <input className="inp" inputMode="numeric" placeholder="مبلغ" value={adjust.amount} onChange={(e) => setAdjust({ ...adjust, amount: e.target.value })} />
              <input className="inp" style={{ marginTop: 6 }} placeholder="دلیل، حداقل ۳ حرف" value={adjust.reason} onChange={(e) => setAdjust({ ...adjust, reason: e.target.value })} />
              <Armed
                danger
                label="اعمال تنظیم"
                busy={run.isPending}
                onConfirm={() => {
                  if (adjust.reason.trim().length < 3 || !Number(adjust.amount)) {
                    toast('مبلغ و دلیل معتبر لازم است.', 'error');
                    return;
                  }
                  run.mutate({
                    url: `/api/web-admin/wallets/${uid}/adjust`,
                    body: { amount: Number(adjust.amount), reason: adjust.reason.trim(), confirm: true },
                  });
                }}
              />
            </article>
          ) : null}
        </>
      ) : null}
    </Desk>
  );
}

function ExamsDesk() {
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [status, setStatus] = useState('');
  const [form, setForm] = useState({ lesson: '', date: '', time: '', teacher: '', location: '', notes: '', group: 'هر دو' });
  const query = useQuery({
    queryKey: ['wa-exams', status],
    queryFn: () => api.get('/api/web-admin/exams', { params: status ? { status } : {} }).then((r) => r.data),
  });
  const create = useMutation({
    mutationFn: (body) => api.post('/api/web-admin/exams', body),
    onSuccess: () => {
      toast('آزمون ثبت شد و به گروه خبر می‌رود.', 'success');
      setForm({ lesson: '', date: '', time: '', teacher: '', location: '', notes: '', group: 'هر دو' });
      qc.invalidateQueries({ queryKey: ['wa-exams'] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });
  const remove = useMutation({
    mutationFn: (id) => api.delete(`/api/web-admin/exams/${id}`),
    onSuccess: () => {
      toast('آزمون حذف شد.', 'success');
      qc.invalidateQueries({ queryKey: ['wa-exams'] });
    },
    onError: (error) => toast(apiError(error), 'error'),
  });
  const counts = query.data?.counts || {};

  return (
    <Desk title="آزمون‌ها" subtitle="جدا از برنامه کلاسی؛ ثبت اینجا به دانشجویان خبر می‌دهد" onRefresh={query.refetch} refreshing={query.isRefetching}>
      <button type="button" className="btn btn-g" onClick={() => navigate('/admin/content/schedule')}>برنامه کلاسی</button>
      <Kpis items={[
        { icon: '🗓', label: 'آینده', value: nfa(counts.scheduled) },
        { icon: '🟢', label: 'در جریان', value: nfa(counts.active) },
        { icon: '✅', label: 'برگزارشده', value: nfa(counts.finished) },
      ]} />
      <Chips
        value={status}
        onChange={setStatus}
        options={[
          { id: '', label: 'همه' },
          { id: 'scheduled', label: 'آینده' },
          { id: 'active', label: 'در جریان' },
          { id: 'finished', label: 'برگزارشده' },
        ]}
      />
      <article className="card" style={{ marginBottom: 10 }}>
        <b>آزمون تازه</b>
        <input className="inp" placeholder="درس" value={form.lesson} onChange={(e) => setForm({ ...form, lesson: e.target.value })} />
        <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
          <input className="inp" placeholder="YYYY-MM-DD" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          <input className="inp" placeholder="HH:MM" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} />
        </div>
        <input className="inp" style={{ marginTop: 6 }} placeholder="استاد" value={form.teacher} onChange={(e) => setForm({ ...form, teacher: e.target.value })} />
        <input className="inp" style={{ marginTop: 6 }} placeholder="مکان" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
        <select className="inp" style={{ marginTop: 6 }} value={form.group} onChange={(e) => setForm({ ...form, group: e.target.value })}>
          <option value="هر دو">هر دو گروه</option>
          <option value="1">گروه ۱</option>
          <option value="2">گروه ۲</option>
        </select>
        <input className="inp" style={{ marginTop: 6 }} placeholder="یادداشت" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        <button type="button" className="btn btn-p" style={{ marginTop: 8 }} disabled={create.isPending || form.lesson.trim().length < 1 || form.date.trim().length < 8} onClick={() => create.mutate(form)}>
          ثبت و اطلاع‌رسانی
        </button>
      </article>
      {query.isLoading ? <Spinner /> : null}
      {query.isError ? <PageError text={apiError(query.error)} onRetry={query.refetch} /> : null}
      {(query.data?.exams || []).map((exam) => (
        <article key={exam.id} className="card" style={{ marginBottom: 8 }}>
          <b>{exam.lesson}</b>
          <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
            {exam.status_fa} · {fa(exam.date)} {fa(exam.time)} · گروه {fa(exam.group)}
            {exam.location ? ` · ${exam.location}` : ''}
          </div>
          <Armed danger label="حذف و خبر لغو" busy={remove.isPending} onConfirm={() => remove.mutate(exam.id)} />
        </article>
      ))}
    </Desk>
  );
}

export {
  AttentionDesk,
  OperationsDesk,
  QuestionsDesk,
  FeaturesDesk,
  GrowthDesk,
  RingDesk,
  SystemJobsDesk,
  FinanceDesk,
  ExamsDesk,
};
