import { useEffect, useState } from "react";

import { ApiError } from "@/lib/auth";
import * as api from "@/lib/moderationApi";
import type { ReportReason } from "@/lib/types";
import { Button } from "@/ui/Button";

/**
 * Reporting has to be two taps from wherever the offence happened.
 *
 * A form buried in settings gets used by nobody, which leaves the operator
 * with no signal at all and the person being harassed with no recourse. The
 * reasons come from the server so the client can never offer one the API
 * would reject.
 */
export function ReportSheet({
  targetUserId,
  targetName,
  messageId,
  onClose,
}: {
  targetUserId: number;
  targetName: string;
  messageId?: number;
  onClose: () => void;
}) {
  const [reasons, setReasons] = useState<ReportReason[]>([]);
  const [reason, setReason] = useState<string>("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void api
      .listReasons()
      .then((rows) => {
        if (cancelled) return;
        setReasons(rows);
        setReason(rows[0]?.key ?? "");
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.submitReport({
        target_user_id: targetUserId,
        reason,
        note,
        ...(messageId ? { message_id: messageId } : {}),
      });
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiError ? (err.firstMessage ?? "ثبت نشد.") : "ثبت نشد.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="animate-fade-in fixed inset-0 z-[60] flex flex-col justify-end bg-black/65 backdrop-blur-[2px]">
      <button type="button" aria-label="بستن" className="flex-1" onClick={onClose} />

      <div
        className="animate-sheet-in rounded-t-sheet border-t border-line bg-surface px-4 pt-3"
        style={{ paddingBottom: "max(1.5rem, env(safe-area-inset-bottom))" }}
      >
        <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-line" />

        {done ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <span className="grid size-16 place-items-center rounded-full bg-ok/15 text-3xl">
              ✓
            </span>
            <p className="text-[17px] font-extrabold">گزارش ثبت شد</p>
            <p className="text-[14px] leading-relaxed text-muted">
              تیم پشتیبانی بررسی می‌کند. اگر آزارت می‌دهد، می‌توانی او را مسدود
              هم بکنی.
            </p>
            <Button onClick={onClose}>باشه</Button>
          </div>
        ) : (
          <>
            <h2 className="mb-1 text-[17px] font-extrabold">گزارش {targetName}</h2>
            <p className="mb-3 text-[12px] text-faint">
              {messageId ? "درباره‌ی این پیام" : "درباره‌ی این کاربر"}
            </p>

            <div className="mb-3 flex flex-col gap-2">
              {reasons.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => setReason(option.key)}
                  className={`press min-h-12 rounded-field border px-4 text-start text-[14px] transition ${
                    reason === option.key
                      ? "border-brand/60 bg-brand/15 font-bold"
                      : "border-line-soft bg-surface-2"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>

            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              maxLength={500}
              placeholder="توضیح بیشتر (اختیاری)"
              className="surface-raised mb-3 w-full resize-none rounded-field px-4 py-3 text-[14px] outline-none placeholder:text-faint focus:border-brand/60"
            />

            {error && <p className="mb-2 text-sm text-bad">{error}</p>}

            <Button busy={busy} disabled={!reason} onClick={submit}>
              ارسال گزارش
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
