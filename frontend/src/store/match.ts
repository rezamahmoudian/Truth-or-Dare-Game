import { create } from "zustand";

import * as api from "@/lib/matchApi";
import type { MatchMode, MatchTicket, Person } from "@/lib/types";
import { socket } from "@/lib/ws";

type MatchStore = {
  modes: MatchMode[];
  onlineCount: number;
  activePeople: Person[];
  loaded: boolean;
  ticket: MatchTicket | null;
  /** Set when a match lands; the screen navigates and clears it. */
  matchedConversationId: string | null;
  expired: { suggestedMode: string } | null;
  error: string | null;

  init: () => void;
  loadLobby: () => Promise<void>;
  loadModes: () => Promise<void>;
  resume: () => Promise<void>;
  enqueue: (mode: string) => Promise<void>;
  cancel: () => Promise<void>;
  clearMatch: () => void;
  dismissExpired: () => void;
};

let wired = false;

export const useMatch = create<MatchStore>((set, get) => ({
  modes: [],
  onlineCount: 0,
  activePeople: [],
  loaded: false,
  ticket: null,
  matchedConversationId: null,
  expired: null,
  error: null,

  init() {
    if (wired) return;
    wired = true;

    socket.onEvent((type, data) => {
      switch (type) {
        case "mm.queued":
        case "mm.searching":
          set({ ticket: data as unknown as MatchTicket, expired: null });
          break;

        case "mm.matched":
          set({
            ticket: null,
            matchedConversationId: String(data.conversation_id),
          });
          break;

        case "mm.expired":
          set({
            ticket: null,
            expired: { suggestedMode: String(data.suggested_mode ?? "group") },
          });
          break;

        case "mm.cancelled":
          set({ ticket: null });
          break;
      }
    });

    // A reconnect must not strand someone on a waiting screen for a queue they
    // are no longer in — or drop them off one they still are. The lobby's
    // queue health and presence row are stale by then too.
    socket.onResume(() => {
      void get().resume();
      void get().loadLobby();
    });
  },

  async loadLobby() {
    const lobby = await api.getLobby();
    set({
      modes: lobby.modes,
      onlineCount: lobby.online_count,
      activePeople: lobby.active_people,
      loaded: true,
    });
  },

  async loadModes() {
    set({ modes: await api.listModes(), loaded: true });
  },

  async resume() {
    const status = await api.getMatchStatus();
    set({ ticket: "id" in status && status.state === "QUEUED" ? status : null });
  },

  async enqueue(mode) {
    set({ error: null, expired: null });
    const ticket = await api.enqueue(mode);
    set({ ticket });
  },

  async cancel() {
    await api.cancelMatch();
    set({ ticket: null });
  },

  clearMatch() {
    set({ matchedConversationId: null });
  },

  dismissExpired() {
    set({ expired: null });
  },
}));
