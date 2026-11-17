import { useMonetization } from "@/lib/features";
import { useCallback, useEffect, useRef, useState } from "react";
import { getInventory, paymentKey, type Inventory } from "@/lib/billingApi";
import { useSession } from "@/store/session";
import { socket } from "@/lib/ws";

export function useInventory() {
  const enabled = useMonetization();
  const userId = useSession(s => s.user?.id);
  const [data, setData] = useState<Inventory | null>(null);
  const [error, setError] = useState("");
  const version = useRef(0);
  const invalidate = useCallback(() => { version.current++; }, []);
  const load = useCallback(async () => {
    if (!enabled) return;
    const current = ++version.current;
    try { const result = await getInventory(); if (current === version.current) { setData(result); setError(""); } }
    catch { if (current === version.current) setError("مجموعه دریافت نشد؛ دوباره امتحان کن."); }
  }, [enabled]);
  useEffect(() => {
    setData(null);
    if (!enabled) return;
    void load();
    const off = socket.onEvent(type => { if (type === "billing.changed") void load(); });
    const resume = socket.onResume(() => void load());
    return () => { invalidate(); off(); resume(); };
  }, [load, invalidate, userId, enabled]);
  return { data, error, load };
}

// Retain ambiguous sends across closing/reopening the sheet. Clear only on a
// confirmed response; retrying after a lost response cannot spend twice.
const keys = new Map<string, string>();
export function pendingItemAction(scope: string): string | null {
  if (keys.has(scope)) return keys.get(scope)!;
  try { return sessionStorage.getItem(`ft.item.${scope}`); } catch { return null; }
}
export function itemActionKey(scope: string) {
  if (!keys.has(scope)) {
    const saved = pendingItemAction(scope);
    keys.set(scope, saved || paymentKey());
    try { sessionStorage.setItem(`ft.item.${scope}`, keys.get(scope)!); } catch { /* Memory retry available. */ }
  }
  return keys.get(scope)!;
}
export function finishItemAction(scope: string) {
  keys.delete(scope);
  try { sessionStorage.removeItem(`ft.item.${scope}`); } catch { /* Memory was cleared. */ }
}
