import { create } from "zustand";

import { authFetch } from "@/lib/auth";
import type { GameInvitation, InvitationLists } from "@/lib/types";
import { socket } from "@/lib/ws";

type InvitationStore = {
  lists: InvitationLists;
  notice: GameInvitation | null;
  init: () => void;
  load: () => Promise<void>;
  send: (userId: number) => Promise<GameInvitation>;
  respond: (id: number, action: "accept" | "decline" | "cancel") => Promise<GameInvitation>;
  dismiss: () => void;
};
let wired = false;
export const useInvitations = create<InvitationStore>((set, get) => ({
  lists: { incoming: [], outgoing: [], ready: [] },
  notice: null,
  init() {
    if (wired) return;
    wired = true;
    socket.onEvent((type, data) => {
      if (type === "conv.updated" && data.status === "CLOSED") { void get().load().catch(() => undefined); return; }
      if (type !== "game.invitation") return;
      const row = data as unknown as GameInvitation;
      if ((row.status === "PENDING" && row.direction === "incoming") || row.status === "ACCEPTED") set({ notice: row });
      else if (get().notice?.id === row.id) set({ notice: null });
      void get().load().catch(() => undefined);
    });
    socket.onResume(() => { void get().load().catch(() => undefined); });
  },
  async load() { set({ lists: await authFetch<InvitationLists>("/game-invitations/") }); },
  async send(userId) {
    const row = await authFetch<GameInvitation>(`/people/${userId}/invite/`, { method: "POST" });
    await get().load();
    return row;
  },
  async respond(id, action) {
    const row = await authFetch<GameInvitation>(`/game-invitations/${id}/${action}/`, { method: "POST" });
    set({ notice: null });
    await get().load();
    return row;
  },
  dismiss() { set({ notice: null }); },
}));
