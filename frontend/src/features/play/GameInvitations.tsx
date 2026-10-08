import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "@/lib/auth";
import { faNum } from "@/lib/dates";
import type { GameInvitation, Person } from "@/lib/types";
import { useInvitations } from "@/store/invitations";
import { Avatar } from "@/ui/Avatar";
import { Header, Screen } from "@/ui/Screen";
import { TabBar } from "@/ui/TabBar";
import { PersonProfileSheet } from "@/features/play/PersonProfileSheet";

export function GameInvitationsScreen() {
  const navigate = useNavigate();
  const lists = useInvitations((s) => s.lists);
  const load = useInvitations((s) => s.load);
  const dismiss = useInvitations((s) => s.dismiss);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"incoming" | "ready" | "outgoing">("incoming");
  const [visible, setVisible] = useState(15);
  const [person, setPerson] = useState<Person | null>(null);
  useEffect(() => {
    dismiss();
    void load().catch(() => setError("دریافت دعوت‌ها ممکن نشد.")).finally(() => setLoading(false));
  }, [load, dismiss]);
  const rows = lists[tab];
  return <Screen header={<Header title="دعوت‌های بازی" subtitle="هر وقت خواستی، دعوت‌ها را بررسی کن" action={<button type="button" className="min-h-11 px-3 text-sm text-muted" onClick={() => navigate("/")}>خانه</button>} />} footer={<TabBar />}>
    <div className="mx-auto max-w-md px-4 py-4">
      <div className="mb-4 grid grid-cols-3 gap-1 rounded-field bg-surface-2 p-1" role="group" aria-label="نوع دعوت">
        {([['incoming', 'دریافتی'], ['ready', 'آمادهٔ بازی'], ['outgoing', 'ارسالی']] as const).map(([key, label]) => <button key={key} type="button" aria-pressed={tab === key} onClick={() => { setTab(key); setVisible(15); }} className={`min-h-11 rounded-field px-1 text-xs font-bold ${tab === key ? 'bg-brand text-white' : 'text-muted'}`}>
          {label} <span className="text-[10px]">({faNum(lists[key].length)})</span>
        </button>)}
      </div>
      {error && <button type="button" className="min-h-11 text-sm text-bad" onClick={() => { void load().then(() => setError("")).catch(() => setError("دریافت دعوت‌ها ممکن نشد.")); }}>{error} تلاش دوباره</button>}
      {loading && <p role="status" className="py-6 text-center text-sm text-muted">در حال دریافت دعوت‌ها…</p>}
      {!loading && !error && !rows.length && <div className="surface-card rounded-card px-4 py-10 text-center"><span className="text-3xl" aria-hidden>🎲</span><p className="mt-3 text-sm text-muted">{tab === 'incoming' ? 'دعوت جدیدی نداری.' : tab === 'ready' ? 'هنوز دعوت پذیرفته‌شده‌ای برای بازی نداری.' : 'دعوتی در انتظار پاسخ نداری.'}</p></div>}
      {rows.length > 0 && <section aria-label="فهرست دعوت‌ها" className="surface-card rounded-card px-4">{rows.slice(0, visible).map((row) => <InvitationRow key={row.id} row={row} onProfile={setPerson} />)}</section>}
      {rows.length > visible && <button type="button" className="mt-3 min-h-11 w-full rounded-field bg-surface-2 text-sm text-brand-soft" onClick={() => setVisible((n) => n + 15)}>نمایش بیشتر</button>}
    </div>
    {person && <PersonProfileSheet key={person.id} person={person} onClose={() => setPerson(null)} />}
  </Screen>;
}

export function GameInvitationsLink() {
  const navigate = useNavigate();
  const count = useInvitations((s) => s.lists.incoming.length);
  return <button type="button" onClick={() => navigate("/invitations")} className="press relative min-h-11 shrink-0 rounded-field bg-surface-2 px-3 text-xs font-bold text-muted">
    دعوت‌ها {count > 0 && <span className="ms-1 rounded-full bg-brand px-1.5 py-0.5 text-white">{faNum(count > 99 ? '+۹۹' : count)}</span>}
  </button>;
}

function InvitationRow({ row, onProfile }: { row: GameInvitation; onProfile: (p: Person) => void }) {
  const navigate = useNavigate();
  const respond = useInvitations((s) => s.respond);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function act(action: "accept" | "decline" | "cancel") {
    setBusy(true); setError("");
    try { const result = await respond(row.id, action); if (result.conversation_id && action === "accept") navigate(`/c/${result.conversation_id}`); }
    catch (err) { setError(err instanceof ApiError ? err.firstMessage || "انجام نشد." : "ارتباط قطع شد؛ دوباره تلاش کن."); }
    finally { setBusy(false); }
  }
  return <article className="border-b border-line-soft py-3 last:border-0">
    <button type="button" onClick={() => onProfile(row.user)} className="flex min-h-11 w-full items-center gap-3 text-start">
      <Avatar photoUrl={row.user.avatar_url} avatarKey={row.user.avatar} name={row.user.display_name} size={40} />
      <span className="min-w-0"><span className="block truncate text-sm font-bold">{row.user.display_name}</span><span className="text-xs text-muted">{row.status === "ACCEPTED" ? "دعوت پذیرفته شد؛ بازی آماده است" : row.direction === "incoming" ? "تو را به بازی دونفره دعوت کرده" : "منتظر پاسخ بازیکن"}</span></span>
    </button>
    <div className="mt-2 flex gap-2">
      {row.status === "ACCEPTED" ? <button type="button" onClick={() => navigate(`/c/${row.conversation_id}`)} className="min-h-11 flex-1 rounded-field bg-brand px-3 text-sm font-bold text-white">ورود به بازی</button> : row.direction === "incoming" ? <>
        <button type="button" disabled={busy} onClick={() => void act("accept")} className="min-h-11 flex-1 rounded-field bg-brand px-3 text-sm font-bold text-white disabled:opacity-40">قبول و شروع بازی</button>
        <button type="button" disabled={busy} onClick={() => void act("decline")} className="min-h-11 rounded-field bg-surface-2 px-4 text-sm text-muted disabled:opacity-40">رد</button>
      </> : <button type="button" disabled={busy} onClick={() => void act("cancel")} className="min-h-11 rounded-field bg-surface-2 px-4 text-sm text-muted disabled:opacity-40">لغو دعوت</button>}
    </div>
    {error && <p role="alert" className="mt-2 text-xs text-bad">{error}</p>}
  </article>;
}

export function GameInviteNotice() {
  const notice = useInvitations((s) => s.notice);
  const dismiss = useInvitations((s) => s.dismiss);
  const location = useLocation();
  const navigate = useNavigate();
  if (!notice || notice.status === "PENDING" || location.pathname === "/invitations" || location.pathname === `/c/${notice.conversation_id}`) return null;
  return <aside role="status" className="fixed inset-x-4 bottom-24 z-40 mx-auto flex max-w-md items-center gap-2 rounded-card border border-brand/40 bg-surface p-3 shadow-xl">
    <button type="button" className="min-h-11 min-w-0 flex-1 text-start text-sm" onClick={() => { dismiss(); navigate(notice.conversation_id ? `/c/${notice.conversation_id}` : "/invitations"); }}>
      <span className="block font-bold">دعوت بازی پذیرفته شد 🎲</span><span className="text-xs text-muted">{notice.user.display_name} · ورود به بازی</span>
    </button>
    <button type="button" aria-label="بستن اعلان دعوت" onClick={dismiss} className="size-11 shrink-0 text-muted">×</button>
  </aside>;
}
