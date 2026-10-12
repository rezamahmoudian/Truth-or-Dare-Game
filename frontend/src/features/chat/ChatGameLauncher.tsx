import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/auth";
import type { Conversation } from "@/lib/types";
import { useGame } from "@/store/game";
import { useSocial } from "@/store/social";

export function ChatGameLauncher({ conversation, selfId }: { conversation: Conversation | null; selfId: number }) {
  const [open, setOpen] = useState(false);
  const other = conversation?.participants.find(p => p.id !== selfId);
  const friends = useSocial(s => s.lists.friends);
  const isFriend = conversation?.max_players === 2 && conversation.participants.length === 2 && friends.some(p => p.id === other?.id);
  if (!conversation || conversation.status === "CLOSED") return null;
  const canStart = conversation.type === "DIRECT" || conversation.owner_id === selfId || isFriend;
  if (!canStart) return null;
  return <>
    <button type="button" className="chat-new-game" onClick={() => setOpen(true)} aria-label="شروع بازی جدید" title="شروع بازی جدید"><span aria-hidden>🎲</span><span>بازی</span></button>
    {open && <GamePicker conversationId={conversation.id} isFriend={isFriend} onClose={() => setOpen(false)} />}
  </>;
}

function GamePicker({ conversationId, isFriend, onClose }: { conversationId: string; isFriend: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<"CLASSIC" | "DEEP_TALK">("CLASSIC");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [replaceId, setReplaceId] = useState<number>();
  const [confirmed, setConfirmed] = useState(false);
  const load = useGame(s => s.load);
  const start = useGame(s => s.start);
  const deep = mode === "DEEP_TALK";
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    element?.showModal();
    return () => { element?.close(); previous?.focus(); };
  }, []);
  useEffect(() => {
    let active = true;
    void load(conversationId).then(() => {
      if (!active) return;
      const session = useGame.getState().byConversation[conversationId]?.session;
      setReplaceId(session?.status === "ACTIVE" ? session.id : undefined);
      setLoading(false);
    }).catch(() => { if (active) setError("دریافت وضعیت بازی ممکن نشد؛ پنجره را ببند و دوباره امتحان کن."); });
    return () => { active = false; };
  }, [conversationId, load]);
  return <dialog ref={dialog} className="chat-game-dialog" aria-labelledby="game-picker-title" onCancel={e => { if (busy) e.preventDefault(); else onClose(); }}>
    <header><div><span className="game-picker-eyebrow">همین‌جا، توی چت خودتون</span><h2 id="game-picker-title">یه بازی تازه؟</h2></div><button type="button" disabled={busy} aria-label="بستن انتخاب بازی" onClick={onClose}>✕</button></header>
    <div className="game-mode-options" role="group" aria-label="انتخاب نوع بازی">
      <button type="button" disabled={busy} aria-pressed={!deep} className="game-mode-classic" onClick={() => setMode("CLASSIC")}><span className="game-mode-icon" aria-hidden>🎲</span><span><strong>جرئت یا حقیقت</strong><small>یه سؤال، یه چالش، کلی خنده</small></span><i aria-hidden>{!deep ? "●" : "○"}</i></button>
      {isFriend ? <button type="button" disabled={busy} aria-pressed={deep} className="game-mode-deep" onClick={() => setMode("DEEP_TALK")}><span className="game-mode-icon" aria-hidden>😏</span><span><em>فقط بین خودمون</em><strong>گفت‌وگوی عمیق</strong><small>یه کم خصوصی‌تر… یه کم جسورتر</small></span><i aria-hidden>{deep ? "●" : "○"}</i></button> : <p className="deep-friends-hint">گفت‌وگوی عمیق در چت دونفره، بعد از قبول دوستی باز می‌شه.</p>}
    </div>
    {deep && <p className="deep-mode-description">حرف‌هایی که معمولاً نمی‌پرسیم 😉<br />سؤال‌های خصوصی و بیشتر جسورانه؛ جواب‌ها توی همین چت. هر سؤال رو نخواستی، ردش کن.</p>}
    {replaceId && <label className="game-restart-confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} /><span>بازی فعلی تمام شود و بازی تازه شروع شود.</span></label>}
    {error && <p role="alert" className="game-launch-error">{error}</p>}
    <button type="button" className={`game-launch-submit ${deep ? "deep" : ""}`} disabled={busy || loading || (!!replaceId && !confirmed)} onClick={async () => {
      setBusy(true); setError("");
      try {
        await start(conversationId, deep ? 3 : 2, { play_mode: mode, ...(replaceId ? { replace_session_id: replaceId } : {}) });
        onClose();
      } catch (e) {
        setError(e instanceof ApiError ? e.firstMessage || "شروع نشد؛ دوباره تلاش کن." : "ارتباط قطع شد؛ دوباره تلاش کن.");
        setConfirmed(false);
        try { await load(conversationId); const latest = useGame.getState().byConversation[conversationId]?.session; setReplaceId(latest?.status === "ACTIVE" ? latest.id : undefined); } catch { setLoading(true); }
      } finally { setBusy(false); }
    }}>{busy ? "داریم شروع می‌کنیم…" : loading ? "در حال دریافت وضعیت…" : deep ? "بریم سر حرف‌های نگفته 😉" : "شروع بازی جدید"}</button>
  </dialog>;
}
