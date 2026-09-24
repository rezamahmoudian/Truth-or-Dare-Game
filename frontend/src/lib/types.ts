export type PublicUser = {
  id: number;
  username: string;
  display_name: string;
  avatar: string;
};

export type MessageType = "TEXT" | "SYSTEM" | "GAME_PROMPT" | "GAME_ANSWER";

export type Message = {
  id: number;
  conversation_id: string;
  type: MessageType;
  body: string;
  sender: PublicUser | null;
  reply_to_id: number | null;
  client_id: string;
  meta: Record<string, unknown>;
  created_at: string;
  is_deleted: boolean;
  reactions: Record<string, number[]>;
};

/** A message shown before the server has confirmed it. */
export type PendingMessage = Message & { pending: true; failed?: boolean };

export type AnyMessage = Message | PendingMessage;

export const isPending = (message: AnyMessage): message is PendingMessage =>
  "pending" in message && message.pending === true;

export type ReportReason = { key: string; label: string };

export type Relation =
  | "SELF"
  | "NONE"
  | "OUTGOING"
  | "INCOMING"
  | "FRIENDS"
  | "BLOCKED";

export type Person = {
  id: number;
  username: string;
  display_name: string;
  avatar: string;
  bio: string;
  gender: "" | "F" | "M";
  age: number | null;
  last_seen_at: string | null;
  relation?: Relation;
};

export type FriendRequest = {
  id: number;
  direction: "incoming" | "outgoing";
  user: Person;
  created_at: string;
};

export type FriendLists = {
  friends: Person[];
  incoming: FriendRequest[];
  outgoing: FriendRequest[];
};

export type MatchMode = {
  key: string;
  title: string;
  subtitle: string;
  emoji: string;
  accent: string;
  size_min: number;
  size_max: number;
  target_gender: "" | "F" | "M";
  is_featured: boolean;
  daily_limit: number;
  /** null = unlimited, 0 = today's cap is used up */
  remaining_today: number | null;
  /** How many people are waiting for a room of this shape, right now. */
  queue_size: number;
  queue_state: "FAST" | "SLOW" | "EMPTY";
};

export type Lobby = {
  modes: MatchMode[];
  online_count: number;
  active_people: Person[];
};

export type MatchTicket = {
  id: number;
  mode: string;
  state: "QUEUED" | "MATCHED" | "CANCELLED" | "EXPIRED";
  widened: boolean;
  waited_seconds: number;
  queue_size: number;
  conversation_id: string | null;
  suggested_mode?: string;
};

export type PromptChoice = "TRUTH" | "DARE";

export type Prompt = {
  id: number;
  type: PromptChoice;
  text: string;
  category: string;
  intensity: number;
};

export type TurnStatus =
  | "CHOOSING"
  | "ANSWERING"
  | "CONFIRMING"
  | "DONE"
  | "SKIPPED";

export type Turn = {
  id: number;
  index: number;
  player_id: number;
  status: TurnStatus;
  choice: PromptChoice | "";
  prompt: Prompt | null;
  answer_message_id: number | null;
  /** Who has vouched that the player did it, and how many are needed. */
  confirmations: number[];
  confirmations_required: number;
  version: number;
};

export type GameSession = {
  id: number;
  conversation_id: string;
  status: "ACTIVE" | "ENDED";
  turn_order: number[];
  turn_index: number;
  /** Which time around the table — display only; a game has no planned end. */
  round_number: number;
  category: string;
  max_intensity: number;
  ended_reason: string;
};

/** The server sends a full snapshot on every transition; never a delta. */
export type GameState = {
  session: GameSession | null;
  turn: Turn | null;
};

export type Conversation = {
  id: string;
  type: "ROOM" | "DIRECT";
  status: "WAITING" | "ACTIVE" | "CLOSED";
  code: string | null;
  owner_id: number | null;
  max_players: number;
  created_at: string;
  last_message_at: string | null;
  last_message_preview: string;
  unread_count: number;
  participants: PublicUser[];
};
