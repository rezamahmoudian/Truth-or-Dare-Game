import { HeroCard, ModeCard, FriendsCard } from "@/features/play/ModeCards";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { GameInvitationsLink } from "@/features/play/GameInvitations";

import { WaitingOverlay } from "@/features/play/WaitingOverlay";
import { AIIntroSheet } from "@/features/play/AIIntroSheet";
import { InstallBanner } from "@/features/pwa/PwaChrome";
import { ApiError } from "@/lib/auth";
import * as chatApi from "@/lib/chatApi";
import { faNum } from "@/lib/dates";
import type { MatchMode, Person } from "@/lib/types";
import { useChat } from "@/store/chat";
import { useMatch } from "@/store/match";
import { useSession } from "@/store/session";
import { Avatar } from "@/ui/Avatar";
import { Button } from "@/ui/Button";
import { FlameIcon } from "@/ui/icons";
import { Screen, Skeleton } from "@/ui/Screen";
import { TabBar } from "@/ui/TabBar";

/**
 * Home.
 *
 * The owner chose the mode picker as the first screen rather than the chat
 * list, so this is what the app opens to. One mode is featured as a hero and
 * the rest sit in a grid: the gender-filtered queues are the ones that starve,
 * and a layout that pushes traffic into them is how a product ends up feeling
 * empty.
 */
export function PlayScreen() {
  const navigate = useNavigate();

  const me = useSession((s) => s.user);
  const modes = useMatch((s) => s.modes);
  const onlineCount = useMatch((s) => s.onlineCount);
  const activePeople = useMatch((s) => s.activePeople);
  const loaded = useMatch((s) => s.loaded);
  const ticket = useMatch((s) => s.ticket);
  const expired = useMatch((s) => s.expired);
  const matchedId = useMatch((s) => s.matchedConversationId);
  const loadLobby = useMatch((s) => s.loadLobby);
  const resume = useMatch((s) => s.resume);
  const enqueue = useMatch((s) => s.enqueue);
  const dismissExpired = useMatch((s) => s.dismissExpired);
  const loadConversations = useChat((s) => s.loadConversations);
  const clearMatch = useMatch((s) => s.clearMatch);

  const [error, setError] = useState<string | null>(null);
  const [showCode, setShowCode] = useState(false);
  const [aiMode, setAIMode] = useState<MatchMode | null>(null);

  useEffect(() => {
    void loadLobby().catch(() => undefined);
    void resume().catch(() => undefined);
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void loadLobby().catch(() => undefined);
    }, 30000);
    return () => window.clearInterval(timer);
  }, [loadLobby, resume]);

  // A match arrives over the socket; the screen follows it into the room.
  useEffect(() => {
    if (!matchedId) return;
    clearMatch();
    void loadConversations();
    navigate(`/c/${matchedId}`);
  }, [matchedId, clearMatch, loadConversations, navigate]);

  async function pick(mode: MatchMode) {
    setError(null);
    if (mode.is_ai) { setAIMode(mode); return; }
    try {
      await enqueue(mode.key);
    } catch (err) {
      setError(
        err instanceof ApiError ? (err.firstMessage ?? "شروع نشد.") : "شروع نشد.",
      );
    }
  }

  const hero = modes.find((m) => m.key === "quick") ?? modes.find((m) => m.is_featured);
  const rest = modes.filter((m) => m.key !== hero?.key);
  const waitingTitle =
    modes.find((m) => m.key === ticket?.mode)?.title ?? "در حال جستجو";

  return (
    <Screen header={<LobbyHeader streak={me?.streak_days ?? 0} />} footer={<TabBar />}>
      {ticket && <WaitingOverlay ticket={ticket} title={waitingTitle} />}
      {aiMode && <AIIntroSheet onClose={() => setAIMode(null)} onStart={async () => {
        await enqueue(aiMode.key, true); setAIMode(null);
      }} />}

      <div className="mx-auto flex max-w-md flex-col gap-5 px-4 pb-8 pt-1">
        <div className="lobby-greeting">
          <div><h1>امروز چقدر <em>پایه‌ای؟</em></h1><p className="mt-1 text-xs leading-6 text-muted">یه کم جرئت، یه کم حقیقت، کلی خاطره.</p></div>
          {onlineCount > 0 && <span className="online-pill"><span className="size-1.5 rounded-full bg-ok" />{faNum(onlineCount)} آنلاین</span>}
        </div>

        {expired && (
          <div className="surface-card animate-rise rounded-card p-4 text-[14px] leading-relaxed">
            <p>کسی پیدا نشد. حالت گروهی معمولاً سریع‌تر پر می‌شود.</p>
            <div className="mt-3 flex gap-2">
              <Button
                className="w-auto flex-1"
                onClick={() => {
                  dismissExpired();
                  const suggestion = modes.find((m) => m.key === expired.suggestedMode);
                  if (suggestion) void pick(suggestion);
                }}
              >
                بازی گروهی
              </Button>
              <Button variant="ghost" className="w-auto px-5" onClick={dismissExpired}>
                بعداً
              </Button>
            </div>
          </div>
        )}

        {!loaded && <LobbySkeleton />}

        {hero && <HeroCard mode={hero} onPick={pick} />}

        {rest.length > 0 && (
          <section>
            <div className="mb-3 flex items-center justify-between gap-2"><h2 className="text-[15px] font-extrabold">یا خودت انتخاب کن</h2><span className="text-[11px] text-muted">چه حال‌وهوایی داری؟</span></div>
            <div className="grid grid-cols-2 gap-3">
              {rest.map((mode) => (
                <ModeCard key={mode.key} mode={mode} onPick={pick} />
              ))}
              <FriendsCard onOpen={() => setShowCode(true)} />
            </div>
            <p className="lobby-caption"><span aria-hidden="true">✧</span> یه بازی ساده، شاید شروع یه رفاقت.</p>
          </section>
        )}

        {error && (
          <p className="animate-rise rounded-field bg-bad/15 px-4 py-3 text-[13px] text-bad">
            {error}
          </p>
        )}

        <ActiveNow people={activePeople} onProfile={person => navigate(`/people/${person.id}`)} />

        <InstallBanner />

        {showCode && <JoinByCode onClose={() => setShowCode(false)} />}
      </div>
    </Screen>
  );
}

/**
 * The wordmark, the streak and the avatar.
 *
 * The streak counts consecutive days on which you actually played — a
 * decorative number that tracks nothing is exactly the kind of detail people
 * notice, and it costs the rest of the screen its credibility.
 */
function LobbyHeader({ streak }: { streak: number }) {
  const navigate = useNavigate();
  const me = useSession((s) => s.user);

  return (
    <header
      className="bar-blur flex shrink-0 items-center gap-2 px-4 pb-3"
      style={{ paddingTop: "max(0.75rem, env(safe-area-inset-top))" }}
    >
      <div className="flex min-w-0 flex-1 items-center gap-2.5"><span className="brand-symbol" aria-hidden="true">✦</span><div><p className="text-[22px] font-black leading-tight">جرأت<span className="text-brand">.</span></p><p className="text-[10px] text-muted">جرئت یا حقیقت آنلاین</p></div></div>
      <GameInvitationsLink />

      {streak > 0 && (
        <span className="flex items-center gap-1 rounded-full bg-surface-3 px-3 py-1.5 text-[13px] font-bold">
          <span className="text-warn">
            <FlameIcon size={15} filled />
          </span>
          {faNum(streak)}
        </span>
      )}

      <button
        type="button"
        onClick={() => navigate("/profile")}
        className="press shrink-0"
        aria-label="پروفایل"
      >
        <Avatar
          photoUrl={me?.avatar_url} avatarKey={me?.avatar || "a1"}
          name={me?.display_name ?? ""}
          size={40}
          glow
        />
      </button>
    </header>
  );
}

function ActiveNow({ people, onProfile }: { people: Person[]; onProfile: (p: Person) => void }) {
  return (
    <section>
      <h2 className="mb-1 text-[17px] font-extrabold">بازیکن‌های آنلاین</h2>
      <p className="mb-3 text-xs leading-6 text-muted">چند هم‌بازی تصادفی؛ روی پروفایل بزن و آشنا شو.</p>
      {!people.length && <p className="surface-card rounded-card p-4 text-sm leading-7 text-muted">فعلاً بازیکن آنلاین دیگری پیدا نشد. کمی بعد دوباره سر بزن.</p>}
      <ul className="-mx-4 flex gap-3 overflow-x-auto px-4 pb-1">
        {people.map((person) => (
          <li key={person.id} className="w-20 shrink-0">
            <button type="button" aria-label={`پروفایل ${person.display_name}`} onClick={() => onProfile(person)} className="press flex min-h-11 w-full flex-col items-center gap-2 rounded-card py-2">
            <span className="relative">
              <Avatar
                photoUrl={person.avatar_url} avatarKey={person.avatar || "a1"}
                name={person.display_name}
                size={56}
                glow
              />
              <span className="absolute bottom-0.5 end-0.5 size-3 rounded-full border-2 border-ink bg-ok" />
            </span>
            <span className="w-full truncate text-center text-[11px] text-muted">
              {person.display_name}
            </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function JoinByCode({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const loadConversations = useChat((s) => s.loadConversations);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState<"create" | "join" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(kind: "create" | "join", action: () => Promise<{ id: string }>) {
    setBusy(kind);
    setError(null);
    try {
      const conversation = await action();
      await loadConversations();
      navigate(`/c/${conversation.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? (err.firstMessage ?? "انجام نشد.") : "انجام نشد.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="animate-fade-in fixed inset-0 z-50 flex flex-col justify-end bg-black/65 backdrop-blur-[2px]">
      <button type="button" aria-label="بستن" className="flex-1" onClick={onClose} />

      <div
        className="animate-sheet-in rounded-t-sheet border-t border-line bg-surface px-4 pt-3"
        style={{ paddingBottom: "max(1.5rem, env(safe-area-inset-bottom))" }}
      >
        <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-line" />
        <h2 className="mb-3 text-[17px] font-extrabold">بازی با دوستات</h2>

        <div className="flex flex-col gap-3">
          <div className="flex gap-2">
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="ABC123"
              dir="ltr"
              maxLength={6}
              autoCapitalize="characters"
              className="surface-raised min-h-12 flex-1 rounded-field px-4 text-center font-mono text-[18px] tracking-[0.3em] outline-none placeholder:tracking-normal placeholder:text-faint focus:border-brand/60"
            />
            <Button
              className="w-auto px-6"
              busy={busy === "join"}
              disabled={code.length < 6}
              onClick={() => run("join", () => chatApi.joinRoom(code))}
            >
              ورود
            </Button>
          </div>

          <Button
            variant="ghost"
            busy={busy === "create"}
            onClick={() => run("create", () => chatApi.createRoom(8))}
          >
            ساختن روم و گرفتن کد
          </Button>

          {error && <p className="text-[13px] text-bad">{error}</p>}
        </div>
      </div>
    </div>
  );
}

function LobbySkeleton() {
  return (
    <div className="flex flex-col gap-5">
      <Skeleton className="h-44 rounded-hero" />
      <div className="grid grid-cols-2 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-[152px] rounded-card" />
        ))}
      </div>
    </div>
  );
}
