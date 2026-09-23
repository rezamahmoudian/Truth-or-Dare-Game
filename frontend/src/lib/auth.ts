import { getDeviceToken } from "@/lib/deviceToken";

const ACCESS_KEY = "ft.access";
const REFRESH_KEY = "ft.refresh";

type Tokens = { access: string; refresh: string };

const memory: Partial<Tokens> = {};

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return key === ACCESS_KEY ? (memory.access ?? null) : (memory.refresh ?? null);
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    if (key === ACCESS_KEY) memory.access = value;
    else memory.refresh = value;
  }
}

export function setTokens(tokens: Tokens): void {
  write(ACCESS_KEY, tokens.access);
  write(REFRESH_KEY, tokens.refresh);
}

export function clearTokens(): void {
  try {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  } catch {
    /* nothing persisted to clear */
  }
  delete memory.access;
  delete memory.refresh;
}

export const getAccessToken = () => read(ACCESS_KEY);

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {
    super(`API ${status}`);
  }

  /** First validation message, ready to show — DRF returns {field: [msg]}. */
  get firstMessage(): string | null {
    if (typeof this.body === "string") return this.body;
    if (!this.body || typeof this.body !== "object") return null;
    for (const value of Object.values(this.body as Record<string, unknown>)) {
      if (Array.isArray(value) && typeof value[0] === "string") return value[0];
      if (typeof value === "string") return value;
    }
    return null;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
    },
  });

  const text = await response.text();
  const body: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}

/** Refresh is deduplicated: several calls failing at once must not each mint a
 *  new refresh token, because rotation invalidates the previous one and the
 *  losers would log the user out. */
let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccess(): Promise<boolean> {
  const refresh = read(REFRESH_KEY);
  if (!refresh) return false;

  refreshInFlight ??= (async () => {
    try {
      const data = await request<{ access: string; refresh?: string }>(
        "/auth/refresh/",
        { method: "POST", body: JSON.stringify({ refresh }) },
      );
      write(ACCESS_KEY, data.access);
      if (data.refresh) write(REFRESH_KEY, data.refresh);
      return true;
    } catch {
      clearTokens();
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

export async function authFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const withAuth = (token: string | null): RequestInit => ({
    ...init,
    headers: token
      ? { ...init.headers, Authorization: `Bearer ${token}` }
      : init.headers,
  });

  try {
    return await request<T>(path, withAuth(getAccessToken()));
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
    if (!(await refreshAccess())) throw error;
    return request<T>(path, withAuth(getAccessToken()));
  }
}

export type Me = {
  id: number;
  username: string;
  display_name: string;
  avatar: string;
  bio: string;
  gender: "" | "F" | "M";
  birth_date: string | null;
  age: number | null;
  is_guest: boolean;
  is_onboarded: boolean;
  can_change_gender: boolean;
  /** Consecutive days played; shown in the lobby header. */
  streak_days: number;
};

export async function signInAsGuest(): Promise<Me> {
  const data = await request<{ access: string; refresh: string; user: Me }>(
    "/auth/guest/",
    {
      method: "POST",
      body: JSON.stringify({ device_token: getDeviceToken() }),
    },
  );
  setTokens({ access: data.access, refresh: data.refresh });
  return data.user;
}

export const fetchMe = () => authFetch<Me>("/users/me/");

export const patchMe = (patch: Partial<Me>) =>
  authFetch<Me>("/users/me/", { method: "PATCH", body: JSON.stringify(patch) });
