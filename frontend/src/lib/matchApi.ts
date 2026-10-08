import { authFetch } from "@/lib/auth";
import type { Lobby, MatchMode, MatchTicket } from "@/lib/types";

/** Everything the home screen needs, in one request. */
export const getLobby = () => authFetch<Lobby>("/lobby/");

export const listModes = () => authFetch<MatchMode[]>("/match-modes/");

export const getMatchStatus = () =>
  authFetch<MatchTicket | { state: "IDLE" }>("/match/");

export const enqueue = (mode: string, aiConsent = false) =>
  authFetch<MatchTicket>("/match/", {
    method: "POST",
    body: JSON.stringify({ mode, ai_consent: aiConsent }),
  });

export const cancelMatch = () => authFetch<null>("/match/", { method: "DELETE" });
