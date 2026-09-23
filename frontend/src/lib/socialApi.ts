import { authFetch } from "@/lib/auth";
import type { FriendLists, Person } from "@/lib/types";

export const listFriends = () => authFetch<FriendLists>("/friends/");

export const getPerson = (userId: number) =>
  authFetch<Person>(`/people/${userId}/`);

export const sendFriendRequest = (userId: number) =>
  authFetch<Person>(`/friends/${userId}/`, { method: "POST" });

export const acceptFriend = (userId: number) =>
  authFetch<{ conversation_id: string; user: Person }>(
    `/friends/${userId}/accept/`,
    { method: "POST" },
  );

export const declineFriend = (userId: number) =>
  authFetch<null>(`/friends/${userId}/decline/`, { method: "POST" });

/** Cancels a sent request or removes a friend — the server knows which. */
export const removeFriend = (userId: number) =>
  authFetch<null>(`/friends/${userId}/`, { method: "DELETE" });
