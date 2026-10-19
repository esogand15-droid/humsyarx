import { useEffect, useRef, useState } from 'react';

import { fa, humanSize } from '../../lib/library';

interface Props {
  url: string;
  kind: 'video' | 'audio' | 'image';
  name: string;
  size: number;
  /** ثانیهٔ ذخیره‌شده برای ادامهٔ پخش */
  startAt: number;
  onPosition: (seconds: number) => void;
}

/** پخش ویدیو/ویس و نمایش تصویر از همان آدرس رله‌شده.
    Range پشتیبانی می‌شود، پس seek روی فایل بزرگ هم کار می‌کند. */
export function MediaView({ url, kind, name, size, startAt, onPosition }: Props) {
  const ref = useRef<HTMLVideoElement | HTMLAudioElement | null>(null);
  const [failed, setFailed] = useState(false);
  const lastSaved = useRef(0);

  // ادامهٔ پخش از همان‌جا که مانده بود (یک بار)
  useEffect(() => {
    const el = ref.current;
    if (!el || !startAt || startAt < 3) return;
    const onMeta = () => {
      try {
        el.currentTime = startAt;
      } catch {
        /* بعضی فرمت‌ها seek اولیه را نمی‌پذیرند؛ از ابتدا پخش می‌شود */
      }
    };
    el.addEventListener('loadedmetadata', onMeta, { once: true });
    return () => el.removeEventListener('loadedmetadata', onMeta);
  }, [startAt]);

  if (kind === 'image') {
    return (
      <div className="reader reader--image">
        <img src={url} alt={name} className="reader__img" onError={() => setFailed(true)} />
        {failed && <p className="small mt-8">تصویر باز نشد؛ لینک ممکن است منقضی شده باشد.</p>}
        <p className="tiny mt-8">{humanSize(size)}</p>
      </div>
    );
  }

  const common = {
    controls: true,
    preload: 'metadata' as const,
    onError: () => setFailed(true),
    onTimeUpdate: (e: React.SyntheticEvent<HTMLMediaElement>) => {
      const t = e.currentTarget.currentTime;
      // ذخیرهٔ هر ۵ ثانیه، نه در هر فریم
      if (t - lastSaved.current > 5) {
        lastSaved.current = t;
        onPosition(t);
      }
    },
    onPause: (e: React.SyntheticEvent<HTMLMediaElement>) => onPosition(e.currentTarget.currentTime),
  };

  return (
    <div className={`reader ${kind === 'video' ? 'reader--video' : 'reader--audio'}`}>
      {kind === 'video' ? (
        <video
          {...common}
          ref={ref as React.RefObject<HTMLVideoElement>}
          className="reader__video"
          src={url}
          playsInline
        >
          مرورگر تو پخش ویدیو را پشتیبانی نمی‌کند.
        </video>
      ) : (
        <div className="reader__center">
          <AudioPlayer
            name={name}
            size={size}
            src={url}
            startAt={startAt}
            onPosition={onPosition}
            onError={() => setFailed(true)}
          />
        </div>
      )}

      {failed && (
        <p className="notice notice--warn mt-12" role="alert">
          پخش ممکن نشد. اگر صفحه مدت زیادی باز مانده، یک بار ببند و دوباره باز کن (لینک ۱۰ دقیقه
          اعتبار دارد).
        </p>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- */
/* پخش‌کنندهٔ صدا — کنترل‌های خودمان، نه نوار بومی مرورگر              */
/* ---------------------------------------------------------------- */

const clock = (sec: number) => {
  if (!Number.isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${fa(m)}:${s < 10 ? '۰' : ''}${fa(s)}`;
};

const RATES = [1, 1.25, 1.5, 2];

function AudioPlayer({
  name,
  size,
  src,
  startAt,
  onPosition,
  onError,
}: {
  name: string;
  size: number;
  src: string;
  startAt: number;
  onPosition: (seconds: number) => void;
  onError: () => void;
}) {
  const ref = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [dur, setDur] = useState(0);
  const [rate, setRate] = useState(1);
  const saved = useRef(0);

  // بازگرداندن نرخ پخش بعد از هر تغییر
  useEffect(() => {
    if (ref.current) ref.current.playbackRate = rate;
  }, [rate]);

  const toggle = () => {
    const el = ref.current;
    if (!el) return;
    if (el.paused) void el.play().catch(() => onError());
    else el.pause();
  };

  const skip = (delta: number) => {
    const el = ref.current;
    if (!el) return;
    el.currentTime = Math.max(0, Math.min(dur || el.duration || 0, el.currentTime + delta));
    setTime(el.currentTime);
  };

  return (
    <div className="aud">
      <audio
        ref={ref}
        src={src}
        preload="metadata"
        onLoadedMetadata={(e) => {
          const el = e.currentTarget;
          setDur(el.duration || 0);
          if (startAt >= 3) {
            try {
              el.currentTime = startAt;
            } catch {
              /* فرمت‌هایی که seek اولیه را نمی‌پذیرند از ابتدا پخش می‌شوند */
            }
          }
        }}
        onTimeUpdate={(e) => {
          const t = e.currentTarget.currentTime;
          setTime(t);
          // ذخیرهٔ هر ۵ ثانیه، نه در هر فریم
          if (t - saved.current > 5) {
            saved.current = t;
            onPosition(t);
          }
        }}
        onPlay={() => setPlaying(true)}
        onPause={(e) => {
          setPlaying(false);
          onPosition(e.currentTarget.currentTime);
        }}
        onEnded={() => setPlaying(false)}
        onError={onError}
      >
        مرورگر تو پخش صدا را پشتیبانی نمی‌کند.
      </audio>

      <p className="aud__name">{name}</p>

      <input
        className="aud__seek"
        type="range"
        style={{ ['--p' as string]: `${dur > 0 ? Math.min(100, (time / dur) * 100) : 0}%` }}
        min={0}
        max={Math.max(1, Math.floor(dur))}
        step={1}
        value={Math.floor(time)}
        aria-label="جای پخش"
        aria-valuetext={`${clock(time)} از ${clock(dur)}`}
        onChange={(e) => {
          const el = ref.current;
          const v = Number(e.target.value);
          if (el) el.currentTime = v;
          setTime(v);
        }}
      />

      <div className="aud__row">
        <button type="button" className="aud__play" onClick={toggle} aria-label={playing ? 'توقف' : 'پخش'}>
          <span className="aud__glyph" aria-hidden="true">{playing ? '❚❚' : '▶'}</span>
        </button>
        <button type="button" className="aud__skip" onClick={() => skip(-10)} aria-label="۱۰ ثانیه عقب">
          <span className="num" dir="ltr">−۱۰</span>
        </button>
        <button type="button" className="aud__skip" onClick={() => skip(10)} aria-label="۱۰ ثانیه جلو">
          <span className="num" dir="ltr">+۱۰</span>
        </button>
        <span className="aud__time num" dir="ltr" aria-live="off">
          {clock(time)} / {clock(dur)}
        </span>
        <button
          type="button"
          className="aud__rate num"
          onClick={() => setRate(RATES[(RATES.indexOf(rate) + 1) % RATES.length])}
          aria-label={`سرعت پخش ${rate} برابر؛ برای تغییر بزن`}
          dir="ltr"
        >
          {rate === 1 ? '۱×' : `${fa(rate)}×`}
        </button>
      </div>

      <p className="tiny mt-8">{humanSize(size)} · پخش فقط داخل هامزیار</p>
    </div>
  );
}
