import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { FriendButton } from "@/features/friends/FriendButton";
import { faNum } from "@/lib/dates";
import type { FriendRequest, Person } from "@/lib/types";
import { openFriendConversation } from "@/lib/socialApi";
import { ApiError } from "@/lib/auth";
import { useSocial } from "@/store/social";
import { Avatar } from "@/ui/Avatar";
import { EmptyState, Header, Screen } from "@/ui/Screen";
import { TabBar } from "@/ui/TabBar";

export function FriendsScreen() {
  const lists = useSocial((s) => s.lists);
  const load = useSocial((s) => s.load);

  useEffect(() => {
    void load().catch(() => undefined);
  }, [load]);

  const empty =
    lists.friends.length === 0 &&
    lists.incoming.length === 0 &&
    lists.outgoing.length === 0;

  return (
    <Screen header={<Header title="دوستان" />} footer={<TabBar />}>
      <div className="mx-auto flex max-w-md flex-col gap-5 px-4 py-4">
        {lists.incoming.length > 0 && (
          <Section title={`درخواست‌ها (${faNum(lists.incoming.length)})`}>
            {lists.incoming.map((row) => (
              <RequestRow key={row.id} request={row} />
            ))}
          </Section>
        )}

        {lists.friends.length > 0 && (
          <Section title={`دوستان (${faNum(lists.friends.length)})`}>
            {lists.friends.map((friend) => (
              <FriendRow key={friend.id} person={friend} />
            ))}
          </Section>
        )}

        {lists.outgoing.length > 0 && (
          <Section title="در انتظار پاسخ">
            {lists.outgoing.map((row) => (
              <PersonRow key={row.id} person={row.user}>
                <FriendButton userId={row.user.id} relation="OUTGOING" compact />
              </PersonRow>
            ))}
          </Section>
        )}

        {empty && <Empty />}
      </div>
    </Screen>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-2 px-1 text-sm font-semibold text-muted">{title}</h2>
      <div className="surface-card overflow-hidden rounded-card">{children}</div>
    </section>
  );
}

function PersonRow({
  person,
  children,
}: {
  person: Person;
  children: React.ReactNode;
}) {
  return (
    <div
      className="press flex w-full items-center gap-3 border-b border-line-soft px-4 py-3 text-start last:border-b-0"
    >
      <Link to={`/people/${person.id}`} aria-label={`پروفایل ${person.display_name}`} className="flex min-w-0 flex-1 items-center gap-3">
      <Avatar photoUrl={person.avatar_url} avatarKey={person.avatar || "a1"} name={person.display_name} size={44} glow />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[15px] font-semibold">{person.display_name}</p>
        <p className="truncate text-xs text-muted">
          @{person.username}
          {person.age !== null && ` · ${faNum(person.age)} ساله`}
        </p>
      </div>
      </Link>
      {children}
    </div>
  );
}

function RequestRow({ request }: { request: FriendRequest }) {
  const decline = useSocial((s) => s.decline);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  return (
    <PersonRow person={request.user}>
      <div className="flex shrink-0 flex-col gap-1">
        <FriendButton userId={request.user.id} relation="INCOMING" compact />
        <button
          type="button"
          disabled={busy}
          onClick={async () => { setBusy(true); setError(""); try { await decline(request.user.id); } catch { setError("انجام نشد؛ دوباره تلاش کن."); } finally { setBusy(false); } }}
          className="press min-h-11 rounded-field bg-surface-2 px-3 text-[12px] text-muted disabled:opacity-40"
        >
          رد
        </button>
        {error && <span role="alert" className="text-xs text-bad">{error}</span>}
      </div>
    </PersonRow>
  );
}

/** Tapping a friend opens the private chat — that is the point of the list. */
function FriendRow({ person }: { person: Person }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function open() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const result = await openFriendConversation(person.id);
      navigate(`/c/${result.conversation_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.firstMessage || "گفتگو باز نشد." : "ارتباط قطع شد؛ دوباره تلاش کن.");
    } finally { setBusy(false); }
  }
  return <div>
    <PersonRow person={person}>
      <button type="button" disabled={busy} onClick={() => void open()} className="min-h-11 shrink-0 rounded-field bg-surface-2 px-3 text-xs text-brand-soft">{busy ? "در حال بازکردن…" : "پیام بده ›"}</button>
    </PersonRow>
    {error && <p role="alert" className="px-4 pb-2 text-xs text-bad">{error}</p>}
  </div>;
}

function Empty() {
  return (
    <div className="py-10">
      <EmptyState
        glyph="👋"
        title="هنوز دوستی نداری"
        hint="بعد از هر بازی، روی اسم بازیکن‌ها بزن و درخواست دوستی بفرست."
      />
    </div>
  );
}
