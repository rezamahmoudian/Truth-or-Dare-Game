import { authFetch } from "@/lib/auth";
import type { Message, Person, ReportReason } from "@/lib/types";

export const listReasons = () => authFetch<ReportReason[]>("/reports/reasons/");

export const submitReport = (body: {
  target_user_id: number;
  reason: string;
  note?: string;
  message_id?: number;
}) =>
  authFetch<{ detail: string }>("/reports/", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const listBlocked = () => authFetch<Person[]>("/blocks/");

export const blockUser = (userId: number) =>
  authFetch<null>(`/blocks/${userId}/`, { method: "POST" });

export const unblockUser = (userId: number) =>
  authFetch<null>(`/blocks/${userId}/`, { method: "DELETE" });

export const deleteMessage = (messageId: number) =>
  authFetch<Message>(`/messages/${messageId}/`, { method: "DELETE" });
