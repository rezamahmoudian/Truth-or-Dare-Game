import { create } from "zustand";

import * as api from "@/lib/gameApi";
import type { GameState } from "@/lib/types";
import { socket } from "@/lib/ws";

type GameStore = {
  byConversation: Record<string, GameState>;
  choiceErrors: Record<number, string>;
  init: () => void;
  load: (conversationId: string) => Promise<void>;
  start: (conversationId: string, maxIntensity: number) => Promise<void>;
  stop: (conversationId: string) => Promise<void>;
  choose: (turnId: number, choice: "TRUTH" | "DARE") => void;
  answer: (turnId: number, body: string) => void;
  skip: (turnId: number) => void;
  confirm: (turnId: number) => void;
  forceNext: (turnId: number) => void;
};

let wired = false;

export const useGame = create<GameStore>((set, get) => ({
  byConversation: {},
  choiceErrors: {},

  init() {
    if (wired) return;
    wired = true;

    socket.onEvent((type, data) => {
      if (type === "error" && typeof data.client_id === "string" && data.client_id.startsWith("game-choice-")) {
        const turnId = Number(data.client_id.slice("game-choice-".length));
        if (Number.isInteger(turnId) && typeof data.message === "string") {
          set((store) => ({ choiceErrors: { ...store.choiceErrors, [turnId]: data.message as string } }));
        }
        return;
      }
      if (type !== "game.state") return;
      // A whole snapshot, so it simply replaces what was there. No ordering to
      // get right, nothing to reconcile, and a snapshot missed during a
      // disconnect is irrelevant once the next one lands.
      const state = data as unknown as GameState;
      const session = state.session;
      if (!session) return;
      set((store) => ({
        byConversation: { ...store.byConversation, [session.conversation_id]: state },
      }));
    });

    // The socket carries transitions; a reconnect needs the current truth.
    socket.onResume(() => {
      for (const conversationId of Object.keys(get().byConversation)) {
        void get().load(conversationId);
      }
    });
  },

  async load(conversationId) {
    const state = await api.fetchGameState(conversationId);
    set((store) => ({
      byConversation: { ...store.byConversation, [conversationId]: state },
    }));
  },

  async start(conversationId, maxIntensity) {
    const state = await api.startGame(conversationId, {
      max_intensity: maxIntensity,
    });
    set((store) => ({
      byConversation: { ...store.byConversation, [conversationId]: state },
    }));
  },

  async stop(conversationId) {
    await api.stopGame(conversationId);
    // Not blanked locally. The server publishes the ended session over the
    // socket, so inventing `session: null` here both contradicted it and
    // raced it — whichever landed last won. Re-reading asks for the truth and
    // also covers the case where the socket happens to be down.
    await get().load(conversationId);
  },

  choose(turnId, choice) {
    set((store) => ({ choiceErrors: { ...store.choiceErrors, [turnId]: "" } }));
    socket.send("game.choose", { turn_id: turnId, choice, client_id: `game-choice-${turnId}` });
  },

  answer(turnId, body) {
    socket.send("game.answer", { turn_id: turnId, body });
  },

  skip(turnId) {
    socket.send("game.skip", { turn_id: turnId });
  },

  confirm(turnId) {
    socket.send("game.confirm", { turn_id: turnId });
  },

  forceNext(turnId) {
    socket.send("game.force_next", { turn_id: turnId });
  },
}));

export const EMPTY_GAME: GameState = { session: null, turn: null };
