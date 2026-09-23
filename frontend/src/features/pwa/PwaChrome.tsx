import { useState } from "react";

import { isIOS, usePwa } from "@/lib/pwa";

const DISMISS_KEY = "ft.install_dismissed_at";
// Asking again after a week is a reminder; asking every launch is nagging.
const DISMISS_FOR_MS = 7 * 24 * 60 * 60 * 1000;

function recentlyDismissed(): boolean {
  try {
    const at = Number(localStorage.getItem(DISMISS_KEY) ?? 0);
    return Date.now() - at < DISMISS_FOR_MS;
  } catch {
    return false;
  }
}

function rememberDismissal(): void {
  try {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
  } catch {
    /* storage unavailable — the banner simply comes back next time */
  }
}

/** "A new version is ready" — offered, never forced mid-conversation. */
export function UpdateToast() {
  const ready = usePwa((s) => s.updateReady);
  const apply = usePwa((s) => s.applyUpdate);
  if (!ready) return null;

  return (
    <div
      className="animate-rise fixed inset-x-3 z-[70] mx-auto flex max-w-md items-center gap-3 rounded-card border border-line bg-surface-3 px-4 py-3 shadow-[0_18px_40px_-18px_black]"
      style={{ bottom: "calc(76px + env(safe-area-inset-bottom))" }}
      role="status"
    >
      <p className="flex-1 text-[13px] leading-relaxed">نسخه‌ی جدید آماده است.</p>
      <button
        type="button"
        onClick={apply}
        className="press shrink-0 rounded-field bg-brand px-4 py-2 text-[13px] font-bold text-white"
      >
        به‌روزرسانی
      </button>
    </div>
  );
}

/** A thin strip rather than a modal: the app still works, messages just queue. */
export function OfflineBar() {
  const offline = usePwa((s) => s.offline);
  if (!offline) return null;

  return (
    <div
      className="animate-fade-in fixed inset-x-0 top-0 z-[70] bg-warn px-4 text-center text-[12px] font-bold text-ink"
      style={{ paddingTop: "env(safe-area-inset-top)" }}
      role="status"
    >
      <span className="block py-1">آفلاین هستی — پیام‌ها بعد از اتصال ارسال می‌شوند</span>
    </div>
  );
}

/**
 * Offered on the lobby, not on launch.
 *
 * The product spreads by link, so most people arrive in a browser tab. Asking
 * them to install before they have played once gets a reflexive "no"; asking
 * on the home screen, dismissibly, and not again for a week, gets considered.
 *
 * iOS never fires the install event, so it gets the manual steps instead.
 */
export function InstallBanner() {
  const event = usePwa((s) => s.installEvent);
  const installed = usePwa((s) => s.installed);
  const promptInstall = usePwa((s) => s.promptInstall);
  const [hidden, setHidden] = useState(recentlyDismissed);
  const [iosSteps, setIosSteps] = useState(false);

  const ios = isIOS();
  if (installed || hidden || (!event && !ios)) return null;

  function dismiss() {
    rememberDismissal();
    setHidden(true);
  }

  return (
    <section className="surface-card animate-rise relative flex items-start gap-3 rounded-card p-4">
      <img
        src="/icons/icon-192.png"
        alt=""
        className="size-12 shrink-0 rounded-field"
      />
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-extrabold">جرأت رو نصب کن</p>
        <p className="text-[12.5px] leading-relaxed text-muted">
          سریع‌تر باز می‌شه و مثل یه اپ واقعی روی صفحه‌ت می‌مونه.
        </p>

        {iosSteps ? (
          <p className="mt-2 rounded-field bg-surface-3 px-3 py-2 text-[12.5px] leading-relaxed">
            در Safari دکمه‌ی <b>اشتراک‌گذاری</b> ⬆️ را بزن، بعد
            <b> «Add to Home Screen»</b>.
          </p>
        ) : (
          <button
            type="button"
            onClick={() => (ios ? setIosSteps(true) : void promptInstall())}
            className="press mt-2 rounded-field bg-brand px-4 py-2 text-[13px] font-bold text-white"
          >
            نصب
          </button>
        )}
      </div>

      <button
        type="button"
        onClick={dismiss}
        aria-label="بعداً"
        className="press grid size-8 shrink-0 place-items-center rounded-full text-faint"
      >
        ✕
      </button>
    </section>
  );
}
