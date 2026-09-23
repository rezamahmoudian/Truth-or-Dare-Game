import { registerSW } from "virtual:pwa-register";
import { create } from "zustand";

/**
 * Service worker lifecycle and install state.
 *
 * Updates are offered, never forced. A worker that reloaded the page on its
 * own would do it in the middle of someone typing a reply; instead the app
 * learns a new version is waiting and asks.
 */

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

type PwaState = {
  updateReady: boolean;
  offline: boolean;
  /** Chrome/Android hands us this; iOS never does. */
  installEvent: BeforeInstallPromptEvent | null;
  installed: boolean;
  applyUpdate: () => void;
  promptInstall: () => Promise<boolean>;
};

let updateSW: ((reload?: boolean) => Promise<void>) | null = null;

export const usePwa = create<PwaState>((set, get) => ({
  updateReady: false,
  offline: typeof navigator !== "undefined" ? !navigator.onLine : false,
  installEvent: null,
  installed: isStandalone(),

  applyUpdate() {
    void updateSW?.(true);
  },

  async promptInstall() {
    const event = get().installEvent;
    if (!event) return false;
    await event.prompt();
    const { outcome } = await event.userChoice;
    // The event is single-use whatever the answer.
    set({ installEvent: null, installed: outcome === "accepted" });
    return outcome === "accepted";
  },
}));

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    // iOS Safari's own flag, which predates the media query.
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

export function isIOS(): boolean {
  const ua = navigator.userAgent;
  // iPadOS reports itself as a Mac, so touch support is the tell.
  return /iPhone|iPad|iPod/.test(ua) || (ua.includes("Mac") && "ontouchend" in document);
}

export function startPwa(): void {
  if (import.meta.env.DEV) return;

  updateSW = registerSW({
    onNeedRefresh() {
      usePwa.setState({ updateReady: true });
    },
  });

  window.addEventListener("beforeinstallprompt", (event) => {
    // Hold on to it rather than letting the browser show its own mini-bar,
    // which appears at a moment of its choosing and not ours.
    event.preventDefault();
    usePwa.setState({ installEvent: event as BeforeInstallPromptEvent });
  });

  window.addEventListener("appinstalled", () => {
    usePwa.setState({ installed: true, installEvent: null });
  });

  window.addEventListener("online", () => usePwa.setState({ offline: false }));
  window.addEventListener("offline", () => usePwa.setState({ offline: true }));
}
