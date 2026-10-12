import { useState } from "react";
import { emojiAsset, KNOWN_EMOJI } from "./emojiData";

export function Emoji({ value }: { value: string }) {
  const [failed, setFailed] = useState(false);
  return KNOWN_EMOJI.has(value) && !failed
    ? <img className="chat-emoji" src={emojiAsset(value)} alt={value} draggable={false} onError={() => setFailed(true)} />
    : <>{value}</>;
}

// Preserve text as React text nodes, including unknown/compound emoji.
const EMOJI_PATTERN = /(\p{Regional_Indicator}{2}|[#*0-9]\ufe0f?\u20e3|\p{Extended_Pictographic}(?:\ufe0f|\p{Emoji_Modifier})?(?:\u200d\p{Extended_Pictographic}(?:\ufe0f|\p{Emoji_Modifier})?)*)/gu;
export function EmojiText({ text }: { text: string }) {
  return <>{text.split(EMOJI_PATTERN).map((part, index) => KNOWN_EMOJI.has(part) ? <Emoji key={`${index}-${part}`} value={part} /> : part)}</>;
}
