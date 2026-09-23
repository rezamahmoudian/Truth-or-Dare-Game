import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "ghost" | "success" | "danger";

const VARIANTS: Record<Variant, string> = {
  // A gradient rather than a flat fill: on a dark screen a single solid violet
  // reads as a sticker, while a two-stop fill gives the button a lit top edge
  // and a shadow that belongs to it.
  primary:
    "bg-gradient-to-b from-brand-soft to-brand text-white shadow-[0_6px_18px_-8px_var(--color-brand)]",
  success:
    "bg-gradient-to-b from-ok to-ok-deep text-ink shadow-[0_6px_18px_-8px_var(--color-ok)]",
  danger: "bg-bad text-white",
  ghost: "surface-raised text-text",
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  busy?: boolean;
  size?: "md" | "lg";
};

export function Button({
  variant = "primary",
  busy = false,
  size = "md",
  disabled,
  children,
  className = "",
  ...rest
}: Props) {
  // min-h keeps every tappable control above the 44px floor without having to
  // remember it per button.
  const height = size === "lg" ? "min-h-14 text-[17px]" : "min-h-12 text-[15px]";

  return (
    <button
      {...rest}
      disabled={disabled || busy}
      className={`press inline-flex w-full items-center justify-center gap-2 rounded-field px-5 font-bold disabled:opacity-40 disabled:shadow-none ${height} ${VARIANTS[variant]} ${className}`}
    >
      {busy ? <Spinner /> : children}
    </button>
  );
}

function Spinner() {
  return (
    <span className="inline-flex gap-1" aria-label="در حال انجام">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="size-1.5 animate-pulse-soft rounded-full bg-current"
          style={{ animationDelay: `${i * 0.18}s` }}
        />
      ))}
    </span>
  );
}
