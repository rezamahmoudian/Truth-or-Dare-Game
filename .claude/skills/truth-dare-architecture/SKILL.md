---
name: truth-dare-architecture
description: Binding architecture and design rules for the Truth-or-Dare social game in this repo (Django + DRF + Channels + Celery + Postgres + Redis backend, React + Vite + Tailwind mobile-first PWA frontend, Persian/RTL). Consult this before writing or reviewing ANY code, model, migration, WebSocket event, API endpoint, or UI screen in this project — including work that looks trivial like "just add a field" or "just add a button". Also use it when discussing the product's data model, chat, matchmaking, game turns, friends, realtime behavior, PWA/APK packaging, moderation, or deployment. These rules were agreed with the product owner after design discussion; violating them silently costs a rewrite later.
---

# Truth-or-Dare Social Game — Architecture Rules

## What this product actually is

A **messenger whose onboarding engine is a game.** Strangers meet through a
random Truth-or-Dare match, then become friends and keep chatting — and can
launch a new game from inside that friend chat at any time.

Both halves matter equally. Day 1 the user opens the app to play. Day 10 they
open it to talk to friends. Code that treats chat as "a feature of the game
room" will have to be rewritten; chat is a first-class product.

The **home screen is the game-mode picker** (quick match, group, gender-filtered,
plus modes added later). Chat, friends and profile live in other tabs. This was
the owner's explicit decision — do not quietly redesign navigation around the
chat list. Do keep an unread badge on the chat tab visible from home, because
without it the chat half of the product decays unnoticed.

---

## Data model invariants

**Everything is a `Conversation`.** Two types: `ROOM` (2–8 people, created by
matchmaking) and `DIRECT` (2 people, created when a friendship is accepted).
One `Message` table, one participant table, one read-tracking mechanism. The
alternative — separate "room chat" and "private chat" systems — means writing
unread counts, typing indicators, reactions, pagination and moderation twice,
and they will drift.

**`GameSession` points at a `Conversation`, never the reverse.** This is what
makes "play with strangers" and "play with a friend mid-conversation" the same
code path: matchmaking creates a ROOM conversation and starts a session in it;
a friend chat already has a DIRECT conversation and starts a session in it.

**Game events are messages.** A turn's choice, the prompt, and the answer are
rows in `Message` with types `SYSTEM` / `GAME_PROMPT` / `GAME_ANSWER`, rendered
inline in the same scroll as ordinary chat. This is the product thesis in the
schema: the game exists to create things to talk about, so the game and the
talking must be one stream, not two panes.

**`Message.id` is bigint, not UUID.** Cursor pagination and unread counts both
reduce to integer comparison (`WHERE id > participant.last_read_message_id`).
`Conversation.id` stays UUID because it appears in shareable links.

**Denormalize `last_message_at` and `last_message_preview` onto `Conversation`.**
The chat list is the most-hit screen in the app; without this it is an N+1 query
on every open.

**`MatchMode` is data, not code.** Modes live in the database with their own
size range, gender target, category, min age, premium flag and sort order. The
frontend renders whatever `GET /api/match-modes/` returns. The owner intends to
add modes over time, and this project ships as an installed APK — a hardcoded
mode list would mean a store release for every new mode.

**Safety fields exist from the first migration**, even before their UI does:
`Block`, `Report`, `User.birth_date`, prompt `intensity` and `category`. Adding
these late means backfilling across live conversations.

---

## Realtime contract

**One WebSocket per user, not per conversation.** The client always joins group
`user.{id}` and receives events for every conversation it belongs to; it
additionally subscribes to `conv.{uuid}` while that conversation's screen is
open, for ephemeral traffic (typing, presence) that must never be persisted.
A socket per conversation means ten friends equals ten sockets on a phone.

**Every client-sent message carries a `client_id`.** The client renders it
immediately (optimistic), the server echoes the same `client_id` back, and the
client reconciles. This also makes retries idempotent — without it, a retry
after a flaky connection creates a duplicate message.

**Treat disconnection as the normal case, not an error path.** Iranian mobile
data drops constantly. From the first realtime commit: reconnect with backoff,
and on reconnect fetch `GET /conversations/{id}/messages?after={last_id}` to
fill the gap. A realtime layer that assumes a stable socket looks fine on
Wi-Fi and fails in the field — test on real mobile data, not the office router.

**Redis is cache and ephemeral state; Postgres is truth.** Presence sets,
typing TTL keys, the matchmaking queue and the cached current turn live in
Redis. Anything whose loss would corrupt a game or lose a message goes to
Postgres. A Redis restart must not end anyone's game.

**All ORM access inside consumers goes through `database_sync_to_async`.**
This is the single most common way Django + Channels projects break, and the
failure is a silent event-loop stall under load, not an exception.

---

## Game engine rules

**The server is the sole authority on turn state.** The client never advances
a turn, never picks the next player, never decides a timeout expired. Clients
render what the server says.

**There are no timers anywhere in the game.** The state machine is
`CHOOSING → ANSWERING → CONFIRMING → next turn`, and every arrow is pulled by a
person. Nothing expires, nothing is scheduled, no Celery task advances a turn.
A room may sit on one turn for an hour while the players talk about something
else — that conversation *is* the product, and a countdown would cut it off.

**A turn advances only by human confirmation.** With two players the opponent
confirms, and the turn then becomes theirs. In a group, more than half of
everyone except the answerer. And the room owner alone, at any moment, with or
without an answer — so there is always somebody who can unstick a turn, and
ownership passes to the oldest remaining member if the owner leaves.

**A game has no planned length.** No round count, no turn cap, nothing to be a
fraction of. It ends when the owner ends it or when fewer than two players
remain — the same rule the room itself follows. Count turns upward for display
("round 3 · turn 7"); never show "7 of 12", because there is no 12.

The general principle behind all three: **the software never decides that
people are finished.** Anything that would end, expire or cap something on the
users' behalf needs a very good reason, and "it keeps the game tidy" is not
one.

**A player leaving mid-game is a defined transition, not an exception.** Decide
and implement: reassign the turn if it was theirs, continue if quorum holds,
end the session if it does not.

---

## Matchmaking rules

**Matching happens in one centralized matcher under a Redis lock**, not in
clients and not in parallel workers. Two users independently deciding they
matched each other produces split rooms — a bug that is very hard to reproduce
and very easy to prevent.

**Relax constraints after ~20 seconds of waiting, and tell the user you did.**
An unbounded wait in a filtered queue is the most common way these apps lose a
first-time user. Widening plus an honest "searching more broadly…" keeps them.

**The waiting screen is never silent.** Show elapsed time, queue size or
position, motion, and a concrete alternative ("try group mode"). Silence reads
as "broken".

**Filter out blocked pairs and recently-played opponents** before matching.

**Gender-filtered modes are asymmetric in practice.** These products skew
heavily male, so demand for "play with a girl" vastly exceeds supply while the
reverse queue fills instantly. Design around it rather than discovering it at
launch: quota or limit the scarce-direction mode, give priority to the
under-supplied side, widen automatically toward group mode, and keep "quick"
and "group" visually dominant on the home screen so traffic flows to queues
that actually fill. Gender is required on the profile and changing it must be
restricted, otherwise the filter is meaningless.

---

## Mobile / PWA rules

This is a mobile-first PWA that is also packaged as a TWA APK. The UI is
Persian and RTL.

- Use `100dvh`, never `100vh` — the mobile address bar collapses and a `vh`
  layout jumps as the user scrolls, which is very visible in a chat screen.
- `dir="rtl"` on `<html>` from the first commit, and Tailwind logical
  properties (`ps-`/`pe-`/`ms-`/`me-`) rather than left/right. Retrofitting RTL
  onto an LTR codebase is painful and never fully clean.
- Chat screens use a fixed shell: header pinned, message list scrolling
  internally, composer pinned with `env(safe-area-inset-bottom)`. Never let the
  page itself scroll.
- Touch targets at least 44px.
- Self-host Vazirmatn; do not load fonts from Google Fonts.
- **The app must be fully playable with no push notifications.** This is
  easier than it sounds here, because nothing in the app expires: no turn times
  out and no game ends on its own, so opening the app late costs nothing.
  Presence and invites arrive over the WebSocket and in-app notification UI
  covers the rest. Web push on Android routes through Google's
  FCM endpoints, which are not reliably reachable for Iranian users — treat push
  as a bonus that may silently never arrive, never as a load-bearing dependency.
- Distribution assumes direct APK download plus Iranian stores (Bazaar, Myket)
  rather than Google Play; hosting assumes an Iran-reachable provider (Liara,
  ArvanCloud) or a self-managed VPS, since Vercel/Netlify/Cloudflare block
  Iranian developers and users. If the product later targets a non-Iranian
  audience, revisit this section explicitly rather than assuming it still holds.

---

## Safety and compliance

Strangers plus private chat plus "dare" content means moderation is
load-bearing, not polish. An 18+ age gate, reporting on both users and
individual messages, two-way blocking that also excludes the pair from
matchmaking, profanity filtering on chat and answers, prompt
`intensity`/`category` tiers, rate limiting, and an admin panel for handling
reports. Iranian app stores ask about this at review, and a product that cannot
answer gets pulled.

---

## Operations

From the first phase: structured logging, a `/health` endpoint, Sentry, and
counters for the events that reveal where users drop — `mm.enqueue`,
`mm.matched`, `mm.expired`, game started, game ended (with its reason), friend
request sent, friend request accepted, message sent. Without those numbers, arguments about why retention is
bad become guesswork.

---

## How to use these rules

They are constraints, not a checklist to recite. When a task touches one,
follow it and briefly say which rule drove the choice so the owner can disagree
knowingly. When a task seems to require breaking one, say so explicitly and
propose the alternative rather than quietly working around it — each rule above
exists because the alternative was considered and costs more later.
