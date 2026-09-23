import { create } from "zustand";

import { ApiError, fetchMe, getAccessToken, patchMe, signInAsGuest, type Me } from "@/lib/auth";

type Status = "loading" | "ready" | "error";

type SessionState = {
  status: Status;
  user: Me | null;
  error: string | null;
  bootstrap: () => Promise<void>;
  updateProfile: (patch: Partial<Me>) => Promise<void>;
};

export const useSession = create<SessionState>((set) => ({
  status: "loading",
  user: null,
  error: null,

  /**
   * Launch path. A returning user has tokens and we just read the profile; a
   * new one (or someone whose refresh token finally expired) falls through to a
   * silent guest sign-in. Either way nobody is asked to log in.
   */
  async bootstrap() {
    set({ status: "loading", error: null });
    try {
      const user = getAccessToken()
        ? await fetchMe().catch(() => signInAsGuest())
        : await signInAsGuest();
      set({ status: "ready", user });
    } catch (error) {
      set({
        status: "error",
        error:
          error instanceof ApiError
            ? (error.firstMessage ?? "ارتباط با سرور برقرار نشد.")
            : "ارتباط با سرور برقرار نشد.",
      });
    }
  },

  async updateProfile(patch) {
    const user = await patchMe(patch);
    set({ user });
  },
}));
