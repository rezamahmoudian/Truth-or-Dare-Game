import { useEffect, useState } from "react";

import { ApiError } from "@/lib/auth";
import { faNum } from "@/lib/dates";
import type { GameState, Prompt, PublicUser } from "@/lib/types";
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
}: {
  conversationId: string;
  selfId: number;
  participants: PublicUser[];
  /** `null` while the conversation is still loading and nobody knows yet. */
  isOwner: boolean | null;
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
    <div
      className={`animate-rise border-t border-line-soft bg-gradient-to-b from-surface-2 to-surface px-3 py-3 ${
        isMine ? "turn-mine" : ""
      }`}
      // Keyed on the turn so the sweep replays when the turn becomes yours
      // again, instead of firing once for the life of the panel.
      key={`turn-${turn.id}`}
    >
      <div className="mx-auto flex max-w-md flex-col gap-2.5">
        <div className="flex items-center gap-2 text-[11px] text-faint">
          {/* No progress bar and no "x of y": the game runs until somebody
              ends it, so there is nothing to be a fraction of. Counting up is
              the honest display. */}
          <span>
            دور {faNum(session.round_number)} · نوبت {faNum(session.turn_index + 1)}
          </span>

          {turn.status === "CONFIRMING" && turn.confirmations_required > 1 && (
            <span className="rounded-full bg-surface-3 px-2 py-0.5">
              {faNum(turn.confirmations.length)} از{" "}
              {faNum(turn.confirmations_required)} تأیید
            </span>
          )}

          {isOwner === true && (
            <span className="ms-auto">
              <EndGameButton conversationId={conversationId} />
            </span>
          )}
        </div>

        {/* A reminder, not a second card. The real card is in the stream, and
            two identical cards stacked on top of each other look like a bug —
            but the stream scrolls, and it scrolls most while the answer is
            being typed, so the question has to stay reachable somehow. */}
        {turn.prompt && <PromptReminder prompt={turn.prompt} />}

        {/* Keyed on the status so the animation replays at each transition
            rather than only when the panel first appears. */}
        <div key={turn.status} className="animate-swap-in">
          {turn.status === "CHOOSING" &&
            (isMine ? (
              <ChooseRow turnId={turn.id} />
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
 * What the current turn is about, in one quiet line.
 *
 * Deliberately smaller, dimmer and left-aligned next to its badge, so it reads
 * as a label for the buttons underneath rather than competing with the card in
 * the stream that it is reminding you of.
 */
function PromptReminder({ prompt }: { prompt: Prompt }) {
  const dare = prompt.type === "DARE";
  return (
    <div
      key={prompt.id}
      className="animate-swap-in flex items-start gap-2 rounded-field bg-surface-3/50 px-3 py-2"
    >
      <span
        className={`mt-px shrink-0 rounded-full px-2 py-0.5 text-[10px] font-extrabold ${
          dare ? "bg-ok/20 text-ok" : "bg-brand/25 text-brand-soft"
        }`}
      >
        {dare ? "جرئت" : "حقیقت"}
      </span>
      <p className="line-clamp-2 min-w-0 flex-1 text-[12.5px] leading-relaxed text-muted">
        {prompt.text}
      </p>
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
        className="press surface-raised rounded-full px-2.5 py-1 text-[11px] text-faint"
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
        className="press rounded-full bg-bad px-2.5 py-1 text-[11px] font-bold text-white disabled:opacity-50"
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
