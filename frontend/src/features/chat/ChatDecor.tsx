export function ChatIcon({ name }: { name: "search" | "edit" | "more" | "smile" | "arrow" | "group" }) {
  return <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === "search" && <><circle cx="10.5" cy="10.5" r="7" /><path d="m16 16 5 5" /></>}
    {name === "edit" && <><path d="M13 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-8M16 3l5 5-9 9-5 1 1-5 8-9Z" /></>}
    {name === "more" && <>{[5,12,19].map(y => <circle key={y} cx="12" cy={y} r="1" />)}</>}
    {name === "smile" && <><circle cx="12" cy="12" r="9" /><path d="M8 14a4 4 0 0 0 8 0M8 8h.01M16 8h.01" /></>}
    {name === "arrow" && <path d="M20 12H4m6-6-6 6 6 6" />}
    {name === "group" && <><circle cx="9" cy="8" r="3" /><path d="M2 20v-2a7 7 0 0 1 14 0v2H2Zm14-15a3 3 0 0 1 0 6m3 3a6 6 0 0 1 3 5" /></>}
  </svg>;
}

export function ChatGameArt() {
  return <span className="chat-game-art" aria-hidden="true"><span>؟</span><span>ϟ</span></span>;
}
