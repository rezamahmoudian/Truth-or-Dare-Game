import { useEffect, useState } from "react";

import { ApiError } from "@/lib/auth";
import * as gameApi from "@/lib/gameApi";
import type { PromptSuggestion } from "@/lib/types";
import { Button } from "@/ui/Button";

const CATEGORIES = [
  ["FRIENDLY", "معمولی"],
  ["FUNNY", "خصوصی"],
  ["DEEP", "عمیق"],
  ["BOLD", "جسورانه"],
] as const;

const STATUS_LABEL: Record<PromptSuggestion["review_status"], string> = {
  PENDING: "در انتظار بررسی",
  APPROVED: "تأیید شده و در بازی",
  REJECTED: "رد شده",
};

const STATUS_COLOR: Record<PromptSuggestion["review_status"], string> = {
  PENDING: "text-warn",
  APPROVED: "text-ok",
  REJECTED: "text-bad",
};

export function PromptSuggestionCard() {
  const [suggestions, setSuggestions] = useState<PromptSuggestion[]>([]);
  const [text, setText] = useState("");
  const [type, setType] = useState<"TRUTH" | "DARE">("TRUTH");
  const [category, setCategory] = useState("FRIENDLY");
  const [intensity, setIntensity] = useState(1);
  const [minPlayers, setMinPlayers] = useState(2);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    void gameApi.listPromptSuggestions().then(setSuggestions).catch(() => undefined);
  }, []);

  async function submit() {
    setBusy(true);
    setError(null);
    setSent(false);
    try {
      const suggestion = await gameApi.suggestPrompt({
        text,
        type,
        category,
        intensity,
        min_players: minPlayers,
      });
      setSuggestions((rows) => [suggestion, ...rows]);
      setText("");
      setSent(true);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? (err.firstMessage ?? "پیشنهاد ثبت نشد.")
          : "پیشنهاد ثبت نشد.",
      );
    } finally {
      setBusy(false);
    }
  }

  const inputClass =
    "surface-raised min-h-11 w-full rounded-field px-3 text-[13px] outline-none placeholder:text-faint focus:border-brand/60";

  return (
    <section className="surface-card rounded-card p-4">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between text-start"
      >
        <span className="text-[15px] font-bold">💡 پیشنهاد سؤال</span>
        <span className="text-faint">{open ? "−" : "+"}</span>
      </button>
      <p className="mt-1 text-[12.5px] leading-relaxed text-muted">
        سؤال جالبی داری؟ بفرست تا بعد از بررسی به بازی اضافه‌اش کنیم.
      </p>

      {open && (
        <div className="mt-3 flex flex-col gap-3">
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="مثلاً: عجیب‌ترین چیزی که در گوشیت داری چیه؟"
            maxLength={500}
            rows={3}
            className={`${inputClass} resize-none py-2`}
          />
          <div className="grid grid-cols-2 gap-2">
            <select value={type} onChange={(event) => setType(event.target.value as "TRUTH" | "DARE")} className={inputClass}>
              <option value="TRUTH">حقیقت</option>
              <option value="DARE">جرئت</option>
            </select>
            <select value={category} onChange={(event) => setCategory(event.target.value)} className={inputClass}>
              {CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <select value={intensity} onChange={(event) => setIntensity(Number(event.target.value))} className={inputClass}>
              <option value={1}>سطح ۱ · امن</option>
              <option value={2}>سطح ۲ · شخصی</option>
              <option value={3}>سطح ۳ · جسورانه</option>
            </select>
            <select value={minPlayers} onChange={(event) => setMinPlayers(Number(event.target.value))} className={inputClass}>
              {[2, 3, 4, 5, 6, 7, 8].map((value) => <option key={value} value={value}>{value} نفر به بالا</option>)}
            </select>
          </div>

          {error && <p className="text-[12px] text-bad">{error}</p>}
          {sent && <p className="text-[12px] text-ok">پیشنهادت برای بررسی ارسال شد.</p>}
          <Button busy={busy} disabled={text.trim().length < 8} onClick={submit}>
            ارسال پیشنهاد
          </Button>

          {suggestions.length > 0 && (
            <div className="mt-2 border-t border-line-soft pt-3">
              <p className="mb-2 text-[12px] font-bold text-muted">پیشنهادهای من</p>
              <div className="flex flex-col gap-2">
                {suggestions.map((suggestion) => (
                  <div key={suggestion.id} className="rounded-field bg-surface-2 px-3 py-2">
                    <p className="text-[13px] leading-relaxed">{suggestion.text}</p>
                    <p className={`mt-1 text-[11px] ${STATUS_COLOR[suggestion.review_status]}`}>
                      {STATUS_LABEL[suggestion.review_status]}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
