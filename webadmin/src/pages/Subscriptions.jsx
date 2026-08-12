import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { DataTable, Loading, ErrorState, Stat, B, toast, Confirm } from '../ui.jsx';

// 💎 اشتراک‌ها + رسیدهای کارت‌به‌کارت + تخفیف‌ها
export default function Subscriptions() {
  const [tab, setTab] = useState('payments');
  const [ov, setOv] = useState(null);
  const [pays, setPays] = useState(null);
  const [status, setStatus] = useState('pending');
  const [discs, setDiscs] = useState(null);
  const [err, setErr] = useState('');
  const [confirm, setConfirm] = useState(null);

  const load = async () => {
    setErr('');
    try {
      const [o, p, d] = await Promise.all([
        api.subOverview().catch(() => null),
        api.subPayments({ status }).catch(() => ({ payments: [] })),
        api.discounts().catch(() => ({ discounts: [] })),
      ]);
      setOv(o); setPays(p.payments || p.items || []); setDiscs(d.discounts || d.items || []);
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, [status]);

  const decide = (pid, approved) => setConfirm({
    text: approved ? 'تأیید این رسید و فعال‌سازی اشتراک؟' : 'رد این رسید؟',
    danger: !approved,
    onYes: async () => {
      try { await api.subPaymentDecision(pid, approved); toast('انجام شد'); load(); }
      catch (e) { toast(errText(e), 'err'); }
    },
  });

  if (err) return <ErrorState error={err} onRetry={load} />;

  const payCols = [
    { k: 'id', label: 'شناسه', render: r => <span className="code">{r.id || r._id}</span> },
    { k: 'user_name', label: 'دانشجو', render: r => r.user_name || r.name || r.user_id },
    { k: 'plan', label: 'پلن', render: r => r.plan_name || r.plan },
    { k: 'amount', label: 'مبلغ', render: r => r.final_amount != null
        ? `${Number(r.final_amount).toLocaleString('fa')} تومان` : (r.amount || '—') },
    { k: 'discount', label: 'تخفیف', render: r => r.discount_code ? <B kind="purple">{r.discount_code}</B> : '—' },
    { k: 'created_at', label: 'تاریخ', render: r => (r.created_at || '').slice(0, 10) },
    { k: 'status', label: 'وضعیت', render: r => r.status === 'pending'
        ? <B kind="warn">در انتظار</B> : r.status === 'approved' ? <B kind="ok">تأیید</B> : <B kind="bad">رد</B> },
    { k: 'ops', label: '', stop: true, render: r => r.status === 'pending' && (
      <div className="row" style={{ gap: 4 }}>
        <button className="btn sm ok" onClick={() => decide(r.id || r._id, true)}>✅ تأیید</button>
        <button className="btn sm danger" onClick={() => decide(r.id || r._id, false)}>❌ رد</button>
      </div>) },
  ];
  const discCols = [
    { k: 'code', label: 'کد', render: r => <span className="code purple">{r.code}</span> },
    { k: 'percent', label: 'درصد', render: r => `٪${r.percent ?? r.discount_percent ?? '—'}` },
    { k: 'uses', label: 'استفاده', render: r => Number(r.uses ?? r.used ?? 0).toLocaleString('fa') },
    { k: 'active', label: 'وضعیت', render: r => r.active === false ? <B kind="bad">غیرفعال</B> : <B kind="ok">فعال</B> },
  ];

  return (
    <>
      <div className="h1">اشتراک‌ها، رسیدها و تخفیف‌ها</div>
      <div className="sub">بررسی رسیدهای کارت‌به‌کارت و سلامت اشتراک‌ها</div>
      {ov && (
        <div className="grid g4" style={{ marginBottom: 14 }}>
          <Stat icon="💎" label="اشتراک فعال" value={Number(ov.active ?? 0).toLocaleString('fa')} tint="var(--teal)" />
          <Stat icon="🧾" label="رسید در انتظار" value={Number(ov.pending_payments ?? 0).toLocaleString('fa')} tint="var(--warn)" />
          <Stat icon="⏳" label="نزدیک به پایان" value={Number(ov.expiring ?? 0).toLocaleString('fa')} tint="var(--acc)" />
          <Stat icon="🎁" label="کدهای تخفیف" value={Number(ov.discounts ?? 0).toLocaleString('fa')} tint="var(--purple)" />
        </div>
      )}
      <div className="tabs">
        <button className={`tab ${tab === 'payments' ? 'on' : ''}`} onClick={() => setTab('payments')}>🧾 رسیدها</button>
        <button className={`tab ${tab === 'discounts' ? 'on' : ''}`} onClick={() => setTab('discounts')}>🎁 تخفیف‌ها</button>
      </div>
      {tab === 'payments' && (
        <>
          <div className="row" style={{ marginBottom: 10 }}>
            {[['pending', 'در انتظار'], ['approved', 'تأییدشده'], ['rejected', 'ردشده'], ['', 'همه']].map(([k, v]) => (
              <button key={k} className={`btn sm ${status === k ? 'primary' : ''}`}
                      onClick={() => setStatus(k)}>{v}</button>
            ))}
          </div>
          {!pays ? <Loading /> : <DataTable columns={payCols} rows={pays} rowKey="id" />}
        </>
      )}
      {tab === 'discounts' && (!discs ? <Loading /> : <DataTable columns={discCols} rows={discs} rowKey="code" />)}
      {confirm && <Confirm text={confirm.text} danger={confirm.danger}
                           onYes={async () => { await confirm.onYes(); setConfirm(null); }}
                           onNo={() => setConfirm(null)} />}
    </>
  );
}
