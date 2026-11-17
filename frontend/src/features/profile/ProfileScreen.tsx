import { VipName } from "@/ui/Vip";
import { MembershipCard } from "@/features/shop/MembershipCard";
import { useEffect, useState } from "react";

import { UpgradeAccountCard } from "@/features/profile/UpgradeAccountCard";
import { Link } from "react-router-dom";
import { AccountSwitch } from "./AccountSwitch";
import { ProfileDetailsEditor } from "./ProfileDetailsEditor";
import { ProfilePhotoEditor } from "@/features/profile/ProfilePhotoEditor";
import { PromptSuggestionCard } from "@/features/profile/PromptSuggestionCard";
import { faNum } from "@/lib/dates";
import * as api from "@/lib/moderationApi";
import type { Person } from "@/lib/types";
import { useSession } from "@/store/session";
import { Avatar } from "@/ui/Avatar";
import { Header, Screen } from "@/ui/Screen";
import { TabBar } from "@/ui/TabBar";
import { ShopEntry } from "@/features/shop/ShopEntry";
import { useMonetization } from "@/lib/features";
import { getPerson } from "@/lib/socialApi";
import { ChevronIcon, FlameIcon, PersonIcon, SparkleIcon } from "@/ui/icons";
import "./profile.css";

export function ProfileScreen() {
  const user = useSession((s) => s.user);
  const monetization = useMonetization();
  const [editing, setEditing] = useState(false);
  const [stats, setStats] = useState<Person["stats"]>();
  useEffect(() => {
    if (!user?.id) return;
    let active = true;
    setStats(undefined);
    void getPerson(user.id).then(person => { if (active) setStats(person.stats); }).catch(() => undefined);
    return () => { active = false; };
  }, [user?.id]);
  if (!user) return null;
  const streak = stats?.streak_days ?? user.streak_days;

  return (
    <Screen className="my-profile-screen" header={<Header title="پروفایل من" action={<span className="profile-header-mark" aria-hidden="true"><SparkleIcon size={21} /></span>} />} footer={<TabBar />}>
      <div className="my-profile-content">
        <section className="my-profile-hero" aria-label="معرفی من">
          <div className="my-profile-cover" aria-hidden="true"><span>✦</span><i /><b>؟</b></div>
          <div className="my-profile-identity">
            <button type="button" className="profile-avatar-edit" onClick={() => setEditing(true)} aria-label="ویرایش عکس و پروفایل" aria-expanded={editing} aria-controls="profile-editor">
              <Avatar vip={user.vip} photoUrl={user.avatar_url} avatarKey={user.avatar || "a1"} name={user.display_name} size={88} />
              <span aria-hidden="true">✎</span>
            </button>
            <h2><VipName vip={user.vip}>{user.display_name}</VipName></h2>
            <p className="my-profile-handle" dir="ltr">@{user.username}</p>
            <p className="my-profile-meta">{[user.gender === "F" ? "زن" : user.gender === "M" ? "مرد" : "", user.age != null ? `${faNum(user.age)} ساله` : "", user.city].filter(Boolean).join(" · ")}</p>
            {user.bio && <p className="my-profile-bio">{user.bio}</p>}
            {!!user.interests?.length && <div className="my-profile-interests">{user.interests.slice(0, 3).map(interest => <span key={interest}>{interest}</span>)}{user.interests.length > 3 && <span>+{faNum(user.interests.length - 3)}</span>}</div>}
            <div className="my-profile-actions">
              <button type="button" onClick={() => setEditing(value => !value)} aria-expanded={editing} aria-controls="profile-editor"><PersonIcon size={18} />{editing ? "بستن ویرایش" : "ویرایش پروفایل"}</button>
              <Link to={`/people/${user.id}`}>نمایش پروفایل<ChevronIcon size={16} /></Link>
            </div>
          </div>
          <dl className="my-profile-stats" aria-label="آمار بازی من">
            <div><dt>بازی</dt><dd>{stats ? faNum(stats.games) : "—"}</dd></div>
            <div><dt>حقیقت</dt><dd>{stats ? faNum(stats.truths) : "—"}</dd></div>
            <div><dt>جرئت</dt><dd>{stats ? faNum(stats.dares) : "—"}</dd></div>
          </dl>
        </section>
        {streak > 0 && <div className="my-profile-streak"><FlameIcon size={20} /><strong>{faNum(streak)} روز همراه بازی</strong><span>پشت سر هم!</span></div>}
        <div id="profile-editor" className="my-profile-editor" hidden={!editing}>
          <ProfilePhotoEditor />
          <ProfileDetailsEditor />
        </div>
        {user.is_guest && <UpgradeAccountCard />}
        {monetization && <div className="my-profile-commerce"><ShopEntry /><Link className="surface-card min-h-14 rounded-card p-4 text-sm font-bold" to="/shop/items">✧ استایل و مجموعهٔ من <span className="float-end text-muted">←</span></Link><MembershipCard key={user.id} /></div>}
        <section className="my-profile-options" aria-labelledby="profile-options-title">
          <h2 id="profile-options-title">حساب و همراهی</h2>
          <PromptSuggestionCard />
          <BlockedList />
          <AccountSwitch />
        </section>
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
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!open || blocked !== null) return;
    let active = true;
    setError("");
    void api.listBlocked().then(rows => { if (active) setBlocked(rows); }).catch(() => { if (active) setError("فهرست دریافت نشد؛ دوباره امتحان کن."); });
    return () => { active = false; };
  }, [open, blocked, attempt]);

  return (
    <section className="surface-card profile-option rounded-card p-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="profile-option-toggle"
        aria-expanded={open}
        aria-controls="blocked-players"
      >
        <span className="profile-option-icon profile-option-icon-muted" aria-hidden="true">⊘</span>
        <span className="profile-option-label"><strong>کاربران مسدودشده</strong><small>مدیریت دسترسی به تو</small></span>
        <ChevronIcon size={17} className={open ? "profile-chevron-open" : ""} />
      </button>

      {open && (
        <div className="mt-3" id="blocked-players">
          {error && <p role="alert" className="text-sm text-bad">{error} <button type="button" className="min-h-11 underline" onClick={() => { setBlocked(null); setAttempt(value => value + 1); }}>تلاش دوباره</button></p>}
          {blocked === null && !error && <p className="text-sm text-muted">در حال دریافت…</p>}
          {blocked?.length === 0 && (
            <p className="text-sm text-muted">کسی را مسدود نکرده‌ای.</p>
          )}
          {blocked?.map((person) => (
            <div
              key={person.id}
              className="flex items-center gap-3 border-b border-line-soft py-2 last:border-b-0"
            >
              <Avatar vip={person.vip}
                photoUrl={person.avatar_url} avatarKey={person.avatar || "a1"}
                name={person.display_name}
                size={36}
              />
              <span className="min-w-0 flex-1 truncate text-sm">
                <VipName vip={person.vip}>{person.display_name}</VipName>
              </span>
              <button
                type="button"
                onClick={() => {
                  setError("");
                  void api.unblockUser(person.id).then(() =>
                    setBlocked((rows) =>
                      (rows ?? []).filter((r) => r.id !== person.id),
                    ),
                  ).catch(() => setError("رفع مسدودی انجام نشد؛ دوباره امتحان کن."));
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
