import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { PlayersSheet } from "@/features/chat/PlayersSheet";
import { GamePanel } from "@/features/game/GamePanel";
import { ReportSheet } from "@/features/moderation/ReportSheet";
import * as api from "@/lib/chatApi";
import { clockTime, dayKey, dayLabel, faNum } from "@/lib/dates";
import { deleteMessage } from "@/lib/moderationApi";
import type { AnyMessage, Conversation } from "@/lib/types";
import { isPending } from "@/lib/types";
import { typingUserIds, useChat } from "@/store/chat";
import { useSession } from "@/store/session";
import { Avatar } from "@/ui/Avatar";
import { Screen, Skeleton } from "@/ui/Screen";

const QUICK_REACTIONS = ["😂", "❤️", "😮", "👏"];

// Shared frozen defaults. A selector that returns `state.x[id] ?? []` builds a
// fresh array on every call, so the store sees a changed snapshot each render
// and re-renders forever. The fallback has to be referentially stable, and
// applying it outside the selector keeps it that way.
const NO_MESSAGES: AnyMessage[] = [];
const NO_ONLINE: number[] = [];

function lastSystemMessageId(messages: AnyMessage[]): number {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message && message.type === "SYSTEM") return message.id;
  }
  return 0;
}

export function ChatRoomScreen() {
  const { id = "" } = useParams();
  const navigate = useNavigate();

  const me = useSession((s) => s.user);
  const messages = useChat((s) => s.messages[id]) ?? NO_MESSAGES;
  const loading = useChat((s) => s.loadingHistory);
  const online = useChat((s) => s.online[id]) ?? NO_ONLINE;
  const typing = useChat((s) => s.typing[id]);
  const status = useChat((s) => s.status);
  const openConversation = useChat((s) => s.openConversation);
  const closeConversation = useChat((s) => s.closeConversation);
  const loadOlder = useChat((s) => s.loadOlder);

  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [showPlayers, setShowPlayers] = useState(false);

  useEffect(() => {
    void openConversation(id);
    void api.getConversation(id).then(setConversation).catch(() => undefined);
    return () => closeConversation();
  }, [id, openConversation, closeConversation]);

  // Joins and departures arrive as system messages, and they change who is in
  // the room. Without this the header and the game panel keep showing the
  // participants as they were when the screen opened, so somebody who joined
  // a moment ago is rendered as "بازیکن".
  const lastSystemId = lastSystemMessageId(messages);
  useEffect(() => {
    if (!lastSystemId) return;
    void api.getConversation(id).then(setConversation).catch(() => undefined);
  }, [id, lastSystemId]);

  const typingIds = typingUserIds(typing, me?.id ?? 0);
  const isOwner =
    conversation?.type === "ROOM" && conversation.owner_id === me?.id;
  const isClosed = conversation?.status === "CLOSED";

  const other = conversation?.participants.find((p) => p.id !== me?.id);
  const title =
    conversation?.type === "ROOM"
      ? `روم ${conversation.code ?? ""}`
      : (other?.display_name ?? "گفتگو");

  const subtitle =
    status !== "open"
      ? "در حال اتصال…"
      : typingIds.length > 0
        ? "در حال نوشتن…"
        : `${faNum(online.length)} نفر آنلاین`;

  return (
    <Screen
      scroll={false}
      header={
        <header
          className="bar-blur flex shrink-0 items-center gap-1 border-b border-line-soft px-2 pb-2.5"
          style={{ paddingTop: "max(0.625rem, env(safe-area-inset-top))" }}
        >
          <button
            type="button"
            onClick={() => navigate("/chats")}
            className="press grid size-10 shrink-0 place-items-center rounded-full text-muted"
            aria-label="بازگشت"
          >
            <BackChevron />
          </button>

          {/* The whole header is the handle for the players sheet — the one
              tap that turns a finished game into a friend request. */}
          <button
            type="button"
            onClick={() => setShowPlayers(true)}
            className="press flex min-w-0 flex-1 items-center gap-2.5 rounded-field py-1 text-start"
          >
            <Avatar
              avatarKey={other?.avatar || "a1"}
              name={title}
              size={38}
              glow
            />
            <span className="min-w-0">
              <span className="block truncate text-[16px] font-bold leading-tight">
                {title}
              </span>
              <span
                className={`block truncate text-[12px] leading-tight ${
                  typingIds.length > 0 ? "text-ok" : "text-faint"
                }`}
              >
                {subtitle}
              </span>
            </span>
          </button>

          {conversation?.code && !isClosed && <CopyCode code={conversation.code} />}

          {isOwner && !isClosed && (
            <CloseRoomButton
              conversationId={id}
              onClosed={(updated) => setConversation(updated)}
            />
          )}
        </header>
      }
      footer={
        isClosed ? (
          <ClosedNotice />
        ) : (
          <>
            <GamePanel
              conversationId={id}
              selfId={me?.id ?? 0}
              participants={conversation?.participants ?? []}
              // A private chat has two equals, so either may start a game;
              // a room belongs to whoever opened it. Until it loads, neither
              // answer is known — and the panel says so rather than guessing.
              isOwner={conversation ? conversation.type === "DIRECT" || isOwner : null}
            />
            <Composer conversationId={id} />
          </>
        )
      }
    >
      <MessageList
        messages={messages}
        loading={loading}
        selfId={me?.id ?? 0}
        conversationId={id}
        onReachTop={() => void loadOlder(id)}
      />

      {showPlayers && (
        <PlayersSheet
          participants={conversation?.participants ?? []}
          selfId={me?.id ?? 0}
          onlineIds={online}
          onClose={() => setShowPlayers(false)}
        />
      )}
    </Screen>
  );
}

/** Points towards the start of the line, which in an RTL app is the right. */
function BackChevron() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M9 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Only the owner sees this, and only in a room.
 *
 * Closing is irreversible for everyone in the room, so it asks first —
 * a mis-tap next to the room code should not end the conversation.
 */
function CloseRoomButton({
  conversationId,
  onClosed,
}: {
  conversationId: string;
  onClosed: (conversation: Conversation) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className="press surface-raised shrink-0 rounded-field px-2.5 py-1.5 text-[11.5px] text-faint"
      >
        بستن
      </button>
    );
  }

  return (
    <div className="animate-fade-in flex shrink-0 gap-1">
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            onClosed(await api.closeRoom(conversationId));
          } finally {
            setBusy(false);
            setConfirming(false);
          }
        }}
        className="press rounded-field bg-bad px-3 py-2 text-[12px] font-bold text-white disabled:opacity-50"
      >
        ببند
      </button>
      <button
        type="button"
        onClick={() => setConfirming(false)}
        className="press rounded-field bg-surface-2 px-3 py-2 text-[12px] text-muted"
      >
        بی‌خیال
      </button>
    </div>
  );
}

function ClosedNotice() {
  return (
    <div
      className="bar-blur shrink-0 border-t border-line-soft px-6 py-4 text-center text-[13px] leading-relaxed text-muted"
      style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}
    >
      این روم بسته شده است. گفتگوها باقی می‌مانند ولی پیام جدیدی ارسال نمی‌شود.
    </div>
  );
}

function CopyCode({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(code).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="press surface-raised shrink-0 rounded-field px-2.5 py-1.5 font-mono text-[12px] tracking-[0.2em] text-muted"
      dir="ltr"
      aria-label="کپی کد روم"
    >
      {copied ? "✓" : code}
    </button>
  );
}

function MessageList({
  messages,
  loading,
  selfId,
  conversationId,
  onReachTop,
}: {
  messages: AnyMessage[];
  loading: boolean;
  selfId: number;
  conversationId: string;
  onReachTop: () => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedToBottom = useRef(true);

  useLayoutEffect(() => {
    const element = scrollRef.current;
    // Only follow new messages when the person is already at the bottom —
    // yanking them down while they read history is worse than a missed scroll.
    if (element && pinnedToBottom.current) element.scrollTop = element.scrollHeight;
  }, [messages.length]);

  function onScroll() {
    const element = scrollRef.current;
    if (!element) return;
    const distanceFromBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    pinnedToBottom.current = distanceFromBottom < 80;
    if (element.scrollTop < 40) onReachTop();
  }

  if (loading && messages.length === 0) return <HistorySkeleton />;

  return (
    <div
      ref={scrollRef}
      onScroll={onScroll}
      className="h-full overflow-y-auto overscroll-contain px-3 py-4"
    >
      <div className="mx-auto flex max-w-md flex-col">
        {messages.map((message, index) => {
          const previous = messages[index - 1];
          const newDay =
            !previous || dayKey(previous.created_at) !== dayKey(message.created_at);

          // Consecutive messages from one person collapse into a block: the
          // name and avatar appear once, and the gap tightens. Repeating the
          // avatar beside every line turns a conversation into a list.
          const sameAuthor =
            !newDay &&
            !!previous &&
            previous.type === message.type &&
            authorOf(previous, selfId) === authorOf(message, selfId);

          return (
            <div key={message.client_id || message.id}>
              {newDay && <DayDivider iso={message.created_at} />}
              <MessageRow
                message={message}
                selfId={selfId}
                conversationId={conversationId}
                grouped={sameAuthor}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function authorOf(message: AnyMessage, selfId: number): number {
  if (isPending(message)) return selfId;
  return message.sender?.id ?? 0;
}

function DayDivider({ iso }: { iso: string }) {
  return (
    <div className="my-3 flex items-center gap-3" role="separator">
      <span className="h-px flex-1 bg-line-soft" />
      <span className="rounded-full bg-surface-2 px-3 py-1 text-[11px] text-faint">
        {dayLabel(iso)}
      </span>
      <span className="h-px flex-1 bg-line-soft" />
    </div>
  );
}

function HistorySkeleton() {
  return (
    <div className="mx-auto flex h-full max-w-md flex-col gap-4 px-3 py-6">
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className={`flex gap-2 ${i % 2 ? "flex-row-reverse" : ""}`}
        >
          {i % 2 === 0 && <Skeleton className="size-8 shrink-0 rounded-full" />}
          <Skeleton
            className="h-12 rounded-card"
            // Uneven widths, because a column of identical bars reads as a
            // loading bar rather than as messages.
            {...{ style: { width: `${45 + ((i * 17) % 35)}%` } }}
          />
        </div>
      ))}
    </div>
  );
}

function MessageRow({
  message,
  selfId,
  conversationId,
  grouped,
}: {
  message: AnyMessage;
  selfId: number;
  conversationId: string;
  grouped: boolean;
}) {
  const [showActions, setShowActions] = useState(false);
  const [reporting, setReporting] = useState(false);
  const toggleReaction = useChat((s) => s.toggleReaction);
  const retryMessage = useChat((s) => s.retryMessage);

  if (message.type === "SYSTEM") {
    return (
      <p className="animate-fade-in my-2 text-center">
        <span className="rounded-full bg-surface/70 px-3 py-1 text-[11.5px] text-faint">
          {message.body}
        </span>
      </p>
    );
  }

  // Prompts are centred cards rather than bubbles: they come from the game,
  // not from a person, and they are what the next few messages are about.
  if (message.type === "GAME_PROMPT") {
    const isDare = message.meta?.choice === "DARE";
    return (
      // The one card in the app that is literally a card being turned over.
      <div className="animate-card-in my-3">
        <div
          className={`relative overflow-hidden rounded-card border p-4 text-center ${
            isDare
              ? "border-ok/30 bg-gradient-to-b from-ok/15 to-transparent"
              : "border-brand/30 bg-gradient-to-b from-brand/15 to-transparent"
          }`}
        >
          <span
            className={`mb-1.5 inline-block rounded-full px-2.5 py-0.5 text-[11px] font-extrabold ${
              isDare ? "bg-ok/20 text-ok" : "bg-brand/25 text-brand-soft"
            }`}
          >
            {isDare ? "جرئت" : "حقیقت"}
          </span>
          <p className="text-[16px] font-semibold leading-relaxed">{message.body}</p>
        </div>
      </div>
    );
  }

  const pending = isPending(message);
  const mine = pending || message.sender?.id === selfId;
  const failed = pending && message.failed;
  const isAnswer = message.type === "GAME_ANSWER";

  return (
    <div
      className={`animate-rise flex gap-2 ${grouped ? "mt-0.5" : "mt-2.5"} ${
        mine ? "flex-row-reverse" : ""
      }`}
    >
      {!mine &&
        (grouped ? (
          <span className="w-8 shrink-0" aria-hidden />
        ) : (
          <Avatar
            avatarKey={message.sender?.avatar || "a1"}
            name={message.sender?.display_name ?? ""}
            size={32}
          />
        ))}

      <div className={`flex max-w-[78%] flex-col ${mine ? "items-end" : "items-start"}`}>
        {!mine && !grouped && message.sender && (
          <span className="mb-0.5 px-1 text-[11.5px] font-semibold text-muted">
            {message.sender.display_name}
          </span>
        )}

        <button
          type="button"
          onClick={() => setShowActions((open) => !open)}
          className={`press whitespace-pre-wrap break-words px-3.5 py-2 text-start text-[15px] leading-relaxed ${
            // The corner nearest the speaker stays tight while the rest are
            // round — the cheapest way to give a bubble a direction without
            // drawing a tail.
            mine
              ? "rounded-card rounded-se-md bg-gradient-to-b from-brand-soft to-brand text-white"
              : "rounded-card rounded-ss-md surface-raised"
          } ${grouped ? (mine ? "rounded-se-card" : "rounded-ss-card") : ""} ${
            isAnswer ? "ring-1 ring-ok/50" : ""
          } ${pending ? "opacity-60" : ""} ${failed ? "ring-1 ring-bad" : ""} ${
            message.is_deleted ? "italic opacity-50" : ""
          }`}
        >
          {message.is_deleted ? "پیام حذف شد" : message.body}
        </button>

        <span
          className={`mt-0.5 px-1 text-[10.5px] tabular-nums text-faint ${
            grouped ? "sr-only" : ""
          }`}
        >
          {pending ? "در حال ارسال…" : clockTime(message.created_at)}
        </span>

        {failed && (
          <button
            type="button"
            onClick={() => retryMessage(conversationId, message.client_id)}
            className="px-1 text-[11.5px] font-semibold text-bad"
          >
            ارسال نشد — تلاش دوباره
          </button>
        )}

        {Object.keys(message.reactions).length > 0 && (
          <div className="-mt-1 flex gap-1">
            {Object.entries(message.reactions).map(([emoji, users]) => (
              <button
                key={emoji}
                type="button"
                onClick={() =>
                  !pending &&
                  toggleReaction(conversationId, message.id, emoji, users.includes(selfId))
                }
                className={`press rounded-full px-2 py-0.5 text-[11.5px] ${
                  users.includes(selfId)
                    ? "bg-brand/30 ring-1 ring-brand/40"
                    : "bg-surface-2"
                }`}
              >
                {emoji} {faNum(users.length)}
              </button>
            ))}
          </div>
        )}

        {showActions && !pending && (
          <div className="animate-rise surface-raised mt-1 flex items-center gap-1 rounded-full px-2 py-1">
            {QUICK_REACTIONS.map((emoji) => (
              <button
                key={emoji}
                type="button"
                onClick={() => {
                  toggleReaction(
                    conversationId,
                    message.id,
                    emoji,
                    (message.reactions[emoji] ?? []).includes(selfId),
                  );
                  setShowActions(false);
                }}
                className="press px-1 text-[19px]"
              >
                {emoji}
              </button>
            ))}

            {/* Reporting sits next to the reactions rather than behind a long
                press: the moment someone wants it, they are already touching
                the message. */}
            <span className="mx-0.5 h-4 w-px bg-line" />
            {mine ? (
              <button
                type="button"
                onClick={() => {
                  void deleteMessage(message.id).catch(() => undefined);
                  setShowActions(false);
                }}
                className="px-1.5 text-[11.5px] text-faint"
              >
                حذف
              </button>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setReporting(true);
                  setShowActions(false);
                }}
                className="px-1.5 text-[13px]"
                aria-label="گزارش پیام"
              >
                🚩
              </button>
            )}
          </div>
        )}

        {reporting && message.sender && (
          <ReportSheet
            targetUserId={message.sender.id}
            targetName={message.sender.display_name}
            messageId={message.id}
            onClose={() => setReporting(false)}
          />
        )}
      </div>
    </div>
  );
}

function Composer({ conversationId }: { conversationId: string }) {
  const [text, setText] = useState("");
  const sendMessage = useChat((s) => s.sendMessage);
  const setTyping = useChat((s) => s.setTyping);
  const typingSentAt = useRef(0);
  const areaRef = useRef<HTMLTextAreaElement>(null);

  function onChange(value: string) {
    setText(value);

    // Grow with the text up to a ceiling, so a long message is visible while
    // it is being written instead of scrolling inside one line.
    const area = areaRef.current;
    if (area) {
      area.style.height = "auto";
      area.style.height = `${Math.min(area.scrollHeight, 128)}px`;
    }

    // Throttled: the indicator only needs to be refreshed every couple of
    // seconds, and a frame per keystroke is pure noise on the channel layer.
    const now = Date.now();
    if (value && now - typingSentAt.current > 2000) {
      typingSentAt.current = now;
      setTyping(conversationId, true);
    }
  }

  function submit() {
    if (!text.trim()) return;
    sendMessage(conversationId, text);
    setText("");
    if (areaRef.current) areaRef.current.style.height = "auto";
    typingSentAt.current = 0;
    setTyping(conversationId, false);
  }

  return (
    <div
      className="bar-blur shrink-0 border-t border-line-soft px-3 py-2"
      style={{ paddingBottom: "max(0.5rem, env(safe-area-inset-bottom))" }}
    >
      <form
        className="mx-auto flex max-w-md items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <textarea
          ref={areaRef}
          value={text}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder="پیام…"
          className="surface-raised max-h-32 min-h-12 flex-1 resize-none rounded-field px-4 py-3 text-[15px] outline-none transition-colors placeholder:text-faint focus:border-brand/60"
        />
        <button
          type="submit"
          disabled={!text.trim()}
          className="press grid size-12 shrink-0 place-items-center rounded-field bg-gradient-to-b from-brand-soft to-brand text-white shadow-[0_6px_18px_-8px_var(--color-brand)] transition-opacity disabled:opacity-35 disabled:shadow-none"
          aria-label="ارسال"
        >
          ➤
        </button>
      </form>
    </div>
  );
}
