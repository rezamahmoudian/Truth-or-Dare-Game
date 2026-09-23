import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { clockTime, faNum } from "@/lib/dates";
import type { Conversation } from "@/lib/types";
import { useChat } from "@/store/chat";
import { Avatar } from "@/ui/Avatar";
import { EmptyState, Header, Screen } from "@/ui/Screen";
import { TabBar } from "@/ui/TabBar";

export function ChatListScreen() {
  const conversations = useChat((s) => s.conversations);
  const status = useChat((s) => s.status);
  const loadConversations = useChat((s) => s.loadConversations);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  return (
    <Screen
      header={
        <Header
          title="چت"
          subtitle={status === "open" ? "متصل" : "در حال اتصال…"}
        />
      }
      footer={<TabBar />}
    >
      {conversations.length === 0 ? (
        <EmptyState
          glyph="💬"
          title="هنوز گفتگویی نداری"
          hint="از تب «بازی» یک روم بساز یا با کد وارد روم دوستت شو."
        />
      ) : (
        <ul className="mx-auto max-w-md divide-y divide-line-soft">
          {conversations.map((conversation) => (
            <ConversationRow key={conversation.id} conversation={conversation} />
          ))}
        </ul>
      )}
    </Screen>
  );
}

function ConversationRow({ conversation }: { conversation: Conversation }) {
  const other = conversation.participants[0];
  const title =
    conversation.type === "ROOM"
      ? `روم ${conversation.code ?? ""}`
      : (other?.display_name ?? "گفتگو");

  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const remove = useChat((s) => s.deleteConversation);

  if (confirming) {
    return (
      <li className="flex items-center gap-2 px-4 py-3">
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
            } finally {
              setBusy(false);
            }
          }}
          className="press min-h-10 shrink-0 rounded-field bg-bad px-3 text-[12px] font-bold text-white disabled:opacity-50"
        >
          پاک کن
        </button>
        <button
          type="button"
          onClick={() => setConfirming(false)}
          className="press min-h-10 shrink-0 rounded-field bg-surface-2 px-3 text-[12px] text-muted"
        >
          بی‌خیال
        </button>
      </li>
    );
  }

  return (
    <li className="flex items-center">
      <Link
        to={`/c/${conversation.id}`}
        className="flex min-w-0 flex-1 items-center gap-3 py-3 ps-4 transition-colors active:bg-surface"
      >
        <Avatar avatarKey={other?.avatar || "a1"} name={title} size={50} glow />

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <p className="min-w-0 flex-1 truncate text-[15.5px] font-bold">{title}</p>
            {conversation.last_message_at && (
              <span className="shrink-0 text-[10.5px] tabular-nums text-faint">
                {clockTime(conversation.last_message_at)}
              </span>
            )}
          </div>
          <p
            className={`truncate text-[13px] ${
              conversation.unread_count > 0 ? "font-semibold text-text" : "text-muted"
            }`}
          >
            {conversation.last_message_preview || "هنوز پیامی نیست"}
          </p>
        </div>

        {conversation.unread_count > 0 && (
          <span className="grid min-w-5 shrink-0 place-items-center rounded-full bg-brand px-1.5 py-0.5 text-[11px] font-bold text-white">
            {faNum(conversation.unread_count)}
          </span>
        )}
      </Link>

      <button
        type="button"
        onClick={() => setConfirming(true)}
        aria-label={`پاک کردن ${title}`}
        className="press grid size-11 shrink-0 place-items-center text-lg text-faint"
      >
        ⋯
      </button>
    </li>
  );
}


