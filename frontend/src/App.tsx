import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { ChatListScreen } from "@/features/chat/ChatListScreen";
import { ChatRoomScreen } from "@/features/chat/ChatRoomScreen";
import { FriendsScreen } from "@/features/friends/FriendsScreen";
import { OfflineBar, UpdateToast } from "@/features/pwa/PwaChrome";
import { Onboarding } from "@/features/onboarding/Onboarding";
import { PlayScreen } from "@/features/play/PlayScreen";
import { ProfileScreen } from "@/features/profile/ProfileScreen";
import { useChat } from "@/store/chat";
import { useGame } from "@/store/game";
import { useMatch } from "@/store/match";
import { useSocial } from "@/store/social";
import { useSession } from "@/store/session";
import { Button } from "@/ui/Button";
import { ErrorBoundary } from "@/ui/ErrorBoundary";

export default function App() {
  const status = useSession((s) => s.status);
  const user = useSession((s) => s.user);
  const error = useSession((s) => s.error);
  const bootstrap = useSession((s) => s.bootstrap);

  const initChat = useChat((s) => s.init);
  const initGame = useGame((s) => s.init);
  const initMatch = useMatch((s) => s.init);
  const initSocial = useSocial((s) => s.init);
  const loadFriends = useSocial((s) => s.load);
  const loadConversations = useChat((s) => s.loadConversations);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  // The socket opens once the session exists and stays open for the whole app
  // — one connection carrying every conversation, not one per screen.
  useEffect(() => {
    if (status !== "ready" || !user?.is_onboarded) return;
    initChat();
    initGame();
    initMatch();
    initSocial();
    void loadConversations();
    void loadFriends();
  }, [
    status,
    user?.is_onboarded,
    initChat,
    initGame,
    initMatch,
    initSocial,
    loadConversations,
    loadFriends,
  ]);

  if (status === "loading") return <Splash />;
  if (status === "error") return <ConnectionError message={error} onRetry={bootstrap} />;
  if (user && !user.is_onboarded) return <Onboarding />;

  return (
    <BrowserRouter>
      <OfflineBar />
      <UpdateToast />
      <RoutedScreens />
    </BrowserRouter>
  );
}

/**
 * Inside the router so the boundary can key off the path: a crash on one screen
 * stays on that screen, and walking away from it clears the error instead of
 * leaving the app wedged.
 */
function RoutedScreens() {
  const location = useLocation();
  return (
    <ErrorBoundary resetKey={location.pathname}>
      <Routes>
        <Route path="/" element={<PlayScreen />} />
        <Route path="/chats" element={<ChatListScreen />} />
        <Route path="/c/:id" element={<ChatRoomScreen />} />
        <Route path="/friends" element={<FriendsScreen />} />
        <Route path="/profile" element={<ProfileScreen />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  );
}

function Splash() {
  return (
    <div className="flex h-[100dvh] flex-col items-center justify-center gap-4">
      <span className="grid size-16 place-items-center rounded-full bg-gradient-to-b from-brand-soft to-brand text-3xl shadow-[0_10px_30px_-10px_var(--color-brand)]">
        🎲
      </span>
      <p className="animate-pulse-soft text-[13px] text-muted">در حال آماده‌سازی…</p>
    </div>
  );
}

function ConnectionError({
  message,
  onRetry,
}: {
  message: string | null;
  onRetry: () => void;
}) {
  return (
    <div className="flex h-[100dvh] items-center justify-center px-6">
      <div className="flex w-full max-w-sm flex-col items-center gap-4 text-center">
        <span className="grid size-16 place-items-center rounded-full bg-surface-2 text-3xl">
          📡
        </span>
        <p className="text-[15px] leading-relaxed">
          {message ?? "ارتباط با سرور برقرار نشد."}
        </p>
        <Button onClick={onRetry}>تلاش دوباره</Button>
      </div>
    </div>
  );
}
