import { useEffect, useId, useRef, useState } from "react";

const PLAY_EVENT = "chat:voice-play";
const BAR_COUNT = 40;
const PLACEHOLDER = Array<number>(BAR_COUNT).fill(7);

function clock(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return "--:--";
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

/** The same player serves a local recording preview and a private chat file. */
export function VoicePlayer({ src, loadSource, caption = "پیام صوتی", fileSize, downloadName }: {
  src?: string; loadSource?: () => Promise<string>; caption?: string; fileSize?: string; downloadName?: string;
}) {
  const audio = useRef<HTMLAudioElement>(null);
  const mounted = useRef(false);
  const pending = useRef(false);
  const [source, setSource] = useState(src || "");
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [duration, setDuration] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [rate, setRate] = useState(1);
  const [bars, setBars] = useState(PLACEHOLDER);
  const [error, setError] = useState("");
  const clipId = `voice-${useId().replace(/:/g, "")}`;

  useEffect(() => {
    mounted.current = true;
    const element = audio.current;
    const pauseOther = (event: Event) => {
      if ((event as CustomEvent).detail !== element) element?.pause();
    };
    window.addEventListener(PLAY_EVENT, pauseOther);
    return () => {
      mounted.current = false;
      element?.pause();
      window.removeEventListener(PLAY_EVENT, pauseOther);
    };
  }, []);

  useEffect(() => {
    if (!source) return;
    let disposed = false;
    let context: AudioContext | undefined;
    const controller = new AbortController();
    // Decode only an already-downloaded blob. In particular, this also gives
    // MediaRecorder WebM files a duration when the audio element reports Infinity.
    async function waveform() {
      try {
        const response = await fetch(source, { signal: controller.signal });
        const bytes = await response.arrayBuffer();
        if (disposed) return;
        context = new AudioContext();
        const decoded = await context.decodeAudioData(bytes);
        if (disposed) return;
        const samples = decoded.getChannelData(0);
        const peaks = Array.from({ length: BAR_COUNT }, (_, index) => {
          const start = Math.floor(index * samples.length / BAR_COUNT);
          const end = Math.floor((index + 1) * samples.length / BAR_COUNT);
          const stride = Math.max(1, Math.floor((end - start) / 500));
          let peak = 0;
          for (let i = start; i < end; i += stride) peak = Math.max(peak, Math.abs(samples[i] ?? 0));
          return peak;
        });
        const max = Math.max(...peaks, 0.01);
        setBars(peaks.map((peak) => 4 + (peak / max) * 28));
        if (Number.isFinite(decoded.duration)) setDuration(decoded.duration);
      } catch {
        // Playback remains available when Web Audio cannot decode this codec.
      } finally { if (context && context.state !== "closed") void context.close().catch(() => undefined); }
    }
    void waveform();
    return () => {
      disposed = true;
      controller.abort();
      if (context && context.state !== "closed") void context.close().catch(() => undefined);
    };
  }, [source]);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const update = () => {
      if (audio.current) setElapsed(audio.current.currentTime);
      frame = requestAnimationFrame(update);
    };
    frame = requestAnimationFrame(update);
    return () => cancelAnimationFrame(frame);
  }, [playing]);

  async function toggle() {
    const element = audio.current;
    if (!element || pending.current) return;
    if (!element.paused) { element.pause(); return; }
    pending.current = true;
    setError("");
    try {
      if (!source) {
        if (!loadSource) return;
        setLoading(true);
        const url = await loadSource();
        if (!mounted.current) return;
        element.src = url;
        setSource(url);
      }
      if (element.error) element.load();
      if (element.ended) element.currentTime = 0;
      element.playbackRate = rate;
      await element.play();
    } catch (err) {
      if (mounted.current) setError(err instanceof Error && err.name === "NotAllowedError"
        ? "برای شروع پخش، یک بار دیگر دکمهٔ پخش را بزنید."
        : "پخش صدا ممکن نشد؛ دوباره تلاش کنید یا فایل را ذخیره کنید.");
    } finally {
      pending.current = false;
      if (mounted.current) setLoading(false);
    }
  }

  const progress = duration > 0 ? Math.min(elapsed / duration, 1) : 0;
  const busy = loading || waiting;
  return <div className="w-60 max-w-full" aria-label={caption}>
    <audio ref={audio} src={src || undefined} preload="metadata"
      onPlay={() => { setPlaying(true); window.dispatchEvent(new CustomEvent(PLAY_EVENT, { detail: audio.current })); }}
      onPause={() => { setPlaying(false); setWaiting(false); }}
      onEnded={() => { setPlaying(false); setWaiting(false); }}
      onWaiting={() => setWaiting(true)} onPlaying={() => setWaiting(false)} onCanPlay={() => setWaiting(false)}
      onTimeUpdate={(e) => setElapsed(e.currentTarget.currentTime)}
      onDurationChange={(e) => { if (Number.isFinite(e.currentTarget.duration)) setDuration(e.currentTarget.duration); }}
      onError={() => { setPlaying(false); setWaiting(false); setError("این صدا قابل پخش نیست؛ فایل را ذخیره کنید یا دوباره تلاش کنید."); }}
    />
    <div className="flex items-center gap-3" dir="ltr">
      <div className="flex shrink-0 flex-col items-center">
      <button type="button" onClick={() => void toggle()} disabled={loading}
        aria-label={loading ? "در حال دریافت وویس" : playing ? "توقف پخش وویس" : "پخش وویس"}
        className="press grid size-11 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand-soft to-brand text-white shadow-[0_4px_16px_-6px_var(--color-brand)] outline-none transition-shadow hover:shadow-[0_4px_20px_-4px_var(--color-brand)] focus-visible:ring-2 focus-visible:ring-brand-soft focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:opacity-60">
        {busy ? <span className="size-5 animate-spin rounded-full border-2 border-white/30 border-t-white motion-reduce:animate-none" aria-hidden="true" /> : <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          {playing ? <><rect x="6" y="4" width="4" height="16" rx="1.5" /><rect x="14" y="4" width="4" height="16" rx="1.5" /></> : <path d="M8 4.8c0-1 1.1-1.6 1.9-1.1l11 7.2c.8.5.8 1.7 0 2.2l-11 7.2C9.1 20.8 8 20.2 8 19.2V4.8Z" />}
        </svg>}
      </button>
      {source && downloadName && <a href={source} download={downloadName} aria-label="ذخیرهٔ فایل صوتی" className="grid size-11 place-items-center rounded-full text-faint hover:text-brand-soft focus-visible:outline focus-visible:outline-brand-soft">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M5 16v4h14v-4" /></svg>
      </a>}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[11px] font-semibold text-muted" dir="rtl">{caption}</p>
        <div className="relative flex h-11 items-center rounded-md focus-within:ring-1 focus-within:ring-brand-soft">
          <svg viewBox="0 0 200 36" preserveAspectRatio="none" className="h-9 w-full" aria-hidden="true">
            <defs><clipPath id={clipId}><rect x="0" y="0" width={progress * 200} height="36" /></clipPath></defs>
            <g className="text-faint/45" fill="currentColor">{bars.map((height, i) => <rect key={i} x={i * 5} y={(36 - height) / 2} width="3" height={height} rx="1.5" />)}</g>
            <g clipPath={`url(#${clipId})`} className="text-brand-soft" fill="currentColor">{bars.map((height, i) => <rect key={i} x={i * 5} y={(36 - height) / 2} width="3" height={height} rx="1.5" />)}</g>
          </svg>
          <input type="range" min="0" max={duration || 1} step="0.1" value={Math.min(elapsed, duration || 0)} disabled={!duration || !source}
            aria-label="موقعیت پخش وویس" aria-valuetext={`${clock(elapsed)} از ${clock(duration)}`} dir="ltr"
            className="absolute inset-0 m-0 h-11 w-full cursor-pointer opacity-0 disabled:cursor-default"
            onChange={(e) => { const time = Number(e.target.value); if (audio.current) { audio.current.currentTime = time; setElapsed(time); } }} />
        </div>
        <div className="flex min-h-11 items-center justify-between text-[11px] tabular-nums text-faint">
          <span>{duration ? `${clock(elapsed)} / ${clock(duration)}` : loading ? "…" : fileSize || "--:--"}</span>
          <button type="button" aria-label={`سرعت پخش ${rate} برابر؛ تغییر سرعت`} className="-me-2 grid min-h-11 min-w-11 place-items-center rounded-full font-bold text-brand-soft outline-none focus-visible:ring-1 focus-visible:ring-brand-soft"
            onClick={() => { const next = rate === 1 ? 1.5 : rate === 1.5 ? 2 : 1; setRate(next); if (audio.current) audio.current.playbackRate = next; }}>{rate}×</button>
        </div>
      </div>
    </div>
    {error && <p role="alert" className="mt-2 text-[11px] leading-relaxed text-bad">{error}</p>}
  </div>;
}
