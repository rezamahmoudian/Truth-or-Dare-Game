import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "@/lib/auth";
import type { Relation } from "@/lib/types";
import { useSocial } from "@/store/social";

/**
 * One button, five states.
 *
 * The moment this exists for is the end of a game with a stranger, so it has
 * to be a single unmissable tap — not a menu. The relation comes from the
 * server with the profile, so the label is right on first paint instead of
 * flickering from "add" to "pending".
 */
export function FriendButton({
  userId,
  relation,
  compact = false,
}: {
  userId: number;
  relation: Relation | undefined;
  compact?: boolean;
}) {
  const navigate = useNavigate();
  const known = useSocial((s) => s.relations[userId]);
  const request = useSocial((s) => s.request);
  const accept = useSocial((s) => s.accept);
  const remove = useSocial((s) => s.remove);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const state: Relation = known ?? relation ?? "NONE";
  if (state === "SELF" || state === "BLOCKED") return null;

  const size = compact
    ? "min-h-9 px-3 text-[12px]"
    : "min-h-11 px-4 text-[14px] w-full justify-center";

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? (err.firstMessage ?? "انجام نشد.") : "انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  const base = `press inline-flex items-center rounded-field font-bold disabled:opacity-40 ${size}`;

  if (state === "FRIENDS") {
    return (
      <button
        type="button"
        disabled={busy}
        onClick={() => run(() => remove(userId))}
        className={`${base} bg-surface-2 text-muted`}
      >
        دوست ✓
      </button>
    );
  }

  if (state === "OUTGOING") {
    return (
      <button
        type="button"
        disabled={busy}
        onClick={() => run(() => remove(userId))}
        className={`${base} bg-surface-2 text-muted`}
      >
        در انتظار…
      </button>
    );
  }

  if (state === "INCOMING") {
    return (
      <button
        type="button"
        disabled={busy}
        onClick={() =>
          run(async () => {
            const conversationId = await accept(userId);
            navigate(`/c/${conversationId}`);
          })
        }
        className={`${base} bg-gradient-to-b from-ok to-ok-deep text-ink`}
      >
        قبول درخواست
      </button>
    );
  }

  return (
    <div className="flex flex-col items-stretch gap-1">
      <button
        type="button"
        disabled={busy}
        onClick={() => run(() => request(userId))}
        className={`${base} bg-gradient-to-b from-brand-soft to-brand text-white`}
      >
        + افزودن دوست
      </button>
      {error && <span className="text-[11px] text-bad">{error}</span>}
    </div>
  );
}
