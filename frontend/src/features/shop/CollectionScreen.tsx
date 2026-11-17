import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "@/lib/auth";
import { getCatalog, getGiftLeaders, equipItem, consumeItem, type Catalog, type DigitalItem, type Offer } from "@/lib/billingApi";
import { faNum } from "@/lib/dates";
import { useSession } from "@/store/session";
import { socket } from "@/lib/ws";
import { Avatar } from "@/ui/Avatar";
import { VipName } from "@/ui/Vip";
import { Header, Screen } from "@/ui/Screen";
import { TabBar } from "@/ui/TabBar";
import { useInventory, itemActionKey, finishItemAction, pendingItemAction } from "./useInventory";
import { ItemVisual } from "./ItemVisual";
import { LivePurchaseSheet } from "./LivePurchaseSheet";
import { formatToman } from "./catalog";
import "./shop.css";

const sections = [{ key: "all", title: "همه" }, { key: "looks", title: "استایل" }, { key: "PACK", title: "سؤال‌ها" }, { key: "GIFT", title: "هدیه" }, { key: "SPOTLIGHT", title: "Spotlight" }, { key: "mine", title: "مجموعهٔ من" }];
const permanent = (kind: string) => !["GIFT", "SPOTLIGHT"].includes(kind);
const equippable = ["FRAME", "NAME", "BADGE", "THEME", "EFFECT"];

export function CollectionScreen() {
  const { data, error: inventoryError, load } = useInventory();
  const me = useSession(s => s.user);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [offer, setOffer] = useState<Offer | null>(null);
  const [leaders, setLeaders] = useState<Awaited<ReturnType<typeof getGiftLeaders>>["results"] | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [leadersError, setLeadersError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const version = useRef(0);
  const invalidate = useCallback(() => { version.current++; }, []);
  const reload = useCallback(async () => {
    const current = ++version.current;
    setRefreshing(true);
    await Promise.all([
      getCatalog().then(value => { if (current === version.current) { setCatalog(value); setCatalogError(""); } })
        .catch(() => { if (current === version.current) setCatalogError("فروشگاه به‌روز نشد؛ دوباره تلاش کن."); }),
      getGiftLeaders().then(value => { if (current === version.current) { setLeaders(value.results); setLeadersError(""); } })
        .catch(() => { if (current === version.current) setLeadersError("فهرست هدیه‌ها دریافت نشد."); }),
    ]);
    if (current === version.current) setRefreshing(false);
  }, []);
  useEffect(() => {
    setCatalog(null); setLeaders(null); setOffer(null); setError(""); setNotice("");
    void reload();
    const off = socket.onEvent(type => { if (type === "billing.changed") void reload(); });
    const resume = socket.onResume(() => void reload());
    const visible = () => { if (document.visibilityState === "visible") { void reload(); void load(); } };
    document.addEventListener("visibilitychange", visible);
    return () => { invalidate(); off(); resume(); document.removeEventListener("visibilitychange", visible); };
  }, [reload, load, invalidate, me?.id]);
  const spotlightScope = (id: number) => `${me?.id}:${id}:spotlight`;
  const ownedIds = new Set(data?.items.map(row => row.item.id));
  const catalogItems = catalog?.items ?? [];
  const items = filter === "mine" ? [...new Map(data?.items.map(row => [row.item.id, { ...row.item, description: "", product_key: "" }])).values()] : catalogItems.filter(item => filter === "all" || item.kind === filter || (filter === "looks" && !["PACK", "GIFT", "SPOTLIGHT"].includes(item.kind)));
  async function activate(item: DigitalItem) {
    const row = (item.kind === "SPOTLIGHT" ? data?.items.find(g => g.item.id === item.id && pendingItemAction(spotlightScope(g.id))) : null)
      ?? data?.items.find(g => g.item.id === item.id && (permanent(item.kind) || g.remaining > 0));
    if (!row || busy) return;
    setBusy(item.id); setError(""); setNotice("");
    try {
      if (equippable.includes(item.kind)) {
        await equipItem(item.kind, row.equipped ? null : row.id);
        setNotice(row.equipped ? "ظاهر پیش‌فرض برگشت." : "استایل جدیدت فعال شد.");
      } else if (item.kind === "SPOTLIGHT") {
        const scope = spotlightScope(row.id);
        await consumeItem(row.id, itemActionKey(scope)); finishItemAction(scope);
        setNotice("فعال‌سازی ثبت شده است؛ زمان پایان را در مجموعه ببین.");
      }
      await load();
    } catch (e) { setError(e instanceof ApiError ? e.firstMessage ?? "انجام نشد." : "نتیجه نامشخص است؛ دوباره همین اقدام را بررسی کن."); }
    finally { setBusy(null); }
  }
  return <Screen className="shop-screen" header={<Header title="کلکسیون بی‌هوا" action={<Link className="min-h-11 content-center text-sm" to="/shop">فروشگاه ←</Link>} />} footer={<TabBar />}>
    <div className="shop-content">
      <section className="collection-hero"><span>به سلیقهٔ خودت</span><h1>یه امضا از تو.</h1><p>استایلت رو پیدا کن، به رفیقت هدیه بده<br />و حرف‌های تازه رو شروع کن.</p><i aria-hidden>✧</i></section>
      <div className="collection-filters" aria-label="دسته‌های کلکسیون">{sections.map(section => <button type="button" key={section.key} aria-pressed={section.key === filter} onClick={() => setFilter(section.key)}>{section.title}</button>)}</div>
      {!catalog && !catalogError && <p className="text-sm text-muted">در حال دریافت کلکسیون…</p>}
      {catalog && !catalog.payment_enabled && <p className="shop-launch-note">خرید هنوز فعال نیست؛ آیتم‌های مجموعه‌ات قابل استفاده‌اند.</p>}
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      {(catalogError || inventoryError) && <p role="alert" className="text-sm text-bad">{catalogError || inventoryError} <button disabled={refreshing} className="min-h-11 underline" type="button" onClick={() => { void reload(); void load(); }}>تلاش دوباره</button></p>}
      {notice && <p role="status" className="text-sm text-hot">{notice}</p>}
      {data?.spotlight_ends_at && Date.parse(data.spotlight_ends_at) > Date.now() && <p className="shop-rule text-sm">✦ Spotlight فعال تا {new Intl.DateTimeFormat("fa-IR", { timeStyle: "short" }).format(new Date(data.spotlight_ends_at))}</p>}
      {filter === "mine" && !data && !inventoryError && <p className="text-sm text-muted">در حال دریافت مجموعهٔ تو…</p>}
      {filter === "mine" && data && items.length === 0 && <div className="shop-empty"><h2>مجموعه‌ات منتظر اولین انتخابته</h2><p>آیتم‌های خریداری‌شده اینجا می‌مانند.</p></div>}
      <div className="collection-grid">{items.map(item => {
        const availableOffer = catalog?.offers.find(o => o.product.item?.id === item.id);
        const mine = data?.items.filter(g => g.item.id === item.id) ?? [];
        const count = mine.reduce((sum, row) => sum + row.remaining, 0);
        const equipped = mine.some(row => row.equipped);
        const owned = ownedIds.has(item.id);
        const pendingSpotlight = item.kind === "SPOTLIGHT" && mine.some(row => pendingItemAction(spotlightScope(row.id)));
        return <article className={`collection-card ${equipped ? "equipped" : ""}`} key={item.id}>
          <div className={`collection-art collection-art-${item.kind.toLowerCase()}`}><ItemVisual item={item} /></div>
          <h2>{item.title}</h2><p>{item.description || (permanent(item.kind) ? "از مجموعهٔ تو؛ مالکیت دائمی" : `${faNum(count)} نوبت باقی‌مانده`)}</p>
          {item.kind === "PACK" && <small>{item.prompt_count ? `${faNum(item.prompt_count)} سؤال تأییدشده` : "سؤال‌ها در انتظار بازبینی"}</small>}
          <small>{item.kind === "SPOTLIGHT" ? `هر نوبت ${faNum(item.spotlight_minutes)} دقیقه` : permanent(item.kind) ? "دائمی · بدون تمدید" : `${faNum(item.units)} هدیه در هر خرید`}</small>
          {owned && <span className="collection-owned">{equipped ? "✓ فعال روی پروفایلت" : permanent(item.kind) ? "✓ در مجموعهٔ تو" : `${faNum(count)} نوبت داری`}</span>}
          {item.kind === "SPOTLIGHT" && count > 0 && <small>نوبت موجود بعدی: {faNum(mine.find(row => row.remaining > 0)!.item.spotlight_minutes)} دقیقه</small>}
          {owned && equippable.includes(item.kind) && <button type="button" disabled={busy !== null} onClick={() => void activate(item)}>{busy === item.id ? "در حال بررسی…" : equipped ? "بازگشت به پیش‌فرض" : "استفاده از این استایل"}</button>}
          {item.kind === "SPOTLIGHT" && (count > 0 || pendingSpotlight) && <button type="button" disabled={busy !== null} onClick={() => void activate(item)}>{busy === item.id ? "در حال بررسی…" : pendingSpotlight ? "بررسی فعال‌سازی قبلی" : "فعال‌سازی یک نوبت"}</button>}
          {owned && ["GIFT", "STICKER", "REACTION", "PACK"].includes(item.kind) && <Link className="collection-action" to="/chats">{item.kind === "PACK" ? "انتخاب از دکمهٔ بازی در چت" : "استفاده در چت"}</Link>}
          {(!owned || !permanent(item.kind)) && <button type="button" disabled={!data || !availableOffer || !catalog?.payment_enabled} onClick={() => availableOffer && setOffer(availableOffer)}>{availableOffer ? `خرید · ${formatToman(availableOffer.amount / 10)}` : "به‌زودی"}</button>}
        </article>;
      })}</div>
      <section className="collection-leaders"><h2>رفیق‌های ستاره‌دار این ماه</h2><p>بر اساس تعداد هدیه‌های دریافتی؛ هدیه‌ها ارزش نقدی ندارند.</p>{leadersError ? <p role="alert">{leadersError} <button disabled={refreshing} className="shop-text-button" type="button" onClick={() => void reload()}>تلاش دوباره</button></p> : leaders === null ? <small>در حال دریافت…</small> : leaders.length ? leaders.map((row, index) => <Link key={row.user.id} to={`/people/${row.user.id}`}><span>{faNum(index + 1)}</span><Avatar vip={row.user.vip} name={row.user.display_name} avatarKey={row.user.avatar} photoUrl={row.user.avatar_url} size={34} /><strong><VipName vip={row.user.vip}>{row.user.display_name}</VipName></strong><small>{faNum(row.gifts)} هدیه</small></Link>) : <small>هنوز هدیه‌ای در این ماه ثبت نشده.</small>}</section>
    </div>
    {offer && <LivePurchaseSheet offer={offer} onClose={() => setOffer(null)} />}
  </Screen>;
}
