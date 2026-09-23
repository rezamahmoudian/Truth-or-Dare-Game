import { useState } from "react";

import { ReportSheet } from "@/features/moderation/ReportSheet";
import * as api from "@/lib/moderationApi";
import { useSocial } from "@/store/social";

/**
 * Report and block, one tap from a person's row.
 *
 * Blocking asks first because it is not only "stop seeing them": it deletes
 * the friendship, and someone tapping it by accident next to a friend button
 * would lose a connection they wanted.
 */
export function PersonMenu({
  userId,
  displayName,
  onBlocked,
}: {
  userId: number;
  displayName: string;
  onBlocked?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [confirmBlock, setConfirmBlock] = useState(false);
  const setRelation = useSocial((s) => s.setRelation);
  const loadFriends = useSocial((s) => s.load);

  async function block() {
    await api.blockUser(userId);
    setRelation(userId, "BLOCKED");
    await loadFriends();
    setOpen(false);
    setConfirmBlock(false);
    onBlocked?.();
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`گزینه‌های ${displayName}`}
        className="press grid size-9 shrink-0 place-items-center rounded-full text-lg text-faint"
      >
        ⋯
      </button>

      {open && (
        <div className="animate-fade-in fixed inset-0 z-[55] flex flex-col justify-end bg-black/65 backdrop-blur-[2px]">
          <button
            type="button"
            aria-label="بستن"
            className="flex-1"
            onClick={() => {
              setOpen(false);
              setConfirmBlock(false);
            }}
          />

          <div
            className="animate-sheet-in rounded-t-sheet border-t border-line bg-surface px-4 pt-3"
            style={{ paddingBottom: "max(1.5rem, env(safe-area-inset-bottom))" }}
          >
            <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-line" />
            <p className="mb-3 px-1 text-[15px] font-bold">{displayName}</p>

            <button
              type="button"
              onClick={() => {
                setOpen(false);
                setReporting(true);
              }}
              className="press surface-raised min-h-12 w-full rounded-field px-4 text-start text-[14px]"
            >
              🚩 گزارش تخلف
            </button>

            {!confirmBlock ? (
              <button
                type="button"
                onClick={() => setConfirmBlock(true)}
                className="press surface-raised mt-2 min-h-12 w-full rounded-field px-4 text-start text-[14px] text-bad"
              >
                🚫 مسدود کردن
              </button>
            ) : (
              <div className="animate-rise surface-raised mt-2 rounded-field p-3">
                <p className="mb-3 text-[12px] leading-relaxed text-muted">
                  دیگر نمی‌توانید به هم پیام بدهید و در بازی‌ها با هم قرار
                  نمی‌گیرید. اگر دوست هستید، دوستی هم حذف می‌شود.
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => void block()}
                    className="press min-h-11 flex-1 rounded-field bg-bad text-[14px] font-bold text-white"
                  >
                    مسدود کن
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmBlock(false)}
                    className="press min-h-11 flex-1 rounded-field bg-surface text-[14px] text-muted"
                  >
                    بی‌خیال
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {reporting && (
        <ReportSheet
          targetUserId={userId}
          targetName={displayName}
          onClose={() => setReporting(false)}
        />
      )}
    </>
  );
}
