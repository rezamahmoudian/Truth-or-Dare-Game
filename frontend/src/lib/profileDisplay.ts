export function publicHandle(person: { username: string; is_ai?: boolean }): string {
  if (person.is_ai && /^ai_[0-9a-f]{16}$/i.test(person.username)) return "";
  return person.username ? `@${person.username}` : "";
}
