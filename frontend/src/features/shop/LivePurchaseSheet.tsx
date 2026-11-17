import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "@/lib/auth";
import { createOrder, getOrder, paymentKey, type Offer } from "@/lib/billingApi";
import { faNum } from "@/lib/dates";
import { useSession } from "@/store/session";
import { ShopSheet } from "./ShopSheet";
import { formatToman } from "./catalog";

export function LivePurchaseSheet({ offer, onClose }: { offer: Offer; onClose: () => void }) {
  const navigate = useNavigate();
  const userId = useSession(s => s.user?.id);
  const cacheKey = `ft.order.${userId}.${offer.id}`;
  const draft = useRef<{ key: string; orderId?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return <ShopSheet title="مرور خرید" onClose={() => { if (!busy) onClose(); }}>
    <h3 className="shop-sheet-heading">{offer.product.title}</h3>
    <dl className="shop-receipt">
      {offer.product.kind !== "ITEM" && <div><dt>اعتبار درخواست</dt><dd>{faNum(offer.product.credits)}</dd></div>}
      {offer.product.item && <div><dt>محتویات خرید</dt><dd>{["GIFT", "SPOTLIGHT"].includes(offer.product.item.kind) ? `${faNum(offer.product.item.units)} نوبت استفاده` : "مالکیت دائمی"}</dd></div>}
      {offer.product.item?.kind === "PACK" && <div><dt>سؤال‌های تأییدشده</dt><dd>{faNum(offer.product.item.prompt_count ?? 0)}</dd></div>}
      {offer.product.kind === "VIP" && <div><dt>مدت عضویت</dt><dd>{faNum(offer.product.duration_days)} روز</dd></div>}
      {!!offer.vip_discount_percent && <div><dt>تخفیف VIP</dt><dd>{faNum(offer.vip_discount_percent)}٪ روی قیمت بسته اعمال شده</dd></div>}
      <div><dt>مبلغ</dt><dd>{formatToman(offer.amount / 10)}</dd></div>
    </dl>
    <p className="shop-sheet-copy">مبلغ نهایی و شناسهٔ سفارش را قبل از رفتن به درگاه می‌بینی. خرید پس از تأیید پرداخت به حسابت اضافه می‌شود.</p>
    {error && <p className="text-sm text-bad" role="alert">{error}</p>}
    <button className="shop-primary" disabled={busy} type="button" onClick={async () => {
      setBusy(true); setError(null);
      try {
        if (!draft.current) {
          try { draft.current = JSON.parse(sessionStorage.getItem(cacheKey) || "null"); } catch { /* In-memory retry still keeps its key. */ }
          if (!draft.current?.key) draft.current = { key: paymentKey() };
        }
        if (draft.current.orderId) {
          const previous = await getOrder(draft.current.orderId);
          if (previous.status !== "FULFILLED" && previous.payment.state !== "EXPIRED") {
            navigate(`/shop/payment/${previous.id}`); return;
          }
          draft.current = { key: paymentKey() };
        }
        try { sessionStorage.setItem(cacheKey, JSON.stringify(draft.current)); } catch { /* Storage may be unavailable. */ }
        const order = await createOrder(offer.id, draft.current.key);
        draft.current.orderId = order.id;
        try { sessionStorage.setItem(cacheKey, JSON.stringify(draft.current)); } catch { /* History also recovers the order. */ }
        navigate(`/shop/payment/${order.id}`);
      } catch (err) { setError(err instanceof ApiError ? err.firstMessage ?? "ثبت سفارش انجام نشد." : "ارتباط قطع شد؛ دوباره امتحان کن. همان سفارش پیگیری می‌شود."); }
      finally { setBusy(false); }
    }}>{busy ? "در حال ثبت…" : "ثبت سفارش و بررسی مبلغ نهایی"}</button>
  </ShopSheet>;
}
