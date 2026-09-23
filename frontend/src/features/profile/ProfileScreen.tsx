import { useEffect, useState } from "react";

import { UpgradeAccountCard } from "@/features/profile/UpgradeAccountCard";
import { faNum } from "@/lib/dates";
import * as api from "@/lib/moderationApi";
import type { Person } from "@/lib/types";
import { useSession } from "@/store/session";
import { Avatar } from "@/ui/Avatar";
import { Header, Screen } from "@/ui/Screen";
import { TabBar } from "@/ui/TabBar";

export function ProfileScreen() {
  const user = useSession((s) => s.user);
  if (!user) return null;

  return (
    <Screen header={<Header title="پروفایل" />} footer={<TabBar />}>
      <div className="mx-auto flex max-w-md flex-col gap-4 px-4 py-5">
        <section className="surface-card flex items-center gap-4 rounded-card p-5">
          <Avatar avatarKey={user.avatar || "a1"} name={user.display_name} size={64} glow />
          <div className="min-w-0">
            <p className="truncate text-[19px] font-extrabold">{user.display_name}</p>
            <p className="truncate text-[13px] text-muted">@{user.username}</p>
            <p className="mt-1 text-[12px] text-faint">
              {user.gender === "F" ? "زن" : "مرد"}
              {user.age !== null && ` · ${faNum(user.age)} ساله`}
            </p>
          </div>
        </section>

        {user.is_guest && <UpgradeAccountCard />}

        <BlockedList />
      </div>
    </Screen>
  );
}

/**
 * Blocking is reversible, so the list has to be somewhere people can find it.
 * A block you cannot undo is a decision made once in anger and regretted
 * silently.
 */
function BlockedList() {
  const [blocked, setBlocked] = useState<Person[] | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open || blocked !== null) return;
    void api.listBlocked().then(setBlocked).catch(() => setBlocked([]));
  }, [open, blocked]);

  return (
    <section className="surface-card rounded-card p-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-start"
      >
        <span className="text-[14px] font-bold">🚫 کاربران مسدودشده</span>
        <span className="text-faint">{open ? "−" : "+"}</span>
      </button>

      {open && (
        <div className="mt-3">
          {blocked === null && <p className="text-sm text-muted">…</p>}
          {blocked?.length === 0 && (
            <p className="text-sm text-muted">کسی را مسدود نکرده‌ای.</p>
          )}
          {blocked?.map((person) => (
            <div
              key={person.id}
              className="flex items-center gap-3 border-b border-line-soft py-2 last:border-b-0"
            >
              <Avatar
                avatarKey={person.avatar || "a1"}
                name={person.display_name}
                size={36}
              />
              <span className="min-w-0 flex-1 truncate text-sm">
                {person.display_name}
              </span>
              <button
                type="button"
                onClick={() => {
                  void api.unblockUser(person.id).then(() =>
                    setBlocked((rows) =>
                      (rows ?? []).filter((r) => r.id !== person.id),
                    ),
                  );
                }}
                className="press min-h-9 shrink-0 rounded-field bg-surface-2 px-3 text-[12px] text-muted"
              >
                رفع مسدودی
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
