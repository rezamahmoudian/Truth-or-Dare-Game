import { useEffect, useState } from "react";

import { FriendButton } from "@/features/friends/FriendButton";
import { PersonMenu } from "@/features/moderation/PersonMenu";
import { faNum } from "@/lib/dates";
import * as social from "@/lib/socialApi";
import type { Person, PublicUser } from "@/lib/types";
import { useSocial } from "@/store/social";
import { Avatar } from "@/ui/Avatar";

/**
 * The people in this room, each with a friend button.
 *
 * This sheet is where the product's loop actually closes: someone finishes a
 * game, remembers who was funny, and taps one button. If that gesture is
 * buried the game produces nothing but a transcript, so it hangs off the room
 * header — one tap from anywhere in the conversation.
 */
export function PlayersSheet({
  participants,
  selfId,
  onlineIds,
  onClose,
}: {
  participants: PublicUser[];
  selfId: number;
  onlineIds: number[];
  onClose: () => void;
}) {
  const setRelation = useSocial((s) => s.setRelation);
  const [people, setPeople] = useState<Record<number, Person>>({});

  // The room payload carries only names and avatars; the relation has to come
  // from the server, or the button would guess.
  useEffect(() => {
    let cancelled = false;
    for (const person of participants) {
      if (person.id === selfId) continue;
      void social
        .getPerson(person.id)
        .then((full) => {
          if (cancelled) return;
          setPeople((current) => ({ ...current, [full.id]: full }));
          if (full.relation) setRelation(full.id, full.relation);
        })
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
  }, [participants, selfId, setRelation]);

  return (
    <div className="animate-fade-in fixed inset-0 z-50 flex flex-col justify-end bg-black/65 backdrop-blur-[2px]">
      <button
        type="button"
        aria-label="بستن"
        className="flex-1"
        onClick={onClose}
      />

      <div
        className="animate-sheet-in rounded-t-sheet border-t border-line bg-surface px-4 pb-6 pt-3"
        style={{ paddingBottom: "max(1.5rem, env(safe-area-inset-bottom))" }}
      >
        <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-line" />
        <h2 className="mb-3 px-1 text-[13px] font-bold text-muted">
          بازیکن‌ها ({faNum(participants.length)})
        </h2>

        <ul className="flex max-h-[50dvh] flex-col overflow-y-auto">
          {participants.map((person) => {
            const full = people[person.id];
            const isSelf = person.id === selfId;

            return (
              <li
                key={person.id}
                className="flex items-center gap-3 border-b border-line-soft py-3 last:border-b-0"
              >
                <span className="relative shrink-0">
                  <Avatar
                    avatarKey={person.avatar || "a1"}
                    name={person.display_name}
                    size={44}
                    glow
                  />
                  {onlineIds.includes(person.id) && (
                    <span className="absolute bottom-0 end-0 size-3 rounded-full border-2 border-surface bg-ok" />
                  )}
                </span>

                <div className="min-w-0 flex-1">
                  <p className="truncate text-[15px] font-bold">
                    {person.display_name}
                    {isSelf && <span className="text-xs text-muted"> (شما)</span>}
                  </p>
                  <p className="truncate text-xs text-muted">
                    @{person.username}
                    {full?.age != null && ` · ${faNum(full.age)} ساله`}
                  </p>
                </div>

                {!isSelf && (
                  <div className="flex shrink-0 items-center gap-1">
                    <FriendButton
                      userId={person.id}
                      relation={full?.relation}
                      compact
                    />
                    <PersonMenu
                      userId={person.id}
                      displayName={person.display_name}
                      onBlocked={onClose}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
