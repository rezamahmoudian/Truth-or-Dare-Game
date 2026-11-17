import { useEffect } from "react";
import { useVipState, useVipStatus, usePublicLook } from "@/store/vip";
import type { PublicVIP } from "@/lib/types";
import { fetchMe } from "@/lib/auth";
import { socket } from "@/lib/ws";
import { useSession } from "@/store/session";

export function VipName({ vip, children }: { vip?: PublicVIP; children: React.ReactNode }) {
  const active = useVipStatus(vip);
  const look = usePublicLook(vip)?.cosmetics;
  const badge = look?.BADGE;
  return <span className={look?.NAME ? `item-name-${look.NAME.visual}` : active?.gold_profile ? "vip-name" : undefined}>{children}{active?.vip_badge && <span className="vip-badge" aria-label="عضو VIP">VIP</span>}{badge && <span className="item-name-badge" title={badge.title} aria-label={badge.title}>{badge.visual === "moon" ? "☾" : badge.visual === "spark" ? "✧" : "★"}</span>}</span>;
}

/** One clock and one refresh path for the whole app, including cached chat senders. */
export function VipSync() {
  const userId = useSession(s => s.user?.id);
  const ready = useSession(s => s.status === "ready");
  useEffect(() => {
    if (!ready || !userId) return;
    let alive = true;
    let inFlight = false;
    const update = (vip: PublicVIP) => {
      if (!alive || useSession.getState().user?.id !== userId) return;
      useVipState.setState(s => {
        const old = s.people[vip.user_id];
        if (old && old.as_of > vip.as_of) return s;
        return { offset: Date.parse(vip.as_of) - Date.now(), now: Date.parse(vip.as_of), people: { ...s.people, [vip.user_id]: vip } };
      });
    };
    const refresh = async () => {
      if (inFlight || !alive) return;
      inFlight = true;
      try {
        const me = await fetchMe();
        if (alive && useSession.getState().user?.id === userId && me.id === userId) {
          if (me.vip) update(me.vip);
          useSession.setState(s => ({ user: s.user ? { ...s.user, vip: me.vip } : s.user }));
        }
      } catch { /* Reconnect and the next refresh retry; existing identity stays usable. */ }
      finally { inFlight = false; }
    };
    const initial = useSession.getState().user?.vip;
    if (initial) update(initial);
    void refresh();
    const off = socket.onEvent((type, payload) => {
      if (type === "billing.changed") void refresh();
      if (type === "user.vip_changed") {
        const vip = (payload as { vip?: PublicVIP }).vip;
        if (vip && typeof vip.user_id === "number") { update(vip); if (vip.user_id === userId) void refresh(); }
      }
    });
    const resume = socket.onResume(() => void refresh());
    const visible = () => { if (document.visibilityState === "visible") void refresh(); };
    document.addEventListener("visibilitychange", visible);
    const poll = window.setInterval(() => { if (document.visibilityState === "visible") void refresh(); }, 60000);
    const tick = window.setInterval(() => useVipState.setState(s => ({ now: Date.now() + s.offset })), 1000);
    return () => { alive = false; off(); resume(); clearInterval(poll); clearInterval(tick);
      document.removeEventListener("visibilitychange", visible); useVipState.setState({ people: {}, offset: 0, now: Date.now() }); };
  }, [ready, userId]);
  return null;
}
