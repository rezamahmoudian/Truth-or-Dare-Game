import { useEffect, useState } from "react";

import { faNum } from "@/lib/dates";
import type { MatchTicket } from "@/lib/types";
import { useMatch } from "@/store/match";
import { Button } from "@/ui/Button";

const SEARCH_TIPS = [
  "اگر سؤالی را دوست نداشتی، با یک لمس بازخورد منفی بده تا بهترش کنیم.",
  "با لمس عکس هر بازیکن، پروفایل، علایق و نشان‌هایش را ببین.",
  "از داخل پروفایل بازیکن‌ها می‌توانی درخواست دوستی یا دعوت بازی بفرستی.",
  "دوستانت را در بخش «دوستان» پیدا کن و هر وقت خواستی به آن‌ها پیام بده.",
  "از داخل هر چت، هر زمان خواستی می‌توانی یک بازی جدید شروع کنی.",
  "چند لحظه صبر کن؛ یک گفت‌وگوی جالب در راه است.",
  "هنوز کسی پیدا نشده؟ نگران نباش، بهترین بازی‌ها گاهی با کمی تأخیر شروع می‌شوند.",
  "یک هم‌بازی، چند سؤال و کلی حرف برای گفتن در راه است.",
  "هنوز در صف جست‌وجو هستی.",
] as const;

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
  const resume = useMatch((s) => s.resume);
  const [elapsed, setElapsed] = useState(ticket.waited_seconds);
  const [tipIndex, setTipIndex] = useState(0);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setTipIndex((index) => (index + 1) % SEARCH_TIPS.length);
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let stopped = false;
    let timer: number;
    const check = async () => {
      try { if (document.visibilityState === "visible") await resume(); }
      catch { /* Socket reconnect and the next check both retry. */ }
      if (!stopped) timer = window.setTimeout(() => void check(), 5000);
    };
    timer = window.setTimeout(() => void check(), 5000);
    const visible = () => { if (document.visibilityState === "visible") void resume().catch(() => undefined); };
    document.addEventListener("visibilitychange", visible);
    return () => { stopped = true; window.clearTimeout(timer); document.removeEventListener("visibilitychange", visible); };
  }, [resume]);

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
          "radial-gradient(ellipse at 50% 30%, var(--lobby-glow, #edddff88), transparent 65%), var(--color-ink)",
      }}
    >
      <Pulse />

      <div>
        <p className="text-[20px] font-extrabold">{title}</p>
        <p className="mt-1 text-[13px] tabular-nums text-muted">
          {faNum(elapsed)} ثانیه · {faNum(ticket.queue_size)} نفر در صف
        </p>
      </div>

      <p
        key={tipIndex}
        role="status"
        aria-live="polite"
        className="surface-card animate-rise flex min-h-[72px] max-w-xs items-center rounded-card px-4 py-3 text-[13px] leading-7 text-muted"
      >
        {SEARCH_TIPS[tipIndex]}
      </p>

      {ticket.widened && (
        <p className="surface-card animate-rise rounded-card px-4 py-3 text-[13px] leading-relaxed text-muted">
          کمی بیشتر می‌گردیم تا زودتر یکی پیدا شود…
        </p>
      )}
      {ticket.uses_credit && <p className="surface-card max-w-xs rounded-card px-4 py-3 text-[13px] leading-7 text-muted">
        یک اعتبار رزرو شده، هنوز مصرف نشده. بعد از دقیقهٔ اول، اگر هر دو پیام بدهید مصرف می‌شود؛ با لغو یا جستجوی بی‌نتیجه آزاد می‌شود. فقط با بازیکنی مطابق انتخابت مچ می‌شوی.
      </p>}

      <Button
        variant="ghost"
        className="max-w-xs"
        busy={cancelling}
        onClick={async () => {
          setCancelling(true);
          setError(null);
          try {
            await cancel();
          } catch {
            setError("لغو انجام نشد؛ دوباره امتحان کن.");
          } finally {
            setCancelling(false);
          }
        }}
      >
        انصراف
      </Button>
      {error && <p className="text-sm text-bad" role="alert">{error}</p>}
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
