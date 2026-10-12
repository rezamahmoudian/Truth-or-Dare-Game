import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { FriendButton } from "@/features/friends/FriendButton";
import { PersonMenu } from "@/features/moderation/PersonMenu";
import { ApiError } from "@/lib/auth";
import { faNum } from "@/lib/dates";
import { getPerson, openFriendConversation } from "@/lib/socialApi";
import type { Person } from "@/lib/types";
import { useInvitations } from "@/store/invitations";
import { useSession } from "@/store/session";
import { useSocial } from "@/store/social";
import { Avatar } from "@/ui/Avatar";
import { Header, Screen, Skeleton } from "@/ui/Screen";
import { ProfilePhotoViewer } from "./ProfilePhotoViewer";

export function PublicProfileScreen() {
  const { userId = "" } = useParams();
  return <ProfileDetails key={userId} userId={Number(userId)} />;
}

function ProfileDetails({ userId }: { userId: number }) {
  const navigate = useNavigate();
  const selfId = useSession(s => s.user?.id);
  const relation = useSocial(s => s.relations[userId]);
  const setRelation = useSocial(s => s.setRelation);
  const send = useInvitations(s => s.send);
  const [person, setPerson] = useState<Person | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [photoOpen, setPhotoOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    getPerson(userId).then(value => {
      if (!active) return;
      setPerson(value);
      if (value.relation) setRelation(userId, value.relation);
    }).catch(e => { if (active) setError(e instanceof ApiError ? e.firstMessage || "پروفایل پیدا نشد." : "دریافت پروفایل ممکن نشد."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [userId, attempt, setRelation]);
  const back = () => { if (window.history.state?.idx > 0) navigate(-1); else navigate("/"); };
  const own = selfId === userId;
  const currentRelation = relation ?? person?.relation;
  async function action(kind: "message" | "invite") {
    if (busy) return;
    setBusy(true); setError("");
    try {
      if (kind === "message") {
        const chat = await openFriendConversation(userId);
        navigate(`/c/${chat.conversation_id}`);
      } else {
        const invite = await send(userId);
        setNotice(invite.direction === "incoming" ? "این بازیکن قبلاً دعوتت کرده؛ در دعوت‌های بازی بررسی کن." : "دعوت بازی فرستاده شد.");
      }
    } catch (e) { setError(e instanceof ApiError ? e.firstMessage || "انجام نشد؛ دوباره تلاش کن." : "ارتباط برقرار نشد؛ دوباره تلاش کن."); }
    finally { setBusy(false); }
  }
  const interests = person?.interests?.length ? person.interests : person?.ai_profile?.interests.split(/[،,\n]/).map(item => item.trim()).filter(Boolean) ?? [];
  const city = person?.city || person?.ai_profile?.city;
  const earned = person?.badges?.filter(badge => badge.earned).length ?? 0;
  return <Screen className="public-profile-screen" header={<Header title="پروفایل بازیکن" action={<button type="button" className="profile-back" onClick={back}>بازگشت ←</button>} />}>
    <div className="public-profile-content">
      {loading ? <div aria-label="در حال دریافت پروفایل" className="space-y-4"><Skeleton className="h-72 rounded-3xl" /><Skeleton className="h-36 rounded-3xl" /></div> : person ? <>
        <section className="public-profile-hero">
          <div className="profile-cover" aria-hidden><i /><i /><span>✦</span><span>✧</span></div>
          <div className="profile-identity">
            <button type="button" className="profile-photo-trigger" aria-label={`نمایش عکس پروفایل ${person.display_name}`} onClick={() => setPhotoOpen(true)}><Avatar photoUrl={person.avatar_url} avatarKey={person.avatar || "a1"} name={person.display_name} size={104} /><span aria-hidden>⤢</span></button>
            <h2>{person.display_name || person.username}</h2><p dir="ltr" className="profile-handle">@{person.username}</p>
            <div className="profile-facts">{person.age != null && <span>{faNum(person.age)} ساله</span>}{person.gender && <span>{person.gender === "F" ? "دختر" : "پسر"}</span>}{city && <span>{city}</span>}</div>
            {person.is_ai && <span className="profile-ai-label">شخصیت داستانی · AI</span>}
            {person.joined_at && <p className="profile-joined">همراه بی‌هوا از {new Intl.DateTimeFormat("fa-IR", { year: "numeric", month: "long", timeZone: "UTC" }).format(new Date(person.joined_at))}</p>}
          </div>
          <div className="profile-actions">
            {own ? <Link to="/profile" className="profile-primary-action">ویرایش پروفایل من</Link> : currentRelation === "BLOCKED" ? <p className="text-sm text-muted">ارتباط با این کاربر مسدود است.</p> : <>
              {currentRelation === "FRIENDS" ? <button type="button" disabled={busy} onClick={() => void action("message")} className="profile-primary-action">{busy ? "یه لحظه…" : "پیام بده"}</button> : <FriendButton userId={userId} relation={currentRelation} />}
              {!person.is_ai && <button type="button" disabled={busy || !!notice} onClick={() => void action("invite")} className="profile-secondary-action">{notice ? "دعوت ثبت شد ✓" : "🎲 دعوت به بازی"}</button>}
            </>}
          </div>
          {notice && <p role="status" className="profile-notice">{notice} <Link to="/invitations">دیدن دعوت‌ها</Link></p>}
        </section>
        <section className="profile-stat-grid" aria-label="آمار بازی">
          <div><strong>{faNum(person.stats?.games ?? 0)}</strong><span>بازی</span></div>
          <div><strong>{faNum(earned)}</strong><span>نشان</span></div>
          <div><strong>{faNum(person.stats?.streak_days ?? 0)}</strong><span>روز بازی پیاپی</span></div>
        </section>
        <section className="public-profile-section"><h3><span>دربارهٔ من</span><span aria-hidden>✎</span></h3><p className={person.bio ? "profile-bio" : "profile-empty"}>{person.bio || "هنوز چیزی دربارهٔ خودش ننوشته."}</p></section>
        <section className="public-profile-section"><h3><span>علایق من</span><span aria-hidden>♡</span></h3>{interests.length ? <div className="profile-interest-list">{interests.map(interest => <span key={interest}>{interest}</span>)}</div> : <p className="profile-empty">علایق هنوز اضافه نشده‌اند.</p>}</section>
        <section className="public-profile-section"><h3><span>افتخارات و نشان‌ها</span><span className="profile-section-count">{faNum(earned)} نشان</span></h3><p className="profile-section-hint">هر بازی، یک قدم به نشان بعدی.</p>
          <div className="profile-badges">{person.badges?.map(badge => <article className={`profile-badge ${badge.earned ? "earned" : "locked"}`} key={badge.key} aria-label={`${badge.title}؛ ${badge.earned ? "به دست آمده" : "هنوز دریافت نشده"}`}>
            <span className="profile-badge-icon" aria-hidden>{badge.icon}</span><div><h4>{badge.title} {badge.earned && <span aria-label="به دست آمده">✓</span>}</h4><p>{badge.description}</p>{!badge.earned && <><progress value={badge.progress} max={badge.target} aria-label={`پیشرفت ${badge.title}`} /><small>{faNum(badge.progress)} از {faNum(badge.target)}</small></>}</div>
          </article>)}</div>
        </section>
        {!own && <div className="profile-moderation"><span>تنظیمات ارتباط با این بازیکن</span><PersonMenu userId={userId} displayName={person.display_name} onBlocked={() => setAttempt(v => v + 1)} /></div>}
      </> : null}
      {error && <div role="alert" className="profile-error"><p>{error}</p>{!person && <button type="button" onClick={() => setAttempt(v => v + 1)}>تلاش دوباره</button>}</div>}
    </div>
    {photoOpen && person && <ProfilePhotoViewer person={person} onClose={() => setPhotoOpen(false)} />}
  </Screen>;
}
