import React, { useEffect, useState } from 'react';
import { api, errText } from './api.js';
import { B, Modal, toast } from './ui.jsx';

/** Generic per-admin saved views. The backend owns identity/scope; pages own filters. */
export default function SavedViews({ scope, filters, onApply, label = 'نماهای ذخیره‌شده' }) {
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const load = async () => {
    try { setItems((await api.savedFilters(scope)).filters || []); }
    catch { setItems([]); }
  };
  useEffect(() => { load(); }, [scope]);
  const save = async () => {
    if (!name.trim()) return;
    try {
      await api.saveFilter({ name: name.trim(), scope, filters });
      toast('نمای فعلی ذخیره شد'); setName(''); setOpen(false); load();
    } catch (e) { toast(errText(e), 'err'); }
  };
  const remove = async id => {
    try { await api.delFilter(id); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  return <>
    <div className="row saved-views" style={{ marginBottom: 10, gap: 6 }}>
      <span className="muted">⏱ {label}:</span>
      {(items || []).map(item => <span className="chip" key={item.id}>
        <a onClick={() => onApply(item.filters || {})}>{item.name}</a>
        <button className="chip-x" aria-label={`حذف نمای ${item.name}`} onClick={() => remove(item.id)}>✕</button>
      </span>)}
      {items && !items.length && <B>هنوز نمایی نیست</B>}
      <button className="btn sm" onClick={() => setOpen(true)}>💾 ذخیره نمای فعلی</button>
    </div>
    {open && <Modal title="ذخیره نمای فعلی" onClose={() => setOpen(false)}>
      <input className="inp" style={{ width: '100%' }} placeholder="نام نما…" value={name} onChange={e => setName(e.target.value)} />
      <div className="row" style={{ marginTop: 12 }}><button className="btn primary" disabled={!name.trim()} onClick={save}>ذخیره</button>
        <button className="btn" onClick={() => setOpen(false)}>انصراف</button></div>
    </Modal>}
  </>;
}
