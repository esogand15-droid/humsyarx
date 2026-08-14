import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Empty, B, toast, Modal } from '../ui.jsx';

// 🛡 مرکز کنترل RBAC — نقش‌ها + ماتریس مجوزها (require_perm واقعی بک‌اند)
export default function Rbac({ me }) {
  const [roles, setRoles] = useState(null);
  const [perms, setPerms] = useState(null);
  const [err, setErr] = useState('');
  const [create, setCreate] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [editRole, setEditRole] = useState(null);
  const canAssign = !!me?.is_owner || (me?.perms || []).includes('users.manage');

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
        {canAssign && <button className="btn" onClick={() => setAssignOpen(true)}>👤 تخصیص نقش به کاربر</button>}
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
              <button className="btn sm" title="ویرایش مشخصات نقش" onClick={() => setEditRole(r)}>✏️</button>
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
      {editRole && <EditRole role={editRole} onClose={() => setEditRole(null)}
                             onDone={() => { setEditRole(null); load(); }} />}
      {assignOpen && <AssignRoles roles={roles} onClose={() => setAssignOpen(false)} />}
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

function PermMatrix({ roleKey, granted, groups, onChanged }) {
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
              <label key={p.key} className="badge" style={{ cursor: 'pointer', gap: 5 }}>
                <input type="checkbox"
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


function EditRole({ role, onClose, onDone }) {
  const [f, setF] = useState({
    label: role.label || '', desc: role.desc || '', icon: role.icon || '🛡',
    color: role.color || '#70A7FF', priority: role.priority ?? 90,
    active: role.active !== false, visible: role.visible !== false,
  });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await api.patchRole(role.key, { ...f, priority: Number(f.priority) || 90 });
      toast('مشخصات نقش ذخیره شد ✅'); onDone();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  return (
    <Modal title={`✏️ ویرایش نقش — ${role.label || role.key}`} onClose={onClose}>
      <div className="grid" style={{ gap: 10 }}>
        <div className="row">
          <input className="inp" style={{ width: 72, textAlign: 'center' }} maxLength={4}
                 value={f.icon} onChange={e => setF({ ...f, icon: e.target.value })} title="آیکون" />
          <input className="inp" style={{ flex: 1 }} value={f.label}
                 onChange={e => setF({ ...f, label: e.target.value })} placeholder="نام نمایشی" />
          <input type="color" value={f.color} onChange={e => setF({ ...f, color: e.target.value })} />
        </div>
        <textarea className="inp" rows={3} value={f.desc}
                  onChange={e => setF({ ...f, desc: e.target.value })} placeholder="توضیح نقش" />
        <label className="fld"><span>اولویت نمایش</span>
          <input className="inp" type="number" min="1" max="999" value={f.priority}
                 onChange={e => setF({ ...f, priority: e.target.value })} /></label>
        <div className="row">
          <label className="badge"><input type="checkbox" checked={f.active}
            onChange={e => setF({ ...f, active: e.target.checked })} /> نقش فعال</label>
          <label className="badge"><input type="checkbox" checked={f.visible}
            onChange={e => setF({ ...f, visible: e.target.checked })} /> قابل‌نمایش</label>
        </div>
        <div className="row">
          <button className="btn primary" disabled={busy || f.label.trim().length < 2} onClick={save}>
            {busy ? '⏳ …' : '💾 ذخیره'}</button>
          <button className="btn" onClick={onClose}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}


function AssignRoles({ roles, onClose }) {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState(null);
  const [picked, setPicked] = useState(null);
  const [current, setCurrent] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [scope, setScope] = useState('');
  const [intakes, setIntakes] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.rbacIntakes().then(r => setIntakes(r.intakes || [])).catch(() => {}); }, []);
  const search = async () => {
    if (q.trim().length < 2) return toast('حداقل ۲ حرف یا آیدی وارد کنید', 'err');
    setBusy(true);
    try { setHits((await api.users({ page: 1, per_page: 20, q: q.trim() })).users || []); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const choose = async (u) => {
    setBusy(true); setPicked(u); setCurrent(null);
    try {
      const r = await api.roleOf(u.id);
      setCurrent(r); setSelected(new Set(r.keys || [])); setScope(r.scope_intake || '');
    } catch (e) { toast(errText(e), 'err'); setPicked(null); }
    setBusy(false);
  };
  const toggle = (key) => setSelected(s => {
    const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n;
  });
  const needsScope = roles.some(r => selected.has(r.key) &&
    (r.key === 'content_scoped' || r.perms?.includes('content.scoped') || r.perms?.includes('grades.scoped')));
  const save = async () => {
    const before = new Set(current?.keys || []);
    const add = [...selected].filter(k => !before.has(k));
    const remove = [...before].filter(k => !selected.has(k));
    if (needsScope && !scope) return toast('برای نقش محدود، ورودی را انتخاب کنید', 'err');
    setBusy(true);
    try {
      const r = await api.assignRoles(picked.id, { add, remove, scope_intake: needsScope ? scope : '' });
      setCurrent(r); setSelected(new Set(r.keys || [])); setScope(r.scope_intake || '');
      toast('نقش‌ها و scope کاربر ذخیره شد ✅');
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  return (
    <Modal title="👤 تخصیص نقش و محدوده به کاربر" onClose={onClose}>
      {!picked ? (<>
        <div className="row">
          <input className="inp" style={{ flex: 1 }} value={q}
                 onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && search()}
                 placeholder="نام، یوزرنیم، شماره دانشجویی یا آیدی عددی…" />
          <button className="btn primary" disabled={busy} onClick={search}>🔎 جست‌وجو</button>
        </div>
        {hits && <div className="grid" style={{ gap: 6, marginTop: 10, maxHeight: '48vh', overflowY: 'auto' }}>
          {!hits.length && <Empty text="کاربری یافت نشد" />}
          {hits.map(u => <button key={u.id} className="pick" onClick={() => choose(u)}>
            <span>👤</span><span style={{ flex: 1, textAlign: 'right' }}>
              <b>{u.display_name || u.name}</b><span className="muted"> · {u.student_id || `#${u.id}`}</span>
            </span><span>‹</span>
          </button>)}
        </div>}
      </>) : !current ? <Loading rows={3} /> : (<>
        <div className="row panel panel-pad" style={{ background: 'var(--bg)', marginBottom: 10 }}>
          <b>{picked.display_name || picked.name}</b><span className="code">#{picked.id}</span>
          <span className="spacer" /><button className="btn sm" onClick={() => { setPicked(null); setCurrent(null); }}>تغییر کاربر</button>
        </div>
        <div className="grid" style={{ gap: 7, maxHeight: '42vh', overflowY: 'auto' }}>
          {roles.map(r => <label key={r.key} className={`pick ${selected.has(r.key) ? 'on' : ''}`}>
            <input type="checkbox" checked={selected.has(r.key)} onChange={() => toggle(r.key)} />
            <span style={{ width: 10, height: 10, borderRadius: 3, background: r.color || 'var(--acc)' }} />
            <span style={{ flex: 1 }}><b>{r.icon || '🛡'} {r.label || r.key}</b>
              <span className="muted code" style={{ marginRight: 6 }}>{r.key}</span></span>
          </label>)}
        </div>
        {needsScope && <label className="fld" style={{ marginTop: 10 }}><span>ورودی مجاز *</span>
          <select className="inp" value={scope} onChange={e => setScope(e.target.value)}>
            <option value="">انتخاب ورودی…</option>
            {intakes.map(i => <option key={i.code} value={i.code}>{i.label || i.code}</option>)}
          </select></label>}
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn primary" disabled={busy} onClick={save}>{busy ? '⏳ …' : '💾 ذخیره تخصیص'}</button>
          <button className="btn" onClick={onClose}>بستن</button>
        </div>
      </>)}
    </Modal>
  );
}
