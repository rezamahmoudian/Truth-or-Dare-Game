import { useState } from "react";
import { faNum } from "@/lib/dates";
import { formatToman, PAYMENT_LABELS, type PaymentView, type ShopProduct } from "./catalog";
import { ShopIcon } from "./ShopIcon";
import { ShopSheet } from "./ShopSheet";

const RESULTS: Record<Exclude<PaymentView, "review">, { title: string; description: string; tone: string }> = {
  pending: { title: "داریم نتیجهٔ پرداخت رو بررسی می‌کنیم", description: "تأیید بانک ممکنه کمی طول بکشه. تا مشخص‌شدن نتیجه دوباره پرداخت نکن؛ از تاریخچه هم می‌تونی پیگیری کنی.", tone: "violet" },
  success: { title: "همه‌چیز آماده‌ست!", description: "خریدت با موفقیت انجام شد و به حسابت اضافه شد.", tone: "lime" },
  failed: { title: "پرداخت کامل نشد", description: "این سفارش تأیید نشده و اعتباری به حساب اضافه نشده. اگر مبلغی از حسابت کم شده، وضعیتش رو از بانک پیگیری کن.", tone: "rose" },
  offline: { title: "ارتباط قطع شد", description: "ممکنه پرداختت انجام شده باشه. بعد از وصل‌شدن اینترنت، اول وضعیت همین سفارش رو بررسی کن.", tone: "rose" },
  unverified: { title: "برگشتی؛ تأیید بانک هنوز نرسیده", description: "بازگشت از درگاه به‌تنهایی به معنی موفقیت یا شکست پرداخت نیست. نتیجهٔ سفارش رو بررسی کن.", tone: "violet" },
  delayed: { title: "پرداخت تأیید شد؛ اعتبار در راهه", description: "پرداختت ثبت شده و در حال اضافه‌کردن خرید به حسابت هستیم. لازم نیست دوباره خرید کنی.", tone: "gold" },
  duplicate: { title: "این سفارش قبلاً ثبت شده", description: "همون سفارش قبلی رو پیگیری می‌کنیم؛ خرید یا اعتبار جدیدی دوباره ثبت نمی‌شه.", tone: "violet" },
};

export function PurchaseSheet({ product, price, preview, initialView = "review", onClose, onWallet }: {
  product: ShopProduct; price?: number; preview: boolean; initialView?: PaymentView; onClose: () => void; onWallet: () => void;
}) {
  const [view, setView] = useState<PaymentView>(initialView);
  const [checked, setChecked] = useState(false);
  const result = view === "review" ? null : RESULTS[view];
  return <ShopSheet title={PAYMENT_LABELS[view]} onClose={onClose}>
    {preview && <div className="shop-demo-note">پیش‌نمایش طراحی · مبلغ‌ها و نتیجه‌ها نمونه‌اند؛ پرداختی انجام نمی‌شه.</div>}
    {view === "review" ? <>
      <div className={`shop-order-product ${product.kind === "vip" ? "gold" : ""}`}>
        <span className="shop-entry-icon"><ShopIcon kind={product.kind === "vip" ? "crown" : "ticket"} size={32} /></span>
        <div><h3>{product.title}</h3><p>{product.kind === "vip" ? "۳۰ روز عضویت + ۱۰ اعتبار این دوره" : "برای بازی با دختر، پسر و حالت‌های ویژه"}</p></div>
      </div>
      <dl className="shop-receipt">
        <div><dt>نوع خرید</dt><dd>{product.kind === "vip" ? "اشتراک ۳۰ روزه" : `${faNum(product.credits)} درخواست ویژه`}</dd></div>
        <div><dt>{product.kind === "vip" ? "تمدید" : "مصرف اعتبار"}</dt><dd>{product.kind === "vip" ? "با انتخاب خودت؛ بدون تمدید خودکار" : "پس از مچ و تعامل دوطرفه"}</dd></div>
        <div className="shop-receipt-total"><dt>مبلغ قابل پرداخت</dt><dd>{price === undefined ? "به‌زودی" : formatToman(price)}</dd></div>
      </dl>
      <div className="shop-rule"><ShopIcon kind="shield" /><p>لغو جستجو، پیدا نشدن هم‌بازی یا خروج سریع طرف مقابل، اعتبارت رو مصرف نمی‌کنه.</p></div>
      {!preview && <p className="shop-coming-note">فروش هنوز شروع نشده؛ قیمت نهایی موقع فعال‌شدن خرید اعلام می‌شه.</p>}
      <button type="button" className="shop-primary" disabled={!preview} onClick={() => setView("pending")}>{preview ? "پیش‌نمایش مرحلهٔ پرداخت" : "خرید به‌زودی فعال می‌شه"}</button>
    </> : result && <>
      <div className={`shop-result-mark ${result.tone}`}><ShopIcon kind={view === "success" ? "check" : view === "failed" || view === "offline" ? "close" : "clock"} size={36} /></div>
      <div role="status" aria-live="polite"><h3 className="shop-sheet-heading">{result.title}</h3><p className="shop-sheet-copy">{result.description}</p></div>
      <dl className="shop-receipt">
        <div><dt>سفارش نمونه</dt><dd>{product.title}</dd></div>
        <div><dt>شناسهٔ پیگیری نمونه</dt><dd><bdi>DEMO-1024</bdi></dd></div>
        {price !== undefined && <div><dt>مبلغ نمونه</dt><dd>{formatToman(price)}</dd></div>}
      </dl>
      {view === "success" ? <button type="button" className="shop-primary" onClick={onWallet}>دیدن کیف اعتبار</button> : <>
        <button type="button" className="shop-primary" onClick={() => {
          if (view === "failed") { setView("review"); setChecked(false); }
          else { setView("pending"); setChecked(true); }
        }}>{view === "failed" ? "برگشت به مرور سفارش" : "بررسی وضعیت سفارش"}</button>
        {checked && <p className="shop-coming-note" role="status">این یک نمونهٔ نمایشی است؛ نتیجهٔ دلخواه را از کنترل پایین انتخاب کن.</p>}
        <button type="button" className="shop-text-button" onClick={onWallet}>رفتن به تاریخچه</button>
      </>}
    </>}
    {preview && <label className="shop-design-select">نمایش وضعیت پرداخت
      <select value={view} onChange={event => { setView(event.target.value as PaymentView); setChecked(false); }}>
        {Object.entries(PAYMENT_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select>
    </label>}
  </ShopSheet>;
}
