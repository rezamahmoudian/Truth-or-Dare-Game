import { create } from "zustand";

import * as api from "@/lib/chatApi";
import type { AnyMessage, Conversation, Message } from "@/lib/types";
import { isPending } from "@/lib/types";
import { socket, type SocketStatus } from "@/lib/ws";

const TYPING_TTL_MS = 4000;

function newClientId(): string {
  return `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function lastServerId(messages: AnyMessage[] | undefined): number {
  if (!messages) return 0;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message && !isPending(message)) return message.id;
  }
  return 0;
}

/**
 * Merge a server message into a conversation.
 *
 * Three cases, and all three happen routinely: it replaces an optimistic bubble
 * of ours (matched by client_id), it is one we already hold (a retry or a
 * duplicate delivery), or it is new.
 */
function mergeMessage(existing: AnyMessage[], incoming: Message): AnyMessage[] {
  const byClientId = incoming.client_id
    ? existing.findIndex((m) => m.client_id === incoming.client_id)
    : -1;
  if (byClientId >= 0) {
    const next = [...existing];
    next[byClientId] = incoming;
    return next;
  }

  if (existing.some((m) => !isPending(m) && m.id === incoming.id)) return existing;

  const next = [...existing, incoming];
  next.sort((a, b) => {
    if (isPending(a)) return 1;
    if (isPending(b)) return -1;
    return a.id - b.id;
  });
  return next;
}

type ChatState = {
  status: SocketStatus;
  conversations: Conversation[];
  messages: Record<string, AnyMessage[]>;
  typing: Record<string, Record<number, number>>;
  online: Record<string, number[]>;
  activeId: string | null;
  loadingHistory: boolean;

  init: () => void;
  loadConversations: () => Promise<void>;
  openConversation: (id: string) => Promise<void>;
  closeConversation: () => void;
  loadOlder: (id: string) => Promise<void>;
  sendMessage: (id: string, body: string) => void;
  retryMessage: (id: string, clientId: string) => void;
  setTyping: (id: string, isTyping: boolean) => void;
  toggleReaction: (id: string, messageId: number, emoji: string, has: boolean) => void;
  markRead: (id: string) => void;
  deleteConversation: (id: string) => Promise<void>;
  totalUnread: () => number;
};

let wired = false;

export const useChat = create<ChatState>((set, get) => ({
  status: "idle",
  conversations: [],
  messages: {},
  typing: {},
  online: {},
  activeId: null,
  loadingHistory: false,

  init() {
    if (wired) return;
    wired = true;

    socket.onStatus((status) => set({ status }));

    socket.onEvent((type, data) => {
      switch (type) {
        case "chat.message": {
          const message = data as unknown as Message;
          const conversationId = message.conversation_id;
          set((state) => ({
            messages: {
              ...state.messages,
              [conversationId]: mergeMessage(
                state.messages[conversationId] ?? [],
                message,
              ),
            },
          }));
          // Reading a conversation you are looking at should not leave it
          // unread the moment a message lands.
          if (get().activeId === conversationId) get().markRead(conversationId);
          break;
        }

        case "conv.updated": {
          const incoming = data as unknown as Conversation;
          set((state) => {
            const existing = state.conversations.find((c) => c.id === incoming.id);
            const merged: Conversation = {
              ...incoming,
              // The socket payload carries no participants or per-user unread;
              // keep what the list already knows rather than blanking it.
              participants: existing?.participants ?? incoming.participants,
              unread_count:
                state.activeId === incoming.id
                  ? 0
                  : (existing?.unread_count ?? 0) + 1,
            };
            const rest = state.conversations.filter((c) => c.id !== incoming.id);
            return { conversations: [merged, ...rest] };
          });
          break;
        }

        case "chat.typing": {
          const { conversation_id, user_id, is_typing } = data as {
            conversation_id: string;
            user_id: number;
            is_typing: boolean;
          };
          set((state) => {
            const forConversation = { ...(state.typing[conversation_id] ?? {}) };
            if (is_typing) forConversation[user_id] = Date.now();
            else delete forConversation[user_id];
            return {
              typing: { ...state.typing, [conversation_id]: forConversation },
            };
          });
          break;
        }

        case "presence": {
          const { conversation_id, online_user_ids } = data as {
            conversation_id: string;
            online_user_ids: number[];
          };
          set((state) => ({
            online: { ...state.online, [conversation_id]: online_user_ids },
          }));
          break;
        }

        case "chat.reaction": {
          const { conversation_id, message_id, user_id, emoji, op } = data as {
            conversation_id: string;
            message_id: number;
            user_id: number;
            emoji: string;
            op: "add" | "remove";
          };
          set((state) => {
            const list = state.messages[conversation_id];
            if (!list) return {};
            return {
              messages: {
                ...state.messages,
                [conversation_id]: list.map((message) => {
                  if (isPending(message) || message.id !== message_id) return message;
                  const users = new Set(message.reactions[emoji] ?? []);
                  if (op === "add") users.add(user_id);
                  else users.delete(user_id);
                  const reactions = { ...message.reactions };
                  if (users.size) reactions[emoji] = [...users];
                  else delete reactions[emoji];
                  return { ...message, reactions };
                }),
              },
            };
          });
          break;
        }

        case "error": {
          const { code, client_id } = data as { code: string; client_id?: string };
          if (!client_id) break;
          // Mark the optimistic bubble failed rather than dropping it, so the
          // person can see what did not send and retry it.
          set((state) => {
            const entries = Object.entries(state.messages).map(([id, list]) => [
              id,
              list.map((message) =>
                isPending(message) && message.client_id === client_id
                  ? { ...message, failed: true, meta: { ...message.meta, error: code } }
                  : message,
              ),
            ]);
            return { messages: Object.fromEntries(entries) as ChatState["messages"] };
          });
          break;
        }
      }
    });

    // After a reconnect, ask for everything that happened while the socket was
    // down. The server hands back only ids greater than the last one held, so
    // this is cheap even after a long outage.
    socket.onResume(() => {
      void get().loadConversations();
      const activeId = get().activeId;
      if (!activeId) return;
      void api
        .fetchMessages(activeId, { after: lastServerId(get().messages[activeId]) })
        .then((missed) => {
          if (!missed.length) return;
          set((state) => ({
            messages: {
              ...state.messages,
              [activeId]: missed.reduce(mergeMessage, state.messages[activeId] ?? []),
            },
          }));
        });
    });

    socket.connect();
  },

  async loadConversations() {
    const conversations = await api.listConversations();
    set({ conversations });
  },

  async openConversation(id) {
    set({ activeId: id, loadingHistory: true });
    socket.subscribe(id);
    try {
      const history = await api.fetchMessages(id, { limit: 50 });
      set((state) => ({
        messages: { ...state.messages, [id]: history },
        loadingHistory: false,
      }));
      get().markRead(id);
    } catch {
      set({ loadingHistory: false });
    }
  },

  closeConversation() {
    const id = get().activeId;
    if (id) socket.unsubscribe(id);
    set({ activeId: null });
  },

  async loadOlder(id) {
    const list = get().messages[id] ?? [];
    const first = list.find((message) => !isPending(message));
    if (!first || isPending(first)) return;

    const older = await api.fetchMessages(id, { before: first.id, limit: 50 });
    if (!older.length) return;
    set((state) => ({
      messages: { ...state.messages, [id]: [...older, ...(state.messages[id] ?? [])] },
    }));
  },

  sendMessage(id, body) {
    const text = body.trim();
    if (!text) return;

    const clientId = newClientId();
    const optimistic: AnyMessage = {
      id: -Date.now(),
      conversation_id: id,
      type: "TEXT",
      body: text,
      sender: null,
      reply_to_id: null,
      client_id: clientId,
      meta: {},
      created_at: new Date().toISOString(),
      is_deleted: false,
      reactions: {},
      pending: true,
    };

    set((state) => ({
      messages: { ...state.messages, [id]: [...(state.messages[id] ?? []), optimistic] },
    }));

    socket.send("chat.send", {
      conversation_id: id,
      client_id: clientId,
      body: text,
    });
  },

  retryMessage(id, clientId) {
    const message = (get().messages[id] ?? []).find((m) => m.client_id === clientId);
    if (!message) return;
    set((state) => ({
      messages: {
        ...state.messages,
        [id]: (state.messages[id] ?? []).map((m) =>
          m.client_id === clientId ? { ...m, failed: false } : m,
        ),
      },
    }));
    // Same client_id: if the original did reach the server, this is recognised
    // as a duplicate instead of posting the message twice.
    socket.send("chat.send", {
      conversation_id: id,
      client_id: clientId,
      body: message.body,
    });
  },

  setTyping(id, isTyping) {
    socket.send("chat.typing", { conversation_id: id, is_typing: isTyping });
  },

  toggleReaction(id, messageId, emoji, has) {
    socket.send("chat.react", {
      conversation_id: id,
      message_id: messageId,
      emoji,
      op: has ? "remove" : "add",
    });
  },

  markRead(id) {
    const upTo = lastServerId(get().messages[id]);
    if (!upTo) return;
    socket.send("chat.read", { conversation_id: id, up_to_message_id: upTo });
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === id ? { ...c, unread_count: 0 } : c,
      ),
    }));
  },

  async deleteConversation(id) {
    await api.deleteConversation(id);
    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== id),
      messages: Object.fromEntries(
        Object.entries(state.messages).filter(([key]) => key !== id),
      ),
      activeId: state.activeId === id ? null : state.activeId,
    }));
  },

  totalUnread() {
    return get().conversations.reduce((sum, c) => sum + c.unread_count, 0);
  },
}));

export const typingUserIds = (
  typing: Record<number, number> | undefined,
  selfId: number,
): number[] => {
  if (!typing) return [];
  const cutoff = Date.now() - TYPING_TTL_MS;
  return Object.entries(typing)
    .filter(([userId, at]) => at > cutoff && Number(userId) !== selfId)
    .map(([userId]) => Number(userId));
};
