import { useEffect, useState } from "react";

import { ApiError } from "@/lib/auth";
import { faNum } from "@/lib/dates";
import type { GameState, PublicUser } from "@/lib/types";
import { EMPTY_GAME, useGame } from "@/store/game";
import { Button } from "@/ui/Button";

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
}: {
  conversationId: string;
  selfId: number;
  participants: PublicUser[];
  isOwner: boolean;
}) {
  const state: GameState =
    useGame((s) => s.byConversation[conversationId]) ?? EMPTY_GAME;
  const load = useGame((s) => s.load);

  useEffect(() => {
    void load(conversationId).catch(() => undefined);
  }, [conversationId, load]);

  const session = state.session;
  const turn = state.turn;

  if (!session || session.status === "ENDED") {
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
    <div className="animate-rise border-t border-line-soft bg-gradient-to-b from-surface-2 to-surface px-3 py-3">
      <div className="mx-auto flex max-w-md flex-col gap-2.5">
        <div className="flex items-center justify-between text-[11px] text-faint">
          <span className="flex items-center gap-1.5">
            {/* A row of pips rather than a bare fraction: progress you can
                read without doing arithmetic. */}
            <span className="flex gap-0.5" aria-hidden>
              {Array.from({ length: Math.min(session.total_turns, 12) }, (_, i) => (
                <span
                  key={i}
                  className={`h-1 w-1.5 rounded-full ${
                    i <= session.turn_index ? "bg-brand" : "bg-line"
                  }`}
                />
              ))}
            </span>
            نوبت {faNum(session.turn_index + 1)} از {faNum(session.total_turns)}
          </span>
          {turn.status === "CONFIRMING" && turn.confirmations_required > 1 && (
            <span className="rounded-full bg-surface-3 px-2 py-0.5">
              {faNum(turn.confirmations.length)} از{" "}
              {faNum(turn.confirmations_required)} تأیید
            </span>
          )}
        </div>

        {turn.status === "CHOOSING" &&
          (isMine ? (
            <ChooseRow turnId={turn.id} />
          ) : (
            <Waiting text={`${playerName} در حال انتخاب است…`} turnId={turn.id} isOwner={isOwner} />
          ))}

        {turn.status === "ANSWERING" &&
          (isMine ? (
            <AnswerRow turnId={turn.id} />
          ) : (
            <Waiting text={`منتظر پاسخ ${playerName}…`} turnId={turn.id} isOwner={isOwner} />
          ))}

        {turn.status === "CONFIRMING" && (
          <ConfirmRow
            turnId={turn.id}
            isMine={isMine}
            isOwner={isOwner}
            playerName={playerName}
            alreadyConfirmed={turn.confirmations.includes(selfId)}
          />
        )}
      </div>
    </div>
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
  isOwner: boolean;
}) {
  const start = useGame((s) => s.start);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOwner) {
    return <Strip>{ended ? "بازی تمام شد." : "هر وقت سازنده‌ی روم بخواهد بازی شروع می‌شود."}</Strip>;
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
              await start(conversationId, 2, 3);
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
    <div className="flex flex-col gap-2">
      <p className="text-center text-[13px] text-muted">
        <span className="animate-pulse-soft">⏳</span> {text}
      </p>
      {isOwner && (
        <button
          type="button"
          onClick={() => forceNext(turnId)}
          className="py-1 text-[11.5px] text-faint underline-offset-4 hover:underline"
        >
          رد کن و برو نفر بعد
        </button>
      )}
    </div>
  );
}

function ChooseRow({ turnId }: { turnId: number }) {
  const choose = useGame((s) => s.choose);
  const skip = useGame((s) => s.skip);

  return (
    <div className="flex flex-col gap-2">
      <p className="text-center text-[14px] font-bold">نوبت توئه — انتخاب کن</p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => choose(turnId, "TRUTH")}
          className="press min-h-14 flex-1 rounded-field bg-gradient-to-b from-brand-soft to-brand text-[17px] font-extrabold text-white shadow-[0_8px_22px_-10px_var(--color-brand)]"
        >
          حقیقت
        </button>
        <button
          type="button"
          onClick={() => choose(turnId, "DARE")}
          className="press min-h-14 flex-1 rounded-field bg-gradient-to-b from-ok to-ok-deep text-[17px] font-extrabold text-ink shadow-[0_8px_22px_-10px_var(--color-ok)]"
        >
          جرئت
        </button>
      </div>
      <button
        type="button"
        onClick={() => skip(turnId)}
        className="py-1 text-[11.5px] text-faint"
      >
        رد کردن نوبت
      </button>
    </div>
  );
}

function AnswerRow({ turnId }: { turnId: number }) {
  const answer = useGame((s) => s.answer);
  const skip = useGame((s) => s.skip);
  const [text, setText] = useState("");

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!text.trim()) return;
        answer(turnId, text);
        setText("");
      }}
    >
      <p className="text-center text-[14px] font-bold">جوابت رو بنویس</p>
      <div className="flex gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          autoFocus
          placeholder="جواب…"
          className="surface-raised min-h-12 flex-1 rounded-field px-4 text-[15px] outline-none placeholder:text-faint focus:border-brand/60"
        />
        <button
          type="submit"
          disabled={!text.trim()}
          className="press min-h-12 shrink-0 rounded-field bg-gradient-to-b from-brand-soft to-brand px-5 font-bold text-white disabled:opacity-40 disabled:shadow-none"
        >
          ثبت
        </button>
      </div>
      <button
        type="button"
        onClick={() => skip(turnId)}
        className="py-1 text-[11.5px] text-faint"
      >
        نمی‌تونم — رد کن
      </button>
    </form>
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
      <div className="flex flex-col gap-2">
        <p className="text-center text-[13px] text-muted">
          <span className="animate-pulse-soft">⏳</span> جواب دادی — منتظر تأیید
          بقیه‌ایم.
        </p>
        {isOwner && (
          <button
            type="button"
            onClick={() => forceNext(turnId)}
            className="press surface-raised min-h-11 rounded-field text-[13px] font-bold"
          >
            برو نفر بعد
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-center text-[14px] font-bold">{playerName} جواب داد؟</p>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={alreadyConfirmed}
          onClick={() => confirm(turnId)}
          className="press min-h-12 flex-1 rounded-field bg-gradient-to-b from-ok to-ok-deep text-[16px] font-extrabold text-ink shadow-[0_8px_22px_-10px_var(--color-ok)] disabled:opacity-50 disabled:shadow-none"
        >
          {alreadyConfirmed ? "تأیید کردی ✓" : "✓ آره، جواب داد"}
        </button>
        {isOwner && (
          <button
            type="button"
            onClick={() => forceNext(turnId)}
            className="press surface-raised min-h-12 rounded-field px-4 text-[13px] text-muted"
          >
            رد کن
          </button>
        )}
      </div>
    </div>
  );
}
