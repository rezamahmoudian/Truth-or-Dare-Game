import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { WaitingOverlay } from "@/features/play/WaitingOverlay";
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
import {
  BoltIcon,
  ChatIcon,
  ChevronIcon,
  FlameIcon,
  FriendsIcon,
  KeyIcon,
  PersonIcon,
  SparkleIcon,
} from "@/ui/icons";
import { Screen, Skeleton } from "@/ui/Screen";
import { TabBar } from "@/ui/TabBar";

/* Each mode carries its own accent. The tile, the icon and the status dot all
   read from one token, so they cannot drift apart. */
const MODE_TINT: Record<string, string> = {
  quick: "var(--color-hot)",
  group: "var(--color-mode-group)",
  girls: "var(--color-mode-girls)",
  boys: "var(--color-mode-boys)",
  deep: "var(--color-mode-group)",
  friends: "var(--color-mode-friends)",
};

const MODE_ICON: Record<string, typeof PersonIcon> = {
  quick: BoltIcon,
  group: FriendsIcon,
  girls: PersonIcon,
  boys: PersonIcon,
  deep: ChatIcon,
  friends: ChatIcon,
};

const QUEUE_LABEL: Record<string, string> = {
  FAST: "صف پر — زود جفت می‌شی",
  SLOW: "صف خلوته، کمی صبر کن",
  EMPTY: "اولین نفر باش",
};

const QUEUE_DOT: Record<string, string> = {
  FAST: "bg-ok",
  SLOW: "bg-warn",
  EMPTY: "bg-faint",
};

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

  useEffect(() => {
    void loadLobby().catch(() => undefined);
    void resume().catch(() => undefined);
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

      <div className="mx-auto flex max-w-md flex-col gap-5 px-4 pb-8 pt-1">
        <p className="text-[17px] font-bold leading-relaxed">
          سلام {me?.display_name}، امروز با کی آشنا می‌شی؟
        </p>

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

        {hero && <HeroCard mode={hero} onlineCount={onlineCount} onPick={pick} />}

        {rest.length > 0 && (
          <section>
            <h2 className="mb-3 text-[17px] font-extrabold">حالت‌های دیگه</h2>
            <div className="grid grid-cols-2 gap-3">
              {rest.map((mode) => (
                <ModeCard key={mode.key} mode={mode} onPick={pick} />
              ))}
              <FriendsCard onOpen={() => setShowCode(true)} />
            </div>
          </section>
        )}

        {error && (
          <p className="animate-rise rounded-field bg-bad/15 px-4 py-3 text-[13px] text-bad">
            {error}
          </p>
        )}

        {activePeople.length > 0 && <ActiveNow people={activePeople} />}

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
      <h1 className="flex-1 text-[26px] font-extrabold leading-none tracking-tight">
        جرأت<span className="text-brand">.</span>
      </h1>

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
          avatarKey={me?.avatar || "a1"}
          name={me?.display_name ?? ""}
          size={40}
          glow
        />
      </button>
    </header>
  );
}

function HeroCard({
  mode,
  onlineCount,
  onPick,
}: {
  mode: MatchMode;
  onlineCount: number;
  onPick: (mode: MatchMode) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onPick(mode)}
      className="press hero-warm relative w-full overflow-hidden rounded-hero p-5 text-start text-white"
    >
      {/* A four-point sparkle bled off the corner. It gives the card a focal
          point without another element competing for the eye. */}
      <span className="pointer-events-none absolute -end-6 -top-8 text-white/15">
        <SparkleIcon size={150} filled />
      </span>

      <div className="relative flex items-start gap-2">
        <span className="grid size-11 place-items-center rounded-field bg-white/20">
          <BoltIcon size={21} filled />
        </span>
        {mode.is_featured && (
          <span className="rounded-full bg-black/25 px-3 py-1.5 text-[12px] font-bold">
            پرطرفدار
          </span>
        )}
        <span className="flex-1" />
        <span className="grid size-9 place-items-center rounded-full bg-white/20">
          <ChevronIcon size={18} />
        </span>
      </div>

      <p className="relative mt-5 text-[27px] font-extrabold leading-tight">
        {mode.title}
      </p>
      <p className="relative text-[14px] leading-relaxed text-white/85">
        {mode.subtitle}
      </p>

      {onlineCount > 0 && (
        <p className="relative mt-3 flex items-center gap-2 text-[13px] font-bold">
          <span className="flex" aria-hidden>
            {["#2eff8e", "#32a9e3", "#ffcc0c"].map((colour, i) => (
              <span
                key={colour}
                className="size-5 rounded-full border-2 border-white/40"
                style={{ background: colour, marginInlineStart: i ? -8 : 0 }}
              />
            ))}
          </span>
          {faNum(onlineCount)} نفر الان آنلاین
        </p>
      )}
    </button>
  );
}

function ModeCard({
  mode,
  onPick,
}: {
  mode: MatchMode;
  onPick: (mode: MatchMode) => void;
}) {
  const Icon = MODE_ICON[mode.key] ?? PersonIcon;
  const tint = MODE_TINT[mode.key] ?? "var(--color-mode-group)";
  const soldOut = mode.remaining_today === 0;

  return (
    <button
      type="button"
      disabled={soldOut}
      onClick={() => onPick(mode)}
      className="press surface-card relative flex min-h-[152px] w-full flex-col rounded-card p-4 text-start disabled:opacity-40"
      style={{ ["--tint" as string]: tint }}
    >
      <div className="flex items-start">
        <span className="tile-tint grid size-11 place-items-center rounded-field">
          <Icon size={21} />
        </span>
        <span className="flex-1" />
        {mode.remaining_today !== null && (
          <span className="rounded-full bg-warn/15 px-2 py-0.5 text-[11px] font-bold text-warn">
            {soldOut ? "تمام شد" : "محدود"}
          </span>
        )}
      </div>

      <p className="mt-auto pt-3 text-[16px] font-extrabold leading-tight">
        {mode.title}
      </p>
      <p className="truncate text-[12.5px] text-muted">{mode.subtitle}</p>

      <p className="mt-2 flex items-center gap-1.5 text-[11.5px] text-muted">
        <span
          className={`size-2 shrink-0 rounded-full ${QUEUE_DOT[mode.queue_state] ?? "bg-faint"}`}
        />
        {QUEUE_LABEL[mode.queue_state] ?? ""}
      </p>
    </button>
  );
}

/** Join-by-code lives in the grid as a mode, because that is how it is used. */
function FriendsCard({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="press surface-card flex min-h-[152px] w-full flex-col rounded-card p-4 text-start"
      style={{ ["--tint" as string]: "var(--color-mode-friends)" }}
    >
      <span className="tile-tint grid size-11 place-items-center rounded-field">
        <KeyIcon size={21} />
      </span>
      <p className="mt-auto pt-3 text-[16px] font-extrabold leading-tight">
        با دوستات
      </p>
      <p className="text-[12.5px] text-muted">با کد روم وارد شو</p>
      <p className="mt-2 text-[11.5px] text-faint">یا خودت یکی بساز</p>
    </button>
  );
}

/**
 * Who is around right now. Real presence, from `last_seen_at` — an app that
 * looks busy when it is not gets found out on the first empty queue.
 */
function ActiveNow({ people }: { people: Person[] }) {
  return (
    <section>
      <h2 className="mb-3 text-[17px] font-extrabold">فعال الان</h2>
      <ul className="-mx-4 flex gap-3 overflow-x-auto px-4 pb-1">
        {people.map((person) => (
          <li key={person.id} className="flex w-16 shrink-0 flex-col items-center gap-1">
            <span className="relative">
              <Avatar
                avatarKey={person.avatar || "a1"}
                name={person.display_name}
                size={56}
                glow
              />
              <span className="absolute bottom-0.5 end-0.5 size-3 rounded-full border-2 border-ink bg-ok" />
            </span>
            <span className="w-full truncate text-center text-[11px] text-muted">
              {person.display_name}
            </span>
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
