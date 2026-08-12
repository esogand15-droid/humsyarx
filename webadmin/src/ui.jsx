import React, { useEffect, useRef, useState } from 'react';

// ── Toast ─────────────────────────────────────────────
let _push;
export function toast(msg, kind = 'ok') { _push && _push(msg, kind); }

export function ToastHost() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    _push = (msg, kind) => {
      const id = Math.random().toString(36).slice(2);
      setItems(s => [...s, { id, msg, kind }]);
      setTimeout(() => setItems(s => s.filter(t => t.id !== id)), 3400);
    };
  }, []);
  return (
    <div className="toast-box">
      {items.map(t => <div key={t.id} className={`toast ${t.kind}`}>{t.msg}</div>)}
    </div>
  );
}

// ── Data states ───────────────────────────────────────
export function Loading({ rows = 4 }) {
  return <div className="grid" style={{ gap: 8 }}>{Array.from({ length: rows }).map((_, i) =>
    <div key={i} className="skel" style={{ height: 42 }} />)}</div>;
}
export function Empty({ icon = '🗂', text = 'موردی یافت نشد' }) {
  return <div className="center-state"><div style={{ fontSize: 30 }}>{icon}</div><div>{text}</div></div>;
}
export function ErrorState({ error, onRetry }) {
  return (
    <div className="center-state">
      <div style={{ fontSize: 28 }}>⚠️</div>
      <div style={{ marginBottom: 10 }}>{error}</div>
      {onRetry && <button className="btn" onClick={onRetry}>🔄 تلاش مجدد</button>}
    </div>
  );
}
export function NoPerm({ text = 'دسترسی لازم برای این بخش را ندارید' }) {
  return <div className="center-state"><div style={{ fontSize: 28 }}>🔒</div><div>{text}</div></div>;
}

// ── Badge ─────────────────────────────────────────────
export function B({ kind = '', children }) { return <span className={`badge ${kind}`}>{children}</span>; }

// ── Switch (WA2.3) ────────────────────────────────────
export function Switch({ on, onChange, disabled }) {
  return (
    <button type="button" className={`switch ${on ? 'on' : ''}`} disabled={disabled}
            onClick={() => onChange && onChange(!on)} aria-pressed={on}>
      <span className="knob" />
    </button>
  );
}

// ── DataTable (سرورساید) ──────────────────────────────
// props: columns[{k,label,render,width}], rows, rowKey, selectable,
// onSelect(ids), pager:{page,pages,total,onPage}, loading, onRow(row)
export function DataTable({ columns, rows, rowKey = 'id', selectable, onSelect,
  pager, loading, onRow, empty }) {
  const [sel, setSel] = useState(new Set());
  const toggle = (id) => {
    const s = new Set(sel); s.has(id) ? s.delete(id) : s.add(id);
    setSel(s); onSelect && onSelect([...s]);
  };
  const allIds = (rows || []).map(r => r[rowKey]);
  const allOn = allIds.length > 0 && allIds.every(id => sel.has(id));
  const toggleAll = () => {
    const s = allOn ? new Set() : new Set([...sel, ...allIds]);
    setSel(s); onSelect && onSelect([...s]);
  };
  return (
    <div className="panel tbl-wrap">
      <table className="tbl">
        <thead>
          <tr>
            {selectable && <th style={{ width: 30 }}>
              <input type="checkbox" checked={allOn} onChange={toggleAll} /></th>}
            {columns.map(c => <th key={c.k} style={c.width ? { width: c.width } : {}}>{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {loading && <tr><td colSpan={columns.length + 1}><Loading rows={3} /></td></tr>}
          {!loading && (!rows || !rows.length) &&
            <tr><td colSpan={columns.length + 1}>{empty || <Empty />}</td></tr>}
          {!loading && (rows || []).map(r => (
            <tr key={r[rowKey]} className={sel.has(r[rowKey]) ? 'sel' : ''}
                onClick={() => onRow && onRow(r)} style={onRow ? { cursor: 'pointer' } : {}}>
              {selectable && <td onClick={e => e.stopPropagation()}>
                <input type="checkbox" checked={sel.has(r[rowKey])} onChange={() => toggle(r[rowKey])} />
              </td>}
              {columns.map(c => (
                <td key={c.k} onClick={c.stop ? e => e.stopPropagation() : undefined}>
                  {c.render ? c.render(r) : (r[c.k] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {pager && (
        <div className="pager">
          <span>{Number(pager.total || 0).toLocaleString('fa')} مورد</span>
          <button className="btn sm" disabled={pager.page <= 1}
                  onClick={() => pager.onPage(pager.page - 1)}>‹ قبلی</button>
          <span>صفحه {pager.page} از {pager.pages || 1}</span>
          <button className="btn sm" disabled={pager.page >= pager.pages}
                  onClick={() => pager.onPage(pager.page + 1)}>بعدی ›</button>
        </div>
      )}
    </div>
  );
}

// ── Drawer / Modal ────────────────────────────────────
export function Drawer({ title, onClose, children, wide }) {
  useEffect(() => {
    const h = e => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="drawer" style={wide ? { width: 'min(640px,96vw)' } : {}}>
        <div className="row" style={{ marginBottom: 12 }}>
          <b style={{ fontSize: 15 }}>{title}</b>
          <span className="spacer" />
          <button className="btn sm" onClick={onClose}>✕ بستن (Esc)</button>
        </div>
        {children}
      </div>
    </>
  );
}
export function Modal({ title, onClose, children }) {
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="modal">
        <div className="row" style={{ marginBottom: 12 }}>
          <b style={{ fontSize: 15 }}>{title}</b>
          <span className="spacer" />
          <button className="btn sm" onClick={onClose}>✕</button>
        </div>
        {children}
      </div>
    </>
  );
}
export function Confirm({ text, onYes, onNo, danger }) {
  return (
    <Modal title="تأیید عملیات" onClose={onNo}>
      <p style={{ color: 'var(--txt2)', marginBottom: 16, lineHeight: 1.8 }}>{text}</p>
      <div className="row">
        <button className={`btn ${danger ? 'danger' : 'primary'}`} onClick={onYes}>تأیید</button>
        <button className="btn" onClick={onNo}>انصراف</button>
      </div>
    </Modal>
  );
}

// ── Command Palette 2.0 (Ctrl+K) — WA2.5: جست‌وجوی سراسری اختیاری ──
// props: open, onClose(bool), commands, search?(q)→[{group,icon,label,hint,go}], go?(path)
export function Palette({ open, onClose, commands, search, go }) {
  const [q, setQ] = useState('');
  const [idx, setIdx] = useState(0);
  const [results, setResults] = useState(null);   // نتایج جست‌وجوی سراسری
  const [searching, setSearching] = useState(false);
  const ref = useRef(null);
  const debRef = useRef(null);

  useEffect(() => { if (open) { setQ(''); setIdx(0); setResults(null); setTimeout(() => ref.current && ref.current.focus(), 30); } }, [open]);
  useEffect(() => {
    const h = e => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); onClose(!open); }
      if (e.key === 'Escape' && open) onClose(false);
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [open, onClose]);

  // WA2.5 — جست‌وجوی سراسری با debounce
  useEffect(() => {
    if (!search) return;
    clearTimeout(debRef.current);
    if (q.trim().length < 2) { setResults(null); setSearching(false); return; }
    setSearching(true);
    debRef.current = setTimeout(async () => {
      try { setResults(await search(q.trim())); }
      catch { setResults([]); }
      setSearching(false);
    }, 300);
    return () => clearTimeout(debRef.current);
  }, [q, search]);

  if (!open) return null;

  const list = commands.filter(c => !q || c.label.includes(q) || (c.hint || '').includes(q));
  const flat = results || [];
  const total = q.trim().length >= 2 && results ? flat.length : list.length;
  const runAt = (i) => {
    if (q.trim().length >= 2 && results) {
      const it = flat[i];
      if (it) { it.run ? it.run() : (it.go && go && go(it.go)); onClose(false); }
    } else if (list[i]) { list[i].run(); onClose(false); }
  };

  return (
    <>
      <div className="scrim" onClick={() => onClose(false)} />
      <div className="palette">
        <input ref={ref} placeholder="جست‌وجو در همه‌چیز… (کاربر، تیکت، سؤال، محتوا، لاگ)"
               value={q}
               onChange={e => { setQ(e.target.value); setIdx(0); }}
               onKeyDown={e => {
                 if (e.key === 'ArrowDown') { e.preventDefault(); setIdx(i => Math.min(i + 1, total - 1)); }
                 if (e.key === 'ArrowUp') { e.preventDefault(); setIdx(i => Math.max(i - 1, 0)); }
                 if (e.key === 'Enter') runAt(idx);
               }} />
        <div style={{ maxHeight: 340, overflowY: 'auto' }}>
          {!(q.trim().length >= 2 && results) && list.map((c, i) => (
            <div key={c.label} className={`opt ${i === idx ? 'on' : ''}`}
                 onMouseEnter={() => setIdx(i)}
                 onClick={() => { c.run(); onClose(false); }}>
              <span>{c.icon}</span><span>{c.label}</span>
              <span className="spacer" /><span className="muted">{c.hint}</span>
            </div>
          ))}
          {q.trim().length >= 2 && results && flat.length === 0 && !searching &&
            <div className="center-state">نتیجه‌ای برای «{q}» نیست</div>}
          {q.trim().length >= 2 && results && (() => {
            const groups = [];
            let lastGroup = null;
            return flat.map((it, i) => {
              const head = it.group !== lastGroup
                ? <div key={'g' + i} className="pal-sec">{it.group}</div> : null;
              lastGroup = it.group;
              return (
                <React.Fragment key={i}>
                  {head}
                  <div className={`opt ${i === idx ? 'on' : ''}`}
                       onMouseEnter={() => setIdx(i)}
                       onClick={() => runAt(i)}>
                    <span>{it.icon}</span>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.label}</span>
                    <span className="spacer" /><span className="muted">{it.hint}</span>
                  </div>
                </React.Fragment>
              );
            });
          })()}
          {q.trim().length >= 2 && searching && <div className="center-state" style={{ padding: 18 }}>… در حال جست‌وجو</div>}
          {!list.length && !(q.trim().length >= 2) && <div className="center-state">نتیجه‌ای نیست</div>}
        </div>
      </div>
    </>
  );
}

export function Stat({ icon, label, value, tint = 'var(--acc)' }) {
  return (
    <div className="panel stat">
      <div className="ic" style={{ background: `${tint}1c`, border: `1px solid ${tint}44` }}>{icon}</div>
      <div><div className="v">{value ?? '—'}</div><div className="l">{label}</div></div>
    </div>
  );
}
