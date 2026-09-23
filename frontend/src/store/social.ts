import { create } from "zustand";

import * as api from "@/lib/socialApi";
import type { FriendLists, Relation } from "@/lib/types";
import { socket } from "@/lib/ws";

const EMPTY: FriendLists = { friends: [], incoming: [], outgoing: [] };

type SocialStore = {
  lists: FriendLists;
  /** Relation per user id, so buttons on a profile render without a fetch. */
  relations: Record<number, Relation>;

  init: () => void;
  load: () => Promise<void>;
  request: (userId: number) => Promise<void>;
  accept: (userId: number) => Promise<string>;
  decline: (userId: number) => Promise<void>;
  remove: (userId: number) => Promise<void>;
  setRelation: (userId: number, relation: Relation) => void;
  pendingCount: () => number;
};

let wired = false;

export const useSocial = create<SocialStore>((set, get) => ({
  lists: EMPTY,
  relations: {},

  init() {
    if (wired) return;
    wired = true;

    socket.onEvent((type) => {
      // Both events change what the friends tab and every profile button
      // should show, so the lists are simply refetched rather than patched —
      // they are small, and a wrong button here is worse than a round trip.
      if (type === "friend.request" || type === "friend.accepted") {
        void get().load();
      }
    });

    socket.onResume(() => {
      void get().load();
    });
  },

  async load() {
    const lists = await api.listFriends();
    const relations: Record<number, Relation> = {};
    for (const friend of lists.friends) relations[friend.id] = "FRIENDS";
    for (const row of lists.incoming) relations[row.user.id] = "INCOMING";
    for (const row of lists.outgoing) relations[row.user.id] = "OUTGOING";
    set({ lists, relations });
  },

  async request(userId) {
    const person = await api.sendFriendRequest(userId);
    get().setRelation(userId, person.relation ?? "OUTGOING");
    await get().load();
  },

  async accept(userId) {
    const result = await api.acceptFriend(userId);
    get().setRelation(userId, "FRIENDS");
    await get().load();
    return result.conversation_id;
  },

  async decline(userId) {
    await api.declineFriend(userId);
    get().setRelation(userId, "NONE");
    await get().load();
  },

  async remove(userId) {
    await api.removeFriend(userId);
    get().setRelation(userId, "NONE");
    await get().load();
  },

  setRelation(userId, relation) {
    set((state) => ({ relations: { ...state.relations, [userId]: relation } }));
  },

  pendingCount() {
    return get().lists.incoming.length;
  },
}));
