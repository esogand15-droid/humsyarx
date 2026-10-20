import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Icon, type IconName } from '../components/Icon';
import { Badge, Chip, Empty, Note as NoteBox } from '../components/ui';
import { Sheet } from '../components/Sheet';
import { useProto } from '../lib/store';
import {
  noteTags,
  notebooks,
  notes as seed,
  pdfPage,
  versions,
  type Note,
} from '../data/notes';

/* ═══════════════════════════════════════════════════════════════════
   یادداشت‌ها — محیط کار مطالعهٔ پزشکی

   چیدمان بر اساس فضای واقعی، نه بزرگ‌نمایی موبایل:
   • ≥۱۲۰۰px  سه‌ستونه: دفترها | فهرست | ویرایشگر (+ پنل زمینه)
   • ۸۶۱–۱۱۹۹ دو‌ستونه: فهرست | ویرایشگر، دفترها در شیت
   • ≤۸۶۰     تک‌ستونه با جابه‌جایی فهرست ⇄ یادداشت (push)
   ═══════════════════════════════════════════════════════════════════ */

type SaveState = 'idle' | 'saving' | 'saved' | 'offline';

const TOOLBAR: { cmd: string; icon: IconName; label: string; arg?: string }[] = [
  { cmd: 'bold', icon: 'text', label: 'درشت' },
  { cmd: 'italic', icon: 'pen', label: 'کج' },
  { cmd: 'hiliteColor', icon: 'highlight', label: 'هایلایت', arg: 'rgba(24,217,245,.28)' },
  { cmd: 'formatBlock', icon: 'layers', label: 'سرتیتر', arg: 'h3' },
  { cmd: 'insertUnorderedList', icon: 'list', label: 'فهرست' },
  { cmd: 'insertOrderedList', icon: 'grid', label: 'فهرست شماره‌دار' },
];

function blocksToHtml(note: Note): string {
  return note.blocks
    .map((b) => {
      switch (b.kind) {
        case 'h2':
          return `<h3>${b.text}</h3>`;
        case 'p':
          return `<p>${b.text}</p>`;
        case 'list':
          return `<ul>${(b.items || []).map((i) => `<li>${i}</li>`).join('')}</ul>`;
        case 'check':
          return `<ul class="chk">${(b.items || [])
            .map((i, k) => `<li>${b.checked?.[k] ? '☑' : '☐'} ${i}</li>`)
            .join('')}</ul>`;
        case 'callout':
          return `<p class="callout"><b>نکته</b> — ${b.text}</p>`;
        case 'quote':
          return `<blockquote>${b.text}</blockquote>`;
        case 'table':
          return `<table><tbody>${(b.rows || [])
            .map((r, ri) => `<tr>${r.map((c) => (ri === 0 ? `<th>${c}</th>` : `<td>${c}</td>`)).join('')}</tr>`)
            .join('')}</tbody></table>`;
        case 'link':
          return `<p class="linked"><span>پیوند</span> ${b.text}</p>`;
        case 'ink':
          return `<p class="ink-slot">— بلوک دست‌نویس —</p>`;
        default:
          return '';
      }
    })
    .join('');
}

export function Notes() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast } = useProto();

  const [notebookId, setNotebookId] = useState('nb-all');
  const [query, setQuery] = useState('');
  const [tag, setTag] = useState<string | null>(null);
  const [onlyStarred, setOnlyStarred] = useState(false);
  const [list, setList] = useState<Note[]>(seed);
  const [save, setSave] = useState<SaveState>('saved');
  const [offline, setOffline] = useState(false);
  const [split, setSplit] = useState(false);
  const [pdfSearch, setPdfSearch] = useState('');
  const [sheet, setSheet] = useState<null | 'versions' | 'new' | 'export' | 'folders' | 'shortcuts'>(null);
  const [ink, setInk] = useState<{ x: number; y: number; w: number; c: string }[][]>([]);
  const [inkTool, setInkTool] = useState<'pen' | 'highlighter' | 'eraser'>('pen');
  const editor = useRef<HTMLDivElement | null>(null);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const drawing = useRef<{ x: number; y: number; w: number; c: string }[] | null>(null);

  const active = list.find((n) => n.id === id) || null;

  const filtered = useMemo(() => {
    return list
      .filter((n) => (notebookId === 'nb-all' ? true : n.notebook === notebookId || n.notebook.startsWith(notebookId)))
      .filter((n) => (tag ? n.tags.includes(tag) : true))
      .filter((n) => (onlyStarred ? n.starred : true))
      .filter((n) => (query ? (n.title + n.tags.join(' ') + blocksToHtml(n)).includes(query) : true))
      .sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned));
  }, [list, notebookId, tag, onlyStarred, query]);

  /* ذخیرهٔ نمایشی: تایپ → «در حال ذخیره» → «ذخیره شد» */
  const scheduleSave = useCallback(() => {
    setSave(offline ? 'offline' : 'saving');
    if (offline) return;
    window.setTimeout(() => setSave('saved'), 850);
  }, [offline]);

  useEffect(() => {
    if (!active || !editor.current) return;
    editor.current.innerHTML = blocksToHtml(active);
    setInk([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  /* کلیک میان‌بر کلیدها */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const meta = e.ctrlKey || e.metaKey;
      if (!meta) return;
      if (e.key.toLowerCase() === 's') {
        e.preventDefault();
        setSave(offline ? 'offline' : 'saved');
        toast(offline ? 'آفلاین — پیش‌نویس محلی ذخیره شد' : 'یادداشت ذخیره شد', offline ? 'info' : 'ok');
      }
      if (e.key === '/') {
        e.preventDefault();
        setSheet('shortcuts');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [offline, toast]);

  /* ── دست‌نویس: بوم ساده و صادق ─────────────────────────────── */
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const box = c.getBoundingClientRect();
    c.width = box.width * dpr;
    c.height = box.height * dpr;
    ctx.scale(dpr, dpr);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    const paint = (strokes: typeof ink) => {
      ctx.clearRect(0, 0, box.width, box.height);
      for (const stroke of strokes) {
        ctx.beginPath();
        stroke.forEach((p, i) => {
          ctx.strokeStyle = p.c;
          ctx.lineWidth = p.w;
          if (i === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        });
        ctx.stroke();
      }
    };
    paint(ink);
    const pos = (e: PointerEvent) => {
      const r = c.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    };
    const down = (e: PointerEvent) => {
      c.setPointerCapture(e.pointerId);
      const p = pos(e);
      // pressure در دستگاه‌هایی که پشتیبانی می‌کنند مقدار واقعی دارد؛ وگرنه ۰٫۵
      const press = e.pressure > 0 ? e.pressure : 0.5;
      const color =
        inkTool === 'highlighter'
          ? 'rgba(24,217,245,.35)'
          : inkTool === 'eraser'
            ? 'rgba(0,0,0,1)'
            : 'var(--ink-stroke)';
      const w = inkTool === 'highlighter' ? 14 : inkTool === 'eraser' ? 18 : 1.4 + press * 3.2;
      drawing.current = [{ ...p, w, c: color }];
      paint([...ink, drawing.current]);
    };
    const move = (e: PointerEvent) => {
      if (!drawing.current) return;
      const p = pos(e);
      const press = e.pressure > 0 ? e.pressure : 0.5;
      const last = drawing.current[drawing.current.length - 1];
      drawing.current.push({ ...p, w: last.w * 0.7 + (1.4 + press * 3.2) * 0.3, c: last.c });
      paint([...ink, drawing.current]);
    };
    const up = () => {
      if (drawing.current) {
        const finished = drawing.current;
        drawing.current = null;
        if (inkTool === 'eraser') {
          setInk([]);
        } else {
          setInk((prev) => [...prev, finished]);
          scheduleSave();
        }
      }
    };
    c.addEventListener('pointerdown', down);
    c.addEventListener('pointermove', move);
    c.addEventListener('pointerup', up);
    c.addEventListener('pointercancel', up);
    return () => {
      c.removeEventListener('pointerdown', down);
      c.removeEventListener('pointermove', move);
      c.removeEventListener('pointerup', up);
      c.removeEventListener('pointercancel', up);
    };
  }, [ink, inkTool, scheduleSave]);

  const run = (cmd: string, arg?: string) => {
    editor.current?.focus();
    document.execCommand(cmd, false, arg);
    scheduleSave();
  };

  const insert = (html: string) => {
    editor.current?.focus();
    document.execCommand('insertHTML', false, html);
    scheduleSave();
  };

  const openNote = (noteId: string) => navigate(`/notes/${noteId}`);

  const toggleStar = (noteId: string) => {
    setList((prev) => prev.map((n) => (n.id === noteId ? { ...n, starred: !n.starred } : n)));
  };

  const pdfParas = pdfPage.paragraphs.filter((p) => (pdfSearch ? p.includes(pdfSearch) : true));

  return (
    <div className="notes" data-open={active ? 'true' : 'false'}>
      {/* ── ستون ۱: دفترها و برچسب‌ها ─────────────────────────── */}
      <aside className="notes__rail" aria-label="دفترها و برچسب‌ها">
        <div className="row" style={{ marginBottom: 'var(--s-3)' }}>
          <b className="sm grow">دفترها</b>
          <button type="button" className="iconbtn iconbtn--sm" onClick={() => setSheet('new')} aria-label="دفتر یا یادداشت تازه">
            <Icon name="plus" size={15} />
          </button>
        </div>
        <nav className="notes__tree">
          {notebooks.map((nb) => (
            <button
              key={nb.id}
              type="button"
              className={`notes__node${notebookId === nb.id ? ' is-on' : ''}`}
              data-depth={nb.depth}
              onClick={() => setNotebookId(nb.id)}
              aria-current={notebookId === nb.id}
            >
              <Icon name={nb.depth ? 'chevron' : 'layers'} size={14} />
              <span className="grow">{nb.title}</span>
              <span className="num muted-2 xs">{nb.count}</span>
            </button>
          ))}
        </nav>

        <div className="row" style={{ margin: 'var(--s-4) 0 var(--s-2)' }}>
          <b className="sm grow">برچسب‌ها</b>
        </div>
        <div className="notes__tags">
          {noteTags.map((t) => (
            <Chip key={t.tag} active={tag === t.tag} onClick={() => setTag(tag === t.tag ? null : t.tag)}>
              {t.tag}
            </Chip>
          ))}
        </div>

        <div className="notes__sticky">
          <button type="button" className="btn btn--ghost btn--sm btn--block" onClick={() => setOnlyStarred((v) => !v)} aria-pressed={onlyStarred}>
            <Icon name="star" size={14} />
            {onlyStarred ? 'فقط نشان‌شده‌ها' : 'همهٔ یادداشت‌ها'}
          </button>
          <p className="xs muted-2" style={{ marginTop: 8 }}>
            ذخیره‌سازی محلی: مرورگر این دستگاه
          </p>
        </div>
      </aside>

      {/* ── ستون ۲: فهرست ─────────────────────────────────────── */}
      <section className="notes__list" aria-label="فهرست یادداشت‌ها">
        <div className="notes__listhead">
          <div className="search" style={{ minWidth: 0, flex: '1 1 auto' }}>
            <Icon name="search" size={15} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="جست‌وجو در یادداشت‌ها…"
              aria-label="جست‌وجو در یادداشت‌ها"
            />
          </div>
          <button type="button" className="btn btn--primary btn--sm press" onClick={() => setSheet('new')}>
            <Icon name="plus" size={14} />
            تازه
          </button>
        </div>
        <div className="row notes__listmeta">
          <span className="xs muted-2 grow">
            {filtered.length} یادداشت {tag ? `· برچسب «${tag}»` : ''}
          </span>
          <button type="button" className="chip chip--ghost" onClick={() => setSheet('folders')}>
            <Icon name="filter" size={13} />
            دفترها
          </button>
        </div>

        <div className="notes__cards">
          {filtered.length === 0 && (
            <Empty
              icon="note"
              title="یادداشتی با این فیلترها نیست"
              text="عبارت جست‌وجو را کوتاه‌تر کن یا فیلتر برچسب را بردار."
              action={
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => { setQuery(''); setTag(null); setNotebookId('nb-all'); }}>
                  پاک‌کردن فیلترها
                </button>
              }
            />
          )}
          {filtered.map((n) => (
            <article key={n.id} className={`ncard${active?.id === n.id ? ' is-on' : ''}`}>
              <button type="button" className="ncard__main" onClick={() => openNote(n.id)}>
                <div className="row" style={{ gap: 6 }}>
                  {n.pinned && <Icon name="pin" size={12} style={{ color: 'var(--cyan-400)' }} />}
                  <b className="ncard__t grow">{n.title}</b>
                </div>
                <p className="xs muted-2 ncard__meta">
                  {n.updated} · {n.words} واژه
                </p>
                <div className="row" style={{ gap: 4, marginTop: 6, flexWrap: 'wrap' }}>
                  {n.tags.slice(0, 2).map((t) => (
                    <Badge key={t}>{t}</Badge>
                  ))}
                  {n.anchor && (
                    <Badge tone="info">
                      <Icon name="file" size={10} /> ص {n.anchor.page}
                    </Badge>
                  )}
                </div>
              </button>
              <button
                type="button"
                className="iconbtn iconbtn--sm ncard__star"
                onClick={() => toggleStar(n.id)}
                aria-label={n.starred ? 'برداشتن نشان' : 'نشان‌کردن'}
                aria-pressed={!!n.starred}
              >
                <Icon name="star" size={14} style={{ color: n.starred ? 'var(--warn)' : 'var(--text-3)' }} />
              </button>
            </article>
          ))}
        </div>
      </section>

      {/* ── ستون ۳: ویرایشگر ──────────────────────────────────── */}
      <section className="notes__doc" aria-label="ویرایشگر یادداشت">
        {!active && (
          <div className="notes__placeholder">
            <Icon name="note" size={26} style={{ color: 'var(--text-3)' }} />
            <p className="h3">یک یادداشت را باز کن</p>
            <p className="sm muted" style={{ maxWidth: 320, textAlign: 'center' }}>
              یا یادداشت تازه‌ای بساز. تغییرات روی همین دستگاه ذخیره می‌شود.
            </p>
            <button type="button" className="btn btn--primary btn--sm" onClick={() => setSheet('new')}>
              <Icon name="plus" size={14} />
              یادداشت تازه
            </button>
          </div>
        )}

        {active && (
          <div className="doc__main">
            <header className="doc__head">
              <button type="button" className="iconbtn iconbtn--sm doc__back" onClick={() => navigate('/notes')} aria-label="بازگشت به فهرست">
                <Icon name="back" size={16} />
              </button>
              <div className="grow" style={{ minWidth: 0 }}>
                <h1 className="doc__title">{active.title}</h1>
                <p className="xs muted-2">
                  {active.updated} · {active.words} واژه ·{' '}
                  <span className={`save save--${save}`}>
                    {save === 'saving' && 'در حال ذخیره…'}
                    {save === 'saved' && (offline ? 'پیش‌نویس محلی' : 'ذخیره شد')}
                    {save === 'offline' && 'آفلاین — در انتظار همگام‌سازی'}
                    {save === 'idle' && 'آماده'}
                  </span>
                </p>
              </div>
              <div className="row" style={{ gap: 4 }}>
                <button
                  type="button"
                  className="chip chip--ghost"
                  aria-pressed={offline}
                  onClick={() => {
                    setOffline((v) => !v);
                    setSave(offline ? 'saving' : 'offline');
                    if (offline) window.setTimeout(() => setSave('saved'), 700);
                  }}
                  title="شبیه‌سازی قطع شبکه"
                >
                  <Icon name="cloud" size={13} />
                  {offline ? 'آفلاین' : 'آنلاین'}
                </button>
                <button type="button" className="iconbtn iconbtn--sm" onClick={() => setSplit((v) => !v)} aria-pressed={split} aria-label="نمای کنار‌هم با سند" title="کنار‌هم با PDF">
                  <Icon name="columns" size={16} />
                </button>
                <button type="button" className="iconbtn iconbtn--sm" onClick={() => setSheet('versions')} aria-label="نسخه‌ها و بازیابی">
                  <Icon name="clock" size={16} />
                </button>
                <button type="button" className="iconbtn iconbtn--sm" onClick={() => setSheet('export')} aria-label="خروجی و اشتراک‌گذاری">
                  <Icon name="share" size={16} />
                </button>
              </div>
            </header>

            <div className="doc__toolbar" role="toolbar" aria-label="قالب‌بندی">
              {TOOLBAR.map((t) => (
                <button key={t.label} type="button" className="toolbtn" onClick={() => run(t.cmd, t.arg)} aria-label={t.label} title={t.label}>
                  <Icon name={t.icon} size={15} />
                </button>
              ))}
              <span className="toolbar__sep" />
              <button type="button" className="toolbtn" onClick={() => insert('<p class="callout"><b>نکته</b> — </p>')} aria-label="جعبهٔ نکته" title="جعبهٔ نکته">
                <Icon name="alert" size={15} />
              </button>
              <button type="button" className="toolbtn" onClick={() => insert('<table><tbody><tr><th>عنوان</th><th>مقدار</th></tr><tr><td>—</td><td>—</td></tr></tbody></table><p></p>')} aria-label="جدول" title="جدول">
                <Icon name="grid" size={15} />
              </button>
              <button type="button" className="toolbtn" onClick={() => insert('<p class="linked"><span>پیوند</span> به منبع/سؤال…</p>')} aria-label="پیوند به منبع" title="پیوند به منبع">
                <Icon name="external" size={15} />
              </button>
              <span className="grow" />
              <button type="button" className="toolbtn" onClick={() => run('undo')} aria-label="واگرد" title="واگرد">
                <Icon name="refresh" size={15} style={{ transform: 'scaleX(-1)' }} />
              </button>
              <button type="button" className="toolbtn" onClick={() => run('redo')} aria-label="ازنو" title="ازنو">
                <Icon name="refresh" size={15} />
              </button>
            </div>

            <div className="doc__scroll">
              <div
                className="editor"
                ref={editor}
                contentEditable
                suppressContentEditableWarning
                spellCheck={false}
                role="textbox"
                aria-multiline="true"
                aria-label="متن یادداشت"
                onInput={() => scheduleSave()}
              />

              {/* ── دست‌نویس ─────────────────────────────────── */}
              <section className="ink" aria-label="دست‌نویس">
                <div className="row ink__head">
                  <b className="sm grow">دست‌نویس</b>
                  {(['pen', 'highlighter', 'eraser'] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      className="chip"
                      aria-pressed={inkTool === t}
                      onClick={() => setInkTool(t)}
                    >
                      <Icon name={t === 'pen' ? 'pen' : t === 'highlighter' ? 'highlight' : 'close'} size={13} />
                      {t === 'pen' ? 'قلم' : t === 'highlighter' ? 'هایلایتر' : 'پاک‌کن'}
                    </button>
                  ))}
                  <button type="button" className="chip chip--ghost" onClick={() => setInk([])}>
                    پاک‌کردن
                  </button>
                </div>
                <canvas className="ink__canvas" ref={canvas} aria-label="سطح نوشتن دست‌نویس" />
                <p className="xs muted-2">
                  فشار قلم در دستگاه‌های پشتیبان‌شده خوانده می‌شود؛ رد کف دست (palm rejection) و ورودی پیشرفتهٔ stylus در مرورگر
                  تضمین‌شده نیست و به لایهٔ بومی نیاز دارد.
                </p>
              </section>

              {/* ── زمینهٔ مطالعه ─────────────────────────────── */}
              {active.anchor && (
                <section className="ctx" aria-label="زمینهٔ مطالعه">
                  <div className="ctx__row">
                    <Icon name="file" size={15} style={{ color: 'var(--cyan-400)' }} />
                    <div className="grow">
                      <b className="sm">{active.anchor.label}</b>
                      <p className="xs muted-2">این یادداشت به صفحهٔ {active.anchor.page} لنگر شده است</p>
                    </div>
                    <button type="button" className="btn btn--ghost btn--sm" onClick={() => navigate(`/library/${active.anchor!.resourceId}`)}>
                      بازکردن
                    </button>
                  </div>
                  <div className="ctx__row">
                    <Icon name="card" size={15} style={{ color: 'var(--teal-500)' }} />
                    <div className="grow">
                      <b className="sm">۴ فلش‌کارت از این یادداشت</b>
                      <p className="xs muted-2">مرور فردا · فاصله‌گذاری ۱ / ۳ / ۷</p>
                    </div>
                    <button type="button" className="btn btn--ghost btn--sm" onClick={() => toast('مرور فلش‌کارت از همین یادداشت ساخته می‌شود.', 'info')}>
                      مرور
                    </button>
                  </div>
                  <div className="ctx__row">
                    <Icon name="sparkle" size={15} style={{ color: 'var(--cyan-400)' }} />
                    <div className="grow">
                      <b className="sm">هوشیار: خلاصهٔ سه‌خطی بساز</b>
                      <p className="xs muted-2">از همین یادداشت</p>
                    </div>
                    <button
                      type="button"
                      className="btn btn--accent btn--sm"
                      onClick={() => insert('<p class="callout"><b>خلاصهٔ هوشیار</b> — سه نکتهٔ کلیدی این جلسه را همین‌جا جمع کن.</p>')}
                    >
                      درج
                    </button>
                  </div>
                </section>
              )}
            </div>
          </div>
        )}

        {/* ── پنل کنار‌هم: سند ─────────────────────────────── */}
        {active && split && (
          <div className="pdfpane" aria-label="نمای سند">
            <div className="pdfpane__head">
              <Icon name="file" size={14} />
              <b className="xs grow">{pdfPage.src}</b>
              <span className="num xs muted-2">
                {pdfPage.page} / {pdfPage.of}
              </span>
              <button type="button" className="iconbtn iconbtn--sm" onClick={() => setSplit(false)} aria-label="بستن سند">
                <Icon name="close" size={14} />
              </button>
            </div>
            <div className="pdfpane__search search" style={{ minWidth: 0 }}>
              <Icon name="search" size={14} />
              <input value={pdfSearch} onChange={(e) => setPdfSearch(e.target.value)} placeholder="جست‌وجو در متن سند…" aria-label="جست‌وجو در متن سند" />
            </div>
            <div className="pdfpane__page">
              <h3 className="pdfpane__h">فصل ۳ — چرخهٔ قلبی</h3>
              {pdfParas.map((p) => (
                <p key={p} className={p.includes('رد کف') || p.includes('فشار بطنی افزایش') ? 'pdfpane__hl' : ''}>
                  {p}
                </p>
              ))}
              {pdfParas.length === 0 && <p className="sm muted">عبارت در این صفحه پیدا نشد.</p>}
              <button
                type="button"
                className="btn btn--ghost btn--sm press"
                onClick={() => insert(`<p class="linked"><span>پیوند</span> «${pdfPage.highlight}» — ص ${pdfPage.page}</p>`)}
              >
                <Icon name="pin" size={13} />
                پیوند این پاراگراف به یادداشت
              </button>
            </div>
            <div className="pdfpane__foot">
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => toast('صفحهٔ قبل')}>
                <Icon name="back" size={13} /> قبل
              </button>
              <span className="xs muted-2 num">حالت مطالعه حفظ می‌شود</span>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => toast('صفحهٔ بعد')}>
                بعد <Icon name="forward" size={13} />
              </button>
            </div>
          </div>
        )}
      </section>

      {/* ── شیت‌ها ────────────────────────────────────────────── */}
      <Sheet open={sheet === 'versions'} title="نسخه‌ها و بازیابی" onClose={() => setSheet(null)}>
        <div className="stack">
          {versions.map((v, i) => (
            <div key={v.id} className="vrow">
              <div className="grow">
                <b className="sm">{v.label}</b>
                <p className="xs muted-2">
                  {v.when} · {v.size}
                </p>
              </div>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                disabled={i === 0}
                onClick={() => {
                  setSheet(null);
                  toast(`«${v.label}» بازیابی شد.`, 'info');
                }}
              >
                بازیابی
              </button>
            </div>
          ))}
        </div>
        <NoteBox tone="warn" icon="alert">
          نسخه‌ها روی سرور نگه داشته می‌شوند؛ اگر دو دستگاه هم‌زمان یک یادداشت را تغییر دهند، نسخهٔ جدیدتر با
          تأیید تو جایگزین می‌شود.
        </NoteBox>
      </Sheet>

      <Sheet open={sheet === 'new'} title="یادداشت تازه" onClose={() => setSheet(null)}>
        <label className="field">
          <span className="field__l">عنوان</span>
          <input className="input" defaultValue="یادداشت تازه" aria-label="عنوان یادداشت" />
        </label>
        <label className="field">
          <span className="field__l">دفتر</span>
          <select className="input" aria-label="دفتر">
            {notebooks.slice(1).map((nb) => (
              <option key={nb.id}>{nb.title}</option>
            ))}
          </select>
        </label>
        <p className="xs muted-2">الگوی آمادهٔ پزشکی: شرح حال، خلاصهٔ جلسه، مرور دارو.</p>
        <div className="row" style={{ marginTop: 'var(--s-3)' }}>
          <button
            type="button"
            className="btn btn--primary btn--sm grow"
            onClick={() => {
              setSheet(null);
              toast('یادداشت در دفتر انتخابی ساخته می‌شود.', 'ok');
            }}
          >
            ساختن
          </button>
        </div>
      </Sheet>

      <Sheet open={sheet === 'export'} title="خروجی و اشتراک" onClose={() => setSheet(null)}>
        <div className="stack">
          {['PDF با قالب مطالعه', 'Markdown', 'تصویر صفحه', 'پیوند اشتراک‌گذاری (فقط‌خواندنی)'].map((x) => (
            <button
              key={x}
              type="button"
              className="vrow vrow--btn"
              onClick={() => {
                setSheet(null);
                toast(`${x}: در نسخهٔ آزمایشی فعال نیست`, 'err');
              }}
            >
              <span className="sm grow">{x}</span>
              <Icon name="download" size={15} />
            </button>
          ))}
        </div>
      </Sheet>

      <Sheet open={sheet === 'folders'} title="دفترها و جابه‌جایی" onClose={() => setSheet(null)}>
        <div className="stack">
          {notebooks.map((nb) => (
            <button
              key={nb.id}
              type="button"
              className="vrow vrow--btn"
              onClick={() => {
                setNotebookId(nb.id);
                setSheet(null);
              }}
            >
              <Icon name={nb.depth ? 'chevron' : 'layers'} size={14} />
              <span className="sm grow">{nb.title}</span>
              <span className="num xs muted-2">{nb.count}</span>
            </button>
          ))}
        </div>
      </Sheet>

      <Sheet open={sheet === 'shortcuts'} title="میان‌برهای صفحه‌کلید" onClose={() => setSheet(null)}>
        <div className="stack">
          {[
            ['Ctrl/⌘ + S', 'ذخیرهٔ فوری'],
            ['Ctrl/⌘ + K', 'جست‌وجوی سراسری'],
            ['Ctrl/⌘ + /', 'همین راهنما'],
            ['Tab', 'حرکت بین کنترل‌ها'],
            ['Esc', 'بستن شیت یا دیالوگ'],
          ].map(([k, v]) => (
            <div key={k} className="vrow">
              <span className="sm grow">{v}</span>
              <kbd className="kbd" dir="ltr">
                {k}
              </kbd>
            </div>
          ))}
        </div>
      </Sheet>
    </div>
  );
}
