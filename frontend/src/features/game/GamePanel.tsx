import { useEffect, useState } from "react";

import { ApiError } from "@/lib/auth";
import { faNum } from "@/lib/dates";
import type { GameState, PublicUser } from "@/lib/types";
import { useSocial } from "@/store/social";
import { EMPTY_GAME, useGame } from "@/store/game";
import { Button } from "@/ui/Button";
import { Skeleton } from "@/ui/Screen";

/**
 * Sits above the composer rather than on a screen of its own.
 *
 * The prompts and answers are already in the message stream; this panel only
 * shows what somebody has to *do* right now. And there is always a somebody —
 * nothing here happens on a timer. A room can leave a turn open for an hour
 * while the players talk about something else, which is the whole point.
 */
export function GamePanel({
  conversationId,
  selfId,
  participants,
  isOwner,
  hideStart = false,
  pairChat = false,
}: {
  conversationId: string;
  selfId: number;
  participants: PublicUser[];
  /** `null` while the conversation is still loading and nobody knows yet. */
  isOwner: boolean | null;
  hideStart?: boolean;
  pairChat?: boolean;
}) {
  const friends = useSocial(s => s.lists.friends);
  const friendCanEnd = pairChat && participants.length === 2 && friends.some(friend => participants.some(p => p.id !== selfId && p.id === friend.id));
  const state: GameState =
    useGame((s) => s.byConversation[conversationId]) ?? EMPTY_GAME;
  const load = useGame((s) => s.load);

  useEffect(() => {
    void load(conversationId).catch(() => undefined);
  }, [conversationId, load]);

  const session = state.session;
  const turn = state.turn;

  if (!session || session.status === "ENDED") {
    if (hideStart) return null;
    return (
      <StartBar
        conversationId={conversationId}
        ended={session?.status === "ENDED"}
        isOwner={isOwner}
      />
    );
  }
  if (!turn || turn.status === "DONE" || turn.status === "SKIPPED") {
    return <Strip>نوبت بعدی…</Strip>;
  }

  const isMine = turn.player_id === selfId;
  const playerName =
    participants.find((p) => p.id === turn.player_id)?.display_name ?? "بازیکن";

  return (
    <div
      className={`chat-game-controls border-t border-line-soft px-3 ${
        isMine ? "turn-mine" : ""
      }`}
      // Keyed on the turn so the sweep replays when the turn becomes yours
      // again, instead of firing once for the life of the panel.
      key={`turn-${turn.id}`}
    >
      <div className="mx-auto flex max-w-md flex-col">
        <div className="game-compact-meta flex items-center gap-2 text-[11px] text-faint">
          {/* No progress bar and no "x of y": the game runs until somebody
              ends it, so there is nothing to be a fraction of. Counting up is
              the honest display. */}
          <span>
            {session.play_mode === "DEEP_TALK" ? "گفت‌وگوی عمیق · " : ""}دور {faNum(session.round_number)} · {isMine ? "نوبت تو" : playerName}
          </span>

          {turn.status === "CONFIRMING" && turn.confirmations_required > 1 && (
            <span className="rounded-full bg-surface-3 px-2 py-0.5">
              {faNum(turn.confirmations.length)} از{" "}
              {faNum(turn.confirmations_required)} تأیید
            </span>
          )}

          {(isOwner === true || friendCanEnd) && (
            <span className="ms-auto">
              <EndGameButton conversationId={conversationId} />
            </span>
          )}
        </div>

        {/* Keyed on the status so the animation replays at each transition
            rather than only when the panel first appears. */}
        <div key={turn.status} className="game-compact-actions">
          {turn.status === "CHOOSING" &&
            (isMine ? (
              session.play_mode === "DEEP_TALK" ? <DeepQuestionRetry turnId={turn.id} /> : <ChooseRow turnId={turn.id} />
            ) : (
              <Waiting
                text={`${playerName} در حال انتخاب است…`}
                turnId={turn.id}
                isOwner={isOwner === true}
              />
            ))}

          {turn.status === "ANSWERING" &&
            (isMine ? (
              <AnswerRow turnId={turn.id} />
            ) : (
              <Waiting text={`منتظر پاسخ ${playerName}…`} turnId={turn.id} isOwner={isOwner === true} />
            ))}

          {turn.status === "CONFIRMING" && (
            <ConfirmRow
              turnId={turn.id}
              isMine={isMine}
              isOwner={isOwner === true}
              playerName={playerName}
              alreadyConfirmed={turn.confirmations.includes(selfId)}
            />
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Ends the game for everybody, so it asks first.
 *
 * Not destructive — every prompt and answer stays in the chat, and the room
 * itself is untouched — but it does stop something other people are in the
 * middle of, and this button sits a few millimetres from the turn counter.
 */
function EndGameButton({ conversationId }: { conversationId: string }) {
  const stop = useGame((s) => s.stop);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className="game-end-button press min-h-11 rounded-full px-2.5 text-[11px] text-faint"
      >
        پایان بازی
      </button>
    );
  }

  return (
    <span className="flex items-center gap-1.5">
      <span className="text-[11px]">تمامش کنم؟</span>
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await stop(conversationId);
          } finally {
            setBusy(false);
          }
        }}
        className="game-end-confirm press rounded-full px-2.5 py-1 text-[11px] font-bold disabled:opacity-50"
      >
        آره
      </button>
      <button
        type="button"
        onClick={() => setConfirming(false)}
        className="press surface-raised rounded-full px-2.5 py-1 text-[11px]"
      >
        نه
      </button>
    </span>
  );
}

function Strip({ children }: { children: React.ReactNode }) {
  return (
    <div className="border-t border-line-soft bg-surface-2/60 px-3 py-3 text-center text-[13px] text-muted">
      {children}
    </div>
  );
}

/**
 * Only the owner may start a game, and a matched room no longer starts one by
 * itself. Two strangers dropped straight into a turn have to perform before
 * they have said hello.
 */
function StartBar({
  conversationId,
  ended,
  isOwner,
}: {
  conversationId: string;
  ended: boolean;
  isOwner: boolean | null;
}) {
  const start = useGame((s) => s.start);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isOwner === null) {
    // Who may start is unknown until the conversation arrives, and saying
    // "the owner will start it" to the owner is worse than saying nothing.
    return (
      <div className="border-t border-line-soft bg-surface-2/60 px-3 py-3">
        <Skeleton className="mx-auto h-12 max-w-md rounded-field" />
      </div>
    );
  }

  if (!isOwner) {
    return (
      <Strip>
        {ended ? "بازی تمام شد." : "هر وقت سازنده‌ی روم بخواهد بازی شروع می‌شود."}
      </Strip>
    );
  }

  return (
    <div className="border-t border-line-soft bg-surface-2/60 px-3 py-3">
      <div className="mx-auto max-w-md">
        {error && <p className="mb-2 text-center text-[12px] text-bad">{error}</p>}
        <Button
          busy={busy}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await start(conversationId, 2);
            } catch (err) {
              setError(
                err instanceof ApiError
                  ? (err.firstMessage ?? "بازی شروع نشد.")
                  : "بازی شروع نشد.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          {ended ? "یک دست دیگه" : "شروع بازی"}
        </Button>
      </div>
    </div>
  );
}

/** What everyone except the current player sees, plus the owner's override. */
function Waiting({
  text,
  turnId,
  isOwner,
}: {
  text: string;
  turnId: number;
  isOwner: boolean;
}) {
  const forceNext = useGame((s) => s.forceNext);

  return (
    <div className="game-status-row flex items-center justify-between gap-2">
      <p className="text-[12px] text-muted">
        {text}
      </p>
      {isOwner && (
        <button
          type="button"
          onClick={() => forceNext(turnId)}
          className="game-skip-button min-h-11 shrink-0 px-2 text-[11.5px] text-faint underline-offset-4 hover:underline"
        >
          نفر بعد
        </button>
      )}
    </div>
  );
}

function DeepQuestionRetry({ turnId }: { turnId: number }) {
  const choose = useGame(s => s.choose);
  const error = useGame(s => s.choiceErrors[turnId]);
  return <div className="text-center"><p className="text-xs text-muted">سؤال تازه‌ای نمانده؛ از بالای چت می‌تونی بازی جدید شروع کنی.</p><button type="button" className="min-h-11 text-xs text-brand-soft" onClick={() => choose(turnId, "TRUTH")}>بررسی سؤال تازه</button>{error && <p role="alert" className="text-xs text-bad">{error}</p>}</div>;
}

function ChooseRow({ turnId }: { turnId: number }) {
  const choose = useGame((s) => s.choose);
  const skip = useGame((s) => s.skip);
  const error = useGame((s) => s.choiceErrors[turnId]);

  return (
    <div className="flex flex-col gap-1">
      {error && <p role="alert" className="text-center text-[12px] leading-relaxed text-bad">{error}</p>}
      <div className="game-choice-row flex items-center gap-2">
        <button
          type="button"
          onClick={() => choose(turnId, "TRUTH")}
          className="game-truth-button press min-h-11 flex-1 rounded-field text-[13px] font-bold"
        >
          حقیقت
        </button>
        <button
          type="button"
          onClick={() => choose(turnId, "DARE")}
          className="game-dare-button press min-h-11 flex-1 rounded-field text-[13px] font-bold"
        >
          جرئت
        </button>
      </div>
      <button
        type="button"
        onClick={() => skip(turnId)}
        className="game-skip-button min-h-11 shrink-0 self-center px-3 text-[11.5px] text-faint"
      >
        رد نوبت
      </button>
    </div>
  );
}

function AnswerRow({ turnId }: { turnId: number }) {
  const skip = useGame((s) => s.skip);
  return (
    <div className="flex items-center justify-between gap-2">
      <p className="text-[12px] text-muted">جوابت رو بنویس…</p>
      <button
        type="button"
        onClick={() => skip(turnId)}
        className="game-skip-button min-h-11 shrink-0 rounded-field px-3 text-[12px] text-faint"
      >
        رد نوبت
      </button>
    </div>
  );
}

/**
 * The turn now waits for people, not a clock.
 *
 * The answerer sees who they are waiting for; everyone else gets the one
 * button that matters. The owner's confirmation counts on its own, so their
 * button says so rather than pretending to be one vote among many.
 */
function ConfirmRow({
  turnId,
  isMine,
  isOwner,
  playerName,
  alreadyConfirmed,
}: {
  turnId: number;
  isMine: boolean;
  isOwner: boolean;
  playerName: string;
  alreadyConfirmed: boolean;
}) {
  const confirm = useGame((s) => s.confirm);
  const forceNext = useGame((s) => s.forceNext);

  if (isMine) {
    return (
      <div className="game-status-row flex items-center justify-between gap-2">
        <p className="text-[12px] text-muted">
          منتظر تأیید پاسخ…
        </p>
        {isOwner && (
          <button
            type="button"
            onClick={() => forceNext(turnId)}
            className="game-skip-button press min-h-11 shrink-0 rounded-field px-3 text-[12px]"
          >
            نفر بعد
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="game-confirm-row flex items-center gap-2">
      <p className="min-w-0 flex-1 text-[12px] text-muted">تأیید پاسخ {playerName}</p>
      <div className="flex shrink-0 gap-2">
        <button
          type="button"
          disabled={alreadyConfirmed}
          onClick={() => confirm(turnId)}
          className="game-dare-button press min-h-11 rounded-field px-3 text-[12px] font-bold disabled:opacity-50"
        >
          {alreadyConfirmed ? "تأیید شد ✓" : "تأیید پاسخ"}
        </button>
        {isOwner && (
          <button
            type="button"
            onClick={() => forceNext(turnId)}
            className="game-skip-button press min-h-11 rounded-field px-2 text-[12px] text-muted"
          >
            رد کن
          </button>
        )}
      </div>
    </div>
  );
}
