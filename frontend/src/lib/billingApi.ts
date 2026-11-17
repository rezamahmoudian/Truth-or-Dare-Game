import { authFetch } from "@/lib/auth";

export type CreditWallet = {
  total: number; reserved: number; available: number;
  by_source: Record<string, { total: number; reserved: number; available: number }>;
  vip: { active: boolean; ends_at: string | null };
};
export type CreditEntry = {
  id: number; kind: "GRANT" | "RESERVE" | "RELEASE" | "CONSUME" | "EXPIRE" | "ADJUST";
  delta: number; reserved_delta: number; reason: string; created_at: string;
  balance_after: number; reserved_after: number;
};
export const getWallet = () => authFetch<CreditWallet>("/billing/wallet/");
export const getLedger = (page = 1) => authFetch<{ results: CreditEntry[]; next: string | null }>(`/billing/ledger/?page=${page}`);

export type Offer = {
  vip_discount_percent?: number; base_amount?: number;
  id: number; amount: number; currency: "IRR";
  product: { key: string; title: string; kind: "CREDITS" | "VIP" | "ITEM"; credits: number; duration_days: number; benefits?: VipBenefits; item?: DigitalItem };
};
export type Catalog = { payment_enabled: boolean; offers: Offer[]; items?: (DigitalItem & { product_key: string; description: string })[]; vip_preview?: { benefits: VipBenefits } };

export type DigitalItem = { id: number; kind: "FRAME" | "NAME" | "BADGE" | "THEME" | "EFFECT" | "STICKER" | "REACTION" | "SPOTLIGHT" | "PACK" | "GIFT"; visual: string; title: string; units: number; spotlight_minutes: number; prompt_count?: number };
export type OwnedItem = { id: number; item: DigitalItem; remaining: number; equipped: boolean };
export type Inventory = { items: OwnedItem[]; slots: Record<string, { visual: string; title: string; grant_id: number }>; spotlight_ends_at: string | null };
export const getInventory = () => authFetch<Inventory>("/billing/inventory/");
export const equipItem = (slot: string, grantId: number | null) => authFetch<Inventory>("/billing/inventory/equip/", { method: "POST", body: JSON.stringify({ slot, grant_id: grantId }) });
export const consumeItem = (grantId: number, key: string, conversationId?: string, recipientId?: number) => authFetch<{ inventory: Inventory; message: import("./types").Message | null }>("/billing/inventory/use/", { method: "POST", body: JSON.stringify({ grant_id: grantId, idempotency_key: key, conversation_id: conversationId, recipient_id: recipientId }) });
export const getGiftLeaders = () => authFetch<{ results: { user: import("./types").Person; gifts: number }[] }>("/billing/gift-leaders/");

export type VipBenefits = {
  gold_profile: boolean; vip_badge: boolean; exclusive_frame: boolean; ad_free: boolean;
  queue_priority_seconds: number; request_discount_percent: number; spotlight_uses: number; spotlight_minutes: number;
};
export type Membership = import("./types").PublicVIP & {
  starts_at: string | null; benefits: Partial<VipBenefits>; auto_renew: false;
  next_period: { starts_at: string; ends_at: string } | null;
  spotlight: { remaining: number; ends_at: string | null };
};
export const getMembership = () => authFetch<Membership>("/billing/vip/");
export const activateSpotlight = (key: string) => authFetch<Membership>("/billing/vip/spotlight/", { method: "POST", body: JSON.stringify({ idempotency_key: key }) });
export type Payment = {
  attempt_id: string | null;
  order_id: string; state: "NOT_STARTED" | "READY" | "PENDING" | "FAILED" | "EXPIRED" | "DELIVERING" | "FULFILLED" | "REVIEW";
  redirect_url: string | null; can_start: boolean;
};
export type BillingOrder = {
  id: string; amount: number; currency: "IRR"; status: "PENDING" | "PAID" | "FULFILLED";
  product_snapshot: { title: string; credits: number; kind: "CREDITS" | "VIP" | "ITEM"; duration_days: number; item?: DigitalItem };
  created_at: string; expires_at: string; payment: Payment;
};
export type OrderSummary = Omit<BillingOrder, "payment">;
export const getCatalog = () => authFetch<Catalog>("/billing/catalog/");
export const getOrder = (id: string) => authFetch<BillingOrder>(`/billing/orders/${encodeURIComponent(id)}/`);
export const listOrders = (page = 1) => authFetch<{ results: OrderSummary[]; next: string | null }>(`/billing/orders/?page=${page}`);
export const createOrder = (offerId: number, key: string) => authFetch<OrderSummary>("/billing/orders/", { method: "POST", body: JSON.stringify({ offer_id: offerId, idempotency_key: key }) });
export const startPayment = (id: string, key: string) => authFetch<Payment>(`/billing/orders/${encodeURIComponent(id)}/payment/`, { method: "POST", body: JSON.stringify({ idempotency_key: key }) });
export const checkPayment = (id: string) => authFetch<Payment>(`/billing/orders/${encodeURIComponent(id)}/check/`, { method: "POST" });
export const paymentKey = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("");
