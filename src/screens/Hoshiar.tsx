import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../components/Icon';
import { Badge, Chip, Dialog, Note } from '../components/ui';
import { fa, useProto } from '../lib/store';
import { aiPrompts, aiSeed, aiThreads, student, type AiMsg } from '../data/demo';

/* ═══════════════════════════════════════════════════════════════════
   SC-040 — هوشیار، دستیار مطالعه
   فضای اختصاصی: ریسهٔ گفتگوها، پاسخ ساخت‌یافته، منابع، کنش‌های بعدی.
   پاسخ نمایشی است و صریحاً همین را می‌گوید؛ هیچ ادعای اتصال به سرویس AI
   واقعی نمی‌شود.
   ═══════════════════════════════════════════════════════════════════ */

type Stage = 'idle' | 'thinking' | 'streaming' | 'error';

const DEMO_ANSWER = {
  paragraphs: [
    'برای اینکه این را دقیق ببینی، اول باید مشخص کنیم دربارهٔ کدام بخش حرف می‌زنیم. اگر منظور «فشار انتهای دیاستول» به‌عنوان پیش‌بار قلب است، رابطهٔ کلیدی این است:',
  ],
  bullets: [
    'افزایش پیش‌بار (EDV) با کشش بیشتر میوکارد، حجم ضربه‌ای را بالا می‌برد — رابطهٔ فرانک–استارلینگ.',
    'در تاکی‌کاردی، دیاستول کوتاه می‌شود و پرشدن کاهش می‌یابد؛ پس پیش‌بار افت می‌کند.',
    'افت پیش‌بار یعنی حجم ضربه‌ای کمتر؛ در ضربان‌های خیلی بالا برون‌ده قلبی هم می‌افتد.',
  ],
  sources: [
    { label: 'جزوهٔ فیزیولوژی قلب — جلسهٔ ۷', ref: 'R1 · ص ۱۲–۱۸' },
    { label: 'بانک سؤال — ۳ سؤال مرتبط', ref: 'Q1 · Q6' },
  ],
};

export function Hoshiar() {
  const navigate = useNavigate();
  const { toast } = useProto();
  const [msgs, setMsgs] = useState<AiMsg[]>(aiSeed);
  const [draft, setDraft] = useState('');
  const [stage, setStage] = useState<Stage>('idle');
  const [activeThread, setActiveThread] = useState('T1');
  const [limitDlg, setLimitDlg] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' });
  }, [msgs, stage]);

  const send = (text: string) => {
    const t = text.trim();
    if (!t) return;
    if (student.subscription.aiDailyUsed >= student.subscription.aiDailyLimit) {
      setLimitDlg(true);
      return;
    }
    setMsgs((m) => [...m, { id: `u${Date.now()}`, role: 'me', text: t, time: '۱۰:۳۲' }]);
    setDraft('');
    setStage('thinking');

    window.setTimeout(() => setStage('streaming'), 900);
    window.setTimeout(() => {
      setMsgs((m) => [
        ...m,
        {
          id: `a${Date.now()}`,
          role: 'ai',
          time: '۱۰:۳۲',
          paragraphs: DEMO_ANSWER.paragraphs,
          bullets: DEMO_ANSWER.bullets,
          sources: DEMO_ANSWER.sources,
        },
      ]);
      setStage('idle');
    }, 2100);
  };

  return (
    <div className="ai-shell">
      {/* ریسهٔ گفتگوها */}
      <aside className="ai-rail" aria-label="گفتگوهای هوشیار">
        <button type="button" className="btn btn--primary btn--sm btn--block" onClick={() => toast('گفتگوی تازه ساخته شد (نمایشی).', 'ok')}>
          <Icon name="plus" size={14} />
          گفتگوی تازه
        </button>

        <div className="xs muted-2" style={{ padding: '12px 4px 4px' }}>
          گفتگوهای اخیر
        </div>
        {aiThreads.map((t) => (
          <button
            key={t.id}
            type="button"
            className="ai-rail__item"
            aria-current={activeThread === t.id}
            onClick={() => setActiveThread(t.id)}
          >
            <b>{t.title}</b>
            <span>{t.when}</span>
          </button>
        ))}

        <div style={{ marginTop: 'auto', paddingTop: 12 }}>
          <div className="panel panel--quiet" style={{ padding: 10 }}>
            <div className="xs muted-2" style={{ marginBottom: 6 }}>
              سهمیهٔ امروز
            </div>
            <div className="row" style={{ gap: 8 }}>
              <div className="bar" style={{ flex: 1 }}>
                <i style={{ width: `${(student.subscription.aiDailyUsed / student.subscription.aiDailyLimit) * 100}%` }} />
              </div>
              <span className="xs num">
                {fa(student.subscription.aiDailyUsed)}/{fa(student.subscription.aiDailyLimit)}
              </span>
            </div>
          </div>
        </div>
      </aside>

      {/* گفتگو */}
      <div className="ai-main">
        <div className="ai-head">
          <span className="avatar avatar--ai">
            <Icon name="sparkle" size={17} />
          </span>
          <div style={{ minWidth: 0 }}>
            <div className="sm" style={{ fontWeight: 600 }}>
              هوشیار
            </div>
            <div className="xs muted-2">دستیار مطالعه — پاسخ‌ها نمایشی‌اند</div>
          </div>
          <span className="grow" />
          <Badge tone="info" className="ai-head__demo">
            <span className="dot" /> نسخهٔ نمایشی
          </Badge>
          <button type="button" className="iconbtn" onClick={() => navigate('/me/subscription')} aria-label="ارتقای پلن">
            <Icon name="card" size={16} />
          </button>
        </div>

        <div className="ai-thread" ref={threadRef} role="log" aria-live="polite" aria-label="گفتگو با هوشیار">
          <div className="row xs muted-2" style={{ justifyContent: 'center', gap: 8 }}>
            <Icon name="shield" size={13} />
            پاسخ‌ها با ارجاع به منابع خود هامزیار ساخته می‌شوند
          </div>

          {msgs.map((m) => (
            <Bubble key={m.id} m={m} onAction={(a) => toast(a, 'ok')} />
          ))}

          {stage === 'thinking' && (
            <div className="msg">
              <span className="avatar avatar--ai">
                <Icon name="sparkle" size={16} />
              </span>
              <div className="msg__b">
                <div className="row xs muted" style={{ gap: 8 }}>
                  <div className="typing">
                    <i /> <i /> <i />
                  </div>
                  در حال مرور منابع درس تو…
                </div>
              </div>
            </div>
          )}

          {stage === 'error' && (
            <div className="msg">
              <div className="msg__b" style={{ borderColor: 'rgba(255,107,122,.35)' }}>
                <div className="row sm" style={{ gap: 8, color: 'var(--danger)' }}>
                  <Icon name="alert" size={15} />
                  پاسخ کامل نشد
                </div>
                <p className="sm muted" style={{ marginTop: 6 }}>
                  ارتباط قطع شد. پیامت حفظ شده است؛ دوباره تلاش کن.
                </p>
                <button type="button" className="btn btn--ghost btn--sm" style={{ marginTop: 10 }} onClick={() => setStage('idle')}>
                  <Icon name="refresh" size={13} />
                  تلاش دوباره
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="composer">
          {msgs.length <= 2 && (
            <div className="prompts">
              {aiPrompts.map((p) => (
                <Chip key={p} onClick={() => send(p)} ai>
                  <Icon name="sparkle" size={12} />
                  {p}
                </Chip>
              ))}
            </div>
          )}

          <div className="composer__box">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  send(draft);
                }
              }}
              placeholder="سؤالت را بنویس… مثلاً: «چرا تاکی‌کاردی حجم ضربه‌ای را کم می‌کند؟»"
              aria-label="متن پیام به هوشیار"
              rows={2}
            />
            <div className="composer__row">
              <button
                type="button"
                className="iconbtn"
                title="پیوست فایل"
                aria-label="پیوست فایل"
                onClick={() => toast('ارسال PDF و تصویر در این نسخهٔ نمایشی وصل نیست.', 'err')}
              >
                <Icon name="clip" size={17} />
              </button>
              <button
                type="button"
                className="iconbtn"
                title="پیام صوتی"
                aria-label="پیام صوتی"
                onClick={() => toast('پیام صوتی در این نسخهٔ نمایشی وصل نیست.', 'err')}
              >
                <Icon name="mic" size={17} />
              </button>
              <span className="xs muted-2">Enter ارسال · Shift+Enter خط تازه</span>
              <span className="grow" />
              <button
                type="button"
                className="btn btn--accent btn--sm"
                onClick={() => send(draft)}
                disabled={!draft.trim() || stage !== 'idle'}
                aria-busy={stage !== 'idle'}
              >
                <Icon name="send" size={14} />
                ارسال
              </button>
            </div>
          </div>

          <div className="row" style={{ marginTop: 8, gap: 8, flexWrap: 'wrap' }}>
            <span className="xs muted-2">پاسخ نمایشی است؛ به سرویس واقعی AI وصل نیست.</span>
            <span className="grow" />
            <button type="button" className="xs" style={{ color: 'var(--text-3)' }} onClick={() => setStage('error')}>
              نمایش حالت خطا
            </button>
          </div>
        </div>
      </div>

      <Dialog
        open={limitDlg}
        title="سهمیهٔ امروز هوشیار تمام شد"
        onClose={() => setLimitDlg(false)}
        actions={
          <>
            <button type="button" className="btn btn--accent btn--sm" onClick={() => { setLimitDlg(false); navigate('/me/subscription'); }}>
              مشاهدهٔ پلن‌ها
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setLimitDlg(false)}>
              فردا ادامه می‌دهم
            </button>
          </>
        }
      >
        سهمیهٔ روزانه از سرور کنترل می‌شود. با پلن بالاتر، تعداد پیام‌های روزانه بیشتر می‌شود؛ در این نسخه
        نمایشی چیزی خریداری نمی‌شود.
      </Dialog>
    </div>
  );
}

function Bubble({ m, onAction }: { m: AiMsg; onAction: (s: string) => void }) {
  const mine = m.role === 'me';
  return (
    <div className={`msg${mine ? ' msg--me' : ''}`}>
      {mine ? (
        <span className="avatar">{student.initials}</span>
      ) : (
        <span className="avatar avatar--ai">
          <Icon name="sparkle" size={16} />
        </span>
      )}
      <div style={{ minWidth: 0 }}>
        <div className="msg__b">
          {m.text && <p>{m.text}</p>}
          {m.paragraphs?.map((p, i) => (
            <p key={i} className={i === 0 && m.text ? '' : undefined}>
              {p}
            </p>
          ))}
          {m.bullets && (
            <ul>
              {m.bullets.map((b) => (
                <li key={b} className="sm">
                  {b}
                </li>
              ))}
            </ul>
          )}
          {m.sources && (
            <div className="msg__src">
              {m.sources.map((s) => (
                <Chip key={s.label} ghost title={s.ref}>
                  <Icon name="file" size={12} />
                  {s.label}
                </Chip>
              ))}
            </div>
          )}
          {!mine && (
            <div className="msg__acts">
              <button type="button" className="btn btn--quiet btn--sm" onClick={() => onAction('پاسخ در کلیپ‌بورد کپی شد.')}>
                <Icon name="copy" size={13} />
                کپی
              </button>
              <button type="button" className="btn btn--quiet btn--sm" onClick={() => onAction('سه سؤال تمرینی از این توضیح ساخته شد.')}>
                <Icon name="question" size={13} />
                سؤال تمرینی بساز
              </button>
              <button type="button" className="btn btn--quiet btn--sm" onClick={() => onAction('به برنامهٔ مطالعه اضافه شد.')}>
                <Icon name="calendar" size={13} />
                افزودن به برنامه
              </button>
              <button type="button" className="btn btn--quiet btn--sm" onClick={() => onAction('بازخورد ثبت شد.')}>
                <Icon name="thumb" size={13} />
                مناسب بود
              </button>
            </div>
          )}
        </div>
        <div className="xs muted-2" style={{ marginTop: 6, paddingInline: 4 }}>
          {m.time}
        </div>
      </div>
    </div>
  );
}

export function HoshiarNote() {
  return (
    <Note tone="ai" icon="sparkle">
      هوشیار در این پروتوتایپ فقط نمایشی است.
    </Note>
  );
}
