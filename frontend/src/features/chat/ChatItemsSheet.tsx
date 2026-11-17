import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "@/lib/auth";
import { consumeItem, type OwnedItem } from "@/lib/billingApi";
import { faNum } from "@/lib/dates";
import type { Conversation } from "@/lib/types";
import { useSession } from "@/store/session";
import { useChat } from "@/store/chat";
import { ItemVisual } from "@/features/shop/ItemVisual";
import { ShopSheet } from "@/features/shop/ShopSheet";
import { useInventory, itemActionKey, finishItemAction, pendingItemAction } from "@/features/shop/useInventory";
import "@/features/shop/shop.css";

export function ChatItemsSheet({ conversation, onClose }: { conversation: Conversation; onClose: () => void }) {
  const me = useSession(s => s.user);
  const { data, error: loadError, load } = useInventory();
  const [kind, setKind] = useState("GIFT");
  const recipients = conversation.participants.filter(p => p.id !== me?.id && !p.is_ai);
  const [recipient, setRecipient] = useState(recipients[0]?.id);
  const [selected, setSelected] = useState<OwnedItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const actionScope = (id: number) => `${me?.id}:${id}:${conversation.id}:${kind === "GIFT" ? recipient : "sticker"}`;
  const available = data?.items.filter(row => row.item.kind === kind && (row.remaining > 0 || pendingItemAction(actionScope(row.id))));
  return <ShopSheet title="یه چیز قشنگ بفرست" onClose={() => { if (!busy) onClose(); }}>
    <div className="collection-filters">{["GIFT", "STICKER"].map(value => <button type="button" disabled={busy} aria-pressed={kind === value} key={value} onClick={() => { setKind(value); setSelected(null); setNotice(""); }}>{value === "GIFT" ? "هدیه" : "استیکر"}</button>)}</div>
    {kind === "GIFT" && <label className="block text-sm">برای کی؟<select className="my-3 min-h-11 w-full rounded-xl bg-surface p-2" value={recipient ?? ""} disabled={busy} onChange={e => { setRecipient(Number(e.target.value)); setSelected(null); setError(""); setNotice(""); }}><option value="" disabled>گیرنده را انتخاب کن</option>{recipients.map(p => <option key={p.id} value={p.id}>{p.display_name}</option>)}</select></label>}
    {kind === "GIFT" && recipients.length === 0 && <p className="shop-sheet-copy">هدیه برای بازیکن انسانی دیگر در همین چت قابل ارسال است.</p>}
    <div className="chat-item-grid">{available?.map(row => <button type="button" disabled={busy} aria-pressed={selected?.id === row.id} key={row.id} onClick={() => setSelected(row)}><ItemVisual item={row.item} /><strong>{row.item.title}</strong><small>{pendingItemAction(actionScope(row.id)) ? "ارسال قبلی نیاز به بررسی دارد" : kind === "GIFT" ? `${faNum(row.remaining)} عدد` : "نامحدود"}</small></button>)}</div>
    {!data && !loadError && <p className="shop-sheet-copy">در حال دریافت مجموعه…</p>}
    {data && !available?.length && <p className="shop-sheet-copy">هنوز {kind === "GIFT" ? "هدیه‌ای برای ارسال" : "استیکری"} در مجموعه‌ات نداری.</p>}
    {(error || loadError) && <p className="text-sm text-bad" role="alert">{error || loadError}</p>}
    {loadError && <button type="button" disabled={busy} className="shop-text-button" onClick={() => void load()}>دریافت دوبارهٔ مجموعه</button>}
    {notice && <p className="text-sm text-hot" role="status">{notice}</p>}
    {selected && <button type="button" className="shop-primary" disabled={busy || (kind === "GIFT" && !recipient)} onClick={async () => {
      setBusy(true); setError(""); setNotice("");
      const target = kind === "GIFT" ? recipient : undefined;
      const scope = actionScope(selected.id);
      try {
        const result = await consumeItem(selected.id, itemActionKey(scope), conversation.id, target);
        if (result.message) useChat.getState().receiveMessage(result.message);
        finishItemAction(scope); setSelected(null); setNotice("فرستاده شد ✓"); await load();
      } catch (e) { setError(e instanceof ApiError ? e.firstMessage ?? "ارسال نشد." : "نتیجه نامشخص است؛ دوباره ارسال را بررسی کن. موجودی دوباره کم نمی‌شود."); }
      finally { setBusy(false); }
    }}>{busy ? "در حال بررسی…" : pendingItemAction(actionScope(selected.id)) ? "بررسی ارسال قبلی" : kind === "GIFT" ? `ارسال یک ${selected.item.title}` : "ارسال استیکر"}</button>}
    <Link className="shop-text-button" to="/shop/items">دیدن کلکسیون</Link>
  </ShopSheet>;
}
