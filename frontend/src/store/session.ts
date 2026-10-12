import { create } from "zustand";

import { ApiError, clearTokens, fetchMe, hasSessionTokens, patchMe, signIn, registerAccount, signInAsGuest, type Me } from "@/lib/auth";

type Status = "loading" | "ready" | "anonymous" | "error";

type SessionState = {
  status: Status;
  user: Me | null;
  error: string | null;
  bootstrap: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, confirm: string) => Promise<void>;
  resumeGuest: () => Promise<void>;
  updateProfile: (patch: Partial<Me>) => Promise<void>;
};

export const useSession = create<SessionState>((set) => ({
  status: "loading",
  user: null,
  error: null,

  async bootstrap() {
    set({ status: "loading", error: null });
    if (!hasSessionTokens()) { set({ status: "anonymous", user: null }); return; }
    try {
      const user = await fetchMe();
      set({ status: "ready", user });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearTokens();
        set({ status: "anonymous", user: null });
        return;
      }
      set({ status: "error", error: "ارتباط با سرور برقرار نشد؛ دوباره تلاش کن." });
    }
  },

  async login(username, password) {
    const user = await signIn(username, password);
    set({ user, status: "ready", error: null });
  },
  async register(username, password, confirm) {
    const user = await registerAccount(username, password, confirm);
    set({ user, status: "ready", error: null });
  },
  async resumeGuest() {
    const user = await signInAsGuest();
    set({ user, status: "ready", error: null });
  },

  async updateProfile(patch) {
    const user = await patchMe(patch);
    set({ user });
  },
}));
