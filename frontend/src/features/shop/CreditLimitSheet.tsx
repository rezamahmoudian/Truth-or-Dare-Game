import { Link } from "react-router-dom";
import { ShopSheet } from "./ShopSheet";
import { ShopIcon } from "./ShopIcon";

export function CreditLimitSheet({ modeTitle, onClose, preview = false }: { modeTitle: string; onClose: () => void; preview?: boolean }) {
  return <ShopSheet title="یه فرصت دیگه برای آشنایی" onClose={onClose}>
    <div className="shop-limit-art"><ShopIcon size={40} /><span>+۱</span></div>
    <h3 className="shop-sheet-heading">سهمیهٔ {modeTitle} تموم شده</h3>
    <p className="shop-sheet-copy">با اعتبار درخواست ویژه می‌تونی دوباره این حالت رو انتخاب کنی. هر مچ موفق، یک اعتبار.</p>
    <div className="shop-rule"><ShopIcon kind="shield" /><p>جستجوی بی‌نتیجه، لغو صف یا خروج سریع هم‌بازی، اعتباری ازت کم نمی‌کنه.</p></div>
    <p className="shop-coming-note">خرید اعتبار به‌زودی فعال می‌شه. تا اون موقع، حالت‌های رایگان در دسترسن.</p>
    {preview ? <button type="button" className="shop-primary" onClick={onClose}>دیدن بسته‌های ویژه</button> : <Link className="shop-primary" to="/shop">دیدن بسته‌های ویژه</Link>}
    <button type="button" className="shop-text-button" onClick={onClose}>برگشت به انتخاب بازی</button>
  </ShopSheet>;
}
