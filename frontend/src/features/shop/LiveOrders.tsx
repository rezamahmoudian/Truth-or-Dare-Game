import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listOrders, type OrderSummary } from "@/lib/billingApi";
import { formatToman } from "./catalog";

export function LiveOrders() {
  const [rows, setRows] = useState<OrderSummary[]>([]);
  const [page, setPage] = useState(0);
  const [more, setMore] = useState(true);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    void listOrders().then(data => { if (active) { setRows(data.results); setMore(!!data.next); setPage(1); } }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, []);
  if (!rows.length && !error) return null;
  return <section className="shop-orders"><h2>سفارش‌های من</h2>
    <div className="flex flex-col gap-3 py-3">{rows.map(order => <Link key={order.id} to={`/shop/payment/${order.id}`} className="surface-card rounded-xl p-4 text-sm">
      <strong>{order.product_snapshot.title}</strong><p className="mt-1 text-xs text-muted">{formatToman(order.amount / 10)} · {order.status === "FULFILLED" ? "تحویل داده شده" : order.status === "PAID" ? "در انتظار تحویل" : "پیگیری نتیجهٔ پرداخت"}</p>
    </Link>)}</div>
    {error && <p className="text-sm text-bad" role="alert">سفارش‌ها دریافت نشدند.</p>}
    {(more || error) && <button className="shop-text-button" disabled={busy} type="button" onClick={async () => {
      setBusy(true);
      try { const data = await listOrders(page + 1); setRows(previous => [...previous, ...data.results.filter(row => !previous.some(old => old.id === row.id))]); setMore(!!data.next); setPage(page + 1); setError(false); }
      catch { setError(true); }
      finally { setBusy(false); }
    }}>{error ? "تلاش دوباره" : "سفارش‌های بیشتر"}</button>}
  </section>;
}
