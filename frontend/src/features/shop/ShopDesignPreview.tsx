import { useEffect } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { ShopScreen } from "./ShopScreen";

// Local design fixtures only. Never used as prices, balances or entitlements by the app.
const EXAMPLE_PRICES_TOMAN = { "requests-3": 29000, "requests-10": 79000, "requests-30": 199000, "vip-30": 149000 };
export default function ShopDesignPreview() {
  return <BrowserRouter><Routes><Route path="/design/shop" element={<ShopScreen previewPrices={EXAMPLE_PRICES_TOMAN} />} /><Route path="*" element={<ExitPreview />} /></Routes></BrowserRouter>;
}

function ExitPreview() {
  const location = useLocation();
  useEffect(() => { window.location.replace(`${location.pathname}${location.search}${location.hash}`); }, [location]);
  return <p className="p-6 text-center">در حال برگشت به بازی…</p>;
}
