export const AVATAR_KEYS = Array.from({ length: 12 }, (_, i) => `a${i + 1}`);

/**
 * Preset avatars are drawn, not uploaded. Phase 1 has no image moderation, and
 * a product that matches strangers cannot safely accept arbitrary profile
 * photos before it can review them.
 *
 * Hues are spaced around the wheel but pulled away from the 50–80° band, where
 * a saturated fill turns muddy yellow-green and looks like a rendering fault
 * rather than a choice.
 */
const HUES: Record<string, number> = Object.fromEntries(
  AVATAR_KEYS.map((key, i) => {
    const raw = Math.round((320 / AVATAR_KEYS.length) * i);
    return [key, raw > 45 ? raw + 40 : raw];
  }),
);

type Props = {
  avatarKey: string;
  name?: string;
  size?: number;
  selected?: boolean;
  /** A soft ring in the same hue; used where the avatar is the focal point. */
  glow?: boolean;
};

export function Avatar({
  avatarKey,
  name = "",
  size = 48,
  selected,
  glow = false,
}: Props) {
  const hue = HUES[avatarKey] ?? 260;
  const initial = name.trim().charAt(0) || "؟";

  return (
    <span
      className={`press inline-grid shrink-0 place-items-center rounded-full font-extrabold text-white ${
        selected ? "ring-2 ring-brand ring-offset-2 ring-offset-surface" : ""
      }`}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.4,
        background: `linear-gradient(145deg, hsl(${hue} 78% 64%), hsl(${(hue + 35) % 360} 72% 46%))`,
        // An inner highlight along the top edge so the circle reads as a solid
        // object rather than a flat swatch.
        boxShadow: glow
          ? `inset 0 1px 0 rgb(255 255 255 / 35%), 0 0 0 4px hsl(${hue} 70% 55% / 12%)`
          : "inset 0 1px 0 rgb(255 255 255 / 30%)",
      }}
      aria-hidden={!name}
    >
      {initial}
    </span>
  );
}
