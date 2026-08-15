import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { DataTable, Loading, ErrorState, Empty, B, toast, Confirm, Modal, NoPerm } from '../ui.jsx';
import SavedViews from '../SavedViews.jsx';
import {
  ContentActionGroup, ContentBreadcrumb, ContentDensityToggle, ContentEmptyState,
  ContentErrorState, ContentIconButton, ContentItem, ContentKV, ContentMetric, ContentMoreActions,
  ContentPane, ContentReorderControls, ContentShell, ContentSkeleton, ContentStats, ContentToolbar,
  ContentWorkspace, FileTypeBadge, ScopeBadge, useContentDensity,
} from '../ContentPrimitives.jsx';

// ════════════════════════════════════════════════════════════════════
// 🌊 WA3 — تب‌های پریتی «مرکز فرماندهی محتوا» (همه روی API موجود، scope-aware)
// ════════════════════════════════════════════════════════════════════

export function useIntakes() {
  const [meta, setMeta] = useState({ intakes: [], scope_kind: 'global', scope_intake: '' });
  useEffect(() => { api.caIntakes().then(r => setMeta({ intakes: r.intakes || [], scope_kind: r.scope_kind || 'global', scope_intake: r.scope_intake || '' })).catch(() => {}); }, []);
  return meta;
}

function IntakeSelect({ intakes, value, onChange, scopeKind = 'global' }) {
  return (
    <select className="inp" value={value} disabled={scopeKind === 'scoped'} onChange={e => onChange(e.target.value)}>
      {scopeKind === 'global' && <option value="">🌐 سراسری (پایه)</option>}
      {intakes.map(i => <option key={i.code || i} value={i.code || i}>🏷 {i.label || i.code || i}</option>)}
    </select>
  );
}

// ── 📖 رفرنس‌ها: موضوع → کتاب → فایل (سه‌ستونه‌ی فرماندهی) ──────────
export function RefsTab() {
  const intakeMeta = useIntakes();
  const intakes = intakeMeta.intakes;
  const [intake, setIntake] = useState('');
  const [subjects, setSubjects] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [sub, setSub] = useState(null);
  const [books, setBooks] = useState(null);
  const [booksReadonly, setBooksReadonly] = useState(false);
  const [book, setBook] = useState(null);
  const [files, setFiles] = useState(null);
  const [filesPage, setFilesPage] = useState({ total: 0, hasMore: false });
  const [filesReadonly, setFilesReadonly] = useState(false);
  const [addModal, setAddModal] = useState(null);   // {kind:'subject'|'book'|'file'}
  const [editModal, setEditModal] = useState(null); // {kind,item}
  const [confirm, setConfirm] = useState(null);     // {text, run}
  const [rootMove, setRootMove] = useState(null);
  const [booksErr, setBooksErr] = useState('');
  const [filesErr, setFilesErr] = useState('');
  const [density, setDensity] = useContentDensity();
  useEffect(() => { if (intakeMeta.scope_kind === 'scoped' && intakeMeta.scope_intake) setIntake(intakeMeta.scope_intake); }, [intakeMeta.scope_kind, intakeMeta.scope_intake]);

  const loadSubjects = async () => {
    setErr('');
    try {
      const r = await api.refSubjects(intake || undefined);
      setSubjects(r.subjects || []);
      if (!intake && r.intake) setIntake(r.intake);
    } catch (e) { if (e.status === 403) setPermErr(true); else setErr(errText(e)); }
  };
  useEffect(() => { setSub(null); setBook(null); loadSubjects(); }, [intake]);
  const loadBooks = async (selectedSubject) => {
    setSub(selectedSubject); setBook(null); setBooks(null); setBooksErr(''); setFilesErr('');
    try { const r = await api.refBooks(selectedSubject.id); setBooks(r.books || []); setBooksReadonly(!!r.readonly); }
    catch (e) { setBooksErr(errText(e)); }
  };
  const loadFiles = async (selectedBook, append = false) => {
    const currentCount = append ? (files || []).length : 0;
    setBook(selectedBook); if (!append) setFiles(null); setFilesErr('');
    try {
      const r = await api.refFiles(selectedBook.id, { skip: currentCount, limit: 50 });
      const batch = r.files || [];
      setFiles(previous => append ? [...(previous || []), ...batch] : batch);
      setFilesPage({ total: Number(r.total ?? batch.length), hasMore: Boolean(r.has_more) });
      setFilesReadonly(!!r.readonly);
    } catch (e) { setFilesErr(errText(e)); }
  };
  const reorderRef = async (fn, reload) => {
    try {
      const r = await fn();
      if (r?.ok === false) return toast('به ابتدا/انتهای فهرست رسیده‌اید', 'err');
      toast('ترتیب ذخیره شد ✅'); await reload();
    } catch (e) { toast(errText(e), 'err'); }
  };

  if (permErr) return <NoPerm text="مدیریت رفرنس‌ها فقط برای مدیر محتواست" />;

  const selectedIntakeLabel = intake ? (intakes.find(item => (item.code || item) === intake)?.label || intake) : 'سراسری';
  return (
    <ContentShell density={density}>
      <ContentBreadcrumb items={[{ label: 'محتوا' }, { label: 'رفرنس‌ها' }, { label: selectedIntakeLabel }, ...(sub ? [{ label: sub.name }] : []), ...(book ? [{ label: book.name }] : [])]} />
      <SavedViews scope="content-references" density={density} filters={{ intake }} onApply={filters => setIntake(filters.intake || '')} label="نماهای رفرنس" />
      <ContentToolbar>
        <IntakeSelect intakes={intakes} value={intake} onChange={setIntake} scopeKind={intakeMeta.scope_kind} />
        <span className="spacer" />
        <ContentDensityToggle value={density} onChange={setDensity} />
        <button className="btn sm primary" onClick={() => setAddModal({ kind: 'subject' })}>➕ موضوع</button>
      </ContentToolbar>
      {err ? <ContentErrorState title="موضوع‌های رفرنس بارگذاری نشد" error={err} onRetry={loadSubjects} /> : (
        <ContentWorkspace columns={3}>
          <ContentPane icon="📖" title="موضوع‌ها" count={subjects ? subjects.length.toLocaleString('fa') : null}>
            {!subjects ? <ContentSkeleton panes={1} rows={5} /> : subjects.length === 0 ?
              <ContentEmptyState icon="📖" title="هنوز موضوعی ثبت نشده" description="برای ساخت ساختار رفرنس، نخستین موضوع را ایجاد کنید."
                action={<button className="btn sm primary" onClick={() => setAddModal({ kind: 'subject' })}>افزودن موضوع</button>} /> :
              subjects.map((subject, index) => (
                <ContentItem key={subject.id} icon="📖" title={subject.name} active={sub?.id === subject.id}
                  readonly={subject.readonly} scope={subject.intake ? 'intake' : 'global'} scopeLabel={subject.intake || 'سراسری'}
                  onClick={() => loadBooks(subject)} actions={!subject.readonly ? <>
                    <ContentReorderControls noun="موضوع" canUp={index > 0} canDown={index < subjects.length - 1}
                      onUp={() => reorderRef(() => api.refSubjectReorder(subject.id, 'up'), loadSubjects)}
                      onDown={() => reorderRef(() => api.refSubjectReorder(subject.id, 'down'), loadSubjects)} />
                    <ContentIconButton icon="✎" label="ویرایش نام موضوع" kind="primary" onClick={() => setEditModal({ kind: 'subject', item: subject })} />
                    <ContentMoreActions>
                      {intakeMeta.scope_kind === 'global' && <ContentIconButton icon="📦" label="انتقال موضوع به دامنه دیگر" onClick={() => setRootMove({ kind: 'subject', id: subject.id, label: subject.name, from: subject.intake || '' })} />}
                      <ContentIconButton icon="🗑" label={`حذف موضوع ${subject.name}`} kind="danger" onClick={() => setConfirm({
                        text: `حذف موضوع «${subject.name}» با همه‌ی کتاب‌ها و فایل‌هایش؟`,
                        run: async () => { await api.refSubjectDel(subject.id); toast('حذف شد'); setSub(null); loadSubjects(); },
                      })} />
                    </ContentMoreActions>
                  </> : null} />
              ))}
          </ContentPane>

          <ContentPane icon="📚" title="کتاب‌ها" subtitle={sub?.name} count={books ? books.length.toLocaleString('fa') : null}
            actions={sub && !sub.readonly ? <button className="btn sm primary" onClick={() => setAddModal({ kind: 'book' })} aria-label={`افزودن کتاب به ${sub.name}`}>➕ کتاب</button> : null}>
            {!sub ? <ContentEmptyState icon="📚" title="موضوعی انتخاب نشده" description="یک موضوع را برای مشاهده کتاب‌های آن انتخاب کنید." />
              : booksErr ? <ContentErrorState title="کتاب‌ها بارگذاری نشد" error={booksErr} compact onRetry={() => loadBooks(sub)} />
                : !books ? <ContentSkeleton panes={1} rows={5} />
                  : books.length === 0 ? <ContentEmptyState icon="📕" title="هنوز کتابی ثبت نشده" description="نخستین کتاب این موضوع را ایجاد کنید."
                    action={!sub.readonly ? <button className="btn sm primary" onClick={() => setAddModal({ kind: 'book' })}>افزودن کتاب</button> : null} />
                    : books.map((entry, index) => {
                      const editable = !booksReadonly || entry.is_fork || entry.intake === intake;
                      const scope = entry.is_fork ? 'override' : (entry.intake ? 'intake' : 'global');
                      return <ContentItem key={entry.id} icon={entry.is_fork ? '⭐' : '📕'} title={entry.name}
                        active={book?.id === entry.id} readonly={!editable} scope={scope}
                        scopeLabel={entry.is_fork ? 'نسخه اختصاصی' : (entry.intake || 'سراسری')}
                        onClick={() => loadFiles(entry)} actions={<>
                          {!entry.is_fork && !entry.intake && intake && <ContentIconButton icon="🍴" label="ساخت نسخه اختصاصی برای این ورودی" kind="primary" onClick={async () => {
                            try { await api.refBookFork(entry.id, intake); toast('نسخه اختصاصی ساخته شد ⭐'); loadBooks(sub); }
                            catch (error) { toast(errText(error), 'err'); }
                          }} />}
                          {editable && <>
                            <ContentReorderControls noun="کتاب" canUp={index > 0} canDown={index < books.length - 1}
                              onUp={() => reorderRef(() => api.refBookReorder(entry.id, 'up'), () => loadBooks(sub))}
                              onDown={() => reorderRef(() => api.refBookReorder(entry.id, 'down'), () => loadBooks(sub))} />
                            <ContentIconButton icon="✎" label="ویرایش نام کتاب" kind="primary" onClick={() => setEditModal({ kind: 'book', item: entry })} />
                            <ContentMoreActions>
                              {entry.is_fork && <ContentIconButton icon="↩" label="بازگشت به نسخه سراسری" onClick={async () => {
                                try { await api.refBookUnfork(entry.id); toast('↩️ بازگشت به نسخه‌ی سراسری'); loadBooks(sub); }
                                catch (error) { toast(errText(error), 'err'); }
                              }} />}
                              <ContentIconButton icon="🗑" label={`حذف کتاب ${entry.name}`} kind="danger" onClick={() => setConfirm({
                                text: `حذف کتاب «${entry.name}» و فایل‌هایش؟`,
                                run: async () => { await api.refBookDel(entry.id); toast('حذف شد'); setBook(null); loadBooks(sub); },
                              })} />
                            </ContentMoreActions>
                          </>}
                        </>} />;
                    })}
          </ContentPane>

          <ContentPane icon="📁" title="فایل‌ها" subtitle={book?.name} count={files ? Number(filesPage.total || files.length).toLocaleString('fa') : null}
            actions={book ? (filesReadonly ? <B>🔒 فقط‌خواندنی</B> : <button className="btn sm primary" onClick={() => setAddModal({ kind: 'file' })}>⬆️ آپلود فایل</button>) : null}>
            {!book ? <ContentEmptyState icon="📁" title="کتابی انتخاب نشده" description="یک کتاب را برای مشاهده فایل‌های آن انتخاب کنید." />
              : filesErr ? <ContentErrorState title="فایل‌های کتاب بارگذاری نشد" error={filesErr} compact onRetry={() => loadFiles(book)} />
                : !files ? <ContentSkeleton panes={1} rows={5} />
                  : files.length === 0 ? <ContentEmptyState icon="📭" title="هنوز فایلی ثبت نشده" description="نخستین فایل این کتاب را بارگذاری کنید."
                    action={!filesReadonly ? <button className="btn sm primary" onClick={() => setAddModal({ kind: 'file' })}>آپلود فایل</button> : null} />
                    : <>{files.map(file => <ContentItem key={file.id}
                      icon={<FileTypeBadge type="document" compact />} title={file.description || '(بدون توضیح)'}
                      meta={`${file.lang === 'fa' ? 'فارسی' : 'English'} · جلد ${file.volume}`} readonly={filesReadonly}
                      scope={book.is_fork ? 'override' : (book.intake ? 'intake' : 'global')}
                      scopeLabel={book.is_fork ? 'نسخه اختصاصی' : (book.intake || 'سراسری')}
                      metrics={<ContentMetric icon="⬇" value={Number(file.downloads || 0).toLocaleString('fa')} label="دریافت" />}
                      actions={!filesReadonly ? <ContentIconButton icon="🗑" label={`حذف فایل ${file.description || 'بدون عنوان'}`} kind="danger" onClick={() => setConfirm({
                        text: `حذف فایل «${file.description || 'بدون عنوان'}» از کتاب «${book.name}»؟`,
                        run: async () => { await api.refFileDel(file.id); toast('حذف شد'); loadFiles(book); },
                      })} /> : null} />)}
                      {filesPage.hasMore && <button className="btn content-load-more" onClick={() => loadFiles(book, true)}>نمایش فایل‌های بیشتر</button>}
                    </>}
          </ContentPane>
        </ContentWorkspace>
      )}

      {addModal && <RefAddModal kind={addModal.kind} sub={sub} book={book} intake={intake}
        onClose={(ok) => {
          const kind = addModal.kind; setAddModal(null);
          if (ok) { if (kind === 'subject') loadSubjects(); else if (kind === 'book') loadBooks(sub); else loadFiles(book); }
        }} />}
      {editModal && <RefNameModal kind={editModal.kind} item={editModal.item}
        onClose={(ok) => { const kind = editModal.kind; setEditModal(null); if (ok) kind === 'subject' ? loadSubjects() : loadBooks(sub); }} />}
      {confirm && <Confirm text={confirm.text} danger onYes={async () => { await confirm.run(); setConfirm(null); }} onNo={() => setConfirm(null)} />}
      {rootMove && <RootMoveControl item={rootMove} intakes={intakes} onClose={(ok) => { setRootMove(null); if (ok) { setSub(null); loadSubjects(); } }} />}
    </ContentShell>
  );
}

function RootMoveControl({ item, intakes, onClose }) {
  const [to, setTo] = useState(item.from || ''); const [busy, setBusy] = useState(false);
  const run = async () => { setBusy(true); try {
    if (item.kind === 'subject') await api.refSubjectMoveRoot(item.id, to);
    else await api.caMoveQbankRoot(item.id, to);
    toast('انتقال root انجام شد ✅'); onClose(true);
  } catch (e) { let conflict = ''; if (e.status === 409) { try { const d = JSON.parse(e.technical || '{}'); conflict = `${d.reason || 'تعارض مقصد'}${d.existing_id ? ` · Existing: ${d.existing_id}` : ''}`; } catch {} } toast(conflict || errText(e), 'err'); setBusy(false); } };
  return <Modal title={`📦 انتقال «${item.label}»`} onClose={() => onClose(false)}><div className="muted">مبدأ: {item.from || 'سراسری'}؛ مقصد را انتخاب کنید. overwrite ضمنی انجام نمی‌شود.</div><select className="inp content-input-full content-row-top-sm" value={to} onChange={e => setTo(e.target.value)}><option value="">🌐 سراسری</option>{intakes.map(x => <option key={x.code || x} value={x.code || x}>{x.label || x.code || x}</option>)}</select><div className="row content-row-top"><button className="btn danger" disabled={busy || to === item.from} onClick={run}>تأیید انتقال</button><button className="btn" onClick={() => onClose(false)}>انصراف</button></div></Modal>;
}

function RefNameModal({ kind, item, onClose }) {
  const [name, setName] = useState(item.name || '');
  const [busy, setBusy] = useState(false);
  return <Modal title={kind === 'subject' ? '✏️ ویرایش موضوع رفرنس' : '✏️ ویرایش نام کتاب'} onClose={() => onClose(false)}>
    <div className="grid content-modal-grid">
      <input className="inp" value={name} onChange={e => setName(e.target.value)} autoFocus />
      <div className="row"><button className="btn primary" disabled={busy || !name.trim()} onClick={async () => {
        setBusy(true);
        try {
          if (kind === 'subject') await api.refSubjectEdit(item.id, name.trim());
          else await api.refBookEdit(item.id, name.trim());
          toast('نام ذخیره شد ✅'); onClose(true);
        } catch (e) { toast(errText(e), 'err'); setBusy(false); }
      }}>ذخیره</button><button className="btn" onClick={() => onClose(false)}>انصراف</button></div>
    </div>
  </Modal>;
}

function RefAddModal({ kind, sub, book, intake, onClose }) {
  const [name, setName] = useState('');
  const [lang, setLang] = useState('fa');
  const [volume, setVolume] = useState(1);
  const [desc, setDesc] = useState('');
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const titles = { subject: '➕ موضوع جدید', book: `➕ کتاب جدید — ${sub?.name}`, file: `⬆️ فایل — ${book?.name}` };
  return (
    <Modal title={titles[kind]} onClose={() => onClose(false)}>
      <div className="grid content-modal-grid">
        {kind !== 'file' && (
          <input className="inp" placeholder={kind === 'subject' ? 'نام موضوع (مثلاً آناتومی)…' : 'نام کتاب…'}
                 value={name} onChange={e => setName(e.target.value)} />
        )}
        {kind === 'file' && (
          <>
            <div className="row">
              <select className="inp" value={lang} onChange={e => setLang(e.target.value)}>
                <option value="fa">🇮🇷 فارسی</option>
                <option value="en">🇬🇧 انگلیسی</option>
              </select>
              <input className="inp content-volume-input" type="number" min="1" value={volume}
                     onChange={e => setVolume(+e.target.value)} title="جلد" />
            </div>
            <input className="inp" placeholder="توضیح فایل…" value={desc} onChange={e => setDesc(e.target.value)} />
            <input type="file" className="inp" onChange={e => setFile(e.target.files[0] || null)} />
          </>
        )}
        <div className="row">
          <button className="btn primary" disabled={busy || (kind === 'file' ? !file : !name.trim())} onClick={async () => {
            setBusy(true);
            try {
              if (kind === 'subject') await api.refSubjectAdd({ name: name.trim(), intake: intake || '' });
              else if (kind === 'book') await api.refBookAdd(sub.id, name.trim());
              else {
                const fd = new FormData();
                fd.append('lang', lang); fd.append('volume', volume);
                fd.append('description', desc || (file && file.name) || '');
                fd.append('file', file);
                await api.refFileAdd(book.id, fd);
              }
              toast('ثبت شد ✅'); onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
          }}>{busy ? '⏳…' : 'ثبت'}</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}

// ── 📅 کلاس‌ها و برنامه (schedule با flex) ──────────────────────────
const SCHED_TYPES = [['', 'همه'], ['class', '🏫 کلاس'], ['exam', '📝 امتحان'], ['makeup', '🔄 جبرانی']];

export function ScheduleTab() {
  const [stype, setStype] = useState('');
  const [view, setView] = useState('list');
  const [items, setItems] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [edit, setEdit] = useState(null);
  const [flex, setFlex] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const load = async () => {
    setErr('');
    try { setItems((await api.caSchedule(stype || undefined)).schedule || []); }
    catch (e) { if (e.status === 403) setPermErr(true); else setErr(errText(e)); }
  };
  useEffect(() => { setItems(null); load(); }, [stype]);

  if (permErr) return <NoPerm text="مدیریت برنامه فقط برای ادمین ارشد محتواست" />;
  if (err) return <ErrorState error={err} onRetry={load} />;

  const TYPE_FA = { class: 'کلاس', exam: 'امتحان', makeup: 'جبرانی' };
  const byDate = (items || []).reduce((acc, item) => { (acc[item.date || 'بدون تاریخ'] ||= []).push(item); return acc; }, {});
  const monthKey = Object.keys(byDate).find(x => /^\d{4}-\d{2}-\d{2}$/.test(x))?.slice(0, 7) || '';
  const monthItems = monthKey ? (items || []).filter(x => (x.date || '').startsWith(monthKey)) : [];
  return (
    <>
      <div className="row content-tab-toolbar">
        <div className="tabs content-inline-tabs" role="tablist" aria-label="نوع برنامه">
          {SCHED_TYPES.map(([k, v]) => (
            <button key={k} type="button" role="tab" aria-selected={stype === k} className={`tab ${stype === k ? 'on' : ''}`} onClick={() => setStype(k)}>{v}</button>
          ))}
        </div>
        <div className="segmented" role="group" aria-label="نمای برنامه">
          {[['list', 'فهرست'], ['week', 'هفته/Agenda'], ['month', 'ماه']].map(([k, label]) => <button key={k} className={view === k ? 'on' : ''} aria-pressed={view === k} onClick={() => setView(k)}>{label}</button>)}
        </div>
        <span className="spacer" />
        <button className="btn primary" onClick={() => setEdit({ type: 'class', group: 'هر دو', flex_type: 'fixed' })}>➕ مورد جدید</button>
      </div>
      {!items ? <Loading /> : items.length === 0 ? <Empty icon="📅" text="موردی نیست" /> : (<>
        <div className={`grid content-list-grid ${view === 'list' ? '' : 'is-hidden'}`}>
          {items.map(s => (
            <div key={s.id} className="panel panel-pad row schedule-list-item">
              <span className="schedule-list-icon">{s.type === 'class' ? '🏫' : s.type === 'exam' ? '📝' : '🔄'}</span>
              <div className="content-grow-min">
                <b className="content-strong">{s.lesson}</b>
                <span className="muted"> {s.teacher || ''}</span>
                <div className="muted content-meta-top">
                  📅 <span className="code">{s.date}</span> {s.time || ''} · {s.group} {s.location ? `· 📍 ${s.location}` : ''}
                </div>
                {s.flex_note && <div className="muted content-meta-top">🔄 آخرین اعلان: {s.flex_note}</div>}
              </div>
              {s.flex_type === 'flexible' && <B kind="warn">منعطف</B>}
              <B>{TYPE_FA[s.type] || s.type}</B>
              {s.flex_type === 'flexible' &&
                <button className="btn sm" title="اعلام زمان جدید کلاس منعطف" onClick={() => setFlex(s)}>🔄 زمان جدید</button>}
              <button className="btn sm" onClick={() => setEdit({ ...s, note: s.note || '' })} aria-label={`ویرایش برنامه ${s.lesson}`}>✏️</button>
              <button className="btn sm" onClick={() => setEdit({ ...s, id: null, lesson: `${s.lesson} — کپی`, note: s.note || '' })} aria-label={`کپی برنامه ${s.lesson}`}>📄</button>
              <button className="btn sm danger" aria-label={`حذف برنامه ${s.lesson}`} onClick={() => setConfirm({
                text: `حذف «${s.lesson}» (${s.date})؟`,
                run: async () => { const r = await api.caScheduleDel(s.id); toast(`برنامه لغو و به ${Number(r.notified || 0).toLocaleString('fa')} نفر اطلاع داده شد`); load(); },
              })}>🗑</button>
            </div>
          ))}
        </div>
        {view === 'week' && <div className="schedule-agenda">
          {Object.entries(byDate).sort(([a], [b]) => a.localeCompare(b)).slice(0, 7).map(([day, rows]) => <section key={day} className="panel panel-pad">
            <div className="section-title"><span className="code">{day}</span><B>{rows.length.toLocaleString('fa')} مورد</B></div>
            <div className="grid content-grid-tight">{rows.map(s => <button key={s.id} className="schedule-agenda-item" onClick={() => setEdit({ ...s, note: s.note || '' })}>
              <span>{s.time || '—'}</span><b>{s.lesson}</b><span className="muted">{TYPE_FA[s.type] || s.type} · {s.group}</span>
            </button>)}</div>
          </section>)}
        </div>}
        {view === 'month' && <div className="schedule-month">
          <div className="schedule-month-head"><b>{monthKey || 'ماه داده‌های موجود'}</b><span className="muted">نمای ماه بر اساس تاریخ‌های واقعی ثبت‌شده</span></div>
          <div className="schedule-month-grid">{Array.from({ length: 31 }, (_, i) => i + 1).map(day => {
            const rows = monthItems.filter(x => Number((x.date || '').slice(8, 10)) === day);
            return <div key={day} className={`schedule-day ${rows.length ? 'has' : ''}`}><span className="muted">{day.toLocaleString('fa')}</span>
              {rows.slice(0, 3).map(s => <button key={s.id} onClick={() => setEdit({ ...s, note: s.note || '' })} title={`${s.lesson} · ${s.time || ''}`}>{s.time || '•'} {s.lesson}</button>)}
              {rows.length > 3 && <B>+{(rows.length - 3).toLocaleString('fa')}</B>}
            </div>;
          })}</div>
        </div>}
      </>)}
      {edit && <ScheduleModal row={edit.id ? edit : null} preset={edit}
                              onClose={(ok) => { setEdit(null); if (ok) load(); }} />}
      {flex && <FlexModal row={flex} onClose={(ok) => { setFlex(null); if (ok) load(); }} />}
      {confirm && <Confirm text={confirm.text} danger
                           onYes={async () => { await confirm.run(); setConfirm(null); }}
                           onNo={() => setConfirm(null)} />}
    </>
  );
}

function ScheduleModal({ row, preset, onClose }) {
  const [f, setF] = useState({
    type: preset.type || 'class', lesson: preset.lesson || '', teacher: preset.teacher || '',
    date: preset.date || '', time: preset.time || '', group: preset.group || 'هر دو',
    location: preset.location || '', note: preset.note || '', flex_type: preset.flex_type || 'fixed',
  });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  return (
    <Modal title={row ? '✏️ ویرایش مورد برنامه' : '➕ مورد جدید برنامه'} onClose={() => onClose(false)}>
      <div className="grid content-modal-grid">
        <div className="row">
          <select className="inp" value={f.type} onChange={e => set('type', e.target.value)}>
            {[['class', '🏫 کلاس'], ['exam', '📝 امتحان'], ['makeup', '🔄 جبرانی']].map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className="inp" value={f.flex_type} onChange={e => set('flex_type', e.target.value)}>
            <option value="fixed">زمان ثابت</option>
            <option value="flexible">منعطف (اعلام بعدی)</option>
          </select>
          <select className="inp" value={f.group} onChange={e => set('group', e.target.value)}>
            <option value="هر دو">👥 هر دو گروه</option>
            <option value="1">1️⃣ گروه ۱</option>
            <option value="2">2️⃣ گروه ۲</option>
          </select>
        </div>
        <input className="inp" placeholder="درس / عنوان *" value={f.lesson} onChange={e => set('lesson', e.target.value)} />
        <div className="row">
          <input className="inp" type="date" value={f.date} onChange={e => set('date', e.target.value)} />
          <input className="inp" type="time" value={f.time} onChange={e => set('time', e.target.value)} />
        </div>
        <input className="inp" placeholder="استاد…" value={f.teacher} onChange={e => set('teacher', e.target.value)} />
        <input className="inp" placeholder="مکان…" value={f.location} onChange={e => set('location', e.target.value)} />
        <textarea className="inp" rows={2} placeholder="یادداشت…" value={f.note} onChange={e => set('note', e.target.value)} />
        <div className="row">
          <button className="btn primary" disabled={busy || !f.lesson.trim() || !f.date} onClick={async () => {
            setBusy(true);
            try {
              const body = { ...f };
              let r;
              if (row) { delete body.type; r = await api.caScheduleEdit(row.id, body); }
              else r = await api.caScheduleCreate(body);
              toast(`ثبت شد و به ${Number(r.notified || 0).toLocaleString('fa')} نفر اطلاع داده شد ✅`); onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
          }}>{row ? 'ذخیره' : 'ایجاد + اطلاع‌رسانی'}</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}

function FlexModal({ row, onClose }) {
  const [f, setF] = useState({ date: row.date || '', time: row.time || '', note: '' });
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={`🔄 اعلام زمان جدید — ${row.lesson}`} onClose={() => onClose(false)}>
      <div className="grid content-modal-grid">
        <p className="muted">این اکشن زمان جدید را ثبت و برای دانشجویان این گروه اطلاع‌رسانی می‌کند.</p>
        <div className="row">
          <input className="inp" type="date" value={f.date} onChange={e => setF(x => ({ ...x, date: e.target.value }))} />
          <input className="inp" type="time" value={f.time} onChange={e => setF(x => ({ ...x, time: e.target.value }))} />
        </div>
        <input className="inp" placeholder="یادداشت (اختیاری)…" value={f.note} onChange={e => setF(x => ({ ...x, note: e.target.value }))} />
        <div className="row">
          <button className="btn primary" disabled={busy || !f.date} onClick={async () => {
            setBusy(true);
            try {
              const r = await api.caFlexChange(row.id, f);
              toast(`زمان جدید ثبت و به ${Number(r.notified || 0).toLocaleString('fa')} نفر اطلاع داده شد ✅`);
              onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
          }}>اعلام</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}

// ── 🗂 بانک سؤال (فایل‌های PDF/ویدیو/ویس مباحث) ─────────────────────
export function QbankTab() {
  const intakeMeta = useIntakes();
  const intakes = intakeMeta.intakes;
  const [intake, setIntake] = useState('');
  const [lesson, setLesson] = useState('');
  const [topic, setTopic] = useState('');
  const [files, setFiles] = useState(null);
  const [filePage, setFilePage] = useState({ total: 0, hasMore: false });
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [addModal, setAddModal] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [rootMove, setRootMove] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [density, setDensity] = useContentDensity();
  useEffect(() => { if (intakeMeta.scope_kind === 'scoped' && intakeMeta.scope_intake) setIntake(intakeMeta.scope_intake); }, [intakeMeta.scope_kind, intakeMeta.scope_intake]);

  const load = async (append = false) => {
    const currentCount = append ? (files || []).length : 0;
    setErr('');
    try {
      const response = await api.caQbank({ lesson, topic, intake, skip: currentCount, limit: 50 });
      const batch = response.files || [];
      setFiles(previous => append ? [...(previous || []), ...batch] : batch);
      setFilePage({ total: Number(response.total ?? batch.length), hasMore: Boolean(response.has_more) });
      if (!append) setSelectedFile(null);
    }
    catch (e) { if (e.status === 403) setPermErr(true); else setErr(errText(e)); }
  };
  useEffect(() => { setFiles(null); load(); }, [intake]);

  if (permErr) return <NoPerm text="بانک سؤال فقط برای مدیر محتواست" />;

  const applyFilters = () => { setFiles(null); load(); };
  const scopeFor = (file) => file.intake ? 'intake' : 'global';
  return (
    <ContentShell density={density}>
      <ContentBreadcrumb items={[{ label: 'محتوا' }, { label: 'بانک سؤال' }, ...(selectedFile ? [{ label: selectedFile.lesson }, { label: selectedFile.topic }] : [])]} />
      <ContentToolbar>
        <IntakeSelect intakes={intakes} value={intake} onChange={setIntake} scopeKind={intakeMeta.scope_kind} />
        <input className="inp" placeholder="درس…" value={lesson} onChange={e => setLesson(e.target.value)} onKeyDown={e => e.key === 'Enter' && applyFilters()} aria-label="فیلتر درس بانک سؤال" />
        <input className="inp" placeholder="مبحث…" value={topic} onChange={e => setTopic(e.target.value)} onKeyDown={e => e.key === 'Enter' && applyFilters()} aria-label="فیلتر مبحث بانک سؤال" />
        <button className="btn sm" onClick={applyFilters}>🔎 اعمال فیلتر</button>
        <span className="spacer" />
        <ContentDensityToggle value={density} onChange={setDensity} />
        <button className="btn primary" onClick={() => setAddModal(true)}>⬆️ آپلود فایل</button>
      </ContentToolbar>
      {err ? <ContentErrorState title="فایل‌های بانک سؤال بارگذاری نشد" error={err} onRetry={() => load()} /> : (
        <ContentWorkspace columns={2}>
          <ContentPane icon="🗂" title="فایل‌های بانک سؤال" count={files ? Number(filePage.total || files.length).toLocaleString('fa') : null}>
            {!files ? <ContentSkeleton panes={1} rows={7} /> : files.length === 0 ?
              <ContentEmptyState icon="🗂" title="فایلی پیدا نشد" description="فیلترها را تغییر دهید یا فایل تازه‌ای بارگذاری کنید."
                action={<button className="btn primary" onClick={() => setAddModal(true)}>آپلود فایل</button>} /> : <>
              {files.map(file => (
                <ContentItem key={file.id} icon={<FileTypeBadge type={file.file_type} compact />}
                  title={`${file.lesson} — ${file.topic}`} meta={file.description || 'بدون توضیح'}
                  active={selectedFile?.id === file.id} readonly={file.readonly}
                  scope={scopeFor(file)} scopeLabel={file.intake || 'سراسری'} onClick={() => setSelectedFile(file)}
                  metrics={<><ContentMetric icon="⬇" value={Number(file.downloads || 0).toLocaleString('fa')} label="دریافت" /><span className="content-date" dir="ltr">{file.upload_date}</span></>}
                  actions={!file.readonly ? <ContentMoreActions label="عملیات فایل">
                    {intakeMeta.scope_kind === 'global' && <ContentIconButton icon="📦" label="انتقال فایل به دامنه دیگر" onClick={() => setRootMove({ kind: 'qbank', id: file.id, label: file.description || `${file.lesson} / ${file.topic}`, from: file.intake || '' })} />}
                    <ContentIconButton icon="🗑" label={`حذف فایل ${file.description || file.topic}`} kind="danger" onClick={() => setConfirm({
                      text: `حذف فایل «${file.description || file.topic}» از ${file.lesson} / ${file.topic}؟`,
                      run: async () => { await api.caQbankDel(file.id); toast('حذف شد'); load(); },
                    })} />
                  </ContentMoreActions> : null} />
              ))}
              {filePage.hasMore && <button className="btn content-load-more" onClick={() => load(true)}>نمایش فایل‌های بیشتر</button>}
              </>}
          </ContentPane>
          <ContentPane icon="🔎" title="بازرس فایل" inspector actions={selectedFile ? <ScopeBadge scope={scopeFor(selectedFile)} label={selectedFile.intake || 'سراسری'} /> : null}>
            {!selectedFile ? <ContentEmptyState icon="🧭" title="فایلی انتخاب نشده" description="برای مشاهده جزئیات و عملیات، یک فایل را از فهرست انتخاب کنید." /> : <>
              <div className="content-inspector-hero"><FileTypeBadge type={selectedFile.file_type} /><div><b>{selectedFile.description || `${selectedFile.lesson} — ${selectedFile.topic}`}</b><span>{selectedFile.lesson} · {selectedFile.topic}</span></div></div>
              <ContentKV label="درس" value={selectedFile.lesson} strong />
              <ContentKV label="مبحث" value={selectedFile.topic} />
              <ContentKV label="نوع فایل" value={<FileTypeBadge type={selectedFile.file_type} compact />} />
              <ContentKV label="تاریخ بارگذاری" value={<span dir="ltr">{selectedFile.upload_date || '—'}</span>} />
              <ContentKV label="دامنه" value={<ScopeBadge scope={scopeFor(selectedFile)} label={selectedFile.intake || 'سراسری'} />} />
              <ContentStats items={[{ value: Number(selectedFile.downloads || 0).toLocaleString('fa'), label: 'دریافت' }]} />
              <ContentActionGroup>
                {selectedFile.readonly ? <B>🔒 فقط‌خواندنی</B> : <>
                  {intakeMeta.scope_kind === 'global' && <button className="btn" onClick={() => setRootMove({ kind: 'qbank', id: selectedFile.id, label: selectedFile.description || `${selectedFile.lesson} / ${selectedFile.topic}`, from: selectedFile.intake || '' })}>📦 انتقال دامنه</button>}
                  <button className="btn danger" onClick={() => setConfirm({
                    text: `حذف فایل «${selectedFile.description || selectedFile.topic}» از ${selectedFile.lesson} / ${selectedFile.topic}؟`,
                    run: async () => { await api.caQbankDel(selectedFile.id); toast('حذف شد'); setSelectedFile(null); load(); },
                  })}>🗑 حذف فایل</button>
                </>}
              </ContentActionGroup>
            </>}
          </ContentPane>
        </ContentWorkspace>
      )}
      {addModal && <QbankAddModal intakes={intakes} scopeKind={intakeMeta.scope_kind} defaultIntake={intake}
        onClose={(ok) => { setAddModal(false); if (ok) load(); }} />}
      {confirm && <Confirm text={confirm.text} danger onYes={async () => { await confirm.run(); setConfirm(null); }} onNo={() => setConfirm(null)} />}
      {rootMove && <RootMoveControl item={rootMove} intakes={intakes} onClose={(ok) => { setRootMove(null); if (ok) load(); }} />}
    </ContentShell>
  );
}

function QbankAddModal({ intakes, scopeKind, defaultIntake, onClose }) {
  const [f, setF] = useState({ lesson: '', topic: '', description: '', intake: defaultIntake || '' });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal title="⬆️ آپلود فایل بانک سؤال" onClose={() => onClose(false)}>
      <div className="grid content-modal-grid">
        <div className="row">
          <input className="inp content-grow" placeholder="درس *" value={f.lesson}
                 onChange={e => setF(x => ({ ...x, lesson: e.target.value }))} />
          <input className="inp content-grow" placeholder="مبحث *" value={f.topic}
                 onChange={e => setF(x => ({ ...x, topic: e.target.value }))} />
        </div>
        <IntakeSelect intakes={intakes} value={f.intake} scopeKind={scopeKind} onChange={v => setF(x => ({ ...x, intake: v }))} />
        <input className="inp" placeholder="توضیح…" value={f.description}
               onChange={e => setF(x => ({ ...x, description: e.target.value }))} />
        <input type="file" className="inp" onChange={e => setFile(e.target.files[0] || null)} />
        <div className="row">
          <button className="btn primary" disabled={busy || !f.lesson.trim() || !f.topic.trim() || !file} onClick={async () => {
            setBusy(true);
            try {
              const fd = new FormData();
              fd.append('lesson', f.lesson.trim()); fd.append('topic', f.topic.trim());
              fd.append('description', f.description); fd.append('intake', f.intake || '');
              fd.append('file', file);
              await api.caQbankAdd(fd);
              toast('آپلود شد ✅'); onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
          }}>{busy ? '⏳ در حال آپلود…' : 'آپلود'}</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}

// ── ❓ FAQ ──────────────────────────────────────────────────────────
export function FaqTab() {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [addModal, setAddModal] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [open, setOpen] = useState({});

  const load = async () => {
    setErr('');
    try { setItems((await api.caFaq()).items || []); }
    catch (e) { if (e.status === 403) setPermErr(true); else setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);

  if (permErr) return <NoPerm text="مدیریت FAQ فقط برای مدیر محتواست" />;
  if (err) return <ErrorState error={err} onRetry={load} />;

  const cats = {};
  (items || []).forEach(i => { (cats[i.category] = cats[i.category] || []).push(i); });
  return (
    <>
      <div className="row content-tab-toolbar">
        <span className="muted">{(items || []).length} پرسش</span>
        <span className="spacer" />
        <button className="btn primary" onClick={() => setAddModal(true)}>➕ پرسش جدید</button>
      </div>
      {!items ? <Loading /> : items.length === 0 ? <Empty icon="❓" text="پرسشی نیست" /> :
        Object.entries(cats).map(([cat, rows]) => (
          <div key={cat} className="panel content-faq-section">
            <div className="panel-pad row content-section-row">
              <b>🗂 {cat}</b><B>{rows.length}</B>
            </div>
            {rows.map(f => (
              <div key={f.id} className="row content-faq-row">
                <div className="content-faq-copy" onClick={() => setOpen(x => ({ ...x, [f.id]: !x[f.id] }))}>
                  <div className="content-faq-question">{open[f.id] ? '▾' : '▸'} {f.question}</div>
                  {open[f.id] && <div className="muted content-faq-answer">{f.answer}</div>}
                </div>
                <button className="btn sm danger" aria-label={`حذف پرسش ${f.question.slice(0, 40)}`} onClick={() => setConfirm({
                  text: `حذف پرسش «${f.question.slice(0, 40)}…»؟`,
                  run: async () => { await api.caFaqDel(f.id); toast('حذف شد'); load(); },
                })}>🗑</button>
              </div>
            ))}
          </div>
        ))}
      {addModal && <FaqAddModal onClose={(ok) => { setAddModal(false); if (ok) load(); }} />}
      {confirm && <Confirm text={confirm.text} danger
                           onYes={async () => { await confirm.run(); setConfirm(null); }}
                           onNo={() => setConfirm(null)} />}
    </>
  );
}

function FaqAddModal({ onClose }) {
  const [f, setF] = useState({ category: 'عمومی', question: '', answer: '' });
  const [busy, setBusy] = useState(false);
  return (
    <Modal title="➕ پرسش متداول جدید" onClose={() => onClose(false)}>
      <div className="grid content-modal-grid">
        <input className="inp" placeholder="دسته…" value={f.category}
               onChange={e => setF(x => ({ ...x, category: e.target.value }))} />
        <input className="inp" placeholder="پرسش (حداقل ۵ حرف) *" value={f.question}
               onChange={e => setF(x => ({ ...x, question: e.target.value }))} />
        <textarea className="inp" rows={4} placeholder="پاسخ (حداقل ۵ حرف) *" value={f.answer}
                  onChange={e => setF(x => ({ ...x, answer: e.target.value }))} />
        <div className="row">
          <button className="btn primary" disabled={busy || f.question.trim().length < 5 || f.answer.trim().length < 5} onClick={async () => {
            setBusy(true);
            try {
              await api.caFaqAdd({ category: f.category.trim() || 'عمومی', question: f.question.trim(), answer: f.answer.trim() });
              toast('ثبت شد ✅'); onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
          }}>ثبت</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}


// ── 🚩 صف و تاریخچه گزارش‌های محتوا/سؤال ────────────────────────
export function ReportsTab() {
  const [status, setStatus] = useState('new');
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const LIMIT = 30;
  const load = async () => {
    setErr(''); setData(null);
    try {
      const [rows, counts] = await Promise.all([
        api.caReports({ status: status || undefined, skip: (page - 1) * LIMIT, limit: LIMIT }),
        api.caReportStats(),
      ]);
      setData(rows); setStats(counts);
    } catch (e) { if (e.status === 403) setPermErr(true); else setErr(errText(e)); }
  };
  useEffect(() => { load(); }, [status, page]);
  const change = async () => {
    const c = confirm; setConfirm(null);
    try { await api.caReportStatus(c.row.id, c.status); toast('وضعیت گزارش ذخیره شد ✅'); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  if (permErr) return <NoPerm text="بررسی گزارش‌های محتوا نیازمند مجوز reports.review است" />;
  if (err) return <ErrorState error={err} onRetry={load} />;
  const total = data?.total || 0;
  const cols = [
    { k: 'reason', label: 'دلیل', render: r => <B kind="warn">{r.reason || '—'}</B> },
    { k: 'target_type', label: 'هدف', render: r => <div><b>{r.target_type === 'question' ? 'سؤال' : 'محتوا'}</b><div className="muted code">{r.target_id || '—'}</div></div> },
    { k: 'note', label: 'توضیح', render: r => <span className="content-pre-wrap">{r.note || '—'}</span> },
    { k: 'reporter_name', label: 'گزارش‌دهنده' },
    { k: 'created_at', label: 'ثبت' },
    { k: 'status', label: 'وضعیت', render: r => <B kind={r.status === 'resolved' ? 'ok' : r.status === 'rejected' ? 'bad' : r.status === 'reviewing' ? 'acc' : 'warn'}>{r.status}</B> },
    { k: 'ops', label: '', stop: true, render: r => <div className="row content-actions-tight">
      {r.status !== 'reviewing' && <button className="btn sm" onClick={() => setConfirm({ row: r, status: 'reviewing' })}>👁 بررسی</button>}
      {r.status !== 'resolved' && <button className="btn sm ok" onClick={() => setConfirm({ row: r, status: 'resolved' })}>✅ حل</button>}
      {r.status !== 'rejected' && <button className="btn sm danger" onClick={() => setConfirm({ row: r, status: 'rejected' })}>✖ رد</button>}
    </div> },
  ];
  return <>
    <div className="row content-tab-toolbar content-wrap">
      <div><div className="h1">گزارش‌های محتوا و سؤال</div><div className="sub">صف بررسی، وضعیت جاری و تاریخچه کامل گزارش‌های دانشجویان</div></div>
      <span className="spacer" />
      {stats && <><B kind="warn">جدید: {Number(stats.new || 0).toLocaleString('fa')}</B><B kind="acc">در بررسی: {Number(stats.reviewing || 0).toLocaleString('fa')}</B><B kind="ok">حل: {Number(stats.resolved || 0).toLocaleString('fa')}</B></>}
    </div>
    <div className="tabs content-tabs-sm" role="tablist" aria-label="وضعیت گزارش‌ها">
      {[['new', 'جدید'], ['reviewing', 'در بررسی'], ['resolved', 'حل‌شده'], ['rejected', 'ردشده'], ['', 'همه تاریخچه']].map(([k, l]) =>
        <button key={k} type="button" role="tab" aria-selected={status === k} className={`tab ${status === k ? 'on' : ''}`} onClick={() => { setStatus(k); setPage(1); }}>{l}</button>)}
    </div>
    <SavedViews scope="reports" filters={{ status }} onApply={f => { setStatus(f.status ?? 'new'); setPage(1); }} label="صف‌های ذخیره‌شده" />
    {!data ? <Loading rows={6} /> : <DataTable columns={cols} rows={data.reports || []} rowKey="id" colToggle
      pager={{ page, pages: Math.max(1, Math.ceil(total / LIMIT)), total, onPage: setPage }}
      empty={<Empty icon="🚩" text="گزارشی در این وضعیت نیست" />} />}
    {confirm && <Confirm danger={confirm.status === 'rejected'}
      text={`تغییر وضعیت گزارش #${confirm.row.id} به «${confirm.status}»؟`}
      onYes={change} onNo={() => setConfirm(null)} />}
  </>;
}
