const STORAGE_KEY = "ft.device_token";

/**
 * The device token *is* the guest account. Whoever holds it can sign in as that
 * user, so it is generated from the platform CSPRNG (256 bits) rather than
 * anything derived from device characteristics, and it never leaves storage
 * except in the sign-in request body.
 */
function generate(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Storage can be unavailable (private mode, blocked site data). Rather than
 * crashing on launch, fall back to an in-memory token: the session still works,
 * it just will not survive a reload — which is the honest outcome when the
 * browser refuses to remember anything.
 */
let memoryToken: string | null = null;

export function getDeviceToken(): string {
  try {
    const existing = localStorage.getItem(STORAGE_KEY);
    if (existing) return existing;

    const fresh = generate();
    localStorage.setItem(STORAGE_KEY, fresh);
    return fresh;
  } catch {
    memoryToken ??= generate();
    return memoryToken;
  }
}

export function isPersistent(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== null;
  } catch {
    return false;
  }
}
