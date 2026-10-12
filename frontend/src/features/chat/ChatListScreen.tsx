import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { clockTime, faNum } from "@/lib/dates";
import type { Conversation } from "@/lib/types";
import { useChat } from "@/store/chat";
import { useSession } from "@/store/session";
import { useInvitations } from "@/store/invitations";
import { Avatar } from "@/ui/Avatar";
import { EmptyState, Screen } from "@/ui/Screen";
import { TabBar } from "@/ui/TabBar";
import { ChatGameArt, ChatIcon } from "./ChatDecor";

export function ChatListScreen() {
  const conversations = useChat((s) => s.conversations);
  const loadConversations = useChat((s) => s.loadConversations);
  const selfId = useSession((s) => s.user?.id);
  const invitations = useInvitations((s) => s.lists.incoming);
  const loadInvitations = useInvitations((s) => s.load);
  const [error, setError] = useState("");

  useEffect(() => {
    void loadConversations().catch(() => setError("دریافت گفتگوها ممکن نشد؛ دوباره تلاش کن."));
  }, [loadConversations]);
  useEffect(() => { void loadInvitations().catch(() => undefined); }, [loadInvitations]);

  return (
    <Screen
      className="chat-screen chat-inbox"
      header={
        <header className="chat-inbox-heading">
          <span className="chat-inbox-mark" aria-hidden="true">
            <svg width="25" height="25" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M20 11.5a8 8 0 0 1-8 8H5l-3 2v-10a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8Z" /><path d="M7 10h8m-8 4h5" /></svg>
          </span>
          <h1>گفت‌وگوها</h1>
          <span className="chat-inbox-flourish" aria-hidden="true"><i /><i /><i /></span>
        </header>
      }
      footer={<TabBar />}
    >
      {invitations.length > 0 && <Link className="chat-invitation-banner" to="/invitations"><ChatGameArt /><span><strong>{invitations.length === 1 ? `${invitations[0]?.user.display_name} منتظر یه دور دیگه‌ست` : `${faNum(invitations.length)} دعوت به بازی داری`}</strong><small>دعوت به بازی دونفره</small></span><span className="chat-lime-link">دیدن دعوت <ChatIcon name="arrow" /></span></Link>}
      {error && <div className="px-5 py-3 text-sm text-bad" role="alert">{error}<button className="min-h-11 px-3" onClick={() => { setError(""); void loadConversations().catch(() => setError("دریافت گفتگوها ممکن نشد؛ دوباره تلاش کن.")); }}>تلاش دوباره</button></div>}
      {conversations.length === 0 ? (
        <EmptyState
          glyph="💬"
          title="هنوز گفتگویی نداری"
          hint="از خانه یک بازی شروع کن یا با کد وارد روم دوستت شو."
        />
      ) : (
        <ul className="chat-conversations">
          {conversations.map((conversation) => (
            <ConversationRow key={conversation.id} conversation={conversation} selfId={selfId} />
          ))}
        </ul>
      )}
    </Screen>
  );
}

function conversationTitle(conversation: Conversation, selfId?: number) {
  return conversation.max_players > 2 ? `جمع ${conversation.code ?? "دوستان"}` : conversation.participants.find(p => p.id !== selfId)?.display_name ?? "گفتگو";
}

function ConversationRow({ conversation, selfId }: { conversation: Conversation; selfId?: number }) {
  const other = conversation.participants.find(p => p.id !== selfId);
  const title = conversationTitle(conversation, selfId);
  const online = useChat(s => s.online[conversation.id]);
  const [error, setError] = useState("");

  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const remove = useChat((s) => s.deleteConversation);

  if (confirming) {
    return (
      <li className="flex flex-wrap items-center gap-2 px-1 py-3">
        <p className="min-w-0 flex-1 text-sm leading-relaxed text-muted">
          «{title}» از لیست شما پاک شود؟ برای طرف مقابل باقی می‌ماند.
        </p>
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await remove(conversation.id);
            } catch {
              setError("گفتگو پاک نشد؛ دوباره تلاش کن.");
            } finally {
              setBusy(false);
            }
          }}
          className="press min-h-11 shrink-0 rounded-field bg-bad px-3 text-[12px] font-bold text-white disabled:opacity-50"
        >
          پاک کن
        </button>
        <button
          type="button"
          onClick={() => setConfirming(false)}
          className="press min-h-11 shrink-0 rounded-field bg-surface-2 px-3 text-[12px] text-muted"
        >
          بی‌خیال
        </button>
        {error && <p className="w-full text-xs text-bad" role="alert">{error}</p>}
      </li>
    );
  }

  return (
    <li className="chat-conversation-row flex items-center" data-unread={conversation.unread_count > 0}>
      <Link to={other && conversation.max_players === 2 ? `/people/${other.id}` : `/c/${conversation.id}`} aria-label={other && conversation.max_players === 2 ? `پروفایل ${title}` : title} className="shrink-0 py-4 me-3">
        <span className="chat-avatar-wrap">{conversation.max_players > 2 ? <span className="chat-group-avatar"><ChatIcon name="group" /></span> : <Avatar photoUrl={other?.avatar_url} avatarKey={other?.avatar || "a1"} name={title} size={52} />}{other && online?.includes(other.id) && <i className="chat-online-dot" aria-label="آنلاین" />}</span>
      </Link>
      <Link
        to={`/c/${conversation.id}`}
        className="flex min-w-0 flex-1 items-center gap-3 py-4 transition-colors active:bg-surface"
      >


        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <p className="min-w-0 flex-1 truncate text-[15.5px] font-bold">{title}</p>
          </div>
          <p
            className={`truncate text-[13px] ${
              conversation.unread_count > 0 ? "font-semibold text-text" : "text-muted"
            }`}
          >
            {conversation.last_message_preview || "هنوز پیامی نیست"}
          </p>
        </div>

        <span className="chat-row-meta">
          {conversation.last_message_at && <span className="chat-row-time">{clockTime(conversation.last_message_at)}</span>}
          {conversation.unread_count > 0 && (
          <span className="chat-unread grid min-w-6 shrink-0 place-items-center rounded-full bg-brand px-1.5 py-0.5 text-[11px] font-bold text-white">
            {faNum(conversation.unread_count)}
          </span>
          )}
        </span>
      </Link>

      <button
        type="button"
        onClick={() => setConfirming(true)}
        aria-label={`پاک کردن ${title}`}
        className="press grid size-11 shrink-0 place-items-center text-lg text-faint"
      >
        <ChatIcon name="more" />
      </button>
    </li>
  );
}


