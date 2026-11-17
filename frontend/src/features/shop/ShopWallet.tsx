import { useState } from "react";
import { ShopIcon } from "./ShopIcon";
import { ShopSheet } from "./ShopSheet";
import { REQUEST_PACKS, VIP, type PaymentView, type ShopProduct } from "./catalog";
import { LiveWallet } from "./LiveWallet";

const EXAMPLE_HISTORY = [
  { id: "sample-refund", title: "برگشت اعتبار", detail: "اصلاح مصرف توسط پشتیبانی", amount: "+۱", kind: "return", date: "امروز · ۱۸:۴۲" },
  { id: "sample-use-2", title: "درخواست ویژه", detail: "بازی با پسر", amount: "−۱", kind: "use", date: "امروز · ۱۸:۴۰" },
  { id: "sample-use-1", title: "درخواست ویژه", detail: "بازی با دختر · مچ موفق", amount: "−۱", kind: "use", date: "امروز · ۱۷:۱۰" },
  { id: "sample-buy", title: "خرید بستهٔ ۱۰تایی", detail: "پرداخت موفق · اعتبار اضافه شد", amount: "+۱۰", kind: "purchase", date: "دیروز · ۲۱:۳۰" },
];

export function ShopWallet({ preview, populated, onBrowse, onOrder }: { preview: boolean; populated: boolean; onBrowse: () => void; onOrder: (product: ShopProduct, view: PaymentView) => void }) {
  const [filter, setFilter] = useState("all");
  const [detailId, setDetailId] = useState<string | null>(null);
  const rows = preview && populated ? EXAMPLE_HISTORY : [];
  const detail = rows.find(row => row.id === detailId);
  if (!preview) return <LiveWallet onBrowse={onBrowse} />;
  return <div className="shop-panel-content">
    <section className="shop-wallet-card">
      <div className="shop-section-heading"><span><ShopIcon kind="wallet" size={20} /> کیف اعتبار</span><small>{preview ? "حساب نمونه" : "به‌زودی"}</small></div>
      <p className="shop-balance-label">آماده برای بازی</p>
      <div className="shop-balance"><strong>{preview ? populated ? "۸" : "۰" : "—"}</strong><span>درخواست ویژه</span></div>
      <div className="shop-balance-breakdown"><span>کل اعتبار <b>{preview ? populated ? "۹" : "۰" : "—"}</b></span><span>در انتظار مچ <b>{preview ? populated ? "۱" : "۰" : "—"}</b></span></div>
    </section>
    {preview && populated && <div className="shop-rule"><ShopIcon kind="clock" /><p>۱ اعتبار برای جستجوی در جریان کنار گذاشته شده؛ هنوز مصرف نشده. با لغو جستجو آزاد می‌شه.</p></div>}
    {preview && populated && <section className="shop-orders"><h2>پیگیری سفارش‌ها</h2>
      <button type="button" onClick={() => onOrder(REQUEST_PACKS[2]!, "pending")}><span className="shop-order-status pending"><ShopIcon kind="clock" size={19} /></span><div><strong>بستهٔ ۳۰ درخواست</strong><p>در حال بررسی · هنوز به موجودی اضافه نشده</p></div><span>پیگیری</span></button>
      <button type="button" onClick={() => onOrder(VIP, "failed")}><span className="shop-order-status failed"><ShopIcon kind="close" size={19} /></span><div><strong>عضویت VIP</strong><p>پرداخت ناموفق · اشتراک فعال نشده</p></div><span>جزئیات</span></button>
    </section>}
    <section>
      <div className="shop-section-heading"><h2>ردِ خرید و بازی‌هات</h2><ShopIcon kind="clock" size={19} /></div>
      <div className="shop-filters" aria-label="فیلتر تاریخچه">
        {[["all", "همه"], ["purchase", "خرید"], ["use", "مصرف"], ["return", "برگشت"]].map(([key, label]) => <button type="button" key={key} aria-pressed={filter === key} onClick={() => setFilter(key!)}>{label}</button>)}
      </div>
      {rows.length ? <ul className="shop-history">{rows.filter(row => filter === "all" || row.kind === filter).map(row => <li key={row.id}>
        <button type="button" onClick={() => setDetailId(row.id)}><span className={`shop-history-icon ${row.kind}`}><ShopIcon kind={row.kind === "return" ? "arrow" : row.kind === "purchase" ? "wallet" : "ticket"} size={22} /></span><div><strong>{row.title}</strong><p>{row.detail}</p><small>{row.date}</small></div><b className={row.kind === "use" ? "" : "positive"}><bdi>{row.amount}</bdi><small>اعتبار</small></b></button>
      </li>)}</ul> : <div className="shop-empty"><span><ShopIcon kind="wallet" size={34} /></span><h3>{preview ? "اولین خریدت، شروع این لیسته" : "کیف اعتبارت به‌زودی آماده می‌شه"}</h3><p>{preview ? "خریدها، مصرف‌ها و اعتبارهای برگشتی رو همین‌جا می‌بینی." : "بعد از فعال‌شدن فروش، موجودی و جزئیات خرید‌هات اینجا نمایش داده می‌شه."}</p><button type="button" onClick={onBrowse}>دیدن بسته‌های درخواست <ShopIcon kind="arrow" size={17} /></button></div>}
    </section>
    {detail && <ShopSheet title="جزئیات تراکنش نمونه" onClose={() => setDetailId(null)}><dl className="shop-receipt"><div><dt>نوع</dt><dd>{detail.title}</dd></div><div><dt>توضیح</dt><dd>{detail.detail}</dd></div><div><dt>تغییر موجودی</dt><dd><bdi>{detail.amount}</bdi> اعتبار</dd></div><div><dt>زمان نمونه</dt><dd>{detail.date}</dd></div></dl><p className="shop-coming-note">این تراکنش فقط برای نمایش طراحی است و به حساب واقعی ارتباطی ندارد.</p></ShopSheet>}
  </div>;
}
