import { Link } from "react-router-dom";
import { ShopIcon } from "./ShopIcon";
import "./shop.css";

export function ShopEntry() {
  return <Link to="/shop" className="shop-profile-entry">
    <span className="shop-entry-icon"><ShopIcon kind="crown" size={27} /></span>
    <div><strong>فروشگاه؛ یه رنگ تازه به بازی</strong><span>درخواست ویژه، VIP و کیف اعتبار</span></div>
    <ShopIcon kind="arrow" size={19} />
  </Link>;
}
