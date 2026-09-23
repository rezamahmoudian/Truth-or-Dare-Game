import { NavLink } from "react-router-dom";

import { faNum } from "@/lib/dates";
import { useChat } from "@/store/chat";
import { useSocial } from "@/store/social";
import { ChatIcon, FriendsIcon, HomeIcon, PersonIcon } from "@/ui/icons";

const TABS = [
  { to: "/", label: "خانه", Icon: HomeIcon, end: true },
  { to: "/chats", label: "چت", Icon: ChatIcon, end: false },
  { to: "/friends", label: "دوستان", Icon: FriendsIcon, end: false },
  { to: "/profile", label: "پروفایل", Icon: PersonIcon, end: false },
];

export function TabBar() {
  // The badges are why this is worth a component. Home is the game screen, so
  // without counts visible from there, a message from a friend or a pending
  // request is invisible until the person happens to open that tab — and the
  // half of the product that keeps people coming back quietly stops being used.
  const unread = useChat((s) =>
    s.conversations.reduce((sum, c) => sum + c.unread_count, 0),
  );
  const requests = useSocial((s) => s.lists.incoming.length);

  return (
    <nav
      className="shrink-0 border-t border-line-soft bg-ink-deep"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <ul className="mx-auto flex max-w-md">
        {TABS.map(({ to, label, Icon, end }) => {
          const badge = to === "/chats" ? unread : to === "/friends" ? requests : 0;

          return (
            <li key={to} className="flex-1">
              <NavLink
                to={to}
                end={end}
                className={({ isActive }) =>
                  `flex h-[64px] w-full flex-col items-center justify-center gap-1 text-[11px] transition-colors ${
                    isActive ? "font-bold text-brand" : "text-faint"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span className="relative">
                      <Icon size={23} filled={isActive} />
                      {badge > 0 && (
                        <span className="absolute -top-1.5 end-full me-0.5 min-w-[18px] rounded-full bg-brand px-1 text-center text-[10px] font-bold leading-[18px] text-white">
                          {faNum(badge > 99 ? "+۹۹" : badge)}
                        </span>
                      )}
                    </span>
                    {label}
                  </>
                )}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
