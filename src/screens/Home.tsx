import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Icon } from '../components/Icon';
import { Badge, Collapse, Note, Progress, Ring, SectionHead } from '../components/ui';
import { PageTitle } from '../components/Shell';
import { fa, useProto } from '../lib/store';
import {
  announcements, lessons, progressSummary, resources, student, tasks, upcomingExams, weekStudy,
} from '../data/demo';

/* ═══════════════════════════════════════════════════════════════════
   SC-010 — خانهٔ دانشجو

   سلسله‌مراتب عمداً برای موبایل نوشته شده و برای دسکتاپ بازچینش می‌شود:
   موبایل (به ترتیب): ۱ قهرمان ۲ آزمون بعدی ۳ دسترسی‌های اصلی
   ۴ نمودار فشردهٔ هفته ۵ کارهای امروز ۶ تازه‌ها ۷ هوشیار ۸ بقیه
   دسکتاپ: دو ستون — اصلی | کنار، بدون کوچک‌شدن فونت و کارت.
   چیدمان با container query روی «قاب» تعیین می‌شود، نه عرض پنجره.
   ═══════════════════════════════════════════════════════════════════ */

export function Home() {
  const navigate = useNavigate();
  const { toast } = useProto();
  const [done, setDone] = useState<Record<string, boolean>>(
    Object.fromEntries(tasks.map((t) => [t.id, t.done])),
  );

  const weekly = Math.round((progressSummary.weeklyMinutes / progressSummary.weeklyTarget) * 100);
  const lastResource = resources[0];
  const nextExam = upcomingExams[0];
  const hours = Math.round(progressSummary.weeklyMinutes / 60);
  const target = Math.round(progressSummary.weeklyTarget / 60);

  const toggle = (id: string) => {
    setDone((d) => {
      const v = !d[id];
      toast(v ? 'کار انجام‌شده علامت خورد.' : 'علامت انجام برداشته شد.', v ? 'ok' : 'info');
      return { ...d, [id]: v };
    });
  };

  return (
    <div className="page">
      <PageTitle
        title={`سلام ${student.name.split(' ')[0]}`}
        sub={`${student.stage} · ${student.major} · ${student.term}`}
        actions={
          <div className="hello__chips">
            <span className="chip">
              <Icon name="flame" size={13} style={{ color: 'var(--warn)' }} />
              <span className="num">{fa(progressSummary.streakDays)}</span> روز پیوسته
            </span>
            <Badge tone="ok">
              <span className="dot" /> اشتراک فعال
            </Badge>
          </div>
        }
      />

      <div className="home">
        <div className="home__main">
          {/* آزمون بعدی — در موبایل بند اول پس از سلام */}
          <section className="sec-exam-next panel examnext" aria-label="آزمون بعدی">
            <span className={`countdown${nextExam.inDays <= 3 ? ' countdown--urgent' : ''}`}>
              <b className="num">{fa(nextExam.inDays)}</b>
              <span>روز</span>
            </span>
            <div className="grow" style={{ minWidth: 0 }}>
              <div className="xs muted-2">آزمون بعدی · {nextExam.kind}</div>
              <b className="sm examnext__t">{nextExam.title}</b>
            </div>
            <button type="button" className="iconbtn" aria-label="برنامهٔ آزمون" onClick={() => navigate('/plan')}>
              <Icon name="calendar" size={16} />
            </button>
          </section>

          {/* ۱. قهرمان: ادامهٔ مطالعه */}
          <section className="continue sec-hero" aria-labelledby="continue-t">
            <div className="continue__top">
              <Icon name="book-open" size={15} />
              ادامهٔ مطالعه
              <span className="grow" />
              <span className="xs">۲ ساعت پیش</span>
            </div>
            <h2 id="continue-t">{lastResource.title}</h2>
            <p>
              {lastResource.lesson} · {lastResource.topic} · {lastResource.teacher}
            </p>

            <div className="continue__bar">
              <div className="row" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
                <span className="xs muted">صفحهٔ ۱۸ از {fa(lastResource.pages ?? 0)}</span>
                <span className="xs num muted">۴۳٪</span>
              </div>
              <Progress value={43} />
            </div>

            <div className="continue__actions">
              <button type="button" className="btn btn--primary" onClick={() => navigate('/library/R1')}>
                <Icon name="play" size={15} fill />
                ادامهٔ خواندن
              </button>
              <button type="button" className="btn btn--ghost" onClick={() => navigate('/exam/practice')}>
                <Icon name="question" size={15} />
                آزمون سریع
              </button>
              <button
                type="button"
                className="btn btn--quiet btn--icon"
                aria-label="افزودن به برنامهٔ مطالعه"
                title="افزودن به برنامه"
                onClick={() => toast('به فهرست «امروز» در برنامهٔ مطالعه اضافه شد.', 'ok')}
              >
                <Icon name="plus" size={16} />
              </button>
            </div>
          </section>

          {/* ۳. دسترسی سریع */}
          <div className="quick sec-quick">
            <Link to="/exam" className="quick__i">
              <Icon name="target" size={19} />
              <b>تمرین هدفمند</b>
              <span>۳۰ سؤال از نقاط ضعف</span>
            </Link>
            <Link to="/ai" className="quick__i">
              <Icon name="sparkle" size={19} />
              <b>پرسش از هوشیار</b>
              <span>توضیح، ساخت سؤال، خلاصه</span>
            </Link>
            <Link to="/notes" className="quick__i">
              <Icon name="note" size={19} />
              <b>یادداشت‌ها</b>
              <span>ادامهٔ نوشتن جلسهٔ ۷</span>
            </Link>
            <Link to="/plan" className="quick__i">
              <Icon name="calendar" size={19} />
              <b>برنامهٔ امروز</b>
              <span>{fa(tasks.filter((t) => !t.done).length)} کار باقی‌مانده</span>
            </Link>
          </div>

          {/* ۵. کارهای امروز */}
          <div className="sec-tasks">
            <SectionHead
              title="امروز چه کاری؟"
              hint={`${fa(Object.values(done).filter(Boolean).length)} از ${fa(tasks.length)} انجام شده`}
              action={
                <Link to="/plan" className="xs" style={{ color: 'var(--cyan-400)' }}>
                  برنامهٔ کامل
                </Link>
              }
            />
            <div className="panel panel--flush">
              {tasks.map((t) => {
                const isDone = done[t.id];
                return (
                  <div key={t.id} className="rrow" style={{ gridTemplateColumns: 'auto minmax(0,1fr) auto' }}>
                    <button
                      type="button"
                      className="check-dot"
                      data-on={isDone ? 'true' : 'false'}
                      onClick={() => toggle(t.id)}
                      aria-pressed={isDone}
                      aria-label={`${t.title} — ${isDone ? 'انجام شده' : 'انجام نشده'}`}
                    >
                      {isDone && <Icon name="check" size={14} />}
                    </button>
                    <span style={{ minWidth: 0 }}>
                      <span
                        className="rrow__t"
                        style={{ textDecoration: isDone ? 'line-through' : 'none', color: isDone ? 'var(--text-3)' : undefined }}
                      >
                        {t.title}
                      </span>
                      <span className="rrow__m">
                        <span>{t.due}</span>
                      </span>
                    </span>
                    {t.urgent && !isDone ? <Badge tone="warn">امروز</Badge> : <span />}
                  </div>
                );
              })}
            </div>
          </div>

          {/* ۶. تازه‌ها */}
          <div className="sec-res">
            <SectionHead
              title="تازه‌های درس‌های تو"
              hint="۳ منبع تازه در ۷ روز"
              action={
                <Link to="/library" className="xs" style={{ color: 'var(--cyan-400)' }}>
                  همهٔ منابع
                </Link>
              }
            />
            <div className="panel panel--flush">
              <Collapse label="منابع">
              {resources.slice(0, 4).map((r) => (
                <button key={r.id} type="button" className="rrow" onClick={() => navigate(`/library/${r.id}`)}>
                  <span className={`rrow__ic rrow__ic--${r.kind}`}>
                    <Icon
                      name={r.kind === 'pdf' ? 'file' : r.kind === 'video' ? 'video' : r.kind === 'audio' ? 'audio' : 'slide'}
                      size={18}
                    />
                  </span>
                  <span style={{ minWidth: 0 }}>
                    <span className="rrow__t" style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.title}
                    </span>
                    <span className="rrow__m">
                      <span>{r.lesson}</span>
                      <span>{r.updatedAt}</span>
                      {r.duration && <span className="num">{r.duration}</span>}
                      {r.pages && <span className="num">{fa(r.pages)} صفحه</span>}
                    </span>
                  </span>
                  {r.locked ? <Badge tone="locked">قفل</Badge> : <Badge tone="info">جدید</Badge>}
                  <span className="rrow__go" aria-hidden="true">
                    <Icon name="back" size={16} />
                  </span>
                </button>
              ))}
              </Collapse>
            </div>
          </div>

          {/* ۷. هوشیار */}
          <div className="ai-strip sec-ai">
            <span className="avatar avatar--ai" style={{ width: 38, height: 38, borderRadius: 11 }}>
              <Icon name="sparkle" size={18} />
            </span>
            <div className="grow">
              <div className="sm" style={{ fontWeight: 600 }}>
                هوشیار منتظر سؤال توست
              </div>
              <div className="xs muted">
                امروز {fa(student.subscription.aiDailyUsed)} از {fa(student.subscription.aiDailyLimit)} پیام
              </div>
            </div>
            <Link to="/ai" className="btn btn--accent btn--sm">
              گفتگو
              <Icon name="back" size={14} />
            </Link>
          </div>
        </div>

        <div className="home__side">
          {/* ۴. هفتهٔ تو — نمودار واکنش‌گرا */}
          <section className="panel panel--pad week-card sec-week" aria-labelledby="week-t">
            <div className="row" style={{ marginBottom: 14 }}>
              <b className="h3" id="week-t">
                هفتهٔ تو
              </b>
              <span className="grow" />
              <span className="xs muted-2">هدف {fa(target)} ساعت</span>
            </div>

            <div className="weekbar-sum">
              <b className="num">{fa(hours)}</b>
              <span className="xs muted">
                از {fa(target)} ساعت · {fa(weekly)}٪ هدف
              </span>
            </div>

            <div className="week-head">
              <Ring value={weekly} size={72} label="هدف هفته" />
              <div className="week-head__stats">
                <div className="stat">
                  <span className="stat__v num">
                    {fa(hours)}
                    <span className="xs muted" style={{ fontWeight: 400 }}> ساعت</span>
                  </span>
                  <span className="stat__l">مطالعهٔ این هفته</span>
                </div>
                <div className="stat">
                  <span className="stat__v num">{fa(progressSummary.accuracy)}٪</span>
                  <span className="stat__l">دقت از {fa(progressSummary.questionsAnswered)} سؤال</span>
                </div>
              </div>
            </div>

            <div className="weekbars" role="img" aria-label={`نمودار مطالعهٔ روزهای هفته: ${fa(hours)} ساعت از ${fa(target)} ساعت هدف`}>
              {weekStudy.map((d) => (
                <div key={d.label} className="weekbars__b" title={`${d.label} — ${fa(d.minutes)} دقیقه`}>
                  <i style={{ height: `${Math.min(100, (d.minutes / 180) * 100)}%` }} />
                  <span>{d.label.slice(0, 3)}</span>
                </div>
              ))}
            </div>
          </section>

          {/* آزمون‌های پیشِ رو (فهرست کامل — دسکتاپ/تبلت) */}
          <section className="panel panel--flush sec-exams" aria-labelledby="exam-t">
            <div className="panel__head">
              <Icon name="calendar" size={16} style={{ color: 'var(--warn)' }} />
              <b className="h3" id="exam-t" style={{ fontSize: 'var(--fs-h3)' }}>
                آزمون‌های پیشِ رو
              </b>
            </div>
            {upcomingExams.map((e) => (
              <div key={e.id} className="rrow" style={{ gridTemplateColumns: 'auto minmax(0,1fr) auto', cursor: 'default' }}>
                <span className={`countdown${e.inDays <= 3 ? ' countdown--urgent' : ''}`}>
                  <b className="num">{fa(e.inDays)}</b>
                  <span>روز</span>
                </span>
                <span style={{ minWidth: 0 }}>
                  <span className="rrow__t">{e.title}</span>
                  <span className="rrow__m">
                    <span>{e.date}</span>
                    <span>{e.scope}</span>
                  </span>
                </span>
                <Badge>{e.kind}</Badge>
              </div>
            ))}
          </section>

          {/* پیشرفت درس‌ها */}
          <section className="panel panel--pad sec-lessons" aria-labelledby="lessons-t">
            <div className="row" style={{ marginBottom: 14 }}>
              <b className="h3" id="lessons-t">
                پیشرفت درس‌ها
              </b>
              <span className="grow" />
              <Link to="/exam" className="xs" style={{ color: 'var(--cyan-400)' }}>
                بانک سؤال
              </Link>
            </div>
            <Collapse label="درس‌ها">
            <div style={{ display: 'grid', gap: 12 }}>
              {lessons.map((l) => (
                <div key={l.id}>
                  <div className="row" style={{ justifyContent: 'space-between', marginBottom: 5 }}>
                    <Link to="/library" className="sm" style={{ fontWeight: 500 }}>
                      {l.name}
                    </Link>
                    <span className="xs num muted-2">{fa(l.progress)}٪</span>
                  </div>
                  <Progress value={l.progress} />
                </div>
              ))}
            </div>
            </Collapse>
          </section>

          {/* اطلاعیه‌ها */}
          <section className="panel panel--flush sec-ann" aria-labelledby="ann-t">
            <div className="panel__head">
              <Icon name="info" size={16} style={{ color: 'var(--cyan-400)' }} />
              <b id="ann-t" className="h3" style={{ fontSize: 'var(--fs-h3)' }}>
                اطلاعیه‌های آموزشی
              </b>
            </div>
            <Collapse label="اطلاعیه‌ها">
            {announcements.map((a) => (
              <div key={a.id} className="announce">
                <div className="announce__d">
                  <b className="num">{a.day}</b>
                  {a.month}
                </div>
                <div style={{ minWidth: 0 }}>
                  <div className="sm" style={{ fontWeight: 600 }}>
                    {a.title}
                  </div>
                  <p className="xs muted" style={{ marginTop: 2 }}>
                    {a.body}
                  </p>
                </div>
              </div>
            ))}
            </Collapse>
          </section>
        </div>
      </div>

      <div className="trace trace--node" />

      <Note tone="ai" icon="sparkle">
        <b>این صفحه نمایشی است.</b> همهٔ اعداد، درس‌ها و اعلان‌ها دادهٔ ساختگی برای بررسی طراحی‌اند و به هیچ سرویس
        واقعی وصل نیستند.
      </Note>
    </div>
  );
}
