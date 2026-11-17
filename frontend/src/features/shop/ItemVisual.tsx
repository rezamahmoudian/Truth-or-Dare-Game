import type { DigitalItem } from "@/lib/billingApi";
import { Avatar } from "@/ui/Avatar";

const icons: Record<string, string> = { rose: "🌹", coffee: "☕", star: "⭐", moon: "🌙", spark: "✨", party: "🥳", highfive: "🙌", wow: "🤩", cards: "🃏", spotlight: "✦", sparkle: "✨", hearts: "♡", forest: "🌿", sunset: "🌅", midnight: "🌌" };
export function ItemVisual({ item }: { item: Pick<DigitalItem, "kind" | "visual"> }) {
  if (item.kind === "FRAME") return <Avatar avatarKey="a4" name="تو" size={48} vip={{ user_id: -2, as_of: "", active: false, ends_at: null, gold_profile: false, vip_badge: false, exclusive_frame: false, cosmetics: { FRAME: { visual: item.visual, title: "قاب" } } }} />;
  if (item.kind === "NAME") return <span className={`item-name-${item.visual} text-xl font-black`}>نام تو</span>;
  return <span aria-hidden className="text-4xl">{icons[item.visual] ?? (item.kind === "REACTION" ? item.visual : "✦")}</span>;
}
