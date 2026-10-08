import { useEffect, useState } from "react";

import { ApiError, authFetch } from "@/lib/auth";
import type { AISettings, Person } from "@/lib/types";
import { faNum } from "@/lib/dates";
import { Avatar } from "@/ui/Avatar";
import { Button } from "@/ui/Button";

type PersonaList = { available: boolean; personas: Person[]; settings: AISettings };

export function AIIntroSheet({ onClose, onStart }: { onClose: () => void; onStart: () => Promise<void> }) {
  const [data, setData] = useState<PersonaList | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    void authFetch<PersonaList>("/ai/personas/")
      .then((result) => { if (active) setData(result); })
      .catch(() => { if (active) setError("دریافت شخصیت‌ها ممکن نشد. دوباره این صفحه را باز کن."); });
    return () => { active = false; };
  }, []);
  return <div className="fixed inset-0 z-50 flex flex-col justify-end bg-black/65 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="بازی با شخصیت هوش مصنوعی">
    <button type="button" aria-label="بستن" className="flex-1" disabled={busy} onClick={onClose} />
    <section className="animate-sheet-in mx-auto flex max-h-[85dvh] w-full max-w-lg flex-col gap-4 overflow-y-auto rounded-t-sheet border-t border-line bg-surface p-5" style={{ paddingBottom: "max(1.25rem, env(safe-area-inset-bottom))" }}>
      <div><h2 className="text-lg font-extrabold">سه شخصیت، سه حال‌وهوای متفاوت</h2>
        <p className="mt-1 text-sm leading-7 text-muted">با یکی از شخصیت‌های فعال مچ می‌شی. هم‌بازی‌ات فقط حقیقت انتخاب می‌کند؛ انتخاب خودت آزاده.
          {data?.settings && <> مدت جلسه تصادفی بین {faNum(data.settings.session_min_minutes)} تا {faNum(data.settings.session_max_minutes)} دقیقه است و بعد خودکار بسته می‌شود.</>}
        </p></div>
      {data?.personas.map((person) => <article key={person.id} className="surface-raised flex gap-3 rounded-card p-3">
        <Avatar photoUrl={person.avatar_url} avatarKey={person.avatar} name={person.display_name} size={48} />
        <div className="min-w-0"><h3 className="font-bold">{person.display_name}</h3>
          <p className="text-xs text-brand-soft">{person.age} ساله · {person.ai_profile?.city}</p>
          <p className="mt-1 text-xs leading-relaxed text-muted">{person.bio}</p></div>
      </article>)}
      {!data && !error && <p role="status" className="text-sm text-faint">در حال دریافت شخصیت‌ها…</p>}
      {data && !data.available && <p className="text-xs text-warn">اتصال هوش مصنوعی هنوز توسط مدیر فعال نشده است.</p>}
      {error && <p role="alert" className="text-xs text-bad">{error}</p>}
      <Button disabled={busy || !data?.available || !data.personas.length} onClick={() => {
        setBusy(true); setError("");
        void onStart().catch((err) => setError(err instanceof ApiError ? err.firstMessage || "شروع نشد." : "ارتباط قطع شد؛ دوباره تلاش کن.")).finally(() => setBusy(false));
      }}>{busy ? "در حال اتصال…" : "شروع بازی با AI"}</Button>
      <button type="button" disabled={busy} onClick={onClose} className="min-h-11 text-sm text-faint">بازگشت</button>
    </section>
  </div>;
}
