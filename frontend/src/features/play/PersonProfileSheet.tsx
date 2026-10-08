import { useEffect, useState } from "react";

import { FriendButton } from "@/features/friends/FriendButton";
import { PersonMenu } from "@/features/moderation/PersonMenu";
import { ApiError } from "@/lib/auth";
import { faNum } from "@/lib/dates";
import { getPerson } from "@/lib/socialApi";
import type { Person } from "@/lib/types";
import { useInvitations } from "@/store/invitations";
import { useSocial } from "@/store/social";
import { Avatar } from "@/ui/Avatar";
import { Button } from "@/ui/Button";

export function PersonProfileSheet({ person, onClose }: { person: Person; onClose: () => void }) {
  const [full, setFull] = useState<Person | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState("");
  const send = useInvitations((s) => s.send);
  const setRelation = useSocial((s) => s.setRelation);
  useEffect(() => {
    let active = true;
    void getPerson(person.id).then((data) => {
      if (!active) return;
      setFull(data);
      if (data.relation) setRelation(data.id, data.relation);
    }).catch(() => { if (active) setError("دریافت پروفایل ممکن نشد؛ دوباره بازش کن."); });
    return () => { active = false; };
  }, [person.id, setRelation]);
  const profile = full ?? person;
  return <div className="fixed inset-0 z-50 flex flex-col justify-end bg-black/65 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={`پروفایل ${person.display_name}`}>
    <button type="button" aria-label="بستن پروفایل" className="flex-1" onClick={onClose} />
    <section className="animate-sheet-in mx-auto max-h-[85dvh] w-full max-w-lg overflow-y-auto rounded-t-sheet border-t border-line bg-surface p-5" style={{ paddingBottom: "max(1.25rem, env(safe-area-inset-bottom))" }}>
      <div className="flex items-center gap-3">
        <Avatar photoUrl={profile.avatar_url} avatarKey={profile.avatar} name={profile.display_name} size={64} glow />
        <div className="min-w-0 flex-1"><h2 className="break-words text-lg font-bold">{profile.display_name}</h2>
          <p className="break-all text-xs text-muted">@{profile.username}{profile.age != null && ` · ${faNum(profile.age)} ساله`}</p></div>
        <PersonMenu userId={profile.id} displayName={profile.display_name} onBlocked={onClose} />
      </div>
      {profile.bio && <p className="my-4 whitespace-pre-wrap break-words text-sm leading-7 text-muted">{profile.bio}</p>}
      {!full && !error && <p className="my-4 text-xs text-muted">در حال دریافت پروفایل…</p>}
      {full && full.relation !== "BLOCKED" && !full.is_ai && <div className="mt-5 flex flex-col gap-3">
        <FriendButton userId={full.id} relation={full.relation} />
        <Button variant="ghost" disabled={busy || !!sent} onClick={async () => {
          setBusy(true); setError("");
          try { const row = await send(full.id); setSent(row.direction === "incoming" ? "این بازیکن قبلاً دعوتت کرده؛ از صفحهٔ دعوت‌های بازی قبول کن." : "دعوت فرستاده شد؛ پاسخ در صفحهٔ دعوت‌های بازی می‌آید."); }
          catch (err) { setError(err instanceof ApiError ? err.firstMessage || "دعوت ارسال نشد." : "ارتباط قطع شد؛ دوباره تلاش کن."); }
          finally { setBusy(false); }
        }}>{busy ? "در حال ارسال…" : sent ? "دعوت ثبت شد" : "🎲 درخواست بازی دونفره"}</Button>
      </div>}
      {sent && <p role="status" className="mt-3 text-sm leading-7 text-ok">{sent}</p>}
      {error && <p role="alert" className="mt-3 text-sm text-bad">{error}</p>}
      <button type="button" onClick={onClose} className="mt-3 min-h-11 w-full text-sm text-muted">بستن</button>
    </section>
  </div>;
}
