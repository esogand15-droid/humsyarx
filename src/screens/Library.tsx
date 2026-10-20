import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Icon } from '../components/Icon';
import { Badge, Chip, Dialog, Empty, Note, Progress, Skeleton } from '../components/ui';
import { PageTitle } from '../components/Shell';
import { fa, useProto } from '../lib/store';
import { resources, resourceFilters, questions, type ResourceItem } from '../data/demo';

/* ═══════════════════════════════════════════════════════════════════
   SC-020 — کشف منابع      SC-021 — جزئیات و پیش‌نمایش منبع
   کشف با فیلتر واقعی (نه چیدمان تزئینی): عبارت، درس، نوع فایل، مرتب‌سازی.
   قفل منابع از سرور می‌آید؛ در UI صادقانه نشان داده می‌شود.
   ═══════════════════════════════════════════════════════════════════ */

type Sort = 'recent' | 'lesson' | 'kind';

export function Library() {
  const navigate = useNavigate();
  const { toast } = useProto();
  const [q, setQ] = useState('');
  const [lesson, setLesson] = useState('همه');
  const [kinds, setKinds] = useState<string[]>([]);
  const [sort, setSort] = useState<Sort>('recent');
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<'all' | 'mine' | 'new'>('all');

  const list = useMemo(() => {
    let out = resources.filter((r) => {
      const hay = `${r.title} ${r.lesson} ${r.topic} ${r.teacher} ${r.tags?.join(' ') ?? ''}`;
      const okQ = !q.trim() || hay.includes(q.trim());
      const okL = lesson === 'همه' || r.lesson === lesson;
      const okK = kinds.length === 0 || kinds.includes(r.kind);
      const okT = tab === 'all' || (tab === 'mine' ? !r.locked : r.updatedAt.includes('پیش') || r.updatedAt.includes('روز'));
      return okQ && okL && okK && okT;
    });
    if (sort === 'lesson') out = [...out].sort((a, b) => a.lesson.localeCompare(b.lesson, 'fa'));
    if (sort === 'kind') out = [...out].sort((a, b) => a.kind.localeCompare(b.kind));
    return out;
  }, [q, lesson, kinds, sort, tab]);

  const toggleKind = (k: string) => setKinds((v) => (v.includes(k) ? v.filter((x) => x !== k) : [...v, k]));

  const simulateLoad = () => {
    setLoading(true);
    window.setTimeout(() => {
      setLoading(false);
      toast('فهرست به‌روز شد.', 'ok');
    }, 1200);
  };

  return (
    <div className="page">
      <PageTitle
        title="منابع درسی"
        sub="جزوه‌ها، ویدیوها، صوت و اسلایدهای درس‌های علوم پایه — مطابق ورودی تحصیلی تو"
        actions={
          <button type="button" className="btn btn--ghost btn--sm" onClick={simulateLoad} aria-busy={loading}>
            <Icon name="refresh" size={15} />
            تازه‌سازی
          </button>
        }
      />

      {/* ── جست‌وجو و فیلتر ─────────────────────────────────── */}
      <div className="panel panel--pad" style={{ display: 'grid', gap: 14 }}>
        <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
          <div className="search" style={{ flex: '1 1 320px', minWidth: 0, maxWidth: 'none' }}>
            <Icon name="search" size={16} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="در عنوان، درس، مبحث یا استاد جست‌وجو کن…"
              aria-label="جست‌وجو در منابع"
            />
            {q && (
              <button type="button" className="iconbtn" style={{ width: 24, height: 24 }} onClick={() => setQ('')} aria-label="پاک‌کردن جست‌وجو">
                <Icon name="close" size={13} />
              </button>
            )}
          </div>
          <div className="seg" role="group" aria-label="مرتب‌سازی">
            {(
              [
                ['recent', 'تازه‌ترین'],
                ['lesson', 'بر اساس درس'],
                ['kind', 'بر اساس نوع'],
              ] as [Sort, string][]
            ).map(([k, l]) => (
              <button key={k} type="button" aria-pressed={sort === k} onClick={() => setSort(k)}>
                {l}
              </button>
            ))}
          </div>
        </div>

        <div className="filters">
          {resourceFilters.lessons.map((l) => (
            <Chip key={l} active={lesson === l} onClick={() => setLesson(l)}>
              {l}
            </Chip>
          ))}
        </div>

        <div className="filters">
          <span className="xs muted-2" style={{ marginInlineEnd: 4 }}>
            نوع فایل:
          </span>
          {resourceFilters.kinds.map((k) => (
            <Chip key={k.key} active={kinds.includes(k.key)} onClick={() => toggleKind(k.key)}>
              <Icon name={k.key === 'pdf' ? 'file' : k.key === 'video' ? 'video' : k.key === 'audio' ? 'audio' : 'slide'} size={13} />
              {k.label}
            </Chip>
          ))}
          {(kinds.length > 0 || lesson !== 'همه' || q) && (
            <button
              type="button"
              className="btn btn--quiet btn--sm"
              onClick={() => {
                setKinds([]);
                setLesson('همه');
                setQ('');
              }}
            >
              <Icon name="close" size={13} />
              پاک‌کردن فیلترها
            </button>
          )}
        </div>
      </div>

      {/* ── تب‌ها ───────────────────────────────────────────── */}
      <div className="tabs" role="tablist" aria-label="نمای فهرست" style={{ marginTop: 18 }}>
        {(
          [
            ['all', 'همهٔ منابع'],
            ['new', 'تازه‌ها'],
            ['mine', 'در دسترس من'],
          ] as ['all' | 'new' | 'mine', string][]
        ).map(([k, l]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className="tab" onClick={() => setTab(k)}>
            {l}
          </button>
        ))}
      </div>

      <div className="result-meta">
        <span className="num">{fa(list.length)}</span> منبع
        {q && <span>برای «{q}»</span>}
        {lesson !== 'همه' && <span>· {lesson}</span>}
        {kinds.length > 0 && <span>· {kinds.length} نوع فایل</span>}
      </div>

      {/* ── فهرست ───────────────────────────────────────────── */}
      {loading ? (
        <div className="panel panel--pad">
          <Skeleton rows={5} />
        </div>
      ) : list.length === 0 ? (
        <div className="panel">
          <Empty
            icon="search"
            title="چیزی با این فیلتر پیدا نشد"
            text="عبارت جست‌وجو کوتاه‌تر کن یا فیلتر درس و نوع فایل را بردار. اگر فکر می‌کنی منبع باید باشد، از پشتیبانی بپرس."
            action={
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => {
                  setQ('');
                  setLesson('همه');
                  setKinds([]);
                }}
              >
                پاک‌کردن فیلترها
              </button>
            }
          />
        </div>
      ) : (
        <div className="panel panel--flush">
          {list.map((r) => (
            <button key={r.id} type="button" className="rrow" onClick={() => navigate(`/library/${r.id}`)}>
              <span className={`rrow__ic rrow__ic--${r.kind}`}>
                <Icon name={r.kind === 'pdf' ? 'file' : r.kind === 'video' ? 'video' : r.kind === 'audio' ? 'audio' : 'slide'} size={18} />
              </span>
              <span style={{ minWidth: 0 }}>
                <span className="rrow__t" style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {r.title}
                </span>
                <span className="rrow__m">
                  <span>{r.lesson}</span>
                  <span>{r.topic}</span>
                  {r.pages ? <span className="num">{fa(r.pages)} صفحه</span> : <span className="num">{r.duration}</span>}
                  <span>{r.updatedAt}</span>
                </span>
              </span>
              {r.locked ? <Badge tone="locked">نیازمند ارتقا</Badge> : <Badge tone="ok">همهٔ پلن‌ها</Badge>}
              <span className="rrow__go" aria-hidden="true">
                <Icon name="back" size={16} />
              </span>
            </button>
          ))}
        </div>
      )}

      <div className="row" style={{ marginTop: 16, gap: 10, flexWrap: 'wrap' }}>
        <Note icon="info">
          دسترسی هر منبع از سرور تعیین می‌شود: منبع «همهٔ پلن‌ها» برای همه باز است و منبع «نیازمند ارتقا» تا
          فعال‌شدن پلن، فقط پیش‌نمایش دارد.
        </Note>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   جزئیات منبع
   ═══════════════════════════════════════════════════════════════════ */
export function ResourceDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast } = useProto();
  const r = resources.find((x) => x.id === id) ?? resources[0];
  const [page, setPage] = useState(18);
  const [playing, setPlaying] = useState(false);
  const [dlg, setDlg] = useState(false);
  const [askAi, setAskAi] = useState(false);

  const related = questions.filter((q) => q.lesson === r.lesson).slice(0, 3);
  const isReading = r.kind === 'pdf' || r.kind === 'slide';
  const total = r.pages ?? 0;

  return (
    <div className="page">
      <nav className="row xs muted-2" style={{ gap: 6, marginBottom: 12 }} aria-label="مسیر">
        <Link to="/library">منابع درسی</Link>
        <Icon name="back" size={12} />
        <span>{r.lesson}</span>
        <Icon name="back" size={12} />
        <span style={{ color: 'var(--text-2)' }}>{r.topic}</span>
      </nav>

      <div className="row" style={{ alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0, flex: '1 1 460px' }}>
          <h1 className="h1">{r.title}</h1>
          <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
            <Badge tone="info">{r.kind === 'pdf' ? 'جزوه' : r.kind === 'video' ? 'ویدیو' : r.kind === 'audio' ? 'صوت' : 'اسلاید'}</Badge>
            <Chip ghost>{r.lesson}</Chip>
            <Chip ghost>{r.topic}</Chip>
            <span className="xs muted-2">{r.teacher}</span>
            <span className="xs muted-2">· به‌روزرسانی {r.updatedAt}</span>
          </div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setAskAi(true)}>
            <Icon name="sparkle" size={14} style={{ color: 'var(--cyan-400)' }} />
            بپرس از هوشیار
          </button>
          <button
            type="button"
            className="btn btn--primary btn--sm"
            onClick={() => (r.locked ? setDlg(true) : toast('برای مطالعهٔ آفلاین آماده شد.', 'ok'))}
          >
            <Icon name="download" size={14} />
            دانلود
          </button>
        </div>
      </div>

      {r.locked && (
        <div style={{ marginTop: 16 }}>
          <Note tone="warn" icon="lock">
            <b>این منبع در پلن فعلی تو نیست.</b> محتوای قفل‌شده از سمت سرور بسته می‌شود؛ دکمهٔ «ارتقای اشتراک»
            وضعیت را بررسی می‌کند، نه اینکه محتوا را در مرورگر باز کند.
          </Note>
        </div>
      )}

      <div className="rdetail" style={{ marginTop: 20 }}>
        {/* پیش‌نمایش */}
        <div>
          <div className="preview">
            <div className="preview__bar">
              <Icon name={isReading ? 'file' : r.kind === 'video' ? 'video' : 'audio'} size={15} />
              <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {r.title}
              </span>
              <span className="grow" />
              {isReading && (
                <>
                  <button type="button" className="btn btn--quiet btn--sm" onClick={() => setPage((p) => Math.max(1, p - 1))} aria-label="صفحهٔ قبل">
                    <Icon name="back" size={14} />
                  </button>
                  <span className="num xs">
                    {fa(page)} / {fa(total)}
                  </span>
                  <button type="button" className="btn btn--quiet btn--sm" onClick={() => setPage((p) => Math.min(total, p + 1))} aria-label="صفحهٔ بعد">
                    <Icon name="forward" size={14} />
                  </button>
                </>
              )}
            </div>

            <div className="preview__page" style={{ position: 'relative' }}>
              {r.locked ? (
                <>
                  <Icon name="lock" size={26} style={{ color: 'var(--text-3)' }} />
                  <div>
                    <b style={{ color: 'var(--text-2)' }}>پیش‌نمایش قفل است</b>
                    <p className="xs" style={{ marginTop: 6, maxWidth: '34ch' }}>
                      پیش‌نمایش رایگان این منبع در پلن تو باز نیست. با ارتقا، مطالعه و دانلود فعال می‌شود.
                    </p>
                  </div>
                  <button type="button" className="btn btn--accent btn--sm" onClick={() => setDlg(true)}>
                    مشاهدهٔ پلن‌ها
                  </button>
                </>
              ) : r.kind === 'video' ? (
                <div style={{ width: '100%', display: 'grid', gap: 12 }}>
                  <div
                    style={{
                      aspectRatio: '16 / 9',
                      borderRadius: 'var(--r-md)',
                      background: 'linear-gradient(160deg, #0B1730, #071020)',
                      border: '1px solid var(--line)',
                      display: 'grid',
                      placeItems: 'center',
                    }}
                  >
                    <button
                      type="button"
                      className="btn btn--ghost"
                      style={{ width: 58, height: 58, borderRadius: 999 }}
                      onClick={() => setPlaying((p) => !p)}
                      aria-label={playing ? 'توقف' : 'پخش'}
                    >
                      <Icon name={playing ? 'pause' : 'play'} size={20} fill />
                    </button>
                  </div>
                  <div className="row" style={{ width: '100%', gap: 10 }}>
                    <span className="xs num">۱۲:۳۴</span>
                    <div style={{ flex: 1 }}>
                      <Progress value={playing ? 34 : 23} />
                    </div>
                    <span className="xs num muted-2">{r.duration}</span>
                  </div>
                  <p className="xs muted-2">پیش‌نمایش کوتاه؛ فایل کامل در کتابخانه است.</p>
                </div>
              ) : r.kind === 'audio' ? (
                <div style={{ width: '100%', display: 'grid', gap: 14 }}>
                  <Icon name="audio" size={30} style={{ color: 'var(--teal-500)' }} />
                  <b style={{ color: 'var(--text-2)' }}>پادکست مرور — {r.duration}</b>
                  <div className="row" style={{ width: '100%', gap: 10, maxWidth: 360 }}>
                    <button type="button" className="btn btn--ghost btn--icon" onClick={() => setPlaying((p) => !p)} aria-label="پخش">
                      <Icon name={playing ? 'pause' : 'play'} size={16} fill />
                    </button>
                    <div style={{ flex: 1 }}>
                      <Progress value={playing ? 41 : 12} />
                    </div>
                    <span className="xs num">۰۸:۱۲</span>
                  </div>
                </div>
              ) : (
                <div style={{ width: '100%', textAlign: 'start' }}>
                  <div className="xs muted-2 num" style={{ marginBottom: 10 }}>
                    صفحهٔ {fa(page)} از {fa(total)}
                  </div>
                  <div style={{ display: 'grid', gap: 8, maxWidth: '54ch', margin: '0 auto' }}>
                    {Array.from({ length: 7 }).map((_, i) => (
                      <div
                        key={i}
                        className="skel"
                        style={{ height: 9, width: i === 6 ? '58%' : i === 2 ? '88%' : '100%', borderRadius: 3 }}
                      />
                    ))}
                    <div className="note note--ai" style={{ marginTop: 12, textAlign: 'start' }}>
                      <Icon name="sparkle" size={14} style={{ marginTop: 3 }} />
                      <span className="xs">
                        هوشیار می‌تواند همین صفحه را خلاصه کند یا از آن سؤال بسازد — نمونهٔ واقعی در صفحهٔ
                        هوشیار.
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="row" style={{ marginTop: 14, gap: 8, flexWrap: 'wrap' }}>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => toast('یادداشت روی این صفحه ذخیره شد.', 'ok')}>
              <Icon name="plus" size={14} />
              یادداشت روی صفحه
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => navigate('/exam/practice')}>
              <Icon name="question" size={14} />
              تمرین از این مبحث
            </button>
            <button type="button" className="btn btn--quiet btn--sm" onClick={() => toast('پیوند کپی شد.')}>
              <Icon name="share" size={14} />
              اشتراک‌گذاری
            </button>
          </div>
        </div>

        {/* ستون اطلاعات */}
        <aside style={{ display: 'grid', gap: 16 }}>
          <section className="panel panel--pad">
            <b className="h3">دربارهٔ این منبع</b>
            <p className="sm muted" style={{ marginTop: 8, lineHeight: 1.85 }}>
              {r.description}
            </p>
            <div className="trace" />
            <dl className="kv">
              <dt>درس</dt>
              <dd>{r.lesson}</dd>
              <dt>مبحث</dt>
              <dd>{r.topic}</dd>
              <dt>استاد</dt>
              <dd>{r.teacher}</dd>
              <dt>{isReading ? 'تعداد صفحه' : 'مدت'}</dt>
              <dd className="num">{isReading ? fa(total) : r.duration}</dd>
              <dt>حجم</dt>
              <dd className="num">{r.size}</dd>
              <dt>دسترسی</dt>
              <dd>{r.locked ? 'نیازمند ارتقای پلن' : 'فعال در پلن تو'}</dd>
            </dl>
          </section>

          <section className="panel panel--pad">
            <div className="row" style={{ marginBottom: 10 }}>
              <b className="h3">تمرین مرتبط</b>
              <span className="grow" />
              <Link to="/exam" className="xs" style={{ color: 'var(--cyan-400)' }}>
                همه
              </Link>
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              {related.map((qu) => (
                <button
                  key={qu.id}
                  type="button"
                  className="panel panel--quiet"
                  style={{ padding: 10, textAlign: 'start', cursor: 'pointer' }}
                  onClick={() => navigate('/exam/practice')}
                >
                  <div className="xs muted-2">
                    {qu.topic} · {qu.difficulty}
                  </div>
                  <div className="sm" style={{ marginTop: 4, lineHeight: 1.7 }}>
                    {qu.stem.slice(0, 74)}…
                  </div>
                </button>
              ))}
              {related.length === 0 && <p className="xs muted-2">برای این درس هنوز سؤالی ثبت نشده است.</p>}
            </div>
          </section>
        </aside>
      </div>

      <Dialog
        open={dlg}
        title="این منبع در پلن فعلی تو نیست"
        onClose={() => setDlg(false)}
        actions={
          <>
            <Link to="/me/subscription" className="btn btn--accent btn--sm">
              مشاهدهٔ پلن‌ها
            </Link>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setDlg(false)}>
              بعداً
            </button>
          </>
        }
      >
        دسترسی به این فایل با پلن «جامع» باز می‌شود. بررسی نهایی همیشه سمت سرور انجام می‌شود؛ این دیالوگ فقط
        توضیح می‌دهد، نه اینکه محتوا را باز کند.
      </Dialog>

      <Dialog
        open={askAi}
        title="پرسش از هوشیار دربارهٔ این منبع"
        onClose={() => setAskAi(false)}
        actions={
          <>
            <button
              type="button"
              className="btn btn--accent btn--sm"
              onClick={() => {
                setAskAi(false);
                navigate('/ai');
              }}
            >
              رفتن به گفتگو
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setAskAi(false)}>
              بستن
            </button>
          </>
        }
      >
        هوشیار می‌تواند از همین منبع خلاصه، سؤال تمرینی یا نقشهٔ مفهومی بسازد. پیام تو با ارجاع به همین
        فایل به گفتگو اضافه می‌شود.
      </Dialog>
    </div>
  );
}

export function LibraryLoadingPreview() {
  return <Skeleton rows={4} />;
}

export type { ResourceItem };
