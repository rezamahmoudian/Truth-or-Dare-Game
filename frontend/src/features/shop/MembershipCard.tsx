import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "@/lib/auth";
import { activateSpotlight, getMembership, paymentKey, type Membership } from "@/lib/billingApi";
import { faNum } from "@/lib/dates";
import { socket } from "@/lib/ws";
import { useSession } from "@/store/session";
import { useVipStatus } from "@/store/vip";

const dates = new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium", timeStyle: "short" });

export function MembershipCard() {
  const userId = useSession(s => s.user?.id);
  const me = useSession(s => s.user);
  const vip = useVipStatus(me?.vip);
  const [data, setData] = useState<Membership | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const version = useRef(0);
  const invalidate = useCallback(() => { version.current++; }, []);
  const key = useRef<string | null>(null);
  const load = useCallback(async () => {
    const current = ++version.current;
    try { const result = await getMembership(); if (current === version.current) { setData(result); setError(""); } }
    catch { if (current === version.current) setError("دریافت وضعیت عضویت ممکن نشد."); }
  }, []);
  useEffect(() => {
    void load();
    const off = socket.onEvent(type => { if (type === "billing.changed") void load(); });
    const resume = socket.onResume(() => void load());
    const visible = () => { if (document.visibilityState === "visible") void load(); };
    document.addEventListener("visibilitychange", visible);
    const poll = window.setInterval(visible, 30000);
    return () => { invalidate(); off(); resume(); clearInterval(poll); document.removeEventListener("visibilitychange", visible); };
  }, [load, invalidate, userId]);
  const active = data?.active && !!vip;
  const spotlight = active && data.spotlight.ends_at && Date.parse(data.spotlight.ends_at) > Date.now();
  return <section className="surface-card rounded-card border border-[#e3b55735] p-4" aria-label="عضویت من">
    <div className="flex items-center justify-between gap-3"><h2 className="font-bold text-[#f5d489]">✦ {active ? "عضویت VIP تو" : "عضویت VIP"}</h2><Link className="min-h-11 content-center text-xs text-[#f5d489]" to="/shop?tab=vip">{active ? "تمدید عضویت" : "دیدن مزایا"}</Link></div>
    {!data && !error && <p className="text-xs text-muted">در حال دریافت وضعیت…</p>}
    {data && <p className="text-xs leading-6 text-muted">{active && data.ends_at ? `فعال تا ${dates.format(new Date(data.ends_at))} · تمدید خودکار ندارد` : "عضویت فعالی نداری؛ چت و بازی معمولی همچنان رایگان‌اند."}</p>}
    {data?.next_period && <p className="mt-2 text-xs text-muted">دوره بعدی خریداری شده؛ شروع از {dates.format(new Date(data.next_period.starts_at))}</p>}
    {active && <div className="mt-3 border-t border-[#e3b55725] pt-3">
      <p className="text-sm font-bold">کمی بیشتر دیده شو</p>
      <p className="mt-1 text-xs leading-6 text-muted">Spotlight پروفایلت را تا {faNum(data.benefits.spotlight_minutes ?? 15)} دقیقه در جایگاه ویژهٔ کاربران آنلاین قرار می‌دهد. برای نمایش، آنلاین بمان؛ نمایش به همه یا مچ تضمین نمی‌شود.</p>
      <p className="mt-2 text-xs text-[#f5d489]">{spotlight && data.spotlight.ends_at ? `فعاله تا ${dates.format(new Date(data.spotlight.ends_at))}` : `${faNum(data.spotlight.remaining)} نوبت باقی‌مانده در این دوره`}</p>
      <button type="button" disabled={busy || !!spotlight || data.spotlight.remaining === 0} className="mt-3 min-h-11 w-full rounded-field border border-[#e3b55755] bg-[#d9ae4318] px-3 text-sm font-bold text-[#f5d489] disabled:opacity-50" onClick={async () => {
        if (busy) return;
        setBusy(true); setError(""); key.current ??= paymentKey();
        const current = ++version.current;
        try { const result = await activateSpotlight(key.current); if (current === version.current) setData(result); key.current = null; }
        catch (err) { if (current === version.current) setError(err instanceof ApiError ? err.firstMessage ?? "فعال‌سازی انجام نشد؛ دوباره بررسی کن." : "اتصال قطع شد؛ دوباره بررسی کن."); }
        finally { setBusy(false); }
      }}>{busy ? "در حال بررسی…" : spotlight ? "Spotlight فعال است" : "فعال‌کردن Spotlight"}</button>
    </div>}
    {error && <p role="alert" className="mt-2 text-xs text-bad">{error} <button type="button" className="min-h-11 underline" onClick={() => void load()}>تلاش دوباره</button></p>}
  </section>;
}
