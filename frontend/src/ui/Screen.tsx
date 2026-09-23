import type { ReactNode } from "react";

/**
 * The fixed three-band shell every screen uses: pinned header, one internally
 * scrolling region, pinned footer. The page itself never scrolls, which is what
 * stops the composer drifting off-screen when the mobile keyboard opens.
 */
export function Screen({
  header,
  footer,
  children,
  scroll = true,
}: {
  header?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  scroll?: boolean;
}) {
  return (
    <div className="flex h-[100dvh] flex-col">
      {header}
      <main
        className={`flex-1 ${scroll ? "overflow-y-auto overscroll-contain" : "overflow-hidden"}`}
      >
        {children}
      </main>
      {footer}
    </div>
  );
}

export function Header({
  title,
  subtitle,
  action,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header
      className="bar-blur flex shrink-0 items-center gap-3 border-b border-line-soft px-4 pb-3"
      style={{ paddingTop: "max(0.75rem, env(safe-area-inset-top))" }}
    >
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-[20px] font-extrabold tracking-tight">{title}</h1>
        {subtitle && (
          <div className="truncate text-[12px] leading-tight text-faint">{subtitle}</div>
        )}
      </div>
      {action}
    </header>
  );
}

/**
 * Empty states carry a mark and one line of guidance, not just an apology.
 * "You have nothing" is a dead end; "here is where things come from" is not.
 */
export function EmptyState({
  glyph,
  title,
  hint,
  action,
}: {
  glyph: string;
  title: string;
  hint: string;
  action?: ReactNode;
}) {
  return (
    <div className="animate-fade-in flex h-full flex-col items-center justify-center gap-3 px-10 text-center">
      <span className="grid size-20 place-items-center rounded-full bg-surface-2 text-4xl">
        {glyph}
      </span>
      <p className="text-[17px] font-bold">{title}</p>
      <p className="text-[14px] leading-relaxed text-muted">{hint}</p>
      {action && <div className="mt-2 w-full max-w-xs">{action}</div>}
    </div>
  );
}

/** Grey blocks in the shape of the thing that is loading, not a spinner. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <span
      className={`block animate-pulse-soft rounded-md bg-surface-2 ${className}`}
      aria-hidden
    />
  );
}
