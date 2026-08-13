import React, { useEffect, useMemo, useRef, useState } from 'react';

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
export function Empty({ icon = '🗂', text = 'موردی یافت نشد', children }) {
  return (
    <div className="center-state">
      <div style={{ fontSize: 30 }} role="img">{icon}</div>
      <div>{text}</div>
      {children && <div style={{ marginTop: 12 }}>{children}</div>}
    </div>
  );
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

// ── DataTable v2 (سرورساید + قابلیت‌های اختیاری دسکتاپی) ──────
// props: columns[{k,label,render,width,sortable,sortVal}], rows, rowKey,
// selectable, onSelect(ids), pager:{page,pages,total,onPage}, loading,
// onRow(row), empty, colToggle(bool → منوی نمایش/پنهان ستون‌ها)
// 🌊 W-Design 3 — sortable کلاینت‌ساید opt-in + نمایش ستون‌ها؛ رفتار قبلی دست‌نخورده
export function DataTable({ columns, rows, rowKey = 'id', selectable, onSelect,
  pager, loading, onRow, empty, colToggle }) {
  const [sel, setSel] = useState(new Set());
  const [sort, setSort] = useState(null);               // {k, dir: 'asc'|'desc'}
  const [hidden, setHidden] = useState(new Set());      // کلید ستون‌های پنهان
  const [colMenu, setColMenu] = useState(false);
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

  const visCols = columns.filter(c => !hidden.has(c.k));
  const sorted = useMemo(() => {
    if (!sort) return rows || [];
    const col = columns.find(c => c.k === sort.k);
    if (!col || !col.sortable) return rows || [];
    const val = (r) => col.sortVal ? col.sortVal(r) : r[col.k];
    return [...(rows || [])].sort((a, b) => {
      const va = val(a); const vb = val(b);
      const na = Number(va); const nb = Number(vb);
      let cmp;
      if (va !== '' && vb !== '' && !isNaN(na) && !isNaN(nb)) cmp = na - nb;
      else cmp = String(va ?? '').localeCompare(String(vb ?? ''), 'fa');
      return sort.dir === 'asc' ? cmp : -cmp;
    });
  }, [rows, sort, columns]);

  const clickSort = (c) => {
    if (!c.sortable) return;
    setSort(s => !s || s.k !== c.k ? { k: c.k, dir: 'asc' }
      : s.dir === 'asc' ? { k: c.k, dir: 'desc' } : null);
  };

  return (
    <div className="panel tbl-wrap">
      {colToggle && (
        <div className="tbl-tools">
          <button className="btn sm" onClick={() => setColMenu(v => !v)}
                  aria-expanded={colMenu} aria-label="نمایش ستون‌ها">☰ ستون‌ها</button>
          {colMenu && (
            <div className="colmenu" role="menu">
              {columns.map(c => (
                <label key={c.k} className="colmenu-item">
                  <input type="checkbox" checked={!hidden.has(c.k)}
                         onChange={() => setHidden(h => {
                           const s = new Set(h);
                           s.has(c.k) ? s.delete(c.k) : s.add(c.k);
                           return s;
                         })} />
                  <span>{c.label || c.k}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      )}
      <table className="tbl">
        <thead>
          <tr>
            {selectable && <th style={{ width: 30 }}>
              <input type="checkbox" checked={allOn} onChange={toggleAll}
                     aria-label="انتخاب همه" /></th>}
            {visCols.map(c => (
              <th key={c.k} style={{ ...(c.width ? { width: c.width } : {}),
                    ...(c.sortable ? { cursor: 'pointer', userSelect: 'none' } : {}) }}
                  onClick={() => clickSort(c)}
                  aria-sort={sort?.k === c.k ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                  title={c.sortable ? 'مرتب‌سازی' : undefined}>
                {c.label}{c.sortable && (
                  <span className="sort-ic">{sort?.k === c.k ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ' ⇅'}</span>)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && <tr><td colSpan={visCols.length + 1}><Loading rows={3} /></td></tr>}
          {!loading && (!sorted || !sorted.length) &&
            <tr><td colSpan={visCols.length + 1}>{empty || <Empty />}</td></tr>}
          {!loading && (sorted || []).map(r => (
            <tr key={r[rowKey]} className={sel.has(r[rowKey]) ? 'sel' : ''}
                aria-selected={sel.has(r[rowKey]) || undefined}
                onClick={() => onRow && onRow(r)} style={onRow ? { cursor: 'pointer' } : {}}>
              {selectable && <td onClick={e => e.stopPropagation()}>
                <input type="checkbox" checked={sel.has(r[rowKey])} onChange={() => toggle(r[rowKey])}
                       aria-label="انتخاب ردیف" />
              </td>}
              {visCols.map(c => (
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
      <div className="drawer" role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : 'پانل'}
           style={wide ? { width: 'min(660px,96vw)' } : {}}>
        <div className="row" style={{ marginBottom: 12 }}>
          <b style={{ fontSize: 15 }}>{title}</b>
          <span className="spacer" />
          <button className="btn sm" onClick={onClose} aria-label="بستن (Esc)">✕ بستن (Esc)</button>
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
      <div className="modal" role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : 'مودال'}>
        <div className="row" style={{ marginBottom: 12 }}>
          <b style={{ fontSize: 15 }}>{title}</b>
          <span className="spacer" />
          <button className="btn sm" onClick={onClose} aria-label="بستن">✕</button>
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

// 🌊 W-Design 4 — delta اختیاری: ترند vs دوره‌ی قبل (▲/▼ خواب‌دار)
export function Stat({ icon, label, value, tint = 'var(--acc)', delta, hint }) {
  return (
    <div className="panel stat">
      <div className="ic" style={{ background: `${tint}1c`, border: `1px solid ${tint}44` }}>{icon}</div>
      <div style={{ minWidth: 0 }}>
        <div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
          <div className="v">{value ?? '—'}</div>
          {delta != null && (
            <span className={`trend ${delta >= 0 ? 'up' : 'down'}`}>
              {delta >= 0 ? '▲' : '▼'} {Number(Math.abs(delta)).toLocaleString('fa')}٪
            </span>
          )}
        </div>
        <div className="l">{label}</div>
        {hint && <div className="l" style={{ color: 'var(--txt3)', fontSize: 'var(--fs-caption)' }}>{hint}</div>}
      </div>
    </div>
  );
}
