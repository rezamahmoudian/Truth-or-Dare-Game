import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "@/lib/auth";
import type { Conversation } from "@/lib/types";
import { useSocial } from "@/store/social";
import { useGame } from "@/store/game";
import { useInvitations } from "@/store/invitations";
import { ChatGameArt, ChatIcon } from "./ChatDecor";

export function ChatPlayCard({ conversation, selfId }: { conversation: Conversation | null; selfId: number }) {
  const navigate = useNavigate();
  const friends = useSocial(s => s.lists.friends);
  const session = useGame(s => conversation ? s.byConversation[conversation.id]?.session : undefined);
  const start = useGame(s => s.start);
  const incoming = useInvitations(s => s.lists.incoming);
  const respond = useInvitations(s => s.respond);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!conversation || conversation.status === "CLOSED") return null;
  const other = conversation.participants.find(p => p.id !== selfId);
  const invite = incoming.find(i => i.user.id === other?.id);
  if (!invite && session && session.status !== "ENDED") return null;
  const canStart = conversation.type === "DIRECT" || conversation.owner_id === selfId || (conversation.max_players === 2 && conversation.participants.length === 2 && friends.some(p => p.id === other?.id));
  return <section className="chat-play-card animate-fade-in" aria-label="بازی جرئت یا حقیقت">
    <ChatGameArt />
    <div><h2>یه دور جرئت یا حقیقت</h2><p>{invite ? `دعوت ${invite.user.display_name} به بازی دونفره` : canStart ? "یه سؤال، یه داستان تازه!" : "منتظر شروع بازی توسط میزبان"}</p>
      {(invite || canStart) && <button type="button" className="chat-lime-link" disabled={busy} onClick={async () => {
        setBusy(true); setError("");
        try {
          if (invite) {
            const pairChat = conversation.participants.length === 2 && (conversation.type === "DIRECT" || conversation.max_players === 2);
            const result = await respond(invite.id, "accept", pairChat ? conversation.id : undefined);
            if (result.conversation_id === conversation.id) await useGame.getState().load(conversation.id);
            else if (result.conversation_id) navigate(`/c/${result.conversation_id}`);
          }
          else await start(conversation.id, 2);
        } catch (e) { setError(e instanceof ApiError ? e.firstMessage || "شروع بازی ممکن نشد." : "ارتباط قطع شد؛ دوباره تلاش کن."); }
        finally { setBusy(false); }
      }}>{busy ? "یه لحظه…" : invite ? "قبول دعوت" : session?.status === "ENDED" ? "یه دور دیگه" : "شروع بازی"}<ChatIcon name="arrow" /></button>}
      {error && <p className="text-bad" role="alert">{error}</p>}
    </div>
  </section>;
}
