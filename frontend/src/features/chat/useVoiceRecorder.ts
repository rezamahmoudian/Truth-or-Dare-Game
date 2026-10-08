import { useCallback, useEffect, useRef, useState } from "react";

type Finish = "send" | "preview" | "cancel";
type Phase = "idle" | "requesting" | "recording" | "finishing";
type RecordingSession = {
  recorder?: MediaRecorder; stream?: MediaStream; started: number;
  finish?: Finish; timer?: number;
};

export function useVoiceRecorder(onRecorded: (file: File, send: boolean) => void) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const callback = useRef(onRecorded);
  callback.current = onRecorded;
  const active = useRef<RecordingSession | null>(null);

  const finish = useCallback((action: Finish) => {
    const session = active.current;
    if (!session || session.finish) return;
    session.finish = action;
    window.clearInterval(session.timer);
    if (session.recorder?.state === "recording") {
      setPhase("finishing");
      session.recorder.stop();
      session.stream?.getTracks().forEach((track) => track.stop());
    } else {
      // Releasing while the permission prompt is open must never start a
      // recording later. The pending request disposes its stream on arrival.
      active.current = null;
      session.stream?.getTracks().forEach((track) => track.stop());
      setPhase("idle");
    }
  }, []);

  useEffect(() => {
    const interrupt = () => finish("cancel");
    const onVisibility = () => { if (document.hidden) interrupt(); };
    window.addEventListener("blur", interrupt);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("blur", interrupt);
      document.removeEventListener("visibilitychange", onVisibility);
      const session = active.current;
      active.current = null;
      if (!session) return;
      window.clearInterval(session.timer);
      session.finish = "cancel";
      if (session.recorder?.state === "recording") session.recorder.stop();
      session.stream?.getTracks().forEach((track) => track.stop());
    };
  }, [finish]);

  async function start() {
    if (active.current) return;
    setError("");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("ضبط صدا به مرورگر به‌روز و اتصال HTTPS یا localhost نیاز دارد.");
      return;
    }
    const session: RecordingSession = { started: 0 };
    active.current = session;
    setSeconds(0);
    setPhase("requesting");
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (active.current !== session) {
        media.getTracks().forEach((track) => track.stop());
        return;
      }
      session.stream = media;
      const mimeType = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(media, mimeType ? { mimeType } : undefined);
      session.recorder = recorder;
      const chunks: BlobPart[] = [];
      let bytes = 0;
      recorder.ondataavailable = (event) => {
        if (active.current !== session) return;
        if (event.data.size) { chunks.push(event.data); bytes += event.data.size; }
        if (bytes > 25 * 1024 * 1024) {
          setError("حجم وویس از ۲۵ مگابایت بیشتر شد؛ کوتاه‌تر ضبط کنید.");
          finish("cancel");
        }
      };
      recorder.onerror = () => {
        if (active.current !== session) return;
        setError("ضبط صدا ناموفق بود. دوباره تلاش کنید.");
        finish("cancel");
      };
      recorder.onstop = () => {
        window.clearInterval(session.timer);
        media.getTracks().forEach((track) => track.stop());
        if (active.current !== session) return;
        active.current = null;
        setPhase("idle");
        if (session.finish === "cancel" || bytes > 25 * 1024 * 1024) return;
        if (!bytes || performance.now() - session.started < 400) {
          setError("برای ضبط وویس، دکمهٔ میکروفون را نگه دارید.");
          return;
        }
        const type = recorder.mimeType || "audio/webm";
        const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
        callback.current(new File(chunks, `voice-${Date.now()}.${ext}`, { type }), session.finish === "send");
      };
      recorder.start(250);
      session.started = performance.now();
      setPhase("recording");
      session.timer = window.setInterval(() => {
        const elapsed = Math.floor((performance.now() - session.started) / 1000);
        setSeconds(Math.min(elapsed, 180));
        // Reaching the limit saves a preview; only a user gesture sends it.
        if (elapsed >= 180) finish("preview");
      }, 200);
    } catch {
      session.stream?.getTracks().forEach((track) => track.stop());
      if (active.current !== session) return;
      active.current = null;
      setPhase("idle");
      setError("میکروفون در دسترس نیست؛ مجوز میکروفون مرورگر را بررسی کنید و دوباره نگه دارید.");
    }
  }

  return { phase, seconds, error, start, finish };
}
