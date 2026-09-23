import { authFetch } from "@/lib/auth";
import type { GameState } from "@/lib/types";

export const fetchGameState = (conversationId: string) =>
  authFetch<GameState>(`/conversations/${conversationId}/game/`);

export const startGame = (
  conversationId: string,
  options: { category?: string; max_intensity?: number; rounds?: number } = {},
) =>
  authFetch<GameState>(`/conversations/${conversationId}/game/`, {
    method: "POST",
    body: JSON.stringify(options),
  });

export const stopGame = (conversationId: string) =>
  authFetch<null>(`/conversations/${conversationId}/game/`, { method: "DELETE" });
