import React, { useEffect, useMemo, useState } from 'react';
import { api, errText } from '../api.js';
import { DataTable, Loading, ErrorState, B, FaDateTime, FilterBar, PageHeader, ScopeBadge, toast, Drawer, Confirm, Empty, Switch, Modal, NoPerm } from '../ui.jsx';
import SavedViews from '../SavedViews.jsx';
import { PersianDatePicker } from '../PersianDatePicker.jsx';
import { queryNumber, readHashQuery, writeHashQuery } from '../urlState.js';

const fa = (n) => Number(n ?? 0).toLocaleString('fa-IR');
const DIFF = { easy: ['آسان', 'ok'], medium: ['متوسط', 'warn'], hard: ['سخت', 'bad'] };
const SRC = { bot: '🤖 ربات', webapp: '📱 مینی‌اپ', user: '👤 کاربر', web_import: '📥 درون‌ریزی وب' };

// 🌊 موج Q-Import — پارس خطی (هر خط = یک سؤال):
// درس | مبحث | سختی | متن سؤال | گزینه۱ ;; گزینه۲ ;; … | شماره گزینه صحیح | توضیح
const DIFF_ALIASES = { 'آسان': 'easy', 'easy': 'easy', 'متوسط': 'medium', 'medium': 'medium', 'سخت': 'hard', 'hard': 'hard' };
function parseImportText(text) {
  const rows = [];
  String(text || '').split('\n').forEach((ln, li) => {
    const t = ln.trim();
    if (!t || t.startsWith('#')) return;                    // خط خالی/کامنت
    const p = t.split('|').map(s => s.trim());
    const err = (m) => rows.push({ li: li + 1, ok: false, error: m, raw: t.slice(0, 60) });
    if (p.length < 6) return err('حداقل ۶ بخش با | لازم است');
    const [lesson, topic, diffRaw, question, opsRaw, corRaw, ...exRest] = p;
    const difficulty = DIFF_ALIASES[diffRaw] || '';
    const options = opsRaw.split(';;').map(s => s.trim()).filter(Boolean);
    const correct = parseInt(corRaw, 10) - 1;               // ورودی انسانی ۱-مبنا
    if (!lesson) return err('درس خالی است');
    if (!difficulty) return err('سختی نامعتبر (آسان/متوسط/سخت)');
    if (question.length < 5) return err('متن سؤال خیلی کوتاه است');
    if (options.length < 2 || options.length > 6) return err('گزینه‌ها باید ۲ تا ۶ باشند (با ;; جدا کنید)');
    if (!(correct >= 0 && correct < options.length)) return err('شماره گزینه صحیح خارج از محدوده است');
    rows.push({ li: li + 1, ok: true,
      item: { lesson, topic, difficulty, question, options, correct, explanation: exRest.join(' | ') } });
  });
  return rows;
}

// 🧪 صف بازبینی سوالات (scope-aware) + ⚡ WA2.4 تأیید/رد گروهی
// 🌊 موج Q-Editor — کشوی جزئیات کامل + ویرایش پیش از تأیید (PATCH واقعی) + فیلترها
export default function Questions({ route = '', go }) {
  const initial = readHashQuery();
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [intakes, setIntakes] = useState([]);
  const [scopeKind, setScopeKind] = useState('global');
  const [intake, setIntake] = useState(initial.get('intake') || '');
  const [sel, setSel] = useState([]);
  const [visibleColumns, setVisibleColumns] = useState([]);
  const [confirm, setConfirm] = useState(null);
  const [bulkResult, setBulkResult] = useState(null);
  const [metadataBulk, setMetadataBulk] = useState(null);
  const [detail, setDetail] = useState(null);        // ردیف باز در کشو
  const wantsCreate = new URLSearchParams(route.split('?')[1] || '').get('create') === '1';
  const [createOpen, setCreateOpen] = useState(wantsCreate);
  const [importOpen, setImportOpen] = useState(false); // 🌊 Q-Import wizard
  const [q, setQ] = useState(initial.get('q') || '');
  const [query, setQuery] = useState(initial.get('q') || '');
  const [status, setStatus] = useState(initial.get('status') || 'pending');
  const [fdiff, setFdiff] = useState(initial.get('difficulty') || '');
  const [fsrc, setFsrc] = useState(initial.get('source') || '');
  const [author, setAuthor] = useState(initial.get('author') || '');
  const [dateFrom, setDateFrom] = useState(initial.get('date_from') || '');
  const [dateTo, setDateTo] = useState(initial.get('date_to') || '');
  const [sortBy, setSortBy] = useState(initial.get('sort_by') || 'created_at');
  const [sortDir, setSortDir] = useState(initial.get('sort_dir') || 'desc');
  const [page, setPage] = useState(queryNumber(initial, 'page', 1));
  const [total, setTotal] = useState(0);
  const LIMIT = 30;
  useEffect(() => { if (wantsCreate) setCreateOpen(true); }, [wantsCreate]);

  const load = async () => {
    setErr('');
    try {
      const r = await api.questions({
        status, intake, q, difficulty: fdiff, source: fsrc, author, date_from: dateFrom, date_to: dateTo,
        sort_by: sortBy, sort_dir: sortDir, skip: (page - 1) * LIMIT, limit: LIMIT,
      });
      setRows(r.questions || []); setTotal(Number(r.total || 0));
    } catch (e) { if (e.status === 403) setPermErr(true); else setErr(errText(e)); }
  };
  useEffect(() => {
    api.questionIntakes().then(r => {
      setIntakes(r.intakes || []); setScopeKind(r.scope_kind || 'global');
      if (r.scope_kind === 'scoped') setIntake(r.scope_intake || r.intakes?.[0]?.code || '');
    }).catch(e => { if (e.status === 403) setPermErr(true); else setErr(errText(e)); });
  }, []);
  useEffect(() => { const t = setTimeout(() => { setQ(query.trim()); setPage(1); }, 350); return () => clearTimeout(t); }, [query]);
  useEffect(() => { writeHashQuery('/questions', { status: status !== 'pending' ? status : '', intake, q: query,
    difficulty: fdiff, source: fsrc, author, date_from: dateFrom, date_to: dateTo,
    sort_by: sortBy !== 'created_at' ? sortBy : '', sort_dir: sortDir !== 'desc' ? sortDir : '',
    page: page > 1 ? page : '', create: createOpen ? 1 : '' });
  }, [status, intake, query, fdiff, fsrc, author, dateFrom, dateTo, sortBy, sortDir, page, createOpen]);
  useEffect(() => { setRows(null); setSel([]); load(); }, [intake, status, q, fdiff, fsrc, author, dateFrom, dateTo, sortBy, sortDir, page]);

  const act = async (qid, kind) => {
    try {
      await (kind === 'approve' ? api.caQuestionApprove(qid) : api.caQuestionReject(qid));
      toast(kind === 'approve' ? 'تأیید شد ✅' : 'رد شد');
      setDetail(null);
      load();
    } catch (e) { toast(errText(e), 'err'); }
  };

  const bulk = async (action, ids = sel, patch = null) => {
    if (!ids.length) return;
    try {
      const r = await api.questionsBulk(action, ids, patch);
      setBulkResult({ ...r, action, patch });
      toast(`${fa(r.done)} موفق · ${fa(r.skipped?.length || 0)} ردشده · ${fa(r.failed?.length || 0)} ناموفق`, r.failed?.length ? 'err' : 'ok');
      setSel([]); load();
    } catch (e) { toast(errText(e), 'err'); }
  };

  const vis = rows || [];

  if (permErr) return <NoPerm text="بازبینی سؤال نیازمند مجوز questions.review یا questions.review_scoped است" />;
  if (err) return <ErrorState error={err} onRetry={load} />;

  const cols = [
    { k: 'question', label: 'سؤال', render: r => (
      <div style={{ maxWidth: 340, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {r.question || r.text}</div>) },
    { k: 'lesson', label: 'درس' },
    { k: 'topic', label: 'مبحث' },
    { k: 'difficulty', label: 'سختی', sortable: true, sortVal: r => r.difficulty || '',
      render: r => { const [l, kk] = DIFF[r.difficulty] || [r.difficulty || '—', '']; return <B kind={kk}>{l}</B>; } },
    { k: 'creator', label: 'طراح', stop: true, render: r => (
      <button className="btn sm" disabled={!r.creator_id} onClick={() => r.creator_id && go?.(`/users?q=${r.creator_id}`)}>
        {r.creator_name || '—'}<span className="muted" style={{ display: 'block' }}>{SRC[r.source] || r.source || ''}</span></button>) },
    { k: 'intake', label: 'ورودی', render: r => r.intake || <B>سراسری</B> },
    { k: 'approved', label: 'وضعیت', render: r => <B kind={r.approved ? 'ok' : 'warn'}>{r.approved ? 'تأییدشده' : 'در انتظار'}</B> },
    { k: 'attempts', label: 'تلاش/دقت', sortable: true, render: r => <span>{fa(r.attempts)} · <B kind={r.accuracy >= 70 ? 'ok' : r.attempts ? 'warn' : ''}>{fa(r.accuracy)}٪</B></span> },
    { k: 'reports', label: 'گزارش', render: r => r.reports ? <B kind="bad">{fa(r.reports)}</B> : '—' },
    { k: 'created_at', label: 'ایجاد', sortable: true, render: r => <FaDateTime value={r.created_at} /> },
    { k: 'ops', label: '', stop: true, render: r => {
      const id = r.id || r._id;
      return (
        <div className="row" style={{ gap: 4 }}>
          <button className="btn sm" title="مشاهده" aria-label="مشاهده سؤال" onClick={() => setDetail(r)}>👁</button>
          {!r.approved && <><button className="btn sm ok" title="تأیید" aria-label="تأیید سؤال" onClick={() => act(id, 'approve')}>✅</button>
          <button className="btn sm danger" title="رد" aria-label="رد سؤال" onClick={() => act(id, 'reject')}>❌</button></>}
        </div>);
    } },
  ];

  return (
    <>
      <PageHeader title="بازبینی سؤال‌ها" description="بازبینی، ویرایش، تأیید و رد تکی یا گروهی با حفظ محدوده ورودی" actions={<>
        <button className="btn primary" onClick={() => setCreateOpen(true)}>➕ ساخت سؤال</button>
        <button className="btn" onClick={() => setImportOpen(true)}>📥 درون‌ریزی گروهی</button>
        <button className="btn" onClick={() => api.exportQuestionsCsv({ status, intake, q: query, difficulty: fdiff, source: fsrc, author, date_from: dateFrom, date_to: dateTo, sort_by: sortBy, sort_dir: sortDir })}>📤 CSV همین فیلترها</button>
        {status === 'pending' && sel.length > 0 && <>
          <span className="badge acc">{fa(sel.length)} انتخاب‌شده</span>
          <button className="btn sm ok" onClick={() => setConfirm({ action: 'approve', n: sel.length })}>✅ تأیید گروهی</button>
          <button className="btn sm danger" onClick={() => setConfirm({ action: 'reject', n: sel.length })}>❌ رد گروهی</button>
          <button className="btn sm" onClick={() => setMetadataBulk({ lesson: '', topic: '', difficulty: '' })}>✏️ metadata گروهی</button>
        </>}
      </>} />

      <FilterBar>
        <select className="inp" value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}>
          <option value="pending">در انتظار بازبینی</option><option value="approved">تأییدشده</option><option value="all">همه سؤال‌ها</option>
        </select>
        <select className="inp" value={intake} disabled={scopeKind === 'scoped'} onChange={e => { setIntake(e.target.value); setPage(1); }}>
          {scopeKind === 'global' && <option value="">🌐 سؤالات سراسری</option>}
          {intakes.map(i => <option key={i.code} value={i.code}>🏷 {i.label || i.code}</option>)}
        </select>
        <input className="inp" style={{ flex: 1, minWidth: 180 }} placeholder="🔎 متن/درس/مبحث/طراح…"
               value={query} onChange={e => setQuery(e.target.value)} />
        <select className="inp" value={fdiff} onChange={e => { setFdiff(e.target.value); setPage(1); }}>
          <option value="">همه‌ی سختی‌ها</option>
          <option value="easy">آسان</option><option value="medium">متوسط</option><option value="hard">سخت</option>
        </select>
        <select className="inp" value={fsrc} onChange={e => { setFsrc(e.target.value); setPage(1); }}>
          <option value="">همه‌ی منابع</option>
          <option value="webapp">📱 مینی‌اپ</option><option value="bot">🤖 ربات</option><option value="web_import">📥 وب‌ادمین</option>
        </select>
        <input className="inp" style={{ width: 150 }} placeholder="طراح یا ID…" value={author} onChange={e => { setAuthor(e.target.value); setPage(1); }} />
        <label className="row"><span className="muted">از</span><PersianDatePicker value={dateFrom} onChange={value => { setDateFrom(value); setPage(1); }} placeholder="تاریخ شمسی" /></label>
        <label className="row"><span className="muted">تا</span><PersianDatePicker value={dateTo} onChange={value => { setDateTo(value); setPage(1); }} placeholder="تاریخ شمسی" /></label>
        <B kind="acc">{fa(total)} نتیجه</B>
      </FilterBar>
      <div className="muted" style={{ margin: '-4px 0 10px' }}>رد سؤال در domain فعلی به‌معنای حذف پیشنهاد و اطلاع به طراح است؛ آرشیو «ردشده»‌ی مستقلی در پایگاه داده وجود ندارد.</div>

      <SavedViews scope="questions" filters={{ status, intake, q: query, difficulty: fdiff, source: fsrc, author, date_from: dateFrom, date_to: dateTo, sortBy, sortDir }}
        columns={visibleColumns} sort={{ key: sortBy, dir: sortDir }} onApply={(f, item) => {
        setStatus(f.status || 'pending'); setIntake(f.intake || ''); setQuery(f.q || '');
        setFdiff(f.difficulty || ''); setFsrc(f.source || ''); setAuthor(f.author || ''); setDateFrom(f.date_from || ''); setDateTo(f.date_to || '');
        setSortBy(f.sortBy || item.sort?.key || 'created_at'); setSortDir(f.sortDir || item.sort?.dir || 'desc'); setVisibleColumns(item.columns || []); setPage(1);
      }} />

      {!rows ? <Loading /> : (
        <DataTable columns={cols} rows={vis} rowKey="id"
          selectable={status === 'pending'} onSelect={setSel} onRow={setDetail} colToggle
          visibleColumns={visibleColumns} onColumnsChange={setVisibleColumns}
          sortState={{ k: sortBy === 'attempt_count' ? 'attempts' : sortBy, dir: sortDir }} onSort={next => {
            setSortBy(next?.k === 'attempts' ? 'attempt_count' : next?.k || 'created_at');
            setSortDir(next?.dir || 'desc'); setPage(1);
          }}
          pager={{ page, pages: Math.max(1, Math.ceil(total / LIMIT)), total, onPage: setPage }}
          empty={<Empty icon="🎉" text={status === 'pending' ? 'صف بازبینی خالی است' : 'سؤالی با این فیلترها نیست'} />} />
      )}

      {detail && (
        <QuestionDrawer row={detail} readonly={!!detail.approved}
          onClose={() => setDetail(null)}
          onAction={(kind) => act(detail.id || detail._id, kind)}
          onSaved={() => { load(); }} />
      )}

      {confirm && (
        <Confirm text={`${confirm.action === 'approve' ? 'تأیید' : 'رد'} ${fa(confirm.n)} سؤال انتخاب‌شده؟ (فقط موارد داخل scope شما پردازش می‌شوند)`}
                 danger={confirm.action === 'reject'}
                 onYes={async () => { await bulk(confirm.action); setConfirm(null); }}
                 onNo={() => setConfirm(null)} />
      )}
      {bulkResult && <Modal title="گزارش عملیات گروهی سؤال" onClose={() => setBulkResult(null)}>
        <div className="row"><B kind="ok">موفق: {fa(bulkResult.succeeded?.length || 0)}</B><B>ردشده: {fa(bulkResult.skipped?.length || 0)}</B><B kind="bad">ناموفق: {fa(bulkResult.failed?.length || 0)}</B></div>
        {[...(bulkResult.skipped || []).map(x => ({ ...x, message: x.reason })), ...(bulkResult.failed || []).map(x => ({ ...x, message: x.error }))].slice(0, 30)
          .map((x, i) => <div className="row" key={`${x.id}-${i}`}><span className="code">{x.id}</span><span className="muted">{x.message}</span></div>)}
        {!!bulkResult.failed?.length && <button className="btn" onClick={() => bulk(bulkResult.action, bulkResult.failed.map(x => x.id), bulkResult.patch)}>↻ تلاش مجدد ناموفق‌ها</button>}
      </Modal>}
      {metadataBulk && <Modal title={`✏️ ویرایش metadata برای ${fa(sel.length)} سؤال`} onClose={() => setMetadataBulk(null)}>
        <div className="muted">فقط فیلدهای پرشده تغییر می‌کنند؛ ویرایش هر سؤال از همان domain validation و audit تکی عبور می‌کند.</div>
        <div className="grid" style={{ gap: 8, marginTop: 10 }}><input className="inp" placeholder="درس جدید (اختیاری)…" value={metadataBulk.lesson} onChange={e => setMetadataBulk({ ...metadataBulk, lesson: e.target.value })} /><input className="inp" placeholder="مبحث جدید (اختیاری)…" value={metadataBulk.topic} onChange={e => setMetadataBulk({ ...metadataBulk, topic: e.target.value })} /><select className="inp" value={metadataBulk.difficulty} onChange={e => setMetadataBulk({ ...metadataBulk, difficulty: e.target.value })}><option value="">سختی بدون تغییر</option><option value="easy">آسان</option><option value="medium">متوسط</option><option value="hard">سخت</option></select></div>
        <div className="row" style={{ marginTop: 12 }}><button className="btn primary" disabled={!metadataBulk.lesson.trim() && !metadataBulk.topic.trim() && !metadataBulk.difficulty} onClick={async () => { const patch = metadataBulk; setMetadataBulk(null); await bulk('metadata', sel, patch); }}>تأیید و اجرا</button><button className="btn" onClick={() => setMetadataBulk(null)}>انصراف</button></div>
      </Modal>}

      {createOpen && <QuestionCreateModal intake={intake} onClose={(ok) => {
        setCreateOpen(false); if (ok) load();
      }} />}
      {importOpen && (
        <ImportWizard intake={intake} onClose={() => setImportOpen(false)}
          onDone={(n) => { setImportOpen(false); toast(`📥 ${fa(n)} سؤال درج شد`); load(); }} />
      )}
    </>
  );
}

/* ── ➕ فرم مستقل ساخت یک سؤال ─────────────────────────── */
function QuestionCreateModal({ intake, onClose }) {
  const [f, setF] = useState({
    lesson: '', topic: '', difficulty: 'medium', question: '',
    options: ['', '', '', ''], correct: 0, explanation: '',
  });
  const [approve, setApprove] = useState(true);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  const setOpt = (i, v) => setF(x => ({ ...x, options: x.options.map((o, j) => j === i ? v : o) }));
  const submit = async () => {
    setBusy(true);
    try {
      const kept = f.options.map((x, i) => ({ text: x.trim(), i })).filter(x => x.text);
      const correct = kept.findIndex(x => x.i === f.correct);
      if (correct < 0) throw new Error('گزینه صحیح نباید خالی باشد');
      const r = await api.caQuestionsImport([{ ...f, options: kept.map(x => x.text), correct }], approve, intake);
      if (!r.inserted) throw new Error(r.failed?.[0]?.error || 'سؤال درج نشد');
      toast(approve ? 'سؤال ساخته و منتشر شد ✅' : 'سؤال در صف بازبینی ثبت شد ✅'); onClose(true);
    } catch (e) { toast(errText(e), 'err'); setBusy(false); }
  };
  return <Modal title="➕ ساخت سؤال جدید" onClose={() => onClose(false)}>
    <div className="grid" style={{ gap: 10 }}>
      <div className="row"><B kind={intake ? 'purple' : 'acc'}>{intake ? `🏷 ورودی ${intake}` : '🌐 سراسری'}</B>
        <span className="spacer" /><label className="row"><Switch on={approve} onChange={setApprove} /><span>انتشار مستقیم</span></label></div>
      <div className="row"><input className="inp" style={{ flex: 1 }} placeholder="درس *" value={f.lesson} onChange={e => set('lesson', e.target.value)} />
        <input className="inp" style={{ flex: 1 }} placeholder="مبحث" value={f.topic} onChange={e => set('topic', e.target.value)} />
        <select className="inp" value={f.difficulty} onChange={e => set('difficulty', e.target.value)}><option value="easy">آسان</option><option value="medium">متوسط</option><option value="hard">سخت</option></select></div>
      <textarea className="inp" rows={3} placeholder="متن سؤال *" value={f.question} onChange={e => set('question', e.target.value)} />
      <b>گزینه‌ها <span className="muted">— گزینه صحیح را علامت بزنید</span></b>
      {f.options.map((o, i) => <div key={i} className="row">
        <input type="radio" name="new-q-correct" checked={f.correct === i} onChange={() => set('correct', i)} />
        <input className="inp" style={{ flex: 1 }} placeholder={`گزینه ${fa(i + 1)}`} value={o} onChange={e => setOpt(i, e.target.value)} />
        <button className="btn sm danger" disabled={f.options.length <= 2} onClick={() => setF(x => ({ ...x,
          options: x.options.filter((_, j) => j !== i), correct: x.correct === i ? 0 : (x.correct > i ? x.correct - 1 : x.correct) }))} aria-label={`حذف گزینه ${i + 1}`}>✕</button>
      </div>)}
      {f.options.length < 6 && <button className="btn sm" onClick={() => set('options', [...f.options, ''])}>➕ گزینه</button>}
      <textarea className="inp" rows={2} placeholder="توضیح پاسخ (اختیاری)" value={f.explanation} onChange={e => set('explanation', e.target.value)} />
      <div className="row"><button className="btn primary" disabled={busy || !f.lesson.trim() || f.question.trim().length < 5 || f.options.filter(x => x.trim()).length < 2} onClick={submit}>{busy ? '⏳…' : 'ثبت سؤال'}</button>
        <button className="btn" onClick={() => onClose(false)}>انصراف</button></div>
    </div>
  </Modal>;
}


/* ── 📥🌊 ویزارد درون‌ریزی گروهی (موج Q-Import) — ۳ گام: متن ← بازبینی ← ثبت ── */
const IM_STEPS = ['ورود متن', 'بازبینی', 'ثبت'];
function ImportWizard({ intake, onClose, onDone }) {
  const [step, setStep] = useState(0);
  const [text, setText] = useState('');
  const [approve, setApprove] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const parsed = useMemo(() => parseImportText(text), [text]);
  const okRows = parsed.filter(r => r.ok);
  const badRows = parsed.filter(r => !r.ok);

  const submit = async () => {
    setBusy(true);
    try {
      const r = await api.caQuestionsImport(okRows.map(r => r.item), approve, intake);
      setResult(r);
      setStep(2);
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  return (
    <Drawer title="📥 درون‌ریزی گروهی سؤال" onClose={onClose} wide>
      <div style={{ marginBottom: 8 }}><B kind={intake ? 'purple' : 'acc'}>{intake ? `🏷 ورودی ${intake}` : '🌐 سراسری'}</B></div>
      <div className="wiz-steps" style={{ marginBottom: 14 }}>
        {IM_STEPS.map((l, i) => (
          <div key={l} className={`wiz-step ${step === i ? 'on' : ''} ${step > i ? 'done' : ''}`}>
            <span className="wiz-n">{fa(i + 1)}</span><span className="wiz-l">{l}</span>
          </div>
        ))}
      </div>

      {step === 0 && (<>
        <div className="muted" style={{ marginBottom: 8 }}>
          هر خط یک سؤال — قالب:
          <div className="code" dir="ltr" style={{ marginTop: 6, padding: 8, fontSize: 11 }}>
            درس | مبحث | سختی | متن سؤال | گزینه۱ ;; گزینه۲ ;; گزینه۳ | شماره صحیح | توضیح
          </div>
          <div style={{ marginTop: 6 }}>سختی: آسان/متوسط/سخت · شماره صحیح از ۱ · خط‌های خالی یا شروع‌شده با # نادیده گرفته می‌شوند</div>
        </div>
        <textarea className="inp" rows={10} dir="auto" style={{ fontFamily: 'inherit', lineHeight: 1.9 }}
          placeholder={'کالبدآنالیز | قلب | متوسط | بزرگ‌ترین لایه دیواره قلب؟ | اندوکارد ;; میوکارد ;; اپیکارد ;; پریکارد | 2 | میوکارد لایه عضلانی است.\n# خط دوم…'}
          value={text} onChange={e => setText(e.target.value)} />
        <label className="row" style={{ gap: 6, marginTop: 10 }}>
          <Switch on={approve} onChange={setApprove} />
          <span>تأیید مستقیم (بدون ورود به صف بازبینی)</span>
        </label>
        <div className="row" style={{ marginTop: 12 }}>
          <span className="spacer" />
          <span className="muted">{fa(okRows.length)} معتبر {badRows.length > 0 && `· ${fa(badRows.length)} معیوب`}</span>
          <button className="btn primary" disabled={!okRows.length || okRows.length > 200}
                  onClick={() => setStep(1)}>بازبینی ←</button>
        </div>
        {okRows.length > 200 && <div className="badge bad" style={{ marginTop: 8 }}>حداکثر ۲۰۰ سؤال در هر بار</div>}
      </>)}

      {step === 1 && (<>
        <div className="row" style={{ flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
          <B kind="ok">{fa(okRows.length)} سؤال معتبر</B>
          {badRows.length > 0 && <B kind="bad">{fa(badRows.length)} خط معیوب (درج نمی‌شوند)</B>}
          <B kind={approve ? 'warn' : 'acc'}>{approve ? 'تأیید مستقیم' : 'صف بازبینی'}</B>
        </div>
        <DataTable columns={[
          { k: 'q', label: 'سؤال', render: r => <div style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.item.question}</div> },
          { k: 'lesson', label: 'درس', render: r => r.item.lesson },
          { k: 'topic', label: 'مبحث', render: r => r.item.topic },
          { k: 'diff', label: 'سختی', render: r => { const [l, kk] = DIFF[r.item.difficulty] || ['—', '']; return <B kind={kk}>{l}</B>; } },
          { k: 'ops', label: 'گزینه/صحیح', render: r => `${fa(r.item.options.length)} / ${fa(r.item.correct + 1)}` },
        ]} rows={okRows.slice(0, 60)} rowKey="li"
          empty={<Empty icon="🗂" text="سؤال معتبری نیست" />} />
        {okRows.length > 60 && <div className="muted" style={{ marginTop: 4 }}>… و {fa(okRows.length - 60)} مورد دیگر</div>}
        {badRows.length > 0 && (
          <div className="panel panel-pad" style={{ marginTop: 10, background: 'var(--bg)' }}>
            <b className="badge bad">خطاهای نادیده‌گرفته‌شده</b>
            {badRows.slice(0, 10).map(r => (
              <div key={r.li} className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                خط {fa(r.li)}: {r.error} <span className="code">{r.raw}</span>
              </div>))}
          </div>
        )}
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn" onClick={() => setStep(0)}>→ ویرایش متن</button>
          <span className="spacer" />
          <button className="btn primary" disabled={busy || !okRows.length} onClick={submit}>
            {busy ? '⏳ در حال درج…' : `ثبت ${fa(okRows.length)} سؤال`}
          </button>
        </div>
      </>)}

      {step === 2 && result && (<>
        <div className="grid g3" style={{ marginTop: 4 }}>
          <div className="panel stat"><div className="ic" style={{ background: 'rgba(52,211,153,.1)' }}>✅</div>
            <div><div className="v">{fa(result.inserted)}</div><div className="l">درج‌شده ({result.approve ? 'تأیید مستقیم' : 'صف بازبینی'})</div></div></div>
          <div className="panel stat"><div className="ic" style={{ background: 'rgba(248,113,113,.1)' }}>❌</div>
            <div><div className="v">{fa((result.failed || []).length)}</div><div className="l">ردشده توسط سرور</div></div></div>
        </div>
        {(result.failed || []).length > 0 && (
          <div className="panel panel-pad" style={{ marginTop: 10, background: 'var(--bg)' }}>
            {result.failed.slice(0, 12).map((f2, i) => (
              <div key={i} className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                ردیف {fa(f2.i + 1)}: {f2.error}
              </div>))}
          </div>
        )}
        <div className="row" style={{ marginTop: 14 }}>
          <span className="spacer" />
          <button className="btn primary" onClick={() => onDone(result.inserted)}>پایان</button>
        </div>
      </>)}
    </Drawer>
  );
}

/* ── 👁✏️ کشوی جزئیات سؤال — مشاهده کامل + ویرایش پیش از تأیید ── */
function QuestionDrawer({ row, readonly = false, onClose, onAction, onSaved }) {
  const [edit, setEdit] = useState(false);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState(() => ({
    question: row.question || '',
    lesson: row.lesson || '',
    topic: row.topic || '',
    difficulty: row.difficulty || 'medium',
    explanation: row.explanation || '',
    options: [...(row.options || [])],
    correct: row.correct ?? row.answer ?? 0,
  }));
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  const setOpt = (i, v) => setF(x => ({ ...x, options: x.options.map((o, j) => j === i ? v : o) }));

  const save = async () => {
    setBusy(true);
    try {
      await api.caQuestionPatch(row.id || row._id, {
        question: f.question, lesson: f.lesson, topic: f.topic,
        difficulty: f.difficulty, explanation: f.explanation,
        options: f.options, correct: f.correct,
      });
      toast('ویرایش ذخیره شد ✅');
      setEdit(false);
      onSaved();
      // داده‌ی محلی کشو را هم تازه نگه دار
      Object.assign(row, { ...f, correct: f.correct });
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  const [dl, dk] = DIFF[row.difficulty] || [row.difficulty || '—', ''];
  return (
    <Drawer wide title={`🧪 ${readonly ? 'سؤال تأییدشده' : 'سؤال در انتظار بازبینی'} — ${row.lesson || ''}`} onClose={onClose}>
      <div className="row" style={{ flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
        <B kind={dk}>{dl}</B>
        <B>{SRC[row.source] || row.source || '—'}</B>
        <ScopeBadge scope={row.intake || 'global'} label={row.intake || 'سراسری'} />
        <span className="spacer" />
        <span className="muted">👤 {row.creator_name || '—'} · <FaDateTime value={row.created_at} fallback="" /></span>
      </div>

      {!edit ? (
        <>
          <div className="panel panel-pad" style={{ background: 'var(--bg)', lineHeight: 2 }}>{f.question}</div>
          <div className="grid" style={{ gap: 6, marginTop: 10 }}>
            {f.options.map((o, i) => (
              <div key={i} className="badge" style={{ justifyContent: 'flex-start', padding: '8px 10px',
                borderColor: i === f.correct ? 'rgba(58,210,155,.6)' : undefined,
                background: i === f.correct ? 'rgba(58,210,155,.07)' : undefined }}>
                {i === f.correct ? '✅' : '▫️'} {o}
              </div>
            ))}
          </div>
          <div className="ct3-kv" style={{ marginTop: 10 }}><span className="muted">درس</span><span>{f.lesson || '—'}</span></div>
          <div className="ct3-kv" style={{ marginTop: 6 }}><span className="muted">مبحث</span><span>{f.topic || '—'}</span></div>
          {f.explanation && (
            <div className="panel panel-pad" style={{ background: 'var(--bg)', marginTop: 10 }}>
              <b>💡 راهنما/توضیح</b>
              <div style={{ marginTop: 6, lineHeight: 1.9, color: 'var(--txt2)' }}>{f.explanation}</div>
            </div>
          )}
          {!readonly ? <div className="row" style={{ marginTop: 14, flexWrap: 'wrap', gap: 6 }}>
            <button className="btn ok" onClick={() => onAction('approve')}>✅ تأیید و انتشار</button>
            <button className="btn danger" onClick={() => onAction('reject')}>❌ رد</button>
            <span className="spacer" />
            <button className="btn" onClick={() => setEdit(true)}>✏️ ویرایش پیش از تأیید</button>
          </div> : <div className="row" style={{ marginTop: 14 }}><B kind="ok">این سؤال منتشر شده و این نما فقط‌خواندنی است</B>
            <span className="spacer" /><B>{fa(row.attempts)} تلاش · دقت {fa(row.accuracy)}٪</B></div>}
        </>
      ) : (
        <div className="grid" style={{ gap: 10 }}>
          <label className="muted" style={{ fontSize: 11 }}>متن سؤال
            <textarea className="inp" rows={4} value={f.question} onChange={e => set('question', e.target.value)} />
          </label>
          <div className="row">
            <input className="inp" placeholder="درس…" value={f.lesson} onChange={e => set('lesson', e.target.value)} />
            <input className="inp" placeholder="مبحث…" value={f.topic} onChange={e => set('topic', e.target.value)} />
            <select className="inp" value={f.difficulty} onChange={e => set('difficulty', e.target.value)}>
              <option value="easy">آسان</option><option value="medium">متوسط</option><option value="hard">سخت</option>
            </select>
          </div>
          <b style={{ marginTop: 4 }}>گزینه‌ها <span className="muted">(تیک = گزینه‌ی صحیح)</span></b>
          {f.options.map((o, i) => (
            <div key={i} className="row">
              <input type="radio" name="q-correct" checked={f.correct === i}
                     onChange={() => set('correct', i)} aria-label="گزینه‌ی صحیح"
                     style={{ accentColor: 'var(--ok)' }} />
              <input className="inp" style={{ flex: 1 }} value={o} onChange={e => setOpt(i, e.target.value)} />
              <button className="btn sm danger" title="حذف گزینه" aria-label={`حذف گزینه ${i + 1}`} disabled={f.options.length <= 2}
                      onClick={() => setF(x => ({
                        ...x,
                        options: x.options.filter((_, j) => j !== i),
                        correct: x.correct === i ? 0 : (x.correct > i ? x.correct - 1 : x.correct),
                      }))}>✕</button>
            </div>
          ))}
          {f.options.length < 6 && (
            <button className="btn sm" onClick={() => set('options', [...f.options, ''])}>➕ افزودن گزینه</button>
          )}
          <label className="muted" style={{ fontSize: 11 }}>راهنما/توضیح (اختیاری)
            <textarea className="inp" rows={2} value={f.explanation} onChange={e => set('explanation', e.target.value)} />
          </label>
          <div className="row">
            <button className="btn" onClick={() => setEdit(false)}>انصراف</button>
            <button className="btn primary" style={{ flex: 1 }}
                    disabled={busy || f.question.trim().length < 5 || f.options.filter(o => o.trim()).length < 2}
                    onClick={save}>
              {busy ? '⏳ …' : '💾 ذخیره‌ی ویرایش'}
            </button>
          </div>
        </div>
      )}
    </Drawer>
  );
}
