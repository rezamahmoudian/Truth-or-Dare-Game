import { useSession } from "@/store/session";

// Server-owned runtime flag: one env setting for both API and UI.
// Missing configuration stays off, including during session bootstrap.
export function useMonetization() {
  return useSession(s => s.user?.monetization_enabled === true);
}
