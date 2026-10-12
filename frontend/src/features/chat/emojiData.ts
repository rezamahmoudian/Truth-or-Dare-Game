export const EMOJI_GROUPS = [
  { id: "faces", label: "چهره‌ها", icon: "😄", items: "😀 😃 😄 😁 😆 😅 😂 🤣 🙂 🙃 😉 😊 😇 🥰 😍 🤩 😘 😋 😛 😜 🤪 😎 🥳 😏 😌 🤔 🤭 🤫 🫣 😐 🙄 😬 😴 😢 😭 🥺 😤 😡 🤯 😱 😳 🥹".split(" ") },
  { id: "gestures", label: "دست‌ها", icon: "👋", items: "👋 🤚 ✋ 👌 ✌️ 🤞 🤟 🤘 🤙 👈 👉 👆 👇 👍 👎 👊 ✊ 🤝 👏 🙌 👐 🤲 🙏 💪".split(" ") },
  { id: "hearts", label: "قلب‌ها", icon: "❤️", items: "❤️ 🧡 💛 💚 💙 💜 🖤 🤍 🤎 💔 ❣️ 💕 💞 💓 💗 💖 💘 💝 💟 💌 💋 🫶".split(" ") },
  { id: "fun", label: "بازی و حال‌وهوا", icon: "🎉", items: "🔥 ✨ ⭐ 🌟 💫 💥 💯 ✅ 🎉 🎊 🎈 🎁 🎮 🎯 🎲 🏆 🥇 ⚽ 🎵 🎶 🌈 ☀️ 🌙 🌸 🌹 🍀 🦋 🐱 🐶 🍕 🍿 ☕".split(" ") },
] as const;

export const KNOWN_EMOJI = new Set<string>(EMOJI_GROUPS.flatMap(group => group.items));
export function emojiAsset(emoji: string) {
  const code = Array.from(emoji.replace(/\ufe0f/g, "")).map(char => char.codePointAt(0)!.toString(16)).join("-");
  return `/emoji/${code}.svg`;
}
