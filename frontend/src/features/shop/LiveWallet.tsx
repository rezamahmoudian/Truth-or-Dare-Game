import { useCallback, useEffect, useRef, useState } from "react";
import { getWallet, getLedger, type CreditWallet, type CreditEntry } from "@/lib/billingApi";
import { faNum } from "@/lib/dates";
import { socket } from "@/lib/ws";
import { ShopIcon } from "./ShopIcon";
import { LiveOrders } from "./LiveOrders";

const LABELS: Record<CreditEntry["kind"], string> = {
  GRANT: "افزایش اعتبار", RESERVE: "رزرو برای جستجو", RELEASE: "آزادسازی اعتبار",
  CONSUME: "مصرف درخواست ویژه", EXPIRE: "انقضای اعتبار",
  ADJUST: "اصلاح اعتبار توسط پشتیبانی",
};
const dateFormat = new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium", timeStyle: "short" });

export function LiveWallet({ onBrowse }: { onBrowse: () => void }) {
  const [wallet, setWallet] = useState<CreditWallet | null>(null);
  const [rows, setRows] = useState<CreditEntry[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const version = useRef(0);
  const invalidate = useCallback(() => { version.current++; }, []);
  const refresh = useCallback(async () => {
    const current = ++version.current;
    setBusy(true);
    try {
      const balance = await getWallet();
      const history = await getLedger();
      if (current !== version.current) return;
      setWallet(balance); setRows(history.results); setPage(1); setHasMore(!!history.next); setError(null);
    } catch { if (current === version.current) setError("دریافت کیف اعتبار انجام نشد؛ دوباره امتحان کن."); }
    finally { if (current === version.current) setBusy(false); }
  }, []);
  useEffect(() => {
    void refresh();
    const off = socket.onEvent(type => { if (type === "billing.changed") void refresh(); });
    const resume = socket.onResume(() => void refresh());
    const visible = () => { if (document.visibilityState === "visible") void refresh(); };
    document.addEventListener("visibilitychange", visible);
    return () => { invalidate(); off(); resume(); document.removeEventListener("visibilitychange", visible); };
  }, [refresh, invalidate]);
  const value = (amount?: number) => amount === undefined ? "—" : faNum(amount);
  return <div className="shop-panel-content" aria-busy={busy}>
    <section className="shop-wallet-card">
      <div className="shop-section-heading"><span><ShopIcon kind="wallet" size={20} /> کیف اعتبار</span><button type="button" className="min-h-11 px-2 text-xs" onClick={() => void refresh()} disabled={busy}>{busy ? "در حال دریافت…" : "به‌روزرسانی"}</button></div>
      <p className="shop-balance-label">آماده برای بازی</p>
      <div className="shop-balance"><strong>{value(wallet?.available)}</strong><span>درخواست ویژه</span></div>
      <div className="shop-balance-breakdown"><span>کل اعتبار <b>{value(wallet?.total)}</b></span><span>رزروشده <b>{value(wallet?.reserved)}</b></span></div>
    </section>
    {error && <p role="alert" className="text-sm text-bad">{error}</p>}
    {!!wallet?.reserved && <div className="shop-rule"><ShopIcon kind="clock" /><p>{faNum(wallet.reserved)} اعتبار برای جستجو یا مچ در انتظار تعامل رزرو شده؛ هنوز مصرف نشده است.</p></div>}
    {wallet?.vip.active && <div className="shop-rule"><ShopIcon kind="crown" /><p>عضویت VIP فعال · {value(wallet.by_source.VIP?.available)} اعتبار دوره قابل‌استفاده{wallet.vip.ends_at ? ` · تا ${dateFormat.format(new Date(wallet.vip.ends_at))}` : ""}</p></div>}
    <section>
      <div className="shop-section-heading"><h2>گردش اعتبار</h2><ShopIcon kind="clock" size={19} /></div>
      {rows.length > 0 ? <ul className="shop-history">{rows.map(row => <li key={row.id}>
        <div className="flex min-h-20 items-center gap-3 py-3">
          <span className={`shop-history-icon ${row.kind === "CONSUME" || row.kind === "ADJUST" ? "use" : "return"}`}><ShopIcon kind={row.kind === "RELEASE" ? "arrow" : "ticket"} size={22} /></span>
          <div className="min-w-0 flex-1"><strong className="text-sm">{LABELS[row.kind]}</strong><p className="text-xs leading-6 text-muted">{row.reason}</p><small className="text-[10px] text-muted">{dateFormat.format(new Date(row.created_at))}</small></div>
          <div className="shrink-0 text-xs font-bold">{row.kind === "RESERVE" ? "۱ رزرو" : row.kind === "RELEASE" ? "۱ آزاد" : <bdi>{row.delta > 0 ? "+" : ""}{faNum(row.delta)}</bdi>}</div>
        </div>
      </li>)}</ul> : wallet && !busy && <div className="shop-empty"><span><ShopIcon kind="wallet" size={34} /></span><h3>هنوز تراکنشی نداری</h3><p>افزایش، رزرو، مصرف و برگشت اعتبارها را اینجا می‌بینی.</p><button type="button" onClick={onBrowse}>دیدن بسته‌ها <ShopIcon kind="arrow" size={17} /></button></div>}
      {hasMore && <button type="button" className="shop-text-button" disabled={busy} onClick={async () => {
        const current = ++version.current; setBusy(true);
        try {
          const history = await getLedger(page + 1);
          if (current !== version.current) return;
          setRows(previous => [...previous, ...history.results.filter(row => !previous.some(old => old.id === row.id))]);
          setPage(page + 1); setHasMore(!!history.next); setError(null);
        } catch { if (current === version.current) setError("دریافت ادامهٔ تاریخچه انجام نشد."); }
        finally { if (current === version.current) setBusy(false); }
      }}>نمایش بیشتر</button>}
    </section>
    <LiveOrders />
  </div>;
}
