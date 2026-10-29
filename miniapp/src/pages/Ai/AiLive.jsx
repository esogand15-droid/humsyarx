import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';

import {
  useQuery,
} from '@tanstack/react-query';

import Header from '../../components/layout/Header';
import {
  Spinner,
} from '../../components/shared/Loading';
import api, {
  API_ORIGIN,
} from '../../lib/api';
import {
  getInitData,
  haptic,
  hapticNotif,
} from '../../lib/telegram';
import { Glyph } from '../../components/ui/Icon';

/* ─────────────────────────────────────────────────────────────
    م9.5 — موتور صوتی سطح استودیویی تماس زنده با هوشیار (Google Gemini Live API)
   - معماری AudioWorkletProcessor روی ترد اختصاصی بلادرنگ صدا (Ring Buffer دایره‌ای ۴۵ ثانیه‌ای)
   - انتقال باینری مستقیم (Zero-Copy ArrayBuffer) روی WebSocket (حذف کامل سربار Base64/JSON روی ترد UI)
   - درون‌یابی ۴ نقطه‌ای مکعبی Catmull-Rom / Half-Band Lagrange از 24kHz به نرخ بومی سخت‌افزار
   - بافر تطبیقی خودتنظیم‌شونده (Adaptive Jitter Buffer) + پوش کسینوسی (Raised-Cosine Fade-In/Out)
   - فیلتر High-Pass 85Hz میکروفون + Local Barge-in Ducking + سیگنال پایان صحبت (audioStreamEnd)
───────────────────────────────────────────────────────────── */

const HUMSYAR_LIVE_WORKLET_CODE = `
class HumsyarLiveAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    const sr = sampleRate || 48000;
    this.sr = sr;
    this.cap = Math.max(48000 * 30, Math.floor(sr * 45));
    this.ring = new Float32Array(this.cap);
    this.readPos = 0;
    this.writePos = 0;
    this.avail = 0;

    // تاریخچه ۴ نقطه‌ای درون‌یابی مکعبی 24kHz -> sampleRate
    this.hasHist = false;
    this.sm2 = 0;
    this.sm1 = 0;
    this.s0 = 0;
    this.resamplePhase = 0;

    // وضعیت Adaptive Jitter Buffer و پوش ضدکلیک کسینوسی
    this.playing = false;
    this.prebuffering = true;
    this.turnComplete = false;
    this.targetPrebufSec = 0.115;
    this.firstBufTime = 0;
    this.lastOut = 0;
    this.fadeInTotal = Math.max(32, Math.floor(sr * 0.003));
    this.fadeInRem = 0;
    this.fadeStartSample = 0;
    this.clearFadeRem = 0;
    this.clearFadeTotal = Math.max(64, Math.floor(sr * 0.004));
    this.duckGain = 1.0;
    this.speakerMuted = false;

    // وضعیت ضبط میکروفون (DC-Blocker 25Hz + Decimator 16kHz + سپر ضد اکوی اسپیکر م9.7)
    this.micMuted = false;
    this.hpPrevX = 0;
    this.hpPrevY = 0;
    this.hpAlpha = Math.exp((-2 * Math.PI * 25) / sr);
    this.decimRatio = sr / 16000;
    this.decimAcc = 0;
    this.decimSum = 0;
    this.decimCount = 0;
    this.micOut = new Int16Array(640); // 40ms @ 16kHz = 640 samples
    this.micIdx = 0;
    this.micVoiceFrames = 0;
    this.echoTailSamples = 0;

    // تله‌متری سطح صدا برای انیمیشن گوی زنده
    this.telemetrySamples = 0;
    this.micSqSum = 0;
    this.micSqCnt = 0;
    this.aiSqSum = 0;
    this.aiSqCnt = 0;

    this.port.onmessage = (ev) => {
      const d = ev.data;
      if (!d) return;
      if (d.type === 'pcm24k' && d.buffer) {
        this._pushPcm24k(new Int16Array(d.buffer));
      } else if (d.type === 'clear') {
        this.readPos = 0;
        this.writePos = 0;
        this.avail = 0;
        this.playing = false;
        this.prebuffering = true;
        this.turnComplete = false;
        this.hasHist = false;
        this.echoTailSamples = 0;
        this.fadeStartSample = this.lastOut;
        this.clearFadeRem = this.clearFadeTotal;
      } else if (d.type === 'turn_complete') {
        this.turnComplete = true;
      } else if (d.type === 'mic_mute') {
        this.micMuted = !!d.muted;
      } else if (d.type === 'speaker_mute') {
        this.speakerMuted = !!d.muted;
      }
    };
  }

  _writeSample(v) {
    if (this.avail >= this.cap) {
      this.readPos = (this.readPos + 1) % this.cap;
      this.avail -= 1;
    }
    this.ring[this.writePos] = v;
    this.writePos = (this.writePos + 1) % this.cap;
    this.avail += 1;
  }

  _pushPcm24k(i16) {
    const n = i16.length;
    if (!n || this.speakerMuted) return;
    if (this.avail === 0) {
      this.firstBufTime = currentTime;
    }
    this.turnComplete = false;
    this.echoTailSamples = Math.floor(this.sr * 0.85);

    if (!this.hasHist) {
      const f0 = i16[0] / 32768.0;
      this.sm2 = f0;
      this.sm1 = f0;
      this.s0 = f0;
      this.resamplePhase = 0;
      this.hasHist = true;
    }

    if (this.sr === 48000) {
      // درون‌یابی ۴ نقطه‌ای Half-Band Lagrange FIR (24kHz -> 48kHz)
      let sm2 = this.sm2;
      let sm1 = this.sm1;
      let s0 = this.s0;
      for (let i = 0; i < n; i += 1) {
        const sp1 = i16[i] / 32768.0;
        let mid = (-0.0625 * sm2) + (0.5625 * sm1) + (0.5625 * s0) - (0.0625 * sp1);
        if (mid > 1.0) mid = 1.0;
        else if (mid < -1.0) mid = -1.0;
        this._writeSample(mid);
        this._writeSample(sp1);
        sm2 = sm1;
        sm1 = s0;
        s0 = sp1;
      }
      this.sm2 = sm2;
      this.sm1 = sm1;
      this.s0 = s0;
      return;
    }

    if (this.sr === 24000) {
      for (let i = 0; i < n; i += 1) {
        this._writeSample(i16[i] / 32768.0);
      }
      return;
    }

    // درون‌یابی مکعبی Hermite برای نرخ‌های نمونه غیر ۴۸ کیلوهرتز (مثل 44.1kHz)
    const step = 24000 / this.sr;
    let phase = this.resamplePhase;
    let sm2 = this.sm2;
    let sm1 = this.sm1;
    let s0 = this.s0;
    for (let i = 0; i < n; i += 1) {
      const sp1 = i16[i] / 32768.0;
      while (phase <= 1.0) {
        const t = phase;
        const c0 = s0;
        const c1 = 0.5 * (sp1 - sm1);
        const c2 = sm1 - 2.5 * s0 + 2.0 * sp1 - 0.5 * sm2;
        const c3 = 0.5 * (sp1 - sm2) + 1.5 * (s0 - sm1);
        let y = ((c3 * t + c2) * t + c1) * t + c0;
        if (y > 1.0) y = 1.0;
        else if (y < -1.0) y = -1.0;
        this._writeSample(y);
        phase += step;
      }
      phase -= 1.0;
      sm2 = sm1;
      sm1 = s0;
      s0 = sp1;
    }
    this.resamplePhase = phase;
    this.sm2 = sm2;
    this.sm1 = sm1;
    this.s0 = s0;
  }

  process(inputs, outputs) {
    const outChan = outputs[0] && outputs[0][0];
    const inChan = inputs[0] && inputs[0][0];
    const len = outChan ? outChan.length : 128;

    // م9.7 — سپر سخت‌افزاری ضد اکوی اسپیکر: تا وقتی صدای هوشیار در حال پخش است (+ 850ms دنباله آکوستیک اتاق)،
    // میکروفون سکوت دیجیتال خالص (0) ارسال می‌کند تا صدای اسپیکر گوشی وارد میکروفون نشود و لوپ ۳ بار «سلام» رخ ندهد.
    if (this.playing || this.avail > 0) {
      this.echoTailSamples = Math.floor(this.sr * 0.85);
    } else if (this.echoTailSamples > 0) {
      this.echoTailSamples = Math.max(0, this.echoTailSamples - len);
    }
    const echoGuardActive = this.playing || this.avail > 0 || this.echoTailSamples > 0;

    // ۱) پردازش میکروفون (بدون Noise Gate مخرب تا صامت‌های ابتدای کلمات فارسی مثل «س» در «سلام» کامل حفظ شوند)
    if (inChan && inChan.length && !this.micMuted) {
      if (echoGuardActive) {
        this.hpPrevX = 0;
        this.hpPrevY = 0;
        this.decimSum = 0;
        this.decimCount = 0;
        this.micVoiceFrames = 0;
        for (let i = 0; i < inChan.length; i += 1) {
          this.decimAcc += 1;
          if (this.decimAcc >= this.decimRatio) {
            this.decimAcc -= this.decimRatio;
            this.micOut[this.micIdx] = 0;
            this.micIdx += 1;
            if (this.micIdx >= 640) {
              const copy = new Int16Array(this.micOut);
              this.port.postMessage({ type: 'mic_pcm16', buffer: copy.buffer }, [copy.buffer]);
              this.micIdx = 0;
            }
          }
        }
      } else {
        let prevX = this.hpPrevX;
        let prevY = this.hpPrevY;
        const alpha = this.hpAlpha;
        let frameSq = 0;

        for (let i = 0; i < inChan.length; i += 1) {
          const x = inChan[i];
          const y = alpha * (prevY + x - prevX);
          prevX = x;
          prevY = y;
          frameSq += y * y;
          this.micSqSum += y * y;
          this.micSqCnt += 1;

          this.decimSum += y;
          this.decimCount += 1;
          this.decimAcc += 1;
          if (this.decimAcc >= this.decimRatio) {
            this.decimAcc -= this.decimRatio;
            const avg = this.decimCount > 0 ? (this.decimSum / this.decimCount) : y;
            this.decimSum = 0;
            this.decimCount = 0;
            const s = avg > 1.0 ? 1.0 : (avg < -1.0 ? -1.0 : avg);
            this.micOut[this.micIdx] = s < 0 ? (s * 0x8000) : (s * 0x7fff);
            this.micIdx += 1;
            if (this.micIdx >= 640) {
              const copy = new Int16Array(this.micOut);
              this.port.postMessage({ type: 'mic_pcm16', buffer: copy.buffer }, [copy.buffer]);
              this.micIdx = 0;
            }
          }
        }
        this.hpPrevX = prevX;
        this.hpPrevY = prevY;
        const fRms = Math.sqrt(frameSq / inChan.length);
        if (fRms > 0.045) {
          this.micVoiceFrames = Math.min(25, this.micVoiceFrames + 1);
        } else {
          this.micVoiceFrames = Math.max(0, this.micVoiceFrames - 1);
        }
      }
    } else {
      this.micVoiceFrames = 0;
    }

    this.duckGain = 1.0;

    // ۲) پخش پیوسته‌ی صدای هوشیار از Ring Buffer با Adaptive Jitter Buffer
    if (outChan) {
      if (this.clearFadeRem > 0) {
        for (let i = 0; i < len; i += 1) {
          if (this.clearFadeRem > 0) {
            const prog = 1.0 - (this.clearFadeRem / this.clearFadeTotal);
            const w = 0.5 * (1.0 + Math.cos(Math.PI * prog));
            outChan[i] = this.fadeStartSample * w;
            this.lastOut = outChan[i];
            this.clearFadeRem -= 1;
          } else {
            outChan[i] = 0;
            this.lastOut = 0;
          }
        }
      } else {
        if (!this.playing) {
          const targetSamples = Math.floor(this.sr * this.targetPrebufSec);
          const waited = this.avail > 0 ? (currentTime - this.firstBufTime) : 0;
          if (
            this.avail >= targetSamples
            || (this.turnComplete && this.avail > 0)
            || (this.avail > 0 && waited >= 0.145)
          ) {
            this.playing = true;
            this.prebuffering = false;
            this.fadeStartSample = this.lastOut;
            this.fadeInRem = this.fadeInTotal;
          }
        }

        if (this.playing) {
          for (let i = 0; i < len; i += 1) {
            if (this.avail > 0) {
              let s = this.ring[this.readPos] * this.duckGain;
              this.readPos = (this.readPos + 1) % this.cap;
              this.avail -= 1;
              if (this.fadeInRem > 0) {
                const prog = 1.0 - (this.fadeInRem / this.fadeInTotal);
                const w = 0.5 * (1.0 - Math.cos(Math.PI * prog));
                s = this.fadeStartSample * (1.0 - w) + s * w;
                this.fadeInRem -= 1;
              }
              outChan[i] = this.speakerMuted ? 0 : s;
              this.lastOut = outChan[i];
              this.aiSqSum += outChan[i] * outChan[i];
              this.aiSqCnt += 1;
            } else {
              // اتمام موجودی بافر: شیب کسینوسی نرم به صفر بدون کلیک
              const rem = len - i;
              const startS = this.lastOut;
              for (let k = 0; k < rem; k += 1) {
                const w = 0.5 * (1.0 + Math.cos(Math.PI * ((k + 1) / rem)));
                outChan[i + k] = startS * w;
              }
              this.lastOut = 0;
              this.playing = false;
              this.prebuffering = true;
              if (!this.turnComplete) {
                // شبکه دچار Jitter شده: افزایش خودکار پیش‌بافرینگ
                this.targetPrebufSec = Math.min(0.220, this.targetPrebufSec + 0.025);
              } else {
                this.targetPrebufSec = Math.max(0.105, this.targetPrebufSec - 0.008);
                this.turnComplete = false;
                this.hasHist = false;
              }
              break;
            }
          }
        } else {
          for (let i = 0; i < len; i += 1) {
            if (Math.abs(this.lastOut) > 0.0001) {
              this.lastOut *= 0.85;
              outChan[i] = this.lastOut;
            } else {
              this.lastOut = 0;
              outChan[i] = 0;
            }
          }
        }
      }
    }

    // ۳) ارسال دوره‌ای سطح صدا و وضعیت پخش به ترد اصلی (هر ~60ms)
    this.telemetrySamples += len;
    if (this.telemetrySamples >= Math.floor(this.sr * 0.06)) {
      const micRms = this.micSqCnt > 0 ? Math.min(1, Math.sqrt(this.micSqSum / this.micSqCnt) * 4.2) : 0;
      const aiRms = this.aiSqCnt > 0 ? Math.min(1, Math.sqrt(this.aiSqSum / this.aiSqCnt) * 3.5) : 0;
      this.micSqSum = 0;
      this.micSqCnt = 0;
      this.aiSqSum = 0;
      this.aiSqCnt = 0;
      this.telemetrySamples = 0;
      this.port.postMessage({
        type: 'telemetry',
        micRms: micRms < 0.018 ? 0 : micRms,
        aiRms: aiRms < 0.012 ? 0 : aiRms,
        playing: this.playing,
      });
    }

    return true;
  }
}
registerProcessor('humsyar-live-audio-processor', HumsyarLiveAudioProcessor);
`.replace('this._ pushPcm24k', 'this._pushPcm24k');

let _workletBlobUrl = null;
function getLiveWorkletBlobUrl() {
  if (!_workletBlobUrl) {
    const blob = new Blob([HUMSYAR_LIVE_WORKLET_CODE], { type: 'application/javascript' });
    _workletBlobUrl = URL.createObjectURL(blob);
  }
  return _workletBlobUrl;
}

function downsampleTo16kPcm16Buffer(float32Buf, inputRate) {
  const ratio = (!inputRate || inputRate === 16000) ? 1 : (inputRate / 16000);
  const outLen = Math.round(float32Buf.length / ratio);
  const pcm16 = new Int16Array(outLen);
  for (let i = 0; i < outLen; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(float32Buf.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    let count = 0;
    for (let j = start; j < end; j += 1) {
      sum += float32Buf[j];
      count += 1;
    }
    const v = count > 0 ? sum / count : float32Buf[start] || 0;
    const s = Math.max(-1, Math.min(1, v));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm16.buffer;
}

function pcm16Base64ToArrayBuffer(b64) {
  const binary = atob(b64);
  const len = binary.length - (binary.length % 2);
  if (len <= 0) return new ArrayBuffer(0);
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

function pcm16ArrayBufferToFloat32(ab) {
  if (!ab || ab.byteLength < 2) return new Float32Array(0);
  const samples = new Int16Array(ab, 0, Math.floor(ab.byteLength / 2));
  const float32 = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i += 1) {
    float32[i] = samples[i] / 32768.0;
  }
  return float32;
}

// م9.4 — ترکیب چند چانک Float32 در یک آرایه پیوسته برای Jitter Buffer بدون شکاف (Fallback)
function concatFloat32Arrays(arrays) {
  if (!arrays || arrays.length === 0) return new Float32Array(0);
  if (arrays.length === 1) return arrays[0];
  let total = 0;
  for (let i = 0; i < arrays.length; i += 1) {
    total += arrays[i].length;
  }
  const merged = new Float32Array(total);
  let offset = 0;
  for (let i = 0; i < arrays.length; i += 1) {
    merged.set(arrays[i], offset);
    offset += arrays[i].length;
  }
  return merged;
}

// م9.5 — درون‌یابی مکعبی ۴ نقطه‌ای 24kHz → 48kHz + نرم‌سازی کسینوسی برای مسیر Fallback
function prepareSmoothAudioSamples(samples24k, ctxSampleRate, prevSampleRef, applyStartFadeIn) {
  if (!samples24k || !samples24k.length) {
    return { data: new Float32Array(0), rate: 24000 };
  }
  let prev = prevSampleRef.current || 0;
  if (ctxSampleRate === 48000) {
    const n = samples24k.length;
    const out = new Float32Array(n * 2);
    let sm2 = prev;
    let sm1 = prev;
    let s0 = samples24k[0];
    for (let i = 0; i < n; i += 1) {
      const sp1 = samples24k[i];
      let mid = (-0.0625 * sm2) + (0.5625 * sm1) + (0.5625 * s0) - (0.0625 * sp1);
      if (mid > 1.0) mid = 1.0;
      else if (mid < -1.0) mid = -1.0;
      out[2 * i] = mid;
      out[2 * i + 1] = sp1;
      sm2 = sm1;
      sm1 = s0;
      s0 = sp1;
    }
    if (applyStartFadeIn) {
      const ramp = Math.min(out.length, 144); // 3ms نرم‌سازی کسینوسی شروع صحبت در 48kHz
      for (let i = 0; i < ramp; i += 1) {
        const w = 0.5 * (1 - Math.cos((Math.PI * (i + 1)) / ramp));
        out[i] *= w;
      }
    }
    prevSampleRef.current = s0;
    return { data: out, rate: 48000 };
  }

  const out = new Float32Array(samples24k.length);
  out.set(samples24k);
  if (applyStartFadeIn) {
    const ramp = Math.min(out.length, 72);
    for (let i = 0; i < ramp; i += 1) {
      const w = 0.5 * (1 - Math.cos((Math.PI * (i + 1)) / ramp));
      out[i] *= w;
    }
  } else if (out.length >= 4) {
    out[0] = 0.5 * (prev + out[0]);
  }
  prevSampleRef.current = out[out.length - 1] || 0;
  return { data: out, rate: 24000 };
}

// م9.4 — گرم‌کردن سخت‌افزار صوتی مرورگر/وب‌ویو با یک بافر بی‌صدا پیش از شروع صحبت هوشیار
function warmUpAudioContext(ctx) {
  if (!ctx || ctx.state === 'closed') return;
  try {
    if (ctx.state === 'suspended') {
      ctx.resume().catch(() => {});
    }
    const silent = ctx.createBuffer(1, 128, ctx.sampleRate || 48000);
    const src = ctx.createBufferSource();
    src.buffer = silent;
    src.connect(ctx.destination);
    src.start(0);
  } catch (_) {}
}

function formatClock(sec) {
  const s = Math.max(0, Math.floor(Number(sec) || 0));
  const mm = String(Math.floor(s / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

export default function AiLive() {
  const {
    data: liveCfg,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['ai-live-config'],
    queryFn: () => api.get('/api/ai/live/config').then((r) => r.data),
  });

  const [status, setStatus] = useState('idle'); // idle | connecting | listening | thinking | speaking | error
  const [errMsg, setErrMsg] = useState('');
  const [micMuted, setMicMuted] = useState(false);
  const [speakerMuted, setSpeakerMuted] = useState(false);
  const [cameraOn, setCameraOn] = useState(false);
  const [facingMode, setFacingMode] = useState('environment'); // environment (پشت) | user (سلفی)
  const [voice, setVoice] = useState('');
  const [targetLang, setTargetLang] = useState('fa');
  const [elapsedSec, setElapsedSec] = useState(0);
  const [maxSessionSec, setMaxSessionSec] = useState(300);
  const [activeModel, setActiveModel] = useState('');
  const [userLiveText, setUserLiveText] = useState('');
  const [aiLiveText, setAiLiveText] = useState('');
  const [historyTurns, setHistoryTurns] = useState([]);
  const [toolNotice, setToolNotice] = useState('');
  const [textInput, setTextInput] = useState('');
  const [micLevel, setMicLevel] = useState(0);
  const [aiLevel, setAiLevel] = useState(0);

  const wsRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const videoStreamRef = useRef(null);
  const videoElRef = useRef(null);
  const videoTimerRef = useRef(null);
  const captureCtxRef = useRef(null);
  const processorRef = useRef(null);
  const workletNodeRef = useRef(null);
  const workletLoadedCtxRef = useRef(null);
  const playCtxRef = useRef(null);
  const playGainRef = useRef(null);
  const nextPlayTimeRef = useRef(0);
  const activeSourcesRef = useRef([]);
  const pendingPcmQueueRef = useRef([]);
  const pendingSamplesCountRef = useRef(0);
  const isPrebufferingRef = useRef(true);
  const flushTimerRef = useRef(null);
  const prevSampleRef = useRef(0);
  const lastLevelTsRef = useRef(0);
  const lastLevelValRef = useRef(0);
  const micMutedRef = useRef(false);
  const speakerMutedRef = useRef(false);
  const aiTurnActiveRef = useRef(false);
  const workletPlayingRef = useRef(false);
  const echoCooldownUntilRef = useRef(0);
  const userBufRef = useRef('');
  const aiBufRef = useRef('');

  useEffect(() => {
    if (liveCfg) {
      if (!voice && liveCfg.voice) setVoice(liveCfg.voice);
      if (liveCfg.target_language) setTargetLang(liveCfg.target_language);
      if (liveCfg.model) setActiveModel(liveCfg.model);
      if (liveCfg.max_session_sec) setMaxSessionSec(liveCfg.max_session_sec);
    }
  }, [liveCfg, voice]);

  useEffect(() => {
    micMutedRef.current = micMuted;
    if (workletNodeRef.current) {
      try {
        workletNodeRef.current.port.postMessage({ type: 'mic_mute', muted: micMuted });
      } catch (_) {}
    }
    if (micMuted) {
      setMicLevel(0);
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        try {
          wsRef.current.send(JSON.stringify({ type: 'audio_stream_end' }));
        } catch (_) {}
      }
    }
  }, [micMuted]);

  useEffect(() => {
    speakerMutedRef.current = speakerMuted;
    if (workletNodeRef.current) {
      try {
        workletNodeRef.current.port.postMessage({ type: 'speaker_mute', muted: speakerMuted });
      } catch (_) {}
    }
  }, [speakerMuted]);

  const stopAllPlayback = useCallback(() => {
    aiTurnActiveRef.current = false;
    workletPlayingRef.current = false;
    echoCooldownUntilRef.current = 0;
    if (workletNodeRef.current) {
      try {
        workletNodeRef.current.port.postMessage({ type: 'clear' });
      } catch (_) {}
    }
    setAiLevel(0);
    if (flushTimerRef.current) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    pendingPcmQueueRef.current = [];
    pendingSamplesCountRef.current = 0;
    isPrebufferingRef.current = true;
    prevSampleRef.current = 0;

    // م9.4 — کاهش نرم بهره صدا (12ms) پیش از توقف منابع برای حذف کامل صدای تق در Barge-in
    const ctx = playCtxRef.current;
    const gainNode = playGainRef.current;
    if (ctx && gainNode && ctx.state === 'running') {
      try {
        const now = ctx.currentTime;
        gainNode.gain.cancelScheduledValues(now);
        gainNode.gain.setValueAtTime(gainNode.gain.value, now);
        gainNode.gain.linearRampToValueAtTime(0.0001, now + 0.012);
        gainNode.gain.setValueAtTime(1.0, now + 0.016);
      } catch (_) {}
    }

    for (const src of activeSourcesRef.current) {
      try {
        src.stop();
      } catch (_) {}
    }
    activeSourcesRef.current = [];
    nextPlayTimeRef.current = 0;
  }, []);

  const stopCameraStream = useCallback(() => {
    if (videoTimerRef.current) {
      window.clearInterval(videoTimerRef.current);
      videoTimerRef.current = null;
    }
    if (videoStreamRef.current) {
      for (const track of videoStreamRef.current.getTracks()) {
        try {
          track.stop();
        } catch (_) {}
      }
      videoStreamRef.current = null;
    }
    if (videoElRef.current) {
      videoElRef.current.srcObject = null;
    }
    setCameraOn(false);
  }, []);

  const startCameraStream = useCallback(async (mode = facingMode) => {
    stopCameraStream();
    try {
      const vStream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: mode,
          width: { ideal: 640 },
          height: { ideal: 480 },
        },
        audio: false,
      });
      videoStreamRef.current = vStream;
      setCameraOn(true);
      setFacingMode(mode);
      if (videoElRef.current) {
        videoElRef.current.srcObject = vStream;
        videoElRef.current.play().catch(() => {});
      }
      const canvas = document.createElement('canvas');
      const ctx2d = canvas.getContext('2d');
      videoTimerRef.current = window.setInterval(() => {
        const vid = videoElRef.current;
        if (!vid || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        if (!vid.videoWidth || !vid.videoHeight) return;
        const scale = Math.min(1, 640 / Math.max(vid.videoWidth, vid.videoHeight));
        canvas.width = Math.round(vid.videoWidth * scale);
        canvas.height = Math.round(vid.videoHeight * scale);
        ctx2d.drawImage(vid, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.65);
        const b64 = dataUrl.split(',')[1] || '';
        if (b64) {
          wsRef.current.send(JSON.stringify({
            type: 'video',
            data: b64,
            mimeType: 'image/jpeg',
          }));
        }
      }, 1000);
    } catch (_) {
      setErrMsg('دسترسی به دوربین داده نشد؛ لطفاً مجوز دوربین را در تلگرام/مرورگر فعال کن.');
    }
  }, [facingMode, stopCameraStream]);

  useEffect(() => {
    if (cameraOn && videoElRef.current && videoStreamRef.current) {
      videoElRef.current.srcObject = videoStreamRef.current;
      videoElRef.current.play().catch(() => {});
    }
  }, [cameraOn]);

  const ensurePlaybackContext = useCallback(() => {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!playCtxRef.current || playCtxRef.current.state === 'closed') {
      try {
        playCtxRef.current = new AC({ latencyHint: 'interactive' });
      } catch (_) {
        playCtxRef.current = new AC();
      }
      playGainRef.current = null;
    }
    const ctx = playCtxRef.current;
    if (ctx.state === 'suspended') {
      ctx.resume().catch(() => {});
    }
    if (!playGainRef.current) {
      const gain = ctx.createGain();
      gain.gain.value = 1.0;
      gain.connect(ctx.destination);
      playGainRef.current = gain;
    }
    return ctx;
  }, []);

  const flushPendingAudio = useCallback((forceFlush = false) => {
    if (flushTimerRef.current && forceFlush) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    if (!pendingPcmQueueRef.current.length) return;

    // م9.4 — Jitter Buffer: صبر برای انباشت حداقل ~140ms (3360 نمونه در 24kHz) در شروع صحبت
    const prebufferSamples = 3360;
    if (isPrebufferingRef.current && !forceFlush && pendingSamplesCountRef.current < prebufferSamples) {
      return;
    }

    if (flushTimerRef.current) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }

    const merged24k = concatFloat32Arrays(pendingPcmQueueRef.current);
    pendingPcmQueueRef.current = [];
    pendingSamplesCountRef.current = 0;
    if (!merged24k.length) return;

    try {
      const ctx = ensurePlaybackContext();
      const now = ctx.currentTime;
      const wasUnderrun = !nextPlayTimeRef.current || nextPlayTimeRef.current <= now + 0.004;
      const applyFadeIn = isPrebufferingRef.current || wasUnderrun;
      isPrebufferingRef.current = false;

      const { data: smoothSamples, rate: bufRate } = prepareSmoothAudioSamples(
        merged24k,
        ctx.sampleRate,
        prevSampleRef,
        applyFadeIn,
      );
      if (!smoothSamples.length) return;

      const audioBuf = ctx.createBuffer(1, smoothSamples.length, bufRate);
      audioBuf.getChannelData(0).set(smoothSamples);

      const src = ctx.createBufferSource();
      src.buffer = audioBuf;
      src.connect(playGainRef.current || ctx.destination);

      // در شروع نوبت صحبت 45ms حاشیه امن (Lookahead) می‌گذاریم تا هرگز Underrun رخ ندهد
      const startAt = wasUnderrun
        ? now + 0.045
        : Math.max(now + 0.008, nextPlayTimeRef.current);
      nextPlayTimeRef.current = startAt + audioBuf.duration;
      const remMs = Math.max(0, (nextPlayTimeRef.current - now) * 1000);
      echoCooldownUntilRef.current = Math.max(echoCooldownUntilRef.current, performance.now() + remMs + 850);

      activeSourcesRef.current.push(src);
      setStatus((prev) => (prev === 'speaking' ? prev : 'speaking'));
      src.onended = () => {
        activeSourcesRef.current = activeSourcesRef.current.filter((x) => x !== src);
        if (activeSourcesRef.current.length === 0 && pendingSamplesCountRef.current === 0) {
          isPrebufferingRef.current = true;
          prevSampleRef.current = 0;
          setStatus((prev) => (prev === 'speaking' ? 'listening' : prev));
        }
      };
      src.start(startAt);
    } catch (e) {
      console.warn('[AiLive playback]', e);
    }
  }, [ensurePlaybackContext]);

  const scheduleAudioChunk = useCallback((rawOrB64) => {
    if (speakerMutedRef.current || !rawOrB64) return;
    try {
      const ab = (rawOrB64 instanceof ArrayBuffer)
        ? rawOrB64
        : pcm16Base64ToArrayBuffer(rawOrB64);
      if (!ab || ab.byteLength < 2) return;

      // م9.7 — ثبت وضعیت پخش فعال و قفل ضد اکوی اسپیکر تا پایان پخش + 850ms
      const chunkMs = (ab.byteLength / 48000.0) * 1000;
      const nowPerf = performance.now();
      aiTurnActiveRef.current = true;
      echoCooldownUntilRef.current = Math.max(echoCooldownUntilRef.current, nowPerf) + chunkMs + 850;

      // م9.5 — مسیر اصلی: انتقال Zero-Copy مستقیم ArrayBuffer به AudioWorkletProcessor روی ترد بلادرنگ صدا
      if (workletNodeRef.current) {
        workletNodeRef.current.port.postMessage({ type: 'pcm24k', buffer: ab }, [ab]);
        setStatus((prev) => (prev === 'speaking' ? prev : 'speaking'));
        return;
      }

      // مسیر Fallback برای مرورگرهای قدیمی بدون AudioWorklet
      const float32 = pcm16ArrayBufferToFloat32(ab);
      if (!float32.length) return;

      const ctx = ensurePlaybackContext();
      const now = ctx.currentTime;
      if (!nextPlayTimeRef.current || nextPlayTimeRef.current <= now + 0.004) {
        isPrebufferingRef.current = true;
      }

      pendingPcmQueueRef.current.push(float32);
      pendingSamplesCountRef.current += float32.length;

      if (isPrebufferingRef.current) {
        if (pendingSamplesCountRef.current >= 3360) {
          flushPendingAudio(true);
        } else if (!flushTimerRef.current) {
          flushTimerRef.current = window.setTimeout(() => {
            flushTimerRef.current = null;
            flushPendingAudio(true);
          }, 110);
        }
      } else {
        flushPendingAudio(true);
      }
    } catch (e) {
      console.warn('[AiLive schedule]', e);
    }
  }, [ensurePlaybackContext, flushPendingAudio]);

  const cleanupSession = useCallback(() => {
    stopAllPlayback();
    stopCameraStream();
    if (workletNodeRef.current) {
      try {
        workletNodeRef.current.port.onmessage = null;
        workletNodeRef.current.disconnect();
      } catch (_) {}
      workletNodeRef.current = null;
    }
    if (processorRef.current) {
      try {
        processorRef.current.disconnect();
      } catch (_) {}
      processorRef.current = null;
    }
    if (captureCtxRef.current && captureCtxRef.current !== playCtxRef.current) {
      try {
        captureCtxRef.current.close();
      } catch (_) {}
    }
    captureCtxRef.current = null;
    if (mediaStreamRef.current) {
      for (const track of mediaStreamRef.current.getTracks()) {
        try {
          track.stop();
        } catch (_) {}
      }
      mediaStreamRef.current = null;
    }
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch (_) {}
      wsRef.current = null;
    }
    setMicLevel(0);
    setAiLevel(0);
  }, [stopAllPlayback, stopCameraStream]);

  useEffect(() => () => cleanupSession(), [cleanupSession]);

  useEffect(() => {
    if (status === 'idle' || status === 'connecting' || status === 'error') {
      return undefined;
    }
    const id = window.setInterval(() => {
      setElapsedSec((s) => s + 1);
    }, 1000);
    return () => window.clearInterval(id);
  }, [status]);

  const startCall = async (withVideo = false) => {
    setErrMsg('');
    setToolNotice('');
    setUserLiveText('');
    setAiLiveText('');
    userBufRef.current = '';
    aiBufRef.current = '';
    setElapsedSec(0);
    haptic('medium');

    // باز کردن و گرم‌کردن AudioContext دقیقاً در لحظه‌ی کلیک کاربر
    try {
      const ctx = ensurePlaybackContext();
      warmUpAudioContext(ctx);
    } catch (_) {}

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch (e) {
      setStatus('error');
      setErrMsg('دسترسی به میکروفون داده نشد؛ لطفاً مجوز میکروفون را در تلگرام/مرورگر فعال کن.');
      return;
    }

    // گرم‌کردن مجدد مسیر صوتی پس از تغییر مسیر سخت‌افزار به حالت مکالمه (Voice Call Route)
    try {
      const ctx = ensurePlaybackContext();
      warmUpAudioContext(ctx);
    } catch (_) {}

    mediaStreamRef.current = stream;
    setStatus('connecting');

    if (withVideo) {
      startCameraStream(facingMode);
    }

    const origin = API_ORIGIN || window.location.origin;
    const wsProto = origin.startsWith('https') ? 'wss' : 'ws';
    const hostPart = origin.replace(/^https?:\/\//i, '');
    const qs = new URLSearchParams({
      init_data: getInitData() || '',
      voice: voice || liveCfg?.voice || 'Sulafat',
      target_language: targetLang || 'fa',
      binary: '1',
    });
    const wsUrl = `${wsProto}://${hostPart}/api/ai/live/ws?${qs.toString()}`;

    const ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onmessage = async (ev) => {
      // م9.5 — دریافت فریم صوتی باینری مستقیم (Zero-Copy ArrayBuffer) از سرور
      if (ev.data instanceof ArrayBuffer) {
        scheduleAudioChunk(ev.data);
        return;
      }

      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch (_) {
        return;
      }
      if (!msg || typeof msg !== 'object') return;

      if (msg.type === 'ready') {
        hapticNotif('success');
        setActiveModel(msg.model || liveCfg?.model || 'gemini-3.8-live');
        if (msg.max_session_sec) setMaxSessionSec(msg.max_session_sec);
        setStatus('listening');

        // م9.5 — راه‌اندازی موتور صوتی AudioWorkletProcessor روی ترد بلادرنگ صدا (با Fallback خودکار)
        try {
          const capCtx = ensurePlaybackContext();
          captureCtxRef.current = capCtx;
          const srcNode = capCtx.createMediaStreamSource(stream);

          if (capCtx.audioWorklet && typeof window.AudioWorkletNode !== 'undefined') {
            try {
              if (workletLoadedCtxRef.current !== capCtx) {
                await capCtx.audioWorklet.addModule(getLiveWorkletBlobUrl());
                workletLoadedCtxRef.current = capCtx;
              }
              const wNode = new window.AudioWorkletNode(capCtx, 'humsyar-live-audio-processor', {
                numberOfInputs: 1,
                numberOfOutputs: 1,
                outputChannelCount: [1],
              });
              wNode.port.postMessage({ type: 'mic_mute', muted: micMutedRef.current });
              wNode.port.postMessage({ type: 'speaker_mute', muted: speakerMutedRef.current });
              wNode.port.onmessage = (wEv) => {
                const d = wEv.data;
                if (!d) return;
                if (d.type === 'mic_pcm16' && d.buffer) {
                  if (!micMutedRef.current && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                    if (
                      aiTurnActiveRef.current
                      || workletPlayingRef.current
                      || performance.now() < echoCooldownUntilRef.current
                    ) {
                      wsRef.current.send(new ArrayBuffer(d.buffer.byteLength));
                    } else {
                      wsRef.current.send(d.buffer);
                    }
                  }
                } else if (d.type === 'telemetry') {
                  setMicLevel(d.micRms || 0);
                  setAiLevel(d.aiRms || 0);
                  workletPlayingRef.current = !!d.playing;
                  if (d.playing) {
                    echoCooldownUntilRef.current = Math.max(echoCooldownUntilRef.current, performance.now() + 850);
                    setStatus((prev) => (prev === 'speaking' ? prev : 'speaking'));
                  } else {
                    setStatus((prev) => (prev === 'speaking' ? 'listening' : prev));
                  }
                }
              };
              srcNode.connect(wNode);
              wNode.connect(playGainRef.current || capCtx.destination);
              workletNodeRef.current = wNode;
              return;
            } catch (workletErr) {
              console.warn('[AiLive worklet fallback]', workletErr);
            }
          }

          // مسیر Fallback برای مرورگرهای قدیمی: ScriptProcessorNode با ارسال فریم باینری مستقیم و سپر ضد اکوی اسپیکر
          const proc = capCtx.createScriptProcessor(2048, 1, 1);
          const silentGain = capCtx.createGain();
          silentGain.gain.value = 0;
          processorRef.current = proc;

          proc.onaudioprocess = (audioEv) => {
            if (micMutedRef.current || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
              if (lastLevelValRef.current !== 0) {
                lastLevelValRef.current = 0;
                setMicLevel(0);
              }
              return;
            }
            const raw = audioEv.inputBuffer.getChannelData(0);
            const nowMs = performance.now();
            const echoBusy = (
              aiTurnActiveRef.current
              || activeSourcesRef.current.length > 0
              || pendingSamplesCountRef.current > 0
              || nowMs < echoCooldownUntilRef.current
            );
            if (echoBusy) {
              if (lastLevelValRef.current !== 0) {
                lastLevelValRef.current = 0;
                setMicLevel(0);
              }
              const outLen = Math.round(raw.length / ((capCtx.sampleRate || 48000) / 16000));
              wsRef.current.send(new ArrayBuffer(outLen * 2));
              return;
            }
            if (nowMs - lastLevelTsRef.current >= 80) {
              let sumSq = 0;
              for (let i = 0; i < raw.length; i += 8) {
                sumSq += raw[i] * raw[i];
              }
              const rms = Math.min(1, Math.sqrt(sumSq / (raw.length / 8)) * 4);
              lastLevelTsRef.current = nowMs;
              if (Math.abs(rms - lastLevelValRef.current) > 0.025 || (rms < 0.02 && lastLevelValRef.current > 0)) {
                const nextLvl = rms < 0.02 ? 0 : rms;
                lastLevelValRef.current = nextLvl;
                setMicLevel(nextLvl);
              }
            }

            const pcmBuf = downsampleTo16kPcm16Buffer(raw, capCtx.sampleRate);
            wsRef.current.send(pcmBuf);
          };

          srcNode.connect(proc);
          proc.connect(silentGain);
          silentGain.connect(capCtx.destination);
        } catch (capErr) {
          console.error('[AiLive capture]', capErr);
        }
        return;
      }

      if (msg.type === 'audio' && msg.data) {
        scheduleAudioChunk(msg.data);
        return;
      }

      if (msg.type === 'interrupted') {
        stopAllPlayback();
        setStatus('listening');
        return;
      }

      if (msg.type === 'input_transcript' && msg.text) {
        userBufRef.current = `${userBufRef.current} ${msg.text}`.trim();
        setUserLiveText(userBufRef.current);
        return;
      }

      if (msg.type === 'user_transcript_override' && msg.text) {
        setHistoryTurns((prev) => {
          if (!prev.length) {
            return [{ role: 'user', text: msg.text }];
          }
          const copy = [...prev];
          for (let i = copy.length - 1; i >= 0; i -= 1) {
            if (copy[i].role === 'user') {
              copy[i] = { ...copy[i], text: msg.text };
              return copy;
            }
          }
          const lastIdx = copy.length - 1;
          copy.splice(lastIdx, 0, { role: 'user', text: msg.text });
          return copy.slice(-14);
        });
        return;
      }

      if (msg.type === 'output_transcript' && msg.text) {
        aiTurnActiveRef.current = true;
        aiBufRef.current = `${aiBufRef.current} ${msg.text}`.trim();
        setAiLiveText(aiBufRef.current);
        return;
      }

      if (msg.type === 'text' && msg.text) {
        aiTurnActiveRef.current = true;
        aiBufRef.current = `${aiBufRef.current} ${msg.text}`.trim();
        setAiLiveText(aiBufRef.current);
        return;
      }

      if (msg.type === 'tool_call') {
        const names = (msg.calls || []).map((c) => c.name).join('،');
        setToolNotice(` در حال بررسی اطلاعات هامزیار (${names})…`);
        setStatus('thinking');
        return;
      }

      if (msg.type === 'turn_state') {
        if (msg.interaction_status === 'IN_PROGRESS') {
          setStatus('thinking');
        } else if (msg.interaction_status === 'IDLE' || msg.turn_complete) {
          aiTurnActiveRef.current = false;
          echoCooldownUntilRef.current = Math.max(echoCooldownUntilRef.current, performance.now() + 850);
          if (workletNodeRef.current) {
            try {
              workletNodeRef.current.port.postMessage({ type: 'turn_complete' });
            } catch (_) {}
          } else {
            flushPendingAudio(true);
          }
          setToolNotice('');
          if (userBufRef.current || aiBufRef.current) {
            const uSnap = userBufRef.current;
            const aSnap = aiBufRef.current;
            setHistoryTurns((prev) => [
              ...prev.slice(-14),
              ...(uSnap ? [{ role: 'user', text: uSnap }] : []),
              ...(aSnap ? [{ role: 'assistant', text: aSnap }] : []),
            ]);
            userBufRef.current = '';
            aiBufRef.current = '';
            setUserLiveText('');
            setAiLiveText('');
          }
          if (!workletNodeRef.current && activeSourcesRef.current.length === 0 && pendingSamplesCountRef.current === 0) {
            setStatus('listening');
          }
        }
        return;
      }

      if (msg.type === 'session_limit') {
        setErrMsg(msg.message || 'مدت زمان مجاز این تماس به پایان رسید.');
        cleanupSession();
        setStatus('idle');
        refetch();
        return;
      }

      if (msg.type === 'error') {
        setErrMsg(msg.message || 'خطا در ارتباط صوتی زنده');
        cleanupSession();
        setStatus('error');
      }
    };

    ws.onerror = () => {
      setErrMsg('خطا در اتصال WebSocket به سرویس تماس زنده.');
      cleanupSession();
      setStatus('error');
    };

    ws.onclose = () => {
      cleanupSession();
      setStatus((prev) => (prev === 'error' ? 'error' : 'idle'));
      refetch();
    };
  };

  const interruptAiSpeech = useCallback(() => {
    haptic('light');
    stopAllPlayback();
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: 'barge_in' }));
      } catch (_) {}
    }
    setStatus('listening');
  }, [stopAllPlayback]);

  const endCall = () => {
    haptic('light');
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: 'stop' }));
      } catch (_) {}
    }
    cleanupSession();
    setStatus('idle');
    refetch();
  };

  const sendTextTurn = () => {
    const txt = textInput.trim();
    if (!txt || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: 'text', text: txt }));
    setHistoryTurns((prev) => [...prev.slice(-14), { role: 'user', text: txt }]);
    setTextInput('');
  };

  if (isLoading) {
    return (
      <main className="page">
        <Header title="تماس صوتی و ویدیویی زنده" back="/ai" />
        <div style={{ padding: 32, textAlign: 'center' }}>
          <Spinner />
        </div>
      </main>
    );
  }

  const isCallActive = status === 'connecting' || status === 'listening' || status === 'thinking' || status === 'speaking';

  const isTranslateModel = (activeModel || liveCfg?.model || '').includes('translate');

  const statusMeta = {
    idle: { label: 'آماده‌ی برقراری تماس صوتی/ویدیویی زنده', color: '#64748B', icon: '🎙' },
    connecting: { label: 'در حال اتصال به Gemini Live…', color: '#F59E0B', icon: '⏳' },
    listening: { label: micMuted ? 'میکروفون بی‌صداست' : 'در حال گوش دادن به شما… صحبت کنید', color: '#10B981', icon: '🟢' },
    thinking: { label: 'هوشیار در حال استدلال و بررسی…', color: '#8B5CF6', icon: '🧠' },
    speaking: { label: 'هوشیار در حال صحبت… (برای نوبت صحبت روی گوی یا دکمه توقف بزنید)', color: '#3B82F6', icon: '🔊' },
    error: { label: 'خطا در تماس زنده', color: '#EF4444', icon: '⚠️' },
  }[status] || { label: '', color: '#64748B', icon: '🎙' };

  const orbScale = status === 'speaking'
    ? 1.06 + Math.min(0.26, aiLevel * 0.42)
    : status === 'listening'
    ? 1 + Math.min(0.25, micLevel * 0.35)
    : 1;

  return (
    <main className="page" style={{ paddingBottom: 32 }}>
      <Header title="تماس صوتی و ویدیویی زنده" back="/ai" />

      <div style={{ padding: '12px 16px', display: 'grid', gap: 14 }}>
        {/* کارت وضعیت، پیش‌نمایش دوربین و گوی صوتی */}
        <section
          className="card"
          style={{
            padding: '22px 16px',
            textAlign: 'center',
            background: 'linear-gradient(180deg, rgba(15,23,42,0.95) 0%, rgba(10,16,32,0.98) 100%)',
            border: `1px solid ${statusMeta.color}44`,
            borderRadius: 20,
          }}
        >
          <div style={{ fontSize: 12, color: 'var(--txm)', marginBottom: 12 }}>
            مدل فعال: <code style={{ direction: 'ltr', color: '#93C5FD' }}>{activeModel || liveCfg?.model || 'gemini-3.8-live'}</code>
            {isCallActive && (
              <span style={{ marginInlineStart: 10, color: '#FBBF24' }}>
                ⏱ {formatClock(elapsedSec)} / {formatClock(maxSessionSec)}
              </span>
            )}
          </div>

          {/* پیش‌نمایش ویدیوی زنده دوربین (هنگام روشن بودن دوربین) */}
          {cameraOn && (
            <div style={{ position: 'relative', maxWidth: 320, margin: '0 auto 14px', borderRadius: 16, overflow: 'hidden', border: '2px solid #3B82F6' }}>
              <video
                ref={videoElRef}
                autoPlay
                playsInline
                muted
                style={{ width: '100%', display: 'block', background: '#000', maxHeight: 220, objectFit: 'cover' }}
              />
              <button
                type="button"
                className="btn sm"
                onClick={() => startCameraStream(facingMode === 'environment' ? 'user' : 'environment')}
                style={{ position: 'absolute', bottom: 8, left: 8, background: 'rgba(15,23,42,0.8)', borderRadius: 999 }}
              >
                <Glyph value="🔄" />تعویض دوربین
              </button>
            </div>
          )}

          {/* گوی انیمیشنی تماس زنده */}
          <div
            onClick={status === 'speaking' ? interruptAiSpeech : undefined}
            style={{
              width: cameraOn ? 84 : 128,
              height: cameraOn ? 84 : 128,
              margin: '10px auto 14px',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: cameraOn ? 32 : 46,
              cursor: status === 'speaking' ? 'pointer' : 'default',
              transform: `scale(${orbScale.toFixed(3)})`,
              transition: 'transform 120ms ease-out, box-shadow 250ms ease',
              background: `radial-gradient(circle at 35% 35%, ${statusMeta.color}55, ${statusMeta.color}18 70%)`,
              border: `2px solid ${statusMeta.color}`,
              boxShadow: isCallActive ? `0 0 36px ${statusMeta.color}55` : 'none',
            }}
          >
            <Glyph value={statusMeta.icon} />
          </div>

          <div style={{ fontWeight: 700, fontSize: 15, color: '#F8FAFC' }}>
            {statusMeta.label}
          </div>

          {status === 'speaking' && (
            <div style={{ marginTop: 10 }}>
              <button
                type="button"
                className="btn sm"
                onClick={interruptAiSpeech}
                style={{
                  borderRadius: 999,
                  background: 'rgba(59,130,246,0.22)',
                  border: '1px solid rgba(59,130,246,0.55)',
                  color: '#93C5FD',
                  padding: '6px 14px',
                  fontSize: 12,
                }}
              >
                <Glyph value="✋" />قطع صحبت هوشیار و شروع صحبت من
              </button>
            </div>
          )}

          {toolNotice && (
            <div style={{ marginTop: 8, fontSize: 12, color: '#C4B5FD' }}>
              {toolNotice}
            </div>
          )}

          {errMsg && (
            <div
              style={{
                marginTop: 12,
                padding: '10px 12px',
                borderRadius: 12,
                background: 'rgba(239,68,68,0.14)',
                border: '1px solid rgba(239,68,68,0.4)',
                color: '#FCA5A5',
                fontSize: 13,
              }}
            >
              {errMsg}
            </div>
          )}

          {/* تنظیمات صدای هوشیار و زبان مقصد پیش از شروع تماس */}
          {!isCallActive && (
            <div style={{ display: 'grid', gap: 10, marginTop: 16, textAlign: 'right' }}>
              <label style={{ fontSize: 12, color: 'var(--txm)' }}>
                <Glyph value="🗣" />صدای هوشیار در مکالمه زنده:
                <select
                  className="inp"
                  style={{ marginTop: 4 }}
                  value={voice}
                  onChange={(e) => setVoice(e.target.value)}
                >
                  {(liveCfg?.voices || [{ id: 'Sulafat', label: 'Sulafat — گرم' }]).map((v) => (
                    <option key={v.id} value={v.id}>{v.label}</option>
                  ))}
                </select>
              </label>

              {isTranslateModel && (
                <label style={{ fontSize: 12, color: 'var(--txm)' }}>
                  <Glyph value="🌐" />زبان مقصد ترجمه‌ی صوت‌به‌صوت:
                  <select
                    className="inp"
                    style={{ marginTop: 4 }}
                    value={targetLang}
                    onChange={(e) => setTargetLang(e.target.value)}
                  >
                    {(liveCfg?.translate_languages || [{ code: 'fa', label: 'فارسی' }]).map((l) => (
                      <option key={l.code} value={l.code}>{l.label}</option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          )}

          {/* دکمه‌های اصلی شروع / پایان و کنترل میکروفون و دوربین */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: 10, marginTop: 18, flexWrap: 'wrap' }}>
            {!isCallActive ? (
              <>
                <button
                  type="button"
                  className="btn primary"
                  disabled={liveCfg && !liveCfg.enabled}
                  onClick={() => startCall(false)}
                  style={{ minWidth: 185, padding: '12px 18px', fontSize: 14, borderRadius: 999 }}
                >
                  <Glyph value="🎙" />تماس صوتی زنده
                </button>
                {!isTranslateModel && (
                  <button
                    type="button"
                    className="btn"
                    disabled={liveCfg && !liveCfg.enabled}
                    onClick={() => startCall(true)}
                    style={{
                      minWidth: 185,
                      padding: '12px 18px',
                      fontSize: 14,
                      borderRadius: 999,
                      background: 'rgba(59,130,246,0.22)',
                      border: '1px solid rgba(59,130,246,0.5)',
                    }}
                  >
                    <Glyph value="📹" />تماس ویدیویی + صوتی
                  </button>
                )}
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setMicMuted((m) => !m)}
                  style={{
                    borderRadius: 999,
                    background: micMuted ? 'rgba(239,68,68,0.2)' : 'rgba(255,255,255,0.08)',
                  }}
                >
                  {micMuted ? 'میکروفون بسته' : 'میکروفون باز'}
                </button>

                {!isTranslateModel && (
                  <button
                    type="button"
                    className="btn"
                    onClick={() => (cameraOn ? stopCameraStream() : startCameraStream(facingMode))}
                    style={{
                      borderRadius: 999,
                      background: cameraOn ? 'rgba(59,130,246,0.28)' : 'rgba(255,255,255,0.08)',
                    }}
                  >
                    {cameraOn ? 'بستن دوربین' : 'روشن کردن دوربین'}
                  </button>
                )}

                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    const next = !speakerMuted;
                    setSpeakerMuted(next);
                    if (next) stopAllPlayback();
                  }}
                  style={{
                    borderRadius: 999,
                    background: speakerMuted ? 'rgba(239,68,68,0.2)' : 'rgba(255,255,255,0.08)',
                  }}
                >
                  {speakerMuted ? 'بلندگو بسته' : 'بلندگو باز'}
                </button>

                <button
                  type="button"
                  className="btn danger"
                  onClick={endCall}
                  style={{ borderRadius: 999, padding: '10px 20px' }}
                >
                  <Glyph value="📴" />پایان تماس
                </button>
              </>
            )}
          </div>
        </section>

        {/* زیرنویس زنده و متن مکالمه */}
        {(userLiveText || aiLiveText || historyTurns.length > 0) && (
          <section className="card" style={{ padding: 14, display: 'grid', gap: 8 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--txm)' }}>
              <Glyph value="📝" />زیرنویس زنده مکالمه
            </div>
            <div style={{ maxHeight: 240, overflowY: 'auto', display: 'grid', gap: 8 }}>
              {historyTurns.map((t, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: '8px 11px',
                    borderRadius: 12,
                    fontSize: 13,
                    background: t.role === 'user' ? 'rgba(59,130,246,0.14)' : 'rgba(16,185,129,0.12)',
                  }}
                >
                  <b>{t.role === 'user' ? 'شما: ' : 'هوشیار: '}</b>
                  <span>{t.text}</span>
                </div>
              ))}
              {userLiveText && (
                <div style={{ padding: '8px 11px', borderRadius: 12, fontSize: 13, background: 'rgba(59,130,246,0.22)' }}>
                  <b><Glyph value="👤" />شما (در حال صحبت…): </b>
                  <span>{userLiveText}</span>
                </div>
              )}
              {aiLiveText && (
                <div style={{ padding: '8px 11px', borderRadius: 12, fontSize: 13, background: 'rgba(16,185,129,0.22)' }}>
                  <b><Glyph value="🤖" />هوشیار (زنده…): </b>
                  <span>{aiLiveText}</span>
                </div>
              )}
            </div>
          </section>
        )}

        {/* ارسال پیام متنی مکمل در حین تماس زنده (برای مدل‌های غیرمترجم) */}
        {isCallActive && !isTranslateModel && (
          <section className="card" style={{ padding: 12, display: 'flex', gap: 8 }}>
            <input
              className="inp"
              style={{ flex: 1 }}
              placeholder="ارسال نکته‌ی متنی حین تماس صوتی…"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendTextTurn()}
            />
            <button
              type="button"
              className="btn primary"
              disabled={!textInput.trim()}
              onClick={sendTextTurn}
            >
              ارسال
            </button>
          </section>
        )}
      </div>
    </main>
  );
}
