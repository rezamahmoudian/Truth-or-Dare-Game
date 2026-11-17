export function ShopIcon({ kind = "ticket", size = 24 }: { kind?: "ticket" | "crown" | "wallet" | "shield" | "check" | "clock" | "arrow" | "close" | "spark"; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {kind === "ticket" && <><path d="M3 5h18v5a2 2 0 0 0 0 4v5H3v-5a2 2 0 0 0 0-4Z" /><path d="M15 5v3m0 3v2m0 3v3M7 9h4m-4 5h3" /></>}
    {kind === "crown" && <><path d="m3 6 4 4 5-7 5 7 4-4-2 12H5ZM6 21h12" /><path d="m10 13 2-2 2 2-2 2Z" /></>}
    {kind === "wallet" && <><path d="M20 8V5H5a2 2 0 0 0 0 4h16v11H5a2 2 0 0 1-2-2V7" /><path d="M21 12h-6v5h6m-3-2.5h.1" /></>}
    {kind === "shield" && <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z" /><path d="m8 12 3 3 5-6" /></>}
    {kind === "check" && <path d="m5 12 4 4L19 6" />}
    {kind === "clock" && <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>}
    {kind === "arrow" && <path d="m10 5 7 7-7 7M17 12H3" />}
    {kind === "close" && <path d="m6 6 12 12M6 18 18 6" />}
    {kind === "spark" && <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z" /><path d="M20 2v4m-2-2h4" /></>}
  </svg>;
}
