import React, { useEffect, useMemo, useState } from 'react';
import { api, errText } from '../api.js';
import { DataTable, Loading, ErrorState, B, FaDateTime, FilterBar, PageHeader, ScopeBadge, toast, Drawer, Modal, Empty, NoPerm } from '../ui.jsx';
import { PersianDatePicker } from '../PersianDatePicker.jsx';
import { queryNumber, readHashQuery, writeHashQuery } from '../urlState.js';

const fa = n => Number(n ?? 0).toLocaleString('fa-IR');
const DIFF = { easy: ['آسان', 'ok'], medium: ['متوسط', 'warn'], hard: ['سخت', 'bad'] };
const STATUS = {
  pending: ['در انتظار', 'warn'], approved: ['تأییدشده', 'ok'],
  rejected: ['ردشده', 'bad'], needs_changes: ['نیازمند اصلاح', 'purple'],
};
const SRC = {
  student_bot: '👤 ربات دانشجو', student_webapp: '📱 مینی‌اپ دانشجو',
  admin_bot: '🛡 ربات مدیر', web_admin: '🖥 وب‌ادمین', ai_student: '🤖 پیشنهاد AI',
  ai_admin_import: '📥 درون‌ریزی JSON', system: '⚙️ سیستم',
};
const CLASS_LABEL = {
  ready: 'آماده', error: 'خطای ساختار', unmatched: 'taxonomy نامشخص', ambiguous: 'taxonomy مبهم',
  exact_duplicate: 'تکراری قطعی', probable_duplicate: 'احتمالاً تکراری', conflict: 'تعارض پاسخ',
};

export default function Questions({ route = '', go }) {
  const initial = readHashQuery();
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [intakes, setIntakes] = useState([]);
  const [scopeKind, setScopeKind] = useState('global');
  const [intake, setIntake] = useState(initial.get('intake') || '');
  const [status, setStatus] = useState(initial.get('status') || 'pending');
  const [query, setQuery] = useState(initial.get('q') || '');
  const [q, setQ] = useState(initial.get('q') || '');
  const [fdiff, setFdiff] = useState(initial.get('difficulty') || '');
  const [fsrc, setFsrc] = useState(initial.get('source') || '');
  const [author, setAuthor] = useState(initial.get('author') || '');
  const [dateFrom, setDateFrom] = useState(initial.get('date_from') || '');
  const [dateTo, setDateTo] = useState(initial.get('date_to') || '');
  const [sortBy, setSortBy] = useState(initial.get('sort_by') || 'created_at');
  const [sortDir, setSortDir] = useState(initial.get('sort_dir') || 'desc');
  const [page, setPage] = useState(queryNumber(initial, 'page', 1));
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState([]);
  const [detail, setDetail] = useState(null);
  const [review, setReview] = useState(null); // {action, ids, reason}
  const [bulkResult, setBulkResult] = useState(null);
  // 🛡 §۸۴ — حذف سخت: برگشت‌ناپذیر است، پس تأیید صریح + دلیل اجباری.
  const [delTarget, setDelTarget] = useState(null); // {id, question, reason}
  const [createOpen, setCreateOpen] = useState(new URLSearchParams(route.split('?')[1] || '').get('create') === '1');
  const [importOpen, setImportOpen] = useState(false);
  const LIMIT = 30;

  const load = async () => {
    setErr('');
    try {
      const result = await api.questions({ status, intake, q, difficulty: fdiff, source: fsrc, author,
        date_from: dateFrom, date_to: dateTo, sort_by: sortBy, sort_dir: sortDir,
        skip: (page - 1) * LIMIT, limit: LIMIT });
      setRows(result.questions || []); setTotal(Number(result.total || 0));
    } catch (e) { if (e.status === 403) setPermErr(true); else setErr(errText(e)); }
  };

  useEffect(() => {
    api.questionIntakes().then(result => {
      setIntakes(result.intakes || []); setScopeKind(result.scope_kind || 'global');
      if (result.scope_kind === 'scoped') setIntake(result.scope_intake || result.intakes?.[0]?.code || '');
    }).catch(e => { if (e.status === 403) setPermErr(true); else setErr(errText(e)); });
  }, []);
  useEffect(() => { const timer = setTimeout(() => { setQ(query.trim()); setPage(1); }, 350); return () => clearTimeout(timer); }, [query]);
  useEffect(() => { setRows(null); setSelected([]); load(); }, [status, intake, q, fdiff, fsrc, author, dateFrom, dateTo, sortBy, sortDir, page]);
  useEffect(() => { writeHashQuery('/questions', { status: status !== 'pending' ? status : '', intake, q: query,
    difficulty: fdiff, source: fsrc, author, date_from: dateFrom, date_to: dateTo,
    sort_by: sortBy !== 'created_at' ? sortBy : '', sort_dir: sortDir !== 'desc' ? sortDir : '', page: page > 1 ? page : '' });
  }, [status, intake, query, fdiff, fsrc, author, dateFrom, dateTo, sortBy, sortDir, page]);

  const approve = async id => {
    try { await api.caQuestionApprove(id); toast('سؤال تأیید و منتشر شد ✅'); setDetail(null); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const runDelete = async () => {
    const reason = (delTarget?.reason || '').trim();
    if (!delTarget || reason.length < 3) return;
    try {
      await api.caQuestionDelete(delTarget.id, reason);
      toast('سؤال برای همیشه حذف شد 🗑');
      setDelTarget(null); setDetail(null); load();
    } catch (e) { toast(errText(e), 'err'); }
  };
  const runReview = async () => {
    const reason = (review?.reason || '').trim();
    if (!review || ((review.action === 'reject' || review.action === 'needs_changes') && reason.length < 3)) return;
    try {
      if (review.ids.length === 1) {
        if (review.action === 'reject') await api.caQuestionReject(review.ids[0], reason);
        else await api.caQuestionNeedsChanges(review.ids[0], reason);
      } else {
        const result = await api.questionsBulk(review.action, review.ids, null, reason);
        setBulkResult(result); setSelected([]);
      }
      toast(review.action === 'reject' ? 'رد با دلیل ثبت شد' : 'درخواست اصلاح ثبت شد');
      setReview(null); setDetail(null); load();
    } catch (e) { toast(errText(e), 'err'); }
  };
  const bulkApprove = async () => {
    try { const result = await api.questionsBulk('approve', selected); setBulkResult(result); setSelected([]); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };

  if (permErr) return <NoPerm text="بازبینی سؤال نیازمند questions.review یا questions.review_scoped است" />;
  if (err) return <ErrorState error={err} onRetry={load} />;

  const columns = [
    { k: 'question', label: 'سؤال', render: row => <div style={{ maxWidth: 350, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.question}</div> },
    { k: 'lesson', label: 'درس/مبحث', render: row => <div>{row.lesson}<small className="muted" style={{ display: 'block' }}>{row.topic}</small></div> },
    { k: 'difficulty', label: 'سختی', sortable: true, render: row => { const [label, kind] = DIFF[row.difficulty] || ['—', '']; return <B kind={kind}>{label}</B>; } },
    { k: 'creator', label: 'طراح', stop: true, render: row => <button className="btn sm" disabled={!row.creator_id} onClick={() => go?.(`/users?q=${row.creator_id}`)}>{row.creator_name || '—'}<small className="muted" style={{ display: 'block' }}>{SRC[row.source] || row.source}</small></button> },
    { k: 'intake', label: 'ورودی', render: row => row.intake || <B>سراسری</B> },
    { k: 'status', label: 'چرخه عمر', render: row => { const [label, kind] = STATUS[row.status] || [row.status, '']; return <div><B kind={kind}>{label}</B>{row.review_reason && <small className="muted" style={{ display: 'block', maxWidth: 180 }}>{row.review_reason}</small>}</div>; } },
    { k: 'attempts', label: 'تلاش/دقت', sortable: true, render: row => `${fa(row.attempts)} · ${fa(row.accuracy)}٪` },
    { k: 'created_at', label: 'ایجاد', sortable: true, render: row => <FaDateTime value={row.created_at} /> },
    { k: 'ops', label: '', stop: true, render: row => <div className="row" style={{ gap: 4 }}>
      <button className="btn sm" aria-label="مشاهده سؤال" onClick={() => setDetail(row)}>👁</button>
      {row.can_approve && <button className="btn sm ok" aria-label="تأیید سؤال" onClick={() => approve(row.id)}>✅</button>}
      {row.can_reject && <button className="btn sm" aria-label="درخواست اصلاح" onClick={() => setReview({ action: 'needs_changes', ids: [row.id], reason: '' })}>✏️</button>}
      {row.can_reject && <button className="btn sm danger" aria-label="رد سؤال" onClick={() => setReview({ action: 'reject', ids: [row.id], reason: '' })}>❌</button>}
      {row.can_delete && <button className="btn sm danger" aria-label="حذف کامل سؤال"
        title="حذف همیشگی — برخلاف «رد»، داده بازیابی نمی‌شود"
        onClick={() => setDelTarget({ id: row.id, question: row.question, reason: '' })}>🗑</button>}
    </div> },
  ];

  return <>
    <PageHeader title="بازبینی سؤال‌ها" description="دامنه مشترک ربات، API و وب‌ادمین؛ رد بدون حذف داده و اصلاح با ارسال مجدد" actions={<>
      <button className="btn primary" onClick={() => setCreateOpen(true)}>➕ پیشنهاد سؤال</button>
      <button className="btn" onClick={() => setImportOpen(true)}>📥 JSON نسخه‌دار</button>
      <button className="btn" title="خروجی CSV از سؤال‌های فیلترشده" onClick={() => api.exportQuestionsCsv({ status, intake, q: query, difficulty: fdiff, source: fsrc, author, date_from: dateFrom, date_to: dateTo, sort_by: sortBy, sort_dir: sortDir })}>📤 CSV</button>
      {status === 'pending' && selected.length > 0 && <>
        <B kind="acc">{fa(selected.length)} انتخاب</B>
        {selected.every(id => rows?.find(row => row.id === id)?.can_approve) && <button className="btn sm ok" onClick={bulkApprove}>✅ تأیید گروهی</button>}
        {selected.every(id => rows?.find(row => row.id === id)?.can_reject) && <button className="btn sm" onClick={() => setReview({ action: 'needs_changes', ids: selected, reason: '' })}>✏️ اصلاح گروهی</button>}
        {selected.every(id => rows?.find(row => row.id === id)?.can_reject) && <button className="btn sm danger" onClick={() => setReview({ action: 'reject', ids: selected, reason: '' })}>❌ رد گروهی</button>}
      </>}
    </>} />
    <FilterBar>
      <select className="inp" value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}>
        <option value="pending">در انتظار</option><option value="needs_changes">نیازمند اصلاح</option>
        <option value="rejected">ردشده</option><option value="approved">تأییدشده</option><option value="all">همه</option>
      </select>
      <select className="inp" value={intake} disabled={scopeKind === 'scoped'} onChange={e => { setIntake(e.target.value); setPage(1); }}>
        {scopeKind === 'global' && <option value="">همه ورودی‌ها</option>}
        {intakes.map(item => <option key={item.code} value={item.code}>{item.label || item.code}</option>)}
      </select>
      <input className="inp" style={{ flex: 1, minWidth: 190 }} placeholder="جست‌وجوی متن، درس، مبحث یا طراح" value={query} onChange={e => setQuery(e.target.value)} />
      <select className="inp" value={fdiff} onChange={e => setFdiff(e.target.value)}><option value="">همه سختی‌ها</option><option value="easy">آسان</option><option value="medium">متوسط</option><option value="hard">سخت</option></select>
      <select className="inp" value={fsrc} onChange={e => setFsrc(e.target.value)}><option value="">همه منابع</option>{Object.entries(SRC).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select>
      <input className="inp" style={{ width: 140 }} placeholder="طراح یا ID" value={author} onChange={e => setAuthor(e.target.value)} />
      <label className="row"><span className="muted">از</span><PersianDatePicker value={dateFrom} onChange={setDateFrom} placeholder="تاریخ شمسی" /></label>
      <label className="row"><span className="muted">تا</span><PersianDatePicker value={dateTo} onChange={setDateTo} placeholder="تاریخ شمسی" /></label>
      <B kind="acc">{fa(total)} نتیجه</B>
    </FilterBar>
    <div className="muted" style={{ margin: '-4px 0 10px' }}>رد و «نیازمند اصلاح» soft lifecycle هستند؛ هیچ سؤال با این عملیات حذف نمی‌شود. طراح دلیل را می‌بیند و فقط در این دو وضعیت می‌تواند اصلاح و دوباره ارسال کند.</div>
    {!rows ? <Loading /> : <DataTable columns={columns} rows={rows} rowKey="id" selectable={status === 'pending'} onSelect={setSelected} onRow={setDetail}
      sortState={{ k: sortBy === 'attempt_count' ? 'attempts' : sortBy, dir: sortDir }} onSort={next => { setSortBy(next?.k === 'attempts' ? 'attempt_count' : next?.k || 'created_at'); setSortDir(next?.dir || 'desc'); setPage(1); }}
      pager={{ page, pages: Math.max(1, Math.ceil(total / LIMIT)), total, onPage: setPage }} empty={<Empty icon="🧪" text="سؤالی با این فیلترها نیست" />} />}

    {detail && <QuestionDrawer row={detail} onClose={() => setDetail(null)} onApprove={() => approve(detail.id)}
      onReview={action => setReview({ action, ids: [detail.id], reason: '' })} onSaved={() => { setDetail(null); load(); }} />}
    {review && <ReviewModal value={review} onChange={setReview} onClose={() => setReview(null)} onSubmit={runReview} />}
    {delTarget && <Modal title="🗑 حذف همیشگی سؤال" onClose={() => setDelTarget(null)}>
      <div className="panel panel-pad" style={{ background: 'var(--bg)', marginBottom: 10 }}>
        <div style={{ maxHeight: 90, overflow: 'auto' }}>{delTarget.question}</div>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        این عملیات <b>برگشت‌ناپذیر</b> است و سؤال از پایگاه داده پاک می‌شود.
        اگر فقط می‌خواهید سؤال از چرخه خارج شود، به‌جای حذف از «❌ رد با دلیل»
        استفاده کنید — داده حفظ و برای طراح قابل اصلاح می‌ماند.
      </p>
      <input className="inp" placeholder="دلیل حذف (حداقل ۳ نویسه) *" value={delTarget.reason}
             onChange={e => setDelTarget({ ...delTarget, reason: e.target.value })} />
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn danger" disabled={delTarget.reason.trim().length < 3}
                onClick={runDelete}>حذف همیشگی</button>
        <button className="btn" onClick={() => setDelTarget(null)}>انصراف</button>
      </div>
    </Modal>}
    {bulkResult && <Modal title="نتیجه عملیات گروهی" onClose={() => setBulkResult(null)}><div className="row"><B kind="ok">موفق {fa(bulkResult.succeeded?.length)}</B><B>ردشده {fa(bulkResult.skipped?.length)}</B><B kind="bad">ناموفق {fa(bulkResult.failed?.length)}</B></div>{[...(bulkResult.skipped || []), ...(bulkResult.failed || [])].slice(0, 30).map((item, i) => <div key={`${item.id}-${i}`} className="row"><span className="code">{item.id}</span><span className="muted">{item.reason || item.error}</span></div>)}</Modal>}
    {createOpen && <QuestionCreateModal intake={intake} onClose={ok => { setCreateOpen(false); if (ok) load(); }} />}
    {importOpen && <ImportWizard onClose={() => setImportOpen(false)} onDone={() => { setImportOpen(false); load(); }} />}
  </>;
}

function ReviewModal({ value, onChange, onClose, onSubmit }) {
  const label = value.action === 'reject' ? 'رد' : 'درخواست اصلاح';
  return <Modal title={`${label} ${fa(value.ids.length)} سؤال`} onClose={onClose}>
    <div className="muted">دلیل برای طراح نمایش داده می‌شود و در تاریخچه بررسی باقی می‌ماند. حداقل ۳ کاراکتر.</div>
    <textarea className="inp" rows={4} autoFocus value={value.reason} onChange={e => onChange({ ...value, reason: e.target.value })} placeholder="دلیل روشن و قابل اقدام…" style={{ marginTop: 10 }} />
    <div className="row" style={{ marginTop: 12 }}><button className={`btn ${value.action === 'reject' ? 'danger' : 'primary'}`} disabled={value.reason.trim().length < 3} onClick={onSubmit}>ثبت {label}</button><button className="btn" onClick={onClose}>انصراف</button></div>
  </Modal>;
}

function TaxonomyFields({ intake, value, onChange }) {
  const [lessons, setLessons] = useState([]);
  useEffect(() => { api.questionTaxonomy(intake).then(r => setLessons(r.lessons || [])).catch(e => toast(errText(e), 'err')); }, [intake]);
  const lesson = lessons.find(item => item.id === value.lesson_id);
  return <div className="row">
    <select className="inp" style={{ flex: 1 }} value={value.lesson_id || ''} onChange={e => { const item = lessons.find(x => x.id === e.target.value); onChange({ ...value, lesson_id: item?.id || '', lesson: item?.name || '', topic_id: '', topic: '' }); }}>
      <option value="">درس را انتخاب کنید</option>{lessons.map(item => <option key={item.id} value={item.id}>{item.name} · {item.intake || 'سراسری'}</option>)}
    </select>
    <select className="inp" style={{ flex: 1 }} value={value.topic_id || ''} disabled={!lesson} onChange={e => { const item = lesson?.topics?.find(x => x.id === e.target.value); onChange({ ...value, topic_id: item?.id || '', topic: item?.name || '' }); }}>
      <option value="">مبحث را انتخاب کنید</option>{(lesson?.topics || []).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select>
  </div>;
}

function QuestionCreateModal({ intake, onClose }) {
  const [form, setForm] = useState({ lesson_id: '', topic_id: '', lesson: '', topic: '', difficulty: 'medium', question: '', options: ['', '', '', ''], correct_answer: 0, explanation: '', intake });
  const [busy, setBusy] = useState(false);
  const setOption = (index, text) => setForm(current => ({ ...current, options: current.options.map((item, i) => i === index ? text : item) }));
  const submit = async () => {
    setBusy(true);
    try { await api.questionCreate({ ...form, intake: intake || null }); toast('سؤال برای بازبینی مستقل ارسال شد ✅'); onClose(true); }
    catch (e) { toast(errText(e), 'err'); setBusy(false); }
  };
  const valid = form.lesson_id && form.topic_id && form.question.trim().length >= 10 && form.options.every(item => item.trim()) && new Set(form.options.map(item => item.trim())).size === 4;
  return <Modal title="➕ پیشنهاد سؤال چهارگزینه‌ای" onClose={() => onClose(false)}>
    <div className="muted">حتی سؤال مدیر مستقیماً منتشر نمی‌شود؛ بازبین دیگری باید آن را تأیید کند.</div>
    <div className="grid" style={{ gap: 10, marginTop: 10 }}>
      <TaxonomyFields intake={intake} value={form} onChange={setForm} />
      <select className="inp" value={form.difficulty} onChange={e => setForm({ ...form, difficulty: e.target.value })}><option value="easy">آسان</option><option value="medium">متوسط</option><option value="hard">سخت</option></select>
      <textarea className="inp" rows={4} placeholder="متن سؤال (حداقل ۱۰ کاراکتر)" value={form.question} onChange={e => setForm({ ...form, question: e.target.value })} />
      {form.options.map((option, index) => <div className="row" key={index}><input type="radio" name="new-correct" checked={form.correct_answer === index} onChange={() => setForm({ ...form, correct_answer: index })} /><input className="inp" style={{ flex: 1 }} placeholder={`گزینه ${fa(index + 1)}`} value={option} onChange={e => setOption(index, e.target.value)} /></div>)}
      <textarea className="inp" rows={2} placeholder="توضیح پاسخ (اختیاری)" value={form.explanation} onChange={e => setForm({ ...form, explanation: e.target.value })} />
      <div className="row"><button className="btn primary" disabled={busy || !valid} onClick={submit}>{busy ? 'در حال ثبت…' : 'ارسال به صف بررسی'}</button><button className="btn" onClick={() => onClose(false)}>انصراف</button></div>
    </div>
  </Modal>;
}

function QuestionDrawer({ row, onClose, onApprove, onReview, onSaved }) {
  const [edit, setEdit] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ lesson_id: row.lesson_id, topic_id: row.topic_id, lesson: row.lesson, topic: row.topic,
    difficulty: row.difficulty, question: row.question, options: [...(row.options || [])], correct: row.correct, explanation: row.explanation || '' });
  const [statusLabel, statusKind] = STATUS[row.status] || [row.status, ''];
  const save = async () => {
    setBusy(true);
    try { await api.caQuestionPatch(row.id, form); toast('ویرایش canonical ذخیره شد'); onSaved(); }
    catch (e) { toast(errText(e), 'err'); setBusy(false); }
  };
  return <Drawer wide title="جزئیات سؤال" onClose={onClose}>
    <div className="row" style={{ flexWrap: 'wrap' }}><B kind={statusKind}>{statusLabel}</B><ScopeBadge scope={row.intake || 'global'} label={row.intake || 'سراسری'} /><B>{SRC[row.source] || row.source}</B><span className="spacer" /><FaDateTime value={row.created_at} /></div>
    {row.review_reason && <div className="panel panel-pad" style={{ marginTop: 10, background: 'var(--bg)' }}><b>دلیل بررسی</b><div>{row.review_reason}</div></div>}
    {!edit ? <>
      <div className="panel panel-pad" style={{ marginTop: 10, lineHeight: 2 }}>{row.question}</div>
      <div className="grid" style={{ gap: 7, marginTop: 10 }}>{(row.options || []).map((option, i) => <div className="badge" key={i} style={{ justifyContent: 'flex-start' }}>{i === row.correct ? '✅' : '▫️'} {option}</div>)}</div>
      <div className="muted" style={{ marginTop: 10 }}>{row.lesson} / {row.topic} · طراح: {row.creator_name || row.creator_id}</div>
      {row.explanation && <div className="panel panel-pad" style={{ marginTop: 10 }}><b>توضیح پاسخ</b><div>{row.explanation}</div></div>}
      {row.status === 'pending' && <div className="row" style={{ marginTop: 14, flexWrap: 'wrap' }}>
        {row.can_approve && <button className="btn ok" onClick={onApprove}>✅ تأیید</button>}
        {row.can_reject && <button className="btn" onClick={() => onReview('needs_changes')}>✏️ نیازمند اصلاح</button>}
        {row.can_reject && <button className="btn danger" onClick={() => onReview('reject')}>❌ رد با دلیل</button>}
        <span className="spacer" />{row.can_edit && <button className="btn" onClick={() => setEdit(true)}>ویرایش پیش از بررسی</button>}
      </div>}
    </> : <div className="grid" style={{ gap: 10, marginTop: 10 }}>
      <TaxonomyFields intake={row.intake} value={form} onChange={setForm} />
      <textarea className="inp" rows={4} value={form.question} onChange={e => setForm({ ...form, question: e.target.value })} />
      {form.options.map((option, index) => <div className="row" key={index}><input type="radio" name="edit-correct" checked={form.correct === index} onChange={() => setForm({ ...form, correct: index })} /><input className="inp" style={{ flex: 1 }} value={option} onChange={e => setForm({ ...form, options: form.options.map((x, i) => i === index ? e.target.value : x) })} /></div>)}
      <select className="inp" value={form.difficulty} onChange={e => setForm({ ...form, difficulty: e.target.value })}><option value="easy">آسان</option><option value="medium">متوسط</option><option value="hard">سخت</option></select>
      <textarea className="inp" rows={2} value={form.explanation} onChange={e => setForm({ ...form, explanation: e.target.value })} />
      <div className="row"><button className="btn primary" disabled={busy || form.options.length !== 4 || form.options.some(x => !x.trim())} onClick={save}>ذخیره</button><button className="btn" onClick={() => setEdit(false)}>انصراف</button></div>
    </div>}
  </Drawer>;
}

function ImportWizard({ onClose, onDone }) {
  const [prompt, setPrompt] = useState(null);
  const [promptError, setPromptError] = useState('');
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [items, setItems] = useState([]);
  const [classification, setClassification] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [mapItem, setMapItem] = useState(null);
  useEffect(() => { api.questionImportPrompt().then(setPrompt).catch(e => { const message = e.status === 403 ? 'درون‌ریزی JSON فقط برای مالک فعال است.' : errText(e); setPromptError(message); toast(message, 'err'); }); }, []);
  const loadItems = async (jobId = preview?.job_id, cls = classification) => {
    if (!jobId) return;
    try { const data = await api.questionImportItems(jobId, { classification: cls, skip: 0, limit: 100 }); setItems(data.items || []); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const upload = async () => {
    if (!file) return; setBusy(true);
    try { const data = await api.questionImportUpload(file); setPreview(data); await loadItems(data.job_id, ''); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const refresh = async () => { const data = await api.questionImportPreview(preview.job_id); setPreview(data); await loadItems(data.job_id); };
  const decision = async (item, value) => { try { await api.questionImportDecision(preview.job_id, item.id, value); await loadItems(); } catch (e) { toast(errText(e), 'err'); } };
  const confirm = async () => {
    setBusy(true); try { const data = await api.questionImportConfirm(preview.job_id); setResult(data); toast('درون‌ریزی نهایی شد ✅'); } catch (e) { toast(errText(e), 'err'); } setBusy(false);
  };
  const cancel = async () => { if (preview) { try { await api.questionImportCancel(preview.job_id); } catch { /* already final */ } } onClose(); };
  const counts = preview?.counts || {};
  return <Drawer wide title="📥 درون‌ریزی JSON نسخه‌دار" onClose={cancel}>
    {promptError && <div className="panel panel-pad"><B kind="bad">دسترسی محدود</B><p>{promptError}</p></div>}
    {!preview && !promptError && <>
      <div className="panel panel-pad" style={{ background: 'var(--bg)' }}><b>۱. استخراج خارج از سامانه</b><p className="muted">prompt نسخه {prompt?.schema_version || '۱.۰'} را کپی کنید، PDF را با آن به مدل بدهید و فقط JSON خروجی را بارگذاری کنید. ورود مستقیم یا فایل با تعداد گزینه غیر از چهار رد می‌شود.</p>
        <button className="btn" disabled={!prompt} onClick={() => navigator.clipboard?.writeText(prompt?.prompt || '').then(() => toast('prompt کپی شد'))}>📋 کپی prompt و schema</button></div>
      <div className="panel panel-pad" style={{ marginTop: 10 }}><b>۲. بارگذاری برای validation و preview</b><input className="inp" type="file" accept="application/json,.json" onChange={e => setFile(e.target.files?.[0] || null)} style={{ marginTop: 10 }} /><button className="btn primary" disabled={!file || busy || !prompt} onClick={upload} style={{ marginTop: 10 }}>{busy ? 'در حال تحلیل…' : 'ساخت پیش‌نمایش'}</button></div>
    </>}
    {preview && !result && <>
      <div className="row" style={{ flexWrap: 'wrap' }}><B>کل {fa(counts.total)}</B><B kind="ok">آماده {fa(counts.ready)}</B><B kind="bad">خطا {fa(counts.errors)}</B><B kind="warn">نامشخص/مبهم {fa(Number(counts.unmatched || 0) + Number(counts.ambiguous || 0))}</B><B>تکراری قطعی {fa(counts.exact_duplicates)}</B><B kind="purple">احتمالی/تعارض {fa(Number(counts.probable_duplicates || 0) + Number(counts.conflicts || 0))}</B></div>
      <div className="muted" style={{ marginTop: 8 }}>job: <span className="code">{preview.job_id}</span> · فایل: {preview.file_name} · تأیید نهایی idempotent است.</div>
      <div className="grid g2" style={{ marginTop: 10 }}>{(preview.classification || []).map(group => <div className="panel panel-pad" key={group.lesson}><b>{group.lesson} · {fa(group.count)}</b><div className="muted">{group.topics.map(t => `${t.topic} (${fa(t.count)})`).join('، ')}</div></div>)}</div>
      <div className="row" style={{ marginTop: 12 }}><select className="inp" value={classification} onChange={async e => { setClassification(e.target.value); await loadItems(preview.job_id, e.target.value); }}><option value="">همه ردیف‌ها</option>{Object.entries(CLASS_LABEL).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><button className="btn" onClick={refresh}>↻ تازه‌سازی</button></div>
      <DataTable columns={[
        { k: 'row', label: 'ردیف', render: x => fa(x.row) },
        { k: 'question', label: 'سؤال', render: x => <div style={{ maxWidth: 280 }}>{x.normalized?.question || x.external_id}<small className="muted" style={{ display: 'block' }}>{x.taxonomy?.lesson || x.raw?.lesson || '—'} / {x.taxonomy?.topic || x.raw?.topic || '—'}</small></div> },
        { k: 'class', label: 'طبقه‌بندی', render: x => <B kind={x.classification === 'ready' ? 'ok' : x.classification === 'error' ? 'bad' : 'warn'}>{CLASS_LABEL[x.classification] || x.classification}</B> },
        { k: 'issue', label: 'جزئیات', render: x => <span className="muted">{x.errors?.join('، ') || x.duplicate?.question || '—'}</span> },
        { k: 'ops', label: '', stop: true, render: x => <div className="row">{['unmatched', 'ambiguous'].includes(x.classification) && <button className="btn sm" onClick={() => setMapItem(x)}>🧭 نگاشت</button>}{['probable_duplicate', 'conflict'].includes(x.classification) && <><button className="btn sm ok" onClick={() => decision(x, 'import')}>ورود</button><button className="btn sm" onClick={() => decision(x, 'skip')}>ردیابی و رد</button></>}{x.decision && <B>{x.decision}</B>}</div> },
      ]} rows={items} rowKey="id" empty={<Empty icon="📥" text="ردیفی در این طبقه نیست" />} />
      <div className="row" style={{ marginTop: 12 }}><button className="btn primary" disabled={busy || preview.status !== 'preview_ready'} onClick={confirm}>{busy ? 'در حال ثبت…' : 'تأیید نهایی و import موارد آماده'}</button><button className="btn" onClick={cancel}>لغو job</button></div>
    </>}
    {result && <div><div className="grid g3"><div className="panel stat"><div><div className="v">{fa(result.imported)}</div><div className="l">واردشده</div></div></div><div className="panel stat"><div><div className="v">{fa(result.skipped)}</div><div className="l">ردشده/تکراری</div></div></div><div className="panel stat"><div><div className="v">{fa(result.failed)}</div><div className="l">ناموفق</div></div></div></div><button className="btn primary" onClick={onDone} style={{ marginTop: 12 }}>پایان</button></div>}
    {mapItem && <ImportMapModal item={mapItem} onClose={() => setMapItem(null)} onSave={async mapping => { try { await api.questionImportMap(preview.job_id, mapItem.id, mapping.lesson_id, mapping.topic_id); setMapItem(null); await refresh(); } catch (e) { toast(errText(e), 'err'); } }} />}
  </Drawer>;
}

function ImportMapModal({ item, onClose, onSave }) {
  const [value, setValue] = useState({ lesson_id: '', topic_id: '', lesson: '', topic: '' });
  return <Modal title={`نگاشت taxonomy ردیف ${fa(item.row)}`} onClose={onClose}><TaxonomyFields intake="" value={value} onChange={setValue} /><div className="muted" style={{ marginTop: 8 }}>مقدار ورودی: {item.raw?.lesson || '—'} / {item.raw?.topic || '—'}</div><div className="row" style={{ marginTop: 12 }}><button className="btn primary" disabled={!value.lesson_id || !value.topic_id} onClick={() => onSave(value)}>ثبت نگاشت</button><button className="btn" onClick={onClose}>انصراف</button></div></Modal>;
}
