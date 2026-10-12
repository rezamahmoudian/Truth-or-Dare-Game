import { useState } from "react";
import { Emoji } from "./Emoji";
import { EMOJI_GROUPS, KNOWN_EMOJI } from "./emojiData";

const RECENT_KEY = "ft.recent-emoji";
function readRecent(): string[] {
  try {
    const values: unknown = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    return Array.isArray(values) ? values.filter((v): v is string => typeof v === "string" && KNOWN_EMOJI.has(v)).slice(0, 24) : [];
  } catch { return []; }
}

export function EmojiPicker({ id, onSelect }: { id: string; onSelect: (emoji: string) => void }) {
  const [recent, setRecent] = useState(readRecent);
  const [category, setCategory] = useState<string>(() => recent.length ? "recent" : "faces");
  const group = EMOJI_GROUPS.find(item => item.id === category);
  const items = category === "recent" ? recent : group?.items ?? [];
  return <div id={id} className="composer-popover composer-emojis" aria-label="انتخاب ایموجی">
    <div className="emoji-category-bar" aria-label="دسته‌بندی ایموجی‌ها">
      <button type="button" aria-label="ایموجی‌های اخیر" aria-pressed={category === "recent"} onClick={() => setCategory("recent")}><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 6v6l4 2" /></svg></button>
      {EMOJI_GROUPS.map(item => <button key={item.id} type="button" aria-label={item.label} aria-pressed={category === item.id} onClick={() => setCategory(item.id)}><Emoji value={item.icon} /></button>)}
    </div>
    <div className="emoji-panel-label">{category === "recent" ? "اخیراً استفاده‌شده" : group?.label}</div>
    <div className="emoji-grid" key={category}>
      {items.map(emoji => <button key={emoji} type="button" aria-label={`افزودن ${emoji}`} onClick={() => {
        const next = [emoji, ...recent.filter(item => item !== emoji)].slice(0, 24);
        setRecent(next);
        try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch { /* Storage is optional. */ }
        onSelect(emoji);
      }}><Emoji value={emoji} /></button>)}
    </div>
    {items.length === 0 && <p className="emoji-empty">ایموجی‌هایی که بفرستی اینجا می‌مانند.</p>}
    <a className="emoji-credit" href="/emoji/NOTICE.txt" target="_blank" rel="noreferrer">Twemoji · CC BY 4.0</a>
  </div>;
}
