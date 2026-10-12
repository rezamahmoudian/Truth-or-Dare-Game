import { authFetch } from "@/lib/auth";
import type { GameState, PromptSuggestion } from "@/lib/types";

export const fetchGameState = (conversationId: string) =>
  authFetch<GameState>(`/conversations/${conversationId}/game/`);

export const startGame = (
  conversationId: string,
  options: { category?: string; max_intensity?: number; play_mode?: "CLASSIC" | "DEEP_TALK"; replace_session_id?: number } = {},
) =>
  authFetch<GameState>(`/conversations/${conversationId}/game/`, {
    method: "POST",
    body: JSON.stringify(options),
  });

export const stopGame = (conversationId: string) =>
  authFetch<null>(`/conversations/${conversationId}/game/`, { method: "DELETE" });

export const listPromptSuggestions = () =>
  authFetch<PromptSuggestion[]>("/game/prompts/suggestions/");

export const suggestPrompt = (body: {
  text: string;
  type: "TRUTH" | "DARE";
  category: string;
  intensity: number;
  min_players: number;
}) =>
  authFetch<PromptSuggestion>("/game/prompts/suggestions/", {
    method: "POST",
    body: JSON.stringify(body),
  });
