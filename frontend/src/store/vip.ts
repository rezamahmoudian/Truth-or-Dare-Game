import { create } from "zustand";
import type { PublicVIP } from "@/lib/types";

export const useVipState = create<{ now: number; offset: number; people: Record<number, PublicVIP> }>(() => ({ now: Date.now(), offset: 0, people: {} }));

// Cosmetic ownership is independent of VIP expiry.
export function usePublicLook(vip?: PublicVIP) {
  return useVipState(state => {
    const live = vip && state.people[vip.user_id];
    return live && live.as_of > vip.as_of ? live : vip;
  });
}

export function useVipStatus(vip?: PublicVIP) {
  return useVipState(state => {
    const live = vip && state.people[vip.user_id];
    const current = live && (!vip || live.as_of > vip.as_of) ? live : vip;
    return current?.active && current.ends_at && Date.parse(current.ends_at) > state.now ? current : null;
  });
}
