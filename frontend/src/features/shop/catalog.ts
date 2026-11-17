/** Phase-one display data. Prices are intentionally absent until server catalog delivery. */
export type ShopProduct = {
  id: string;
  title: string;
  kind: "credits" | "vip";
  credits: number;
  caption: string;
  recommended?: boolean;
};

export const REQUEST_PACKS: ShopProduct[] = [
  { id: "requests-3", title: "بستهٔ ۳ درخواست", kind: "credits", credits: 3, caption: "برای شروع" },
  { id: "requests-10", title: "بستهٔ ۱۰ درخواست", kind: "credits", credits: 10, caption: "برای آشنایی‌های بیشتر", recommended: true },
  { id: "requests-30", title: "بستهٔ ۳۰ درخواست", kind: "credits", credits: 30, caption: "برای همیشه‌پایه‌ها" },
];
export const VIP: ShopProduct = { id: "vip-30", title: "VIP سی‌روزه", kind: "vip", credits: 10, caption: "یه امضای طلایی برای پروفایلت" };

export type PaymentView = "review" | "pending" | "success" | "failed" | "offline" | "unverified" | "delayed" | "duplicate";
export const PAYMENT_LABELS: Record<PaymentView, string> = {
  review: "مرور سفارش", pending: "در حال بررسی", success: "پرداخت موفق", failed: "پرداخت ناموفق",
  offline: "قطع اینترنت", unverified: "بازگشت بدون تأیید", delayed: "تحویل با تأخیر", duplicate: "درخواست تکراری",
};
export const formatToman = (amount: number) => `${new Intl.NumberFormat("fa-IR").format(amount)} تومان`;
