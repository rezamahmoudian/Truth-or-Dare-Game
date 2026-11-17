import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "@/lib/auth";
import { checkPayment, getOrder, paymentKey, startPayment, type BillingOrder, type Payment } from "@/lib/billingApi";
import { faNum } from "@/lib/dates";
import { Screen } from "@/ui/Screen";
import { ShopIcon } from "./ShopIcon";
import { formatToman } from "./catalog";
import "./shop.css";

const LABEL: Record<Payment["state"], [string, string]> = {
  NOT_STARTED: ["سفارش آمادهٔ پرداخت است", "مبلغ را بررسی کن؛ سپس به درگاه برو."],
  READY: ["لینک پرداخت آماده است", "اگر از درگاه برگشته‌ای، ابتدا نتیجه را بررسی کن؛ لینک پایین همان پرداخت قبلی است."],
  PENDING: ["در حال بررسی پرداخت", "نتیجه هنوز مشخص نیست؛ پرداخت تازه‌ای شروع نکن."],
  FAILED: ["پرداخت کامل نشد", "درگاه این تلاش را ناموفق اعلام کرده است؛ اعتباری اضافه نشده."],
  EXPIRED: ["مهلت سفارش تمام شده", "برای خرید، از فروشگاه سفارش تازه‌ای ثبت کن."],
  DELIVERING: ["پرداخت تأیید شد", "خرید در حال اضافه‌شدن به حسابت است. دوباره پرداخت نکن."],
  FULFILLED: ["خرید به حسابت اضافه شد", "خریدت آمادهٔ استفاده است."],
  REVIEW: ["پرداخت نیاز به بررسی دارد", "نتیجه قطعی نشده است. شناسهٔ سفارش را برای پیگیری نگه دار و دوباره پرداخت نکن."],
};

export function PaymentScreen() {
  const { orderId = "" } = useParams();
  const [order, setOrder] = useState<BillingOrder | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const keys = useRef<Record<string, string>>({});
  const version = useRef(0);
  const activeOrder = useRef(orderId);
  useEffect(() => {
    activeOrder.current = orderId;
    return () => { activeOrder.current = ""; };
  }, [orderId]);
  const refresh = useCallback(async () => {
    const current = ++version.current;
    try { const result = await getOrder(orderId); if (current === version.current) { setOrder(result); setError(null); } }
    catch (err) { if (current === version.current) setError(err instanceof ApiError ? err.firstMessage ?? "سفارش دریافت نشد." : "ارتباط برقرار نیست. بعد از اتصال، نتیجهٔ همین سفارش را بررسی کن."); }
  }, [orderId]);
  useEffect(() => { setOrder(null); keys.current = {}; void refresh(); }, [refresh]);
  useEffect(() => {
    if (!order || !["READY", "PENDING", "DELIVERING"].includes(order.payment.state)) return;
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void refresh(); }, 10000);
    return () => window.clearInterval(timer);
  }, [order, refresh]);
  const state = order?.payment.state;
  return <Screen className="shop-screen" header={<header className="shop-header"><Link className="shop-icon-button" to="/shop" aria-label="برگشت به فروشگاه"><ShopIcon kind="arrow" /></Link><h1>پیگیری خرید</h1></header>}>
    <div className="shop-content">
      {state && <><div className={`shop-result-mark ${state === "FULFILLED" ? "lime" : "violet"}`}><ShopIcon kind={state === "FULFILLED" ? "check" : "clock"} size={36} /></div><div role="status"><h2 className="shop-sheet-heading">{LABEL[state][0]}</h2><p className="shop-sheet-copy">{LABEL[state][1]}</p></div></>}
      {!order && !error && <p className="shop-sheet-copy">در حال دریافت سفارش…</p>}
      {order && <dl className="shop-receipt"><div><dt>محصول</dt><dd>{order.product_snapshot.title}</dd></div>{order.product_snapshot.kind !== "ITEM" && <div><dt>تعداد اعتبار</dt><dd>{faNum(order.product_snapshot.credits)}</dd></div>}<div><dt>مبلغ نهایی</dt><dd>{formatToman(order.amount / 10)}</dd></div><div><dt>شناسهٔ سفارش</dt><dd className="break-all text-xs"><bdi>{order.id}</bdi></dd></div></dl>}
      {error && <p className="mb-4 text-sm text-bad" role="alert">{error}</p>}
      {order?.payment.can_start && <button type="button" className="shop-primary" disabled={busy} onClick={async () => {
        setBusy(true); setError(null);
        try {
          const storageKey = `ft.payment.${order.id}.${state === "FAILED" ? order.payment.attempt_id : "initial"}`;
          if (!keys.current[storageKey]) {
            try { keys.current[storageKey] = sessionStorage.getItem(storageKey) || ""; } catch { /* In-memory key remains available. */ }
            keys.current[storageKey] ||= paymentKey();
            try { sessionStorage.setItem(storageKey, keys.current[storageKey]); } catch { /* Recover via order history. */ }
          }
          const result = await startPayment(order.id, keys.current[storageKey]);
          if (activeOrder.current !== order.id) return;
          if (result.redirect_url) window.location.assign(result.redirect_url);
          else await refresh();
        } catch (err) { setError(err instanceof ApiError ? err.firstMessage ?? "پرداخت شروع نشد." : "نتیجه نامشخص است؛ وضعیت همین سفارش را بررسی کن."); }
        finally { setBusy(false); }
      }}>{busy ? "در حال آماده‌سازی…" : state === "FAILED" ? "تلاش دوباره برای پرداخت" : "رفتن به درگاه پرداخت"}</button>}
      {order?.payment.redirect_url && <a className="shop-primary" href={order.payment.redirect_url}>ادامهٔ همان پرداخت در درگاه</a>}
      {state !== "FULFILLED" && <button type="button" className="shop-text-button" disabled={busy} onClick={async () => {
        setBusy(true);
        try { if (order) await checkPayment(order.id); await refresh(); }
        catch { setError("بررسی انجام نشد؛ کمی بعد دوباره امتحان کن."); }
        finally { setBusy(false); }
      }}>بررسی دوبارهٔ وضعیت</button>}
      <Link className="shop-text-button" to="/shop?tab=wallet">کیف اعتبار و سفارش‌ها</Link>
      {order?.product_snapshot.kind === "ITEM" && <Link className="shop-primary" to="/shop/items">رفتن به مجموعهٔ من</Link>}
    </div>
  </Screen>;
}
