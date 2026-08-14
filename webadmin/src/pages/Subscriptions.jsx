import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { DataTable, Loading, ErrorState, Stat, B, toast, Confirm, Drawer, Empty } from '../ui.jsx';

// 💎 اشتراک‌ها + رسیدهای کارت‌به‌کارت + تخفیف‌ها
export default function Subscriptions() {
  const [tab, setTab] = useState('payments');
  const [ov, setOv] = useState(null);
  const [pays, setPays] = useState(null);
  const [status, setStatus] = useState('pending');
  const [discs, setDiscs] = useState(null);
  const [err, setErr] = useState('');
  const [confirm, setConfirm] = useState(null);
  const [rcpt, setRcpt] = useState(null);          // 🌊 W-Design — دراور بازبینی رسید

  const load = async () => {
    setErr('');
    try {
      const [o, p, d] = await Promise.all([
        api.subOverview(),
        api.subPayments({ status }),
        api.discounts(),
      ]);
      setOv(o); setPays(p.payments || p.items || []); setDiscs(d.discounts || d.items || []);
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, [status]);

  const decide = (pid, approved, note = '') => setConfirm({
    text: approved ? 'تأیید این رسید و فعال‌سازی اشتراک؟' : 'رد این رسید؟',
    danger: !approved,
    onYes: async () => {
      try {
        await api.subPaymentDecision(pid, approved, note);
        toast('انجام شد'); setRcpt(null); load();
      } catch (e) { toast(errText(e), 'err'); }
    },
  });

  if (err) return <ErrorState error={err} onRetry={load} />;

  const ovStats = ov?.stats || ov || {};
  const payCols = [
    { k: 'id', label: 'شناسه', render: r => <span className="code">{r.id || r._id}</span> },
    { k: 'user_name', label: 'دانشجو', render: r => r.user_name || r.name || r.user_id },
    { k: 'plan', label: 'پلن', render: r => r.plan_name || r.plan },
    { k: 'amount', label: 'مبلغ', render: r => (r.final_price ?? r.final_amount ?? r.amount) != null
        ? `${Number(r.final_price ?? r.final_amount ?? r.amount).toLocaleString('fa')} تومان` : '—' },
    { k: 'discount', label: 'تخفیف', render: r => r.discount_code ? <B kind="purple">{r.discount_code}</B> : '—' },
    { k: 'receipt', label: 'رسید', render: r => r.has_receipt ? <B kind="acc">🖼 دارد</B> : <span className="muted">—</span> },
    { k: 'created_at', label: 'تاریخ', render: r => (r.submitted_at || r.created_at || '').slice(0, 10) },
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
    { k: 'uses', label: 'استفاده', render: r => Number(r.used_count ?? r.uses ?? r.used ?? 0).toLocaleString('fa') },
    { k: 'active', label: 'وضعیت', render: r => r.active === false ? <B kind="bad">غیرفعال</B> : <B kind="ok">فعال</B> },
  ];

  return (
    <>
      <div className="h1">اشتراک‌ها، رسیدها و تخفیف‌ها</div>
      <div className="sub">بررسی رسیدهای کارت‌به‌کارت و سلامت اشتراک‌ها</div>
      {ov && (
        <div className="grid g4" style={{ marginBottom: 14 }}>
          <Stat icon="💎" label="اشتراک فعال" value={Number(ovStats.active ?? 0).toLocaleString('fa')} tint="var(--teal)" />
          <Stat icon="🧾" label="رسید در انتظار" value={Number(ovStats.pending ?? 0).toLocaleString('fa')} tint="var(--warn)" />
          <Stat icon="⏳" label="نزدیک به پایان (۷ روز)" value={Number(ovStats.expiring ?? 0).toLocaleString('fa')} tint="var(--acc)" />
          <Stat icon="🎁" label="کدهای تخفیف" value={Number(ovStats.discounts ?? discs?.length ?? 0).toLocaleString('fa')} tint="var(--purple)" />
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
          {!pays ? <Loading /> : (
            <DataTable columns={payCols} rows={pays} rowKey="id" colToggle
                       onRow={r => setRcpt(r)} />
          )}
        </>
      )}
      {tab === 'discounts' && (!discs ? <Loading /> : <DataTable columns={discCols} rows={discs} rowKey="code" />)}
      {rcpt && <ReceiptDrawer pay={rcpt} decide={decide} onClose={() => setRcpt(null)} />}
      {confirm && <Confirm text={confirm.text} danger={confirm.danger}
                           onYes={async () => { await confirm.onYes(); setConfirm(null); }}
                           onNo={() => setConfirm(null)} />}
    </>
  );
}

/* ── 🧾🌊 W-Design — بازبینی رسید دوپه‌ای: جزئیات | تصویر ───────── */
function ReceiptDrawer({ pay, decide, onClose }) {
  const r = pay;
  const id = r.id || r._id;
  const [note, setNote] = useState('');
  const [imgErr, setImgErr] = useState(false);
  return (
    <Drawer wide title={`🧾 بازبینی رسید — ${r.user_name || r.name || r.user_id}`} onClose={onClose}>
      <div className="rcpt">
        <div>
          <dl className="kv" style={{ marginTop: 0 }}>
            {Object.entries({
              'دانشجو': r.user_name || r.name,
              'شماره دانشجویی': r.student_id,
              'یوزرنیم': r.username && '@' + r.username,
              'پلن': r.plan_name || r.plan,
              'مبلغ پایه': r.price != null ? `${Number(r.price).toLocaleString('fa')} تومان` : null,
              'مبلغ نهایی': (r.final_price ?? r.final_amount) != null
                ? `${Number(r.final_price ?? r.final_amount).toLocaleString('fa')} تومان` : null,
              'کد تخفیف': r.discount_code,
              'ثبت': (r.submitted_at || r.created_at || '').replace('T', ' '),
              'یادداشت بررسی': r.review_note,
            }).filter(([, v]) => v).map(([k, v]) => (
              <React.Fragment key={k}><dt>{k}</dt><dd>{String(v)}</dd></React.Fragment>
            ))}
          </dl>
          {r.status === 'pending' && (
            <div className="panel panel-pad" style={{ background: 'var(--bg)' }}>
              <b>تصمیم بررسی</b>
              <input className="inp" style={{ width: '100%', marginTop: 8 }}
                     placeholder="یادداشت بررسی (اختیاری — برای دانشجو/لاگ)…"
                     value={note} onChange={e => setNote(e.target.value)} />
              <div className="row" style={{ marginTop: 10 }}>
                <button className="btn ok" onClick={() => decide(id, true, note.trim())}>✅ تأیید و فعال‌سازی</button>
                <button className="btn danger" onClick={() => decide(id, false, note.trim())}>❌ رد رسید</button>
              </div>
            </div>
          )}
        </div>
        <div className="rcpt-img">
          {r.has_receipt && !imgErr ? (
            <>
              <img src={api.subReceiptSrc(id)} alt="تصویر رسید پرداخت"
                   onError={() => setImgErr(true)} />
              <div className="zoom-hint">رسید مستقیماً از همان فایل تلگرام سرو می‌شود — بدون ذخیره‌ی جدید</div>
            </>
          ) : (
            <Empty icon="🖼" text="تصویر رسیدی پیوست نشده است" />
          )}
        </div>
      </div>
    </Drawer>
  );
}
