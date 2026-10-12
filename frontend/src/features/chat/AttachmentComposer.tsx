import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { Media } from "./Attachments";
import { useVoiceRecorder } from "./useVoiceRecorder";
import { ApiError } from "@/lib/auth";
import { uploadAttachment } from "@/lib/chatApi";
import { useChat } from "@/store/chat";
import { ChatIcon } from "./ChatDecor";
import { EmojiPicker } from "./EmojiPicker";

type Draft = { file: File; voice: boolean; id: string; url: string };
type IconName = "mic" | "clip" | "send" | "lock" | "trash" | "stop" | "image" | "video" | "file";
const paths: Record<IconName, ReactNode> = {
  mic: <><rect x="9" y="2" width="6" height="13" rx="3" /><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8" /></>,
  clip: <path d="m8 12 7-7a4 4 0 0 1 6 6L10 22a6 6 0 0 1-8-8L13 3m-8 14a2 2 0 0 0 3 3l11-11" />,
  send: <path d="m21 3-7 18-4-7-7-4 18-7ZM10 14 21 3" />,
  lock: <><rect x="5" y="10" width="14" height="11" rx="3" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" /></>,
  trash: <path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7" />,
  stop: <rect x="6" y="6" width="12" height="12" rx="3" />,
  image: <><rect x="3" y="3" width="18" height="18" rx="4" /><circle cx="8" cy="8" r="1" /><path d="m3 17 5-5 4 4 4-6 5 7" /></>,
  video: <><rect x="3" y="5" width="18" height="14" rx="4" /><path d="m10 9 5 3-5 3V9Z" /></>,
  file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Zm0 0v6h6M8 13h8m-8 4h5" /></>,
};
function Icon({ name }: { name: IconName }) {
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

const action = "grid size-12 shrink-0 place-items-center rounded-full transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand disabled:opacity-40";

export function AttachmentComposer({ conversationId, children, hasText, onSendText, onInsertEmoji }: {
  conversationId: string; children: ReactNode; hasText: boolean; onSendText: () => void;
  onInsertEmoji?: (emoji: string) => void;
}) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [menu, setMenu] = useState(false);
  const [emojiMenu, setEmojiMenu] = useState(false);
  const sectionRef = useRef<HTMLElement>(null);
  const [locked, setLocked] = useState(false);
  const [cancelReady, setCancelReady] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);
  const uploading = useRef(false);
  const draftUrl = useRef("");
  const gesture = useRef<{ id: number; x: number; y: number; cancel: boolean } | null>(null);
  const keyboard = useRef(false);
  const helpId = useId();
  const menuId = useId();
  const emojiMenuId = useId();
  const voice = useVoiceRecorder((file, sendNow) => {
    const next = select(file, true);
    if (next && sendNow) void send(next);
  });
  const active = voice.phase !== "idle";

  useEffect(() => {
    if (!menu && !emojiMenu) return;
    const outside = (e: PointerEvent) => { if (!sectionRef.current?.contains(e.target as Node)) { setMenu(false); setEmojiMenu(false); } };
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") { setMenu(false); setEmojiMenu(false); } };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [menu, emojiMenu]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (draftUrl.current) URL.revokeObjectURL(draftUrl.current);
    };
  }, []);

  function clearDraft() {
    if (draftUrl.current) URL.revokeObjectURL(draftUrl.current);
    draftUrl.current = "";
    setDraft(null);
  }

  function select(file: File, isVoice = false) {
    if (!file.size || file.size > 25 * 1024 * 1024) {
      setError("فایل خالی یا بزرگ‌تر از ۲۵ مگابایت قابل ارسال نیست.");
      return;
    }
    clearDraft();
    setMenu(false);
    setEmojiMenu(false);
    setError("");
    draftUrl.current = URL.createObjectURL(file);
    const next = { file, voice: isVoice, id: crypto.randomUUID?.() ?? `f-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`, url: draftUrl.current };
    setDraft(next);
    return next;
  }

  async function send(next: Draft) {
    if (uploading.current) return;
    uploading.current = true;
    setBusy(true);
    setError("");
    try {
      const message = await uploadAttachment(conversationId, next.file, next.voice, next.id, "");
      useChat.getState().receiveMessage(message);
      if (mounted.current) clearDraft();
    } catch (err) {
      if (mounted.current) setError(err instanceof ApiError ? err.firstMessage || "ارسال نشد؛ دوباره تلاش کنید." : "ارتباط قطع شد؛ ضبط شما محفوظ است. دوباره ارسال را بزنید.");
    } finally {
      uploading.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  function begin(lock = false) {
    if (active || draft || uploading.current) return;
    setMenu(false);
    setEmojiMenu(false);
    setError("");
    setLocked(lock);
    setCancelReady(false);
    void voice.start();
  }

  function endGesture(cancel = false) {
    if (!gesture.current) return;
    const discard = cancel || gesture.current.cancel;
    gesture.current = null;
    setCancelReady(false);
    voice.finish(discard ? "cancel" : "send");
  }

  const kind = draft?.voice ? "voice" : draft?.file.type.startsWith("image/") && draft.file.type !== "image/svg+xml" ? "image" : draft?.file.type.startsWith("video/") ? "video" : draft?.file.type.startsWith("audio/") ? "audio" : "file";
  const time = `${Math.floor(voice.seconds / 60)}:${String(voice.seconds % 60).padStart(2, "0")}`;
  return <section ref={sectionRef} className="chat-composer relative mx-auto flex max-w-md flex-col gap-2" aria-label="ارسال پیام و پیوست">
    <input ref={input} type="file" className="hidden" aria-label="انتخاب فایل" onChange={(e) => { const file = e.target.files?.[0]; if (file) select(file); e.target.value = ""; }} />
    {menu && <div id={menuId} className="composer-popover composer-attachments animate-rise surface-raised flex gap-2 rounded-card p-2" aria-label="انتخاب پیوست">
      {([["عکس", "image/*", "image"], ["ویدئو", "video/*", "video"], ["فایل", "", "file"]] as const).map(([label, accept, icon]) => <button key={label} type="button" className="press flex min-h-16 flex-1 flex-col items-center justify-center gap-1 rounded-field bg-surface-2 text-[12px] text-muted hover:bg-surface-3" onClick={() => { if (input.current) { input.current.accept = accept; input.current.click(); } }}><Icon name={icon} />{label}</button>)}
    </div>}
    {emojiMenu && <EmojiPicker id={emojiMenuId} onSelect={emoji => { onInsertEmoji?.(emoji); setEmojiMenu(false); }} />}
    {draft && <div className="animate-rise surface-raised flex max-h-[40dvh] flex-col gap-3 overflow-y-auto rounded-card p-3">
      <div className="flex items-center gap-2 text-[12px]">
        <span className="text-brand-soft"><Icon name={draft.voice ? "mic" : "file"} /></span>
        <span className="min-w-0 flex-1 truncate">{draft.voice ? "پیام صوتی شما" : draft.file.name}</span>
        <span className="text-faint" dir="ltr">{(draft.file.size / 1024 / 1024).toFixed(1)} MB</span>
      </div>
      <Media kind={kind} url={draft.url} name={draft.file.name} />
      <div className="flex items-center justify-between gap-2">
        <button type="button" disabled={busy} onClick={clearDraft} className={`${action} text-bad hover:bg-bad/10`} aria-label="حذف پیوست"><Icon name="trash" /></button>
        <button type="button" disabled={busy} onClick={() => void send(draft)} className="press flex min-h-11 items-center gap-2 rounded-full bg-brand px-5 text-[13px] font-bold text-white disabled:opacity-50">{busy ? "در حال ارسال…" : error ? "ارسال دوباره" : draft.voice ? "ارسال وویس" : "ارسال پیوست"}<Icon name="send" /></button>
      </div>
    </div>}
    <div className="composer-row flex flex-row-reverse items-end gap-2">
      <div className={`composer-field surface-raised flex min-h-12 min-w-0 flex-1 items-center rounded-[1.6rem] ${cancelReady ? "ring-1 ring-bad/60" : ""}`}>
        {active ? <div className="flex min-h-12 min-w-0 flex-1 items-center gap-2 px-3">
          <span className={`size-2 shrink-0 rounded-full bg-bad ${voice.phase === "recording" ? "motion-safe:animate-pulse" : ""}`} aria-hidden="true" />
          <span className="text-[13px] tabular-nums text-muted" dir="ltr" aria-label="زمان ضبط">{time}</span>
          <span className={`min-w-0 flex-1 text-center text-[11px] ${cancelReady ? "text-bad" : "text-faint"}`} role="status">
            {voice.phase === "requesting" ? "مجوز میکروفون را فعال کنید…" : voice.phase === "finishing" ? "آماده‌سازی وویس…" : locked ? "ضبط بدون نگه‌داشتن" : cancelReady ? "رها کن تا لغو شود" : "← برای لغو به چپ بکش"}
          </span>
          {locked && voice.phase === "recording" && <button type="button" className={`${action} text-muted`} onClick={() => voice.finish("preview")} aria-label="توقف و گوش‌دادن قبل از ارسال"><Icon name="stop" /></button>}
        </div> : <>
          <button type="button" className={`${action} text-faint hover:text-brand-soft`} aria-label={menu ? "بستن پیوست‌ها" : "افزودن پیوست"} aria-expanded={menu} aria-controls={menuId} disabled={busy || !!draft} onClick={() => { setMenu((open) => !open); setEmojiMenu(false); }}><Icon name="clip" /></button>
          {children}
      {onInsertEmoji && <button type="button" className={`${action} composer-smile`} disabled={busy || !!draft} aria-label="انتخاب ایموجی" aria-expanded={emojiMenu} aria-controls={emojiMenuId} onClick={() => { setEmojiMenu(v => !v); setMenu(false); }}><ChatIcon name="smile" /></button>}
        </>}
      </div>
      {hasText && !active ? <button type="button" onPointerDown={(e) => e.preventDefault()} onClick={onSendText} className={`${action} bg-gradient-to-b from-brand-soft to-brand text-white`} aria-label="ارسال پیام"><Icon name="send" /></button> : <div className="relative shrink-0">
        {active && !locked && <div className="pointer-events-none absolute bottom-full start-0 mb-4 flex w-12 flex-col items-center gap-2 rounded-full border border-line bg-surface py-3 text-brand-soft shadow-lg" aria-hidden="true"><Icon name="lock" /><span className="text-sm">↑</span></div>}
        <button type="button"
          aria-label={locked && active ? "ارسال وویس" : "برای ضبط وویس نگه دارید"} aria-describedby={helpId}
          disabled={busy || !!draft || voice.phase === "finishing"}
          className={`${action} touch-none select-none bg-gradient-to-b from-brand-soft to-brand text-white shadow-[0_6px_18px_-8px_var(--color-brand)] transition-transform ${active && !locked ? "scale-110 ring-8 ring-brand/15" : ""} ${cancelReady ? "from-bad to-brand-deep" : ""}`}
          style={{ WebkitTouchCallout: "none" }}
          onContextMenu={(e) => e.preventDefault()}
          onPointerDown={(e) => {
            if (!e.isPrimary || e.button !== 0) return;
            e.preventDefault();
            if (locked && active) { voice.finish("send"); return; }
            if (active) return;
            e.currentTarget.setPointerCapture(e.pointerId);
            gesture.current = { id: e.pointerId, x: e.clientX, y: e.clientY, cancel: false };
            begin();
          }}
          onPointerMove={(e) => {
            const held = gesture.current;
            if (!held || held.id !== e.pointerId) return;
            held.cancel = held.x - e.clientX > 80;
            setCancelReady(held.cancel);
            if (!held.cancel && held.y - e.clientY > 70 && voice.phase === "recording") {
              gesture.current = null;
              setLocked(true);
              setCancelReady(false);
            }
          }}
          onPointerUp={(e) => { if (gesture.current?.id === e.pointerId) endGesture(); }}
          onPointerCancel={() => endGesture(true)}
          onLostPointerCapture={() => endGesture(true)}
          onKeyDown={(e) => {
            if (e.key === "Escape") { voice.finish("cancel"); keyboard.current = false; return; }
            if ((e.key === " " || e.key === "Enter") && !e.repeat) {
              e.preventDefault();
              if (locked && active) { voice.finish("send"); return; }
              keyboard.current = true;
              begin();
            }
          }}
          onKeyUp={(e) => {
            if (e.key === " " || e.key === "Enter") {
              e.preventDefault();
              if (keyboard.current) { keyboard.current = false; voice.finish("send"); }
            }
          }}
          onBlur={() => { if (keyboard.current) { keyboard.current = false; voice.finish("cancel"); } }}
          onClick={(e) => { if (e.detail === 0 && !keyboard.current) { if (active) voice.finish("send"); else begin(true); } }}
        ><Icon name={locked && active ? "send" : cancelReady ? "trash" : "mic"} /></button>
      </div>}
    </div>
    <div className={active ? "flex min-h-5 items-center justify-center text-[11px] text-faint" : "sr-only"} id={helpId}>
      {active && locked ? <button type="button" className="min-h-11 px-5 text-[12px] text-bad" onClick={() => voice.finish("cancel")}>حذف وویس</button> : active ? "رها کن برای ارسال · به بالا بکش برای قفل ضبط" : "برای وویس نگه دار؛ برای ارسال رها کن"}
    </div>
    {(error || voice.error) && <p className="text-center text-[12px] text-bad" role="alert">{error || voice.error}</p>}
  </section>;
}
