import { useEffect, useState } from "react";

import { faNum } from "@/lib/dates";
import type { MatchTicket } from "@/lib/types";
import { useMatch } from "@/store/match";
import { Button } from "@/ui/Button";

/**
 * The waiting screen is never silent.
 *
 * Elapsed time, how many people are in the same queue, motion, and — once the
 * search widens — an explicit sentence saying so. A spinner with no numbers is
 * indistinguishable from a broken app, and this is the screen a first-time
 * user sees before they have any reason to trust the product.
 */
export function WaitingOverlay({ ticket, title }: { ticket: MatchTicket; title: string }) {
  const cancel = useMatch((s) => s.cancel);
  const [elapsed, setElapsed] = useState(ticket.waited_seconds);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    setElapsed(ticket.waited_seconds);
  }, [ticket.waited_seconds]);

  useEffect(() => {
    const timer = window.setInterval(() => setElapsed((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 px-8 text-center"
      style={{
        background:
          "radial-gradient(60rem 40rem at 50% 30%, #241d45 0%, transparent 60%), var(--color-ink)",
      }}
    >
      <Pulse />

      <div>
        <p className="text-[20px] font-extrabold">{title}</p>
        <p className="mt-1 text-[13px] tabular-nums text-muted">
          {faNum(elapsed)} ثانیه · {faNum(ticket.queue_size)} نفر در صف
        </p>
      </div>

      {ticket.widened && (
        <p className="surface-card animate-rise rounded-card px-4 py-3 text-[13px] leading-relaxed text-muted">
          کمی بیشتر می‌گردیم تا زودتر یکی پیدا شود…
        </p>
      )}

      <Button
        variant="ghost"
        className="max-w-xs"
        busy={cancelling}
        onClick={async () => {
          setCancelling(true);
          try {
            await cancel();
          } finally {
            setCancelling(false);
          }
        }}
      >
        انصراف
      </Button>
    </div>
  );
}

function Pulse() {
  return (
    <span className="relative grid size-24 place-items-center">
      {/* Two rings at different phases read as a search sweeping outwards,
          where one ring just blinks. */}
      <span className="absolute size-24 animate-ping rounded-full bg-brand/20" />
      <span
        className="absolute size-20 animate-ping rounded-full bg-brand/25"
        style={{ animationDelay: "0.4s" }}
      />
      <span className="relative grid size-16 place-items-center rounded-full bg-gradient-to-b from-brand-soft to-brand text-3xl shadow-[0_10px_30px_-10px_var(--color-brand)]">
        🎲
      </span>
    </span>
  );
}
