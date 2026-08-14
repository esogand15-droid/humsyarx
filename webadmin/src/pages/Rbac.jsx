import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Empty, B, toast, Modal } from '../ui.jsx';

// 🛡 مرکز کنترل RBAC — نقش‌ها + ماتریس مجوزها (require_perm واقعی بک‌اند)
export default function Rbac() {
  const [roles, setRoles] = useState(null);
  const [perms, setPerms] = useState(null);
  const [err, setErr] = useState('');
  const [create, setCreate] = useState(false);

  const load = async () => {
    setErr('');
    try {
      const [r, p] = await Promise.all([api.roles(), api.perms()]);
      setRoles(r.roles || []); setPerms(p.permissions || []);
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);

  if (err) return <ErrorState error={err} onRetry={load} />;
  if (!roles || !perms) return <Loading rows={6} />;

  // گروه‌بندی مجوزها بر اساس دسته‌ی واقعی کاتالوگ
  const groups = {};
  perms.forEach(p => {
    const g = p.category || p.key.split('.')[0];
    (groups[g] = groups[g] || []).push({ key: p.key, label: p.label || p.key });
  });

  return (
    <>
      <div className="row">
        <div><div className="h1">نقش‌ها و مجوزها</div>
          <div className="sub">تک‌منبع حقیقت RBAC — تغییرات هم‌زمان لاگ می‌شوند</div></div>
        <span className="spacer" />
        <MatrixPreview roles={roles} perms={perms} />
        <button className="btn primary" onClick={() => setCreate(true)}>➕ نقش جدید</button>
      </div>

      <div className="grid g2">
        {roles.map(r => (
          <div key={r.key} className="panel panel-pad">
            <div className="row">
              <span style={{ width: 12, height: 12, borderRadius: 4, background: r.color || 'var(--acc)' }} />
              <b>{r.label || r.key}</b>
              <span className="code">{r.key}</span>
              {r.system && <B kind="acc">سیستمی</B>}
              {r.users_count != null && <B>{Number(r.users_count).toLocaleString('fa')} کاربر</B>}
              <span className="spacer" />
              {!r.system && (
                <button className="btn sm danger"
                        onClick={async () => {
                          if (!confirm(`حذف نقش «${r.label || r.key}»؟`)) return;
                          try { await api.deleteRole(r.key); toast('حذف شد'); load(); }
                          catch (e) { toast(errText(e), 'err'); }
                        }}>🗑</button>
              )}
            </div>
            {r.desc && <p className="muted" style={{ margin: '8px 0' }}>{r.desc}</p>}
            <PermMatrix roleKey={r.key} granted={r.perms || []} groups={groups}
                        system={!!r.system} onChanged={load} />
          </div>
        ))}
        {!roles.length && <Empty text="نقشی تعریف نشده" />}
      </div>

      {create && <CreateRole onClose={() => setCreate(false)} onDone={() => { setCreate(false); load(); }} />}
    </>
  );
}

// 🌊 موج RBAC-Matrix — نمای سراسری ماتریس نقش × مجوز (فقط‌خواندنی، برای
// پاسخ سریع به «کدام نقش چه دسترسی‌هایی دارد؟» بدون بازکردن تک‌تک کارت‌ها)
function MatrixPreview({ roles, perms }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="btn" onClick={() => setOpen(true)}>🧮 ماتریس سراسری</button>
      {open && (
        <Modal title="🧮 ماتریس سراسری نقش × مجوز (فقط‌خواندنی)" onClose={() => setOpen(false)}>
          <div style={{ overflowX: 'auto', maxHeight: '62vh', overflowY: 'auto' }}>
            <table className="tbl" style={{ minWidth: 90 + roles.length * 92 }}>
              <thead>
                <tr>
                  <th style={{ position: 'sticky', right: 0, background: 'var(--bg2)', zIndex: 1 }}>مجوز</th>
                  {roles.map(r => (
                    <th key={r.key} style={{ textAlign: 'center', minWidth: 84 }}>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                        <span style={{ width: 9, height: 9, borderRadius: 3, background: r.color || 'var(--acc)' }} />
                        {r.label || r.key}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {perms.map(p => (
                  <tr key={p.key}>
                    <td style={{ position: 'sticky', right: 0, background: 'var(--panel)', zIndex: 1 }}>
                      <div style={{ fontSize: 12 }}>{p.label || p.key}</div>
                      <div className="muted code" style={{ fontSize: 10 }}>{p.key}</div>
                    </td>
                    {roles.map(r => (
                      <td key={r.key} style={{ textAlign: 'center' }}>
                        {(r.perms || []).includes(p.key)
                          ? <span style={{ color: 'var(--ok)', fontWeight: 800 }}>✓</span>
                          : <span className="muted">·</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted" style={{ marginTop: 10, fontSize: 11 }}>
            💡 برای تغییر مجوزها، از کارت نقش مربوط در همین صفحه استفاده کنید؛ این جدول فقط نمای است.
          </p>
        </Modal>
      )}
    </>
  );
}

function PermMatrix({ roleKey, granted, groups, system, onChanged }) {
  const [g, setG] = useState(new Set(granted));
  const save = async (perm, on) => {
    const next = new Set(g); on ? next.add(perm) : next.delete(perm);
    setG(next);
    try { await api.patchRole(roleKey, { perms: [...next] }); toast('ذخیره شد'); onChanged(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  return (
    <div className="grid" style={{ gap: 10, marginTop: 10 }}>
      {Object.entries(groups).map(([grp, items]) => (
        <div key={grp}>
          <div className="muted" style={{ marginBottom: 4 }}>{grp}</div>
          <div className="row" style={{ gap: 6 }}>
            {items.map(p => (
              <label key={p.key} className="badge" style={{ cursor: system ? 'not-allowed' : 'pointer', gap: 5 }}>
                <input type="checkbox" disabled={system}
                       checked={g.has(p.key)} onChange={e => save(p.key, e.target.checked)} />
                {p.label}
              </label>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function CreateRole({ onClose, onDone }) {
  const [f, setF] = useState({ key: '', label: '', desc: '', color: '#38b6ff', perms: [] });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try { await api.createRole({ key: f.key || undefined, label: f.label, desc: f.desc, color: f.color }); toast('نقش ساخته شد'); onDone(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  return (
    <Modal title="نقش جدید" onClose={onClose}>
      <div className="grid" style={{ gap: 10 }}>
        <input className="inp" dir="ltr" placeholder="key (انگلیسی: support_lead)"
               value={f.key} onChange={e => setF({ ...f, key: e.target.value })} />
        <input className="inp" placeholder="نام نمایشی"
               value={f.label} onChange={e => setF({ ...f, label: e.target.value })} />
        <input className="inp" placeholder="توضیح"
               value={f.desc} onChange={e => setF({ ...f, desc: e.target.value })} />
        <label className="row muted">رنگ:
          <input type="color" value={f.color} onChange={e => setF({ ...f, color: e.target.value })} />
        </label>
        <button className="btn primary" disabled={busy || !f.key || !f.label} onClick={save}>
          {busy ? '…' : 'ساخت نقش'}
        </button>
      </div>
    </Modal>
  );
}
