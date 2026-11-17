import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Avatar } from "@/ui/Avatar";
import { VipName } from "@/ui/Vip";
import { Screen } from "@/ui/Screen";
import { TabBar } from "@/ui/TabBar";
import { useSession } from "@/store/session";
import { faNum } from "@/lib/dates";
import { REQUEST_PACKS, VIP, formatToman, type PaymentView, type ShopProduct } from "./catalog";
import { ShopIcon } from "./ShopIcon";
import { ShopWallet } from "./ShopWallet";
import { PurchaseSheet } from "./PurchaseSheet";
import { CreditLimitSheet } from "./CreditLimitSheet";
import { LivePurchaseSheet } from "./LivePurchaseSheet";
import { getCatalog, type Catalog } from "@/lib/billingApi";
import { socket } from "@/lib/ws";
import { useVipStatus } from "@/store/vip";
import { MembershipCard } from "./MembershipCard";
import "./shop.css";

type Section = "credits" | "vip" | "wallet";
const SECTIONS: { key: Section; title: string; icon: "ticket" | "crown" | "wallet" }[] = [
  { key: "credits", title: "درخواست ویژه", icon: "ticket" },
  { key: "vip", title: "عضویت VIP", icon: "crown" },
  { key: "wallet", title: "کیف اعتبار", icon: "wallet" },
];

export function ShopScreen({ previewPrices }: { previewPrices?: Record<string, number> }) {
  const me = useSession(state => state.user);
  const membership = useVipStatus(me?.vip);
  const preview = !!previewPrices;
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogRetry, setCatalogRetry] = useState(0);
  useEffect(() => {
    if (preview) { setCatalogError(""); setCatalogLoading(false); return;
    }
    let active = true;
    const refresh = () => {
      setCatalogLoading(true);
      void getCatalog().then(value => {
        if (active) { setCatalog(value); setCatalogError(""); }
      }).catch(() => {
        if (active) setCatalogError("اطلاعات فروشگاه دریافت نشد؛ دوباره تلاش کن.");
      }).finally(() => { if (active) setCatalogLoading(false); });
    };
    refresh();
    const off = socket.onEvent(type => { if (type === "billing.changed") refresh(); });
    const resume = socket.onResume(refresh);
    return () => { active = false; off(); resume(); };
  }, [preview, me?.id, membership?.active, catalogRetry]);
  function offerFor(item: ShopProduct) {
    return catalog?.offers.find(offer => offer.product.key === item.id && offer.product.credits === item.credits
      && offer.product.kind === (item.kind === "vip" ? "VIP" : "CREDITS")
      && (item.kind !== "vip" || offer.product.duration_days === 30));
  }
  function priceFor(item: ShopProduct) {
    const offer = offerFor(item);
    return preview ? previewPrices?.[item.id] : offer ? offer.amount / 10 : undefined;
  }
  const [search, setSearch] = useSearchParams();
  const section: Section = search.get("tab") === "vip" ? "vip" : search.get("tab") === "wallet" ? "wallet" : "credits";
  const [selectedId, setSelectedId] = useState("requests-10");
  const selected = REQUEST_PACKS.find(pack => pack.id === selectedId) ?? REQUEST_PACKS[1]!;
  const product = section === "vip" ? VIP : selected;
  const [purchase, setPurchase] = useState<{ product: ShopProduct; view: PaymentView } | null>(null);
  const [limitOpen, setLimitOpen] = useState(false);
  const [walletPopulated, setWalletPopulated] = useState(true);
  const [vipActive, setVipActive] = useState(false);
  const isVip = preview ? vipActive : !!membership;
  const perks = preview ? { gold_profile: true, vip_badge: true, exclusive_frame: true, queue_priority_seconds: 60, request_discount_percent: 10, spotlight_uses: 1, spotlight_minutes: 15, ad_free: true } : offerFor(VIP)?.product.benefits ?? catalog?.vip_preview?.benefits;
  const visualPreview = { user_id: -1, active: !!perks, as_of: new Date().toISOString(), ends_at: "2099-01-01T00:00:00Z", gold_profile: !!perks?.gold_profile, vip_badge: !!perks?.vip_badge, exclusive_frame: !!perks?.exclusive_frame };
  const panel = useRef<HTMLDivElement>(null);
  function chooseSection(key: Section) {
    setSearch(key === "credits" ? {} : { tab: key }, { replace: true });
    panel.current?.closest("main")?.scrollTo({ top: 0 });
  }
  const price = priceFor(product);
  return <Screen className="shop-screen" header={<header className="shop-header">
    <Link className="shop-icon-button" to="/" aria-label="برگشت به خانه"><ShopIcon kind="arrow" /></Link>
    <div><p>یه انتخاب بیشتر، یه آشنایی تازه</p><h1>فروشگاه</h1></div>
    <button type="button" className="shop-wallet-shortcut" onClick={() => chooseSection("wallet")} aria-label="دیدن کیف اعتبار"><ShopIcon kind="wallet" size={21} /><span>{preview ? walletPopulated ? "۸ اعتبار" : "۰ اعتبار" : "کیف اعتبار"}</span></button>
  </header>} footer={<>
    {section !== "wallet" && <div className="shop-purchase-dock"><div><span>{product.title}</span><strong>{price === undefined ? "به‌زودی" : formatToman(price)}</strong></div><button type="button" disabled={!preview && (catalogLoading || price === undefined)} className={`shop-primary ${section === "vip" ? "gold" : ""}`} onClick={() => setPurchase({ product, view: "review" })}>{catalogLoading ? "در حال دریافت…" : section === "vip" ? isVip ? "مرور تمدید VIP" : "دیدن جزئیات VIP" : "بررسی بسته"}<ShopIcon kind="arrow" size={18} /></button></div>}
    <TabBar />
  </>}>
    <div className="shop-content" ref={panel}>
      {!preview && <Link to="/shop/items" className="shop-vip-teaser"><span className="text-3xl" aria-hidden>✧</span><div><strong>کلکسیون بی‌هوا</strong><span>استایل، هدیه و سؤال‌های تازه</span></div><ShopIcon kind="arrow" size={19} /></Link>}
      {!preview && catalogError && <div className="shop-launch-note" role="alert"><span />{catalogError}<button type="button" className="shop-text-button" disabled={catalogLoading} onClick={() => setCatalogRetry(value => value + 1)}>تلاش دوباره</button></div>}
      {preview ? <div className="shop-preview-banner"><span>پیش‌نمایش طراحی</span><p>قیمت‌ها و موجودی نمونه‌اند؛ خرید واقعی انجام نمی‌شه.</p></div> : <div className="shop-launch-note"><span />{catalogLoading && !catalog ? "در حال دریافت وضعیت خرید…" : catalog?.payment_enabled ? "پرداخت از طریق درگاه؛ تحویل پس از تأیید بانک." : catalogError ? "وضعیت خرید فعلاً در دسترس نیست." : "خرید هنوز فعال نیست؛ کیف اعتبار و پیگیری سفارش‌ها در دسترس است."}</div>}
      <div className="shop-tabs" role="tablist" aria-label="بخش‌های فروشگاه">
        {SECTIONS.map(({ key, title, icon }, index) => <button type="button" key={key} id={`shop-tab-${key}`} role="tab" aria-selected={section === key} aria-controls={`shop-panel-${key}`} tabIndex={section === key ? 0 : -1} onClick={() => chooseSection(key)} onKeyDown={event => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const next = event.key === "Home" ? 0 : event.key === "End" ? 2 : (index + (event.key === "ArrowLeft" ? 1 : 2)) % 3;
          const item = SECTIONS[next]!;
          chooseSection(item.key);
          document.getElementById(`shop-tab-${item.key}`)?.focus();
        }}><ShopIcon kind={icon} size={18} />{title}</button>)}
      </div>
      <div role="tabpanel" id={`shop-panel-${section}`} aria-labelledby={`shop-tab-${section}`} tabIndex={0} className="shop-panel" key={section}>
        {section === "credits" && <div className="shop-panel-content">
          <section className="shop-hero">
            <div className="shop-hero-copy"><span className="shop-eyebrow">هم‌بازی، با انتخاب تو</span><h2>یه درخواست،<br /><em>یه احتمال تازه.</em></h2><p>بازی با دختر، پسر و حالت‌های ویژه؛<br />بسته‌ات رو انتخاب کن و آشنا شو.</p></div>
            <div className="shop-ticket-art" aria-hidden="true"><i className="shop-art-star">✦</i><div className="shop-art-back" /><div className="shop-art-front"><ShopIcon size={36} /><strong>ویژه</strong><span>PLAY YOUR WAY</span><b>✦ ✦ ✦</b></div><i className="shop-art-dot" /></div>
          </section>
          <section>
            <div className="shop-section-heading"><h2>چقدر پایه‌ای؟</h2><small>انتخاب بستهٔ درخواست</small></div>
            <div className="shop-pack-grid" role="group" aria-label="انتخاب بسته">
              {REQUEST_PACKS.map(pack => <button type="button" key={pack.id} className={`shop-pack ${selectedId === pack.id ? "selected" : ""}`} aria-pressed={selectedId === pack.id} onClick={() => setSelectedId(pack.id)}>
                {pack.recommended && <span className="shop-pack-ribbon">پیشنهاد ما</span>}
                <span className="shop-pack-check">{selectedId === pack.id && <ShopIcon kind="check" size={12} />}</span>
                <ShopIcon size={23} /><strong>{faNum(pack.credits)}</strong><span>درخواست ویژه</span><small>{pack.caption}</small>
                <b>{priceFor(pack) === undefined ? "قیمت به‌زودی" : formatToman(priceFor(pack)!)}</b>
                {!!offerFor(pack)?.vip_discount_percent && <small>{faNum(offerFor(pack)!.vip_discount_percent!)}٪ تخفیف VIP اعمال شده</small>}
              </button>)}
            </div>
            <p className="shop-pack-caption">یک بسته برای همهٔ حالت‌های ویژه؛ انتخاب با توئه.</p>
          </section>
          <div className="shop-rule"><ShopIcon kind="shield" /><div><strong>اعتبارت، فقط برای یک بازی واقعی</strong><p>فقط بعد از مچ و شروع تعامل دوطرفه مصرف می‌شه. جستجوی ناموفق، لغو یا خروج سریع هم‌بازی هزینه‌ای نداره.</p></div></div>
          <button type="button" className="shop-vip-teaser" onClick={() => chooseSection("vip")}><span className="shop-entry-icon"><ShopIcon kind="crown" size={27} /></span><div><strong>طلایی بازی کن</strong><span>VIP سی‌روزه + ۱۰ درخواست ویژه</span></div><ShopIcon kind="arrow" size={19} /></button>
          <section className="shop-faq"><h2>قبل از انتخاب بدون</h2>
            <details><summary>اگه کسی پیدا نشد چی؟</summary><p>اعتباری مصرف نمی‌شه. اگر اعتباری برای جستجو کنار گذاشته شده باشه، با لغو یا پایان ناموفق جستجو آزاد می‌شه. خرید بسته، پیدا شدن فوری هم‌بازی رو تضمین نمی‌کنه.</p></details>
            <details><summary>بستهٔ درخواست با VIP چه فرقی داره؟</summary><p>بسته، تعداد مشخصی درخواست ویژه بهت می‌ده. VIP یک عضویت ۳۰روزه با ظاهر طلایی، امکانات اضافه و ۱۰ درخواست در همون دوره است. برای یک درخواست دوبار هزینه نمی‌دی.</p></details>
            <details><summary>چت و بازی معمولی همچنان رایگانه؟</summary><p>بله. چت، دوستی، ارسال فایل و بازی معمولی رایگان می‌مونن. اعتبار ویژه برای انتخاب حالت‌های محدود استفاده می‌شه.</p></details>
          </section>
        </div>}
        {section === "vip" && <div className="shop-panel-content">
          <section className="shop-vip-hero"><span className="shop-vip-label"><ShopIcon kind="crown" size={16} /> عضویت ۳۰ روزه</span><h2>امضای تو، <em>طلایی.</em></h2><p>کمی خاص‌تر دیده شو، بیشتر آشنا شو.</p>
            <div className="shop-profile-preview"><Avatar vip={visualPreview} name={me?.display_name ?? "بازیکن"} photoUrl={me?.avatar_url} avatarKey={me?.avatar || "a1"} size={68} /><strong><VipName vip={visualPreview}>{me?.display_name ?? "پروفایل تو"}</VipName></strong><small>پیش‌نمایش ظاهر پروفایلت</small></div>
          </section>
          {preview && vipActive && <div className="shop-vip-active"><ShopIcon kind="check" /><div><strong>عضویت نمونه فعاله</strong><p>۱۲ روز تا پایان این دوره · تمدید خودکار خاموش</p></div></div>}
          {!preview && <MembershipCard key={me?.id} />}
          <div className="shop-benefits">
            {[
              ["crown", "ظاهر عضویت", perks ? [perks.gold_profile && "نام طلایی", perks.vip_badge && "نشان VIP", perks.exclusive_frame && "قاب اختصاصی"].filter(Boolean).join("، ") || "ظاهر معمولی" : "در حال دریافت مزایا…"],
              ["ticket", "۱۰ فرصت آشنایی در هر دوره", "۱۰ اعتبار ویژه همراه عضویت ۳۰روزه"],
              ["spark", "اولویت منصفانه در صف", perks ? `تا ${faNum(perks.queue_priority_seconds)} ثانیه تقدم؛ بدون تضمین مچ فوری یا کنارگذاشتن فیلترها` : "در حال دریافت…"],
              ["spark", "فرصت بیشتر برای دیده‌شدن", perks ? `${faNum(perks.spotlight_uses)} نوبت Spotlight، هر بار تا ${faNum(perks.spotlight_minutes)} دقیقه در دوره` : "در حال دریافت…"],
              ["wallet", "تخفیف بسته‌های درخواست", perks ? `${faNum(perks.request_discount_percent)}٪ تخفیف هنگام عضویت فعال؛ قیمت نهایی پیش از پرداخت مشخص است` : "در حال دریافت…"],
            ].map(([icon, title, description]) => <div key={title}><span><ShopIcon kind={icon as "crown" | "ticket" | "spark" | "wallet"} /></span><div><strong>{title}</strong><p>{description}</p></div></div>)}
          </div>
          <section className="shop-comparison"><h2>چه چیزی فرق می‌کنه؟</h2><table><thead><tr><th scope="col">امکانات</th><th scope="col">عادی</th><th scope="col">VIP</th></tr></thead><tbody>
            <tr><th scope="row">چت و بازی معمولی</th><td>رایگان</td><td>رایگان</td></tr>
            <tr><th scope="row">اعتبار همراه عضویت</th><td>ندارد</td><td>۱۰ در دوره</td></tr>
            <tr><th scope="row">پروفایل طلایی</th><td>ندارد</td><td>{perks ? perks.gold_profile ? "دارد" : "ندارد" : "—"}</td></tr>
            <tr><th scope="row">اولویت در صف</th><td>عادی</td><td>{perks ? `${faNum(perks.queue_priority_seconds)} ثانیه` : "—"}</td></tr>
            <tr><th scope="row">Spotlight در دوره</th><td>ندارد</td><td>{perks ? faNum(perks.spotlight_uses) : "—"}</td></tr>
            <tr><th scope="row">تخفیف بسته‌ها</th><td>ندارد</td><td>{perks ? `${faNum(perks.request_discount_percent)}٪` : "—"}</td></tr>
          </tbody></table></section>
          <p className="shop-pack-caption">فعلاً در بازی تبلیغی نمایش داده نمی‌شود.</p>
          <div className="shop-rule gold"><ShopIcon kind="shield" /><p>۳۰ روز عضویت؛ تمدید فقط با انتخاب خودت. اعتبارهای جداگانه‌ای که خریدی با پایان VIP حذف نمی‌شن.</p></div>
        </div>}
        {section === "wallet" && <ShopWallet preview={preview} populated={walletPopulated} onBrowse={() => chooseSection("credits")} onOrder={(orderProduct, view) => setPurchase({ product: orderProduct, view })} />}
      </div>
      {preview && <details className="shop-design-tools"><summary>حالت‌های پیش‌نمایش طراحی</summary><p>این کنترل‌ها فقط برای بررسی طرح‌اند.</p><div>
        <button type="button" onClick={() => { chooseSection("credits"); setLimitOpen(true); }}>کمبود اعتبار</button>
        <button type="button" onClick={() => { setWalletPopulated(false); chooseSection("wallet"); }}>کیف خالی</button>
        <button type="button" onClick={() => { setWalletPopulated(true); chooseSection("wallet"); }}>کیف با تراکنش</button>
        <button type="button" onClick={() => { setVipActive(value => !value); chooseSection("vip"); }}>{vipActive ? "VIP غیرفعال" : "VIP فعال"}</button>
        <button type="button" onClick={() => setPurchase({ product, view: "pending" })}>وضعیت‌های پرداخت</button>
      </div></details>}
    </div>
    {purchase && (!preview && catalog?.payment_enabled && offerFor(purchase.product)
      ? <LivePurchaseSheet offer={offerFor(purchase.product)!} onClose={() => setPurchase(null)} />
      : <PurchaseSheet product={purchase.product} price={priceFor(purchase.product)} preview={preview} initialView={purchase.view} onClose={() => setPurchase(null)} onWallet={() => { setPurchase(null); chooseSection("wallet"); }} />)}
    {limitOpen && <CreditLimitSheet preview modeTitle="بازی با دختر" onClose={() => setLimitOpen(false)} />}
  </Screen>;
}
