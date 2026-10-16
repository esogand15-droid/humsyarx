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


/* ─────────────────────────────────────────────────────────────
   🎙📹 م9 — تماس صوتی و ویدیویی زنده با هوشیار (Google Gemini Live API)
   - اتصال دوطرفه‌ی WebSocket به /api/ai/live/ws
   - ارسال میکروفون با فرمت استاندارد گوگل:
     16-bit PCM, 16kHz, mono, little-endian (با Downsample از نرخ بومی سخت‌افزار)
   - ارسال فریم‌های ویدیویی زنده (دوربین جلو/پشت):
     JPEG 1fps از طریق realtimeInput.video
   - دریافت و پخش بدون وقفه‌ی صدای هوشیار:
     16-bit PCM, 24kHz, mono, little-endian
   - پشتیبانی کامل از پریدن وسط حرف (Barge-in / interrupted)،
     زیرنویس زنده‌ی ورودی/خروجی، و وضعیت تفکر (interactionStatus)
───────────────────────────────────────────────────────────── */


function downsampleTo16k(float32Buf, inputRate) {
  if (!inputRate || inputRate === 16000) {
    return float32Buf;
  }
  const ratio = inputRate / 16000;
  const outLen = Math.round(float32Buf.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(float32Buf.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    let count = 0;
    for (let j = start; j < end; j += 1) {
      sum += float32Buf[j];
      count += 1;
    }
    out[i] = count > 0 ? sum / count : float32Buf[start] || 0;
  }
  return out;
}


function float32ToPcm16Base64(float32Buf) {
  const pcm16 = new Int16Array(float32Buf.length);
  for (let i = 0; i < float32Buf.length; i += 1) {
    const s = Math.max(-1, Math.min(1, float32Buf[i]));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const bytes = new Uint8Array(pcm16.buffer);
  let binary = '';
  const step = 0x8000;
  for (let i = 0; i < bytes.length; i += step) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + step));
  }
  return btoa(binary);
}


function pcm16Base64ToFloat32(b64) {
  const binary = atob(b64);
  const len = binary.length - (binary.length % 2);
  if (len <= 0) return new Float32Array(0);
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  const samples = new Int16Array(bytes.buffer);
  const float32 = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i += 1) {
    float32[i] = samples[i] / 32768.0;
  }
  return float32;
}


// م9.4 — ترکیب چند چانک Float32 در یک آرایه پیوسته برای Jitter Buffer بدون شکاف
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


// م9.4 — درونیابی خطی پیوسته 24kHz → 48kHz + نرم‌سازی مرز چانک‌ها برای حذف کامل خش‌خش ابتدای مکالمه
function prepareSmoothAudioSamples(samples24k, ctxSampleRate, prevSampleRef, applyStartFadeIn) {
  if (!samples24k || !samples24k.length) {
    return { data: new Float32Array(0), rate: 24000 };
  }
  let prev = prevSampleRef.current || 0;
  if (ctxSampleRate === 48000) {
    const n = samples24k.length;
    const out = new Float32Array(n * 2);
    for (let i = 0; i < n; i += 1) {
      const cur = samples24k[i];
      out[2 * i] = 0.5 * (prev + cur);
      out[2 * i + 1] = cur;
      prev = cur;
    }
    if (applyStartFadeIn) {
      const ramp = Math.min(out.length, 96); // 2ms نرم‌سازی شروع صحبت در 48kHz
      for (let i = 0; i < ramp; i += 1) {
        out[i] *= (i + 1) / ramp;
      }
    }
    prevSampleRef.current = prev;
    return { data: out, rate: 48000 };
  }

  const out = new Float32Array(samples24k.length);
  out.set(samples24k);
  if (applyStartFadeIn) {
    const ramp = Math.min(out.length, 48); // 2ms نرم‌سازی شروع صحبت در 24kHz
    for (let i = 0; i < ramp; i += 1) {
      out[i] *= (i + 1) / ramp;
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

  const wsRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const videoStreamRef = useRef(null);
  const videoElRef = useRef(null);
  const videoTimerRef = useRef(null);
  const captureCtxRef = useRef(null);
  const processorRef = useRef(null);
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
  }, [micMuted]);

  useEffect(() => {
    speakerMutedRef.current = speakerMuted;
  }, [speakerMuted]);

  const stopAllPlayback = useCallback(() => {
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

  const scheduleAudioChunk = useCallback((b64Data) => {
    if (speakerMutedRef.current || !b64Data) return;
    try {
      const float32 = pcm16Base64ToFloat32(b64Data);
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
    });
    const wsUrl = `${wsProto}://${hostPart}/api/ai/live/ws?${qs.toString()}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
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

        // م9.4 — استفاده از همان AudioContext گرم‌شده (حذف کامل پرش سخت‌افزاری ناشی از ساخت AudioContext دوم)
        try {
          const capCtx = ensurePlaybackContext();
          captureCtxRef.current = capCtx;
          const srcNode = capCtx.createMediaStreamSource(stream);
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
            if (nowMs - lastLevelTsRef.current >= 100) {
              let sumSq = 0;
              for (let i = 0; i < raw.length; i += 8) {
                sumSq += raw[i] * raw[i];
              }
              const rms = Math.min(1, Math.sqrt(sumSq / (raw.length / 8)) * 4);
              lastLevelTsRef.current = nowMs;
              if (Math.abs(rms - lastLevelValRef.current) > 0.03 || (rms < 0.02 && lastLevelValRef.current > 0)) {
                const nextLvl = rms < 0.02 ? 0 : rms;
                lastLevelValRef.current = nextLvl;
                setMicLevel(nextLvl);
              }
            }

            const pcm16k = downsampleTo16k(raw, capCtx.sampleRate);
            const b64 = float32ToPcm16Base64(pcm16k);
            wsRef.current.send(JSON.stringify({
              type: 'audio',
              data: b64,
              mimeType: 'audio/pcm;rate=16000',
            }));
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

      if (msg.type === 'output_transcript' && msg.text) {
        aiBufRef.current = `${aiBufRef.current} ${msg.text}`.trim();
        setAiLiveText(aiBufRef.current);
        return;
      }

      if (msg.type === 'text' && msg.text) {
        aiBufRef.current = `${aiBufRef.current} ${msg.text}`.trim();
        setAiLiveText(aiBufRef.current);
        return;
      }

      if (msg.type === 'tool_call') {
        const names = (msg.calls || []).map((c) => c.name).join('، ');
        setToolNotice(`🔧 در حال بررسی اطلاعات هامزیار (${names})…`);
        setStatus('thinking');
        return;
      }

      if (msg.type === 'turn_state') {
        if (msg.interaction_status === 'IN_PROGRESS') {
          setStatus('thinking');
        } else if (msg.interaction_status === 'IDLE' || msg.turn_complete) {
          flushPendingAudio(true);
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
          if (activeSourcesRef.current.length === 0 && pendingSamplesCountRef.current === 0) {
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
        <Header title="🎙 تماس صوتی و ویدیویی زنده" back="/ai" />
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
    speaking: { label: 'هوشیار در حال صحبت… (هر لحظه صحبت کنید قطع می‌شود)', color: '#3B82F6', icon: '🔊' },
    error: { label: 'خطا در تماس زنده', color: '#EF4444', icon: '⚠️' },
  }[status] || { label: '', color: '#64748B', icon: '🎙' };

  const orbScale = status === 'speaking'
    ? 1.12
    : status === 'listening'
    ? 1 + Math.min(0.25, micLevel * 0.35)
    : 1;

  return (
    <main className="page" style={{ paddingBottom: 32 }}>
      <Header title="🎙 تماس صوتی و ویدیویی زنده" back="/ai" />

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
                🔄 تعویض دوربین
              </button>
            </div>
          )}

          {/* گوی انیمیشنی تماس زنده */}
          <div
            style={{
              width: cameraOn ? 84 : 128,
              height: cameraOn ? 84 : 128,
              margin: '10px auto 14px',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: cameraOn ? 32 : 46,
              transform: `scale(${orbScale.toFixed(3)})`,
              transition: 'transform 120ms ease-out, box-shadow 250ms ease',
              background: `radial-gradient(circle at 35% 35%, ${statusMeta.color}55, ${statusMeta.color}18 70%)`,
              border: `2px solid ${statusMeta.color}`,
              boxShadow: isCallActive ? `0 0 36px ${statusMeta.color}55` : 'none',
            }}
          >
            {statusMeta.icon}
          </div>

          <div style={{ fontWeight: 700, fontSize: 15, color: '#F8FAFC' }}>
            {statusMeta.label}
          </div>

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
                🗣 صدای هوشیار در مکالمه زنده:
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
                  🌐 زبان مقصد ترجمه‌ی صوت‌به‌صوت:
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
                  🎙 تماس صوتی زنده
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
                    📹 تماس ویدیویی + صوتی
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
                  {micMuted ? '🔇 میکروفون بسته' : '🎤 میکروفون باز'}
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
                    {cameraOn ? '📹 بستن دوربین' : '📷 روشن کردن دوربین'}
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
                  {speakerMuted ? '🔈 بلندگو بسته' : '🔊 بلندگو باز'}
                </button>

                <button
                  type="button"
                  className="btn danger"
                  onClick={endCall}
                  style={{ borderRadius: 999, padding: '10px 20px' }}
                >
                  📴 پایان تماس
                </button>
              </>
            )}
          </div>
        </section>

        {/* زیرنویس زنده و متن مکالمه */}
        {(userLiveText || aiLiveText || historyTurns.length > 0) && (
          <section className="card" style={{ padding: 14, display: 'grid', gap: 8 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--txm)' }}>
              📝 زیرنویس زنده مکالمه
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
                  <b>{t.role === 'user' ? '👤 شما: ' : '🤖 هوشیار: '}</b>
                  <span>{t.text}</span>
                </div>
              ))}
              {userLiveText && (
                <div style={{ padding: '8px 11px', borderRadius: 12, fontSize: 13, background: 'rgba(59,130,246,0.22)' }}>
                  <b>👤 شما (در حال صحبت…): </b>
                  <span>{userLiveText}</span>
                </div>
              )}
              {aiLiveText && (
                <div style={{ padding: '8px 11px', borderRadius: 12, fontSize: 13, background: 'rgba(16,185,129,0.22)' }}>
                  <b>🤖 هوشیار (زنده…): </b>
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
