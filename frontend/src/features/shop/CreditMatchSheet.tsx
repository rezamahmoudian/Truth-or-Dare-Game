import { useEffect, useState } from "react";
import { ApiError } from "@/lib/auth";
import { getWallet, type CreditWallet } from "@/lib/billingApi";
import { faNum } from "@/lib/dates";
import { ShopSheet } from "./ShopSheet";
import { ShopIcon } from "./ShopIcon";

export function CreditMatchSheet({ modeTitle, onClose, onStart }: {
  modeTitle: string; onClose: () => void; onStart: () => Promise<void>;
}) {
  const [wallet, setWallet] = useState<CreditWallet | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    void getWallet().then(value => { if (active) setWallet(value); }).catch(() => { if (active) setError("موجودی دریافت نشد؛ صفحه را ببند و دوباره امتحان کن."); });
    return () => { active = false; };
  }, []);
  return <ShopSheet title="شروع با اعتبار ویژه" onClose={() => { if (!busy) onClose(); }}>
    <div className="shop-limit-art"><ShopIcon size={40} /><span>۱</span></div>
    <h3 className="shop-sheet-heading">{modeTitle}</h3>
    <p className="shop-sheet-copy">یک اعتبار برای جستجو کنار گذاشته می‌شود. پس از دقیقهٔ اول مچ، فقط اگر هر دو نفر پیام بدهید، مصرف می‌شود.</p>
    <div className="shop-rule"><ShopIcon kind="shield" /><p>لغو، پیدا نشدن یا خروج سریع هم‌بازی هزینه‌ای ندارد. فیلتر انتخابت حفظ می‌شود و این درخواست به بازیکن انسانی وصل می‌شود.</p></div>
    <p className="shop-coming-note" aria-live="polite">{wallet ? `${faNum(wallet.available)} اعتبار قابل‌استفاده · ${faNum(wallet.reserved)} رزروشده` : "در حال دریافت موجودی…"}</p>
    {error && <p className="text-sm text-bad" role="alert">{error}</p>}
    <button type="button" className="shop-primary disabled:opacity-50" disabled={busy || !wallet?.available} onClick={async () => {
      setBusy(true); setError(null);
      try { await onStart(); }
      catch (err) { setError(err instanceof ApiError ? err.firstMessage ?? "شروع نشد؛ دوباره امتحان کن." : "ارتباط برقرار نشد؛ دوباره امتحان کن."); void getWallet().then(setWallet).catch(() => undefined); }
      finally { setBusy(false); }
    }}>{busy ? "در حال شروع…" : "رزرو ۱ اعتبار و شروع جستجو"}</button>
    <button type="button" className="shop-text-button" disabled={busy} onClick={onClose}>فعلاً نه</button>
  </ShopSheet>;
}
