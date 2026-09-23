import { authFetch } from "@/lib/auth";
import type { Conversation, Message } from "@/lib/types";

export const listConversations = () => authFetch<Conversation[]>("/conversations/");

export const getConversation = (id: string) =>
  authFetch<Conversation>(`/conversations/${id}/`);

export const createRoom = (maxPlayers = 8) =>
  authFetch<Conversation>("/conversations/rooms/", {
    method: "POST",
    body: JSON.stringify({ max_players: maxPlayers }),
  });

export const joinRoom = (code: string) =>
  authFetch<Conversation>("/conversations/join/", {
    method: "POST",
    body: JSON.stringify({ code }),
  });

/** Owner-only. A room stays open until someone deliberately ends it. */
export const closeRoom = (id: string) =>
  authFetch<Conversation>(`/conversations/${id}/close/`, { method: "POST" });

/** Removes it from *your* list only; the other side keeps everything. */
export const deleteConversation = (id: string) =>
  authFetch<null>(`/conversations/${id}/delete/`, { method: "DELETE" });

export const leaveConversation = (id: string) =>
  authFetch<null>(`/conversations/${id}/leave/`, { method: "POST" });

/**
 * `after` is the reconnect path — everything newer than the last id held
 * locally. `before` pages backwards through history.
 */
export const fetchMessages = (
  id: string,
  params: { before?: number; after?: number; limit?: number } = {},
) => {
  const query = new URLSearchParams();
  if (params.before !== undefined) query.set("before", String(params.before));
  if (params.after !== undefined) query.set("after", String(params.after));
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query}` : "";
  return authFetch<Message[]>(`/conversations/${id}/messages/${suffix}`);
};
