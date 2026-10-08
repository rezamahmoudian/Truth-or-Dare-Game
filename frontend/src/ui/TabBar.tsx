import { NavLink } from "react-router-dom";

import { faNum } from "@/lib/dates";
import { useChat } from "@/store/chat";
import { useSocial } from "@/store/social";
import { useInvitations } from "@/store/invitations";
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
  const invitations = useInvitations((s) => s.lists.incoming.length + s.lists.ready.length);

  return (
    <nav
      className="app-tabbar shrink-0"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <ul className="mx-auto flex max-w-md gap-1 rounded-[24px] border border-line bg-surface p-1.5">
        {TABS.map(({ to, label, Icon, end }) => {
          const badge = to === "/chats" ? unread : to === "/friends" ? requests : to === "/" ? invitations : 0;

          return (
            <li key={to} className="flex-1">
              <NavLink
                to={to}
                end={end}
                className={({ isActive }) =>
                  `flex h-[56px] w-full flex-col items-center justify-center gap-1 rounded-[18px] text-[11px] transition-colors ${
                    isActive ? "bg-brand/10 font-bold text-brand" : "text-muted"
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
