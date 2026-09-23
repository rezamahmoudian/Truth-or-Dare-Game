import { clearTokens, getAccessToken } from "@/lib/auth";

export type SocketStatus = "idle" | "connecting" | "open" | "reconnecting" | "dead";

type EventHandler = (type: string, data: Record<string, unknown>) => void;
type StatusHandler = (status: SocketStatus) => void;

const SUBPROTOCOL = "ft.jwt";
const PING_INTERVAL_MS = 20_000;
const MAX_BACKOFF_MS = 30_000;

function socketUrl(): string {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/ws/`;
}

/**
 * One connection for the whole app.
 *
 * Disconnection is treated as the normal case rather than an error path: on
 * mobile data the socket drops constantly, so reconnecting, re-subscribing and
 * telling the app to backfill what it missed are ordinary operations, not
 * recovery from a fault.
 */
class AppSocket {
  private ws: WebSocket | null = null;
  private status: SocketStatus = "idle";
  private attempts = 0;
  private reconnectTimer: number | null = null;
  private pingTimer: number | null = null;
  // `close()` is a teardown, not a dropped connection. Without this flag the
  // socket's own onclose handler treats an intentional close as a failure and
  // immediately reconnects, so the socket can never actually be shut down.
  private closedOnPurpose = false;

  private readonly eventHandlers = new Set<EventHandler>();
  private readonly statusHandlers = new Set<StatusHandler>();
  private readonly subscriptions = new Set<string>();
  private readonly outbox: string[] = [];

  /** Fired after a reconnect so callers can fetch what they missed. */
  private readonly resumeHandlers = new Set<() => void>();
  private hasConnectedBefore = false;

  connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const token = getAccessToken();
    if (!token) return;

    this.closedOnPurpose = false;
    this.setStatus(this.hasConnectedBefore ? "reconnecting" : "connecting");

    // The token travels as a subprotocol rather than a query parameter: query
    // strings land in access and proxy logs, and this one is a live credential.
    const ws = new WebSocket(socketUrl(), [SUBPROTOCOL, token]);
    this.ws = ws;

    ws.onopen = () => {
      this.attempts = 0;
      this.setStatus("open");

      for (const conversationId of this.subscriptions) {
        this.raw({ type: "conv.subscribe", data: { conversation_id: conversationId } });
      }
      while (this.outbox.length) {
        const frame = this.outbox.shift();
        if (frame) ws.send(frame);
      }

      this.startPing();
      if (this.hasConnectedBefore) this.resumeHandlers.forEach((handler) => handler());
      this.hasConnectedBefore = true;
    };

    ws.onmessage = (event) => {
      try {
        const frame = JSON.parse(event.data as string) as {
          type: string;
          data: Record<string, unknown>;
        };
        this.eventHandlers.forEach((handler) => handler(frame.type, frame.data ?? {}));
      } catch {
        /* a frame we cannot parse is not worth killing the connection over */
      }
    };

    ws.onclose = (event) => {
      this.stopPing();
      this.ws = null;
      if (this.closedOnPurpose) return;

      // 4401 means the token was rejected, not that the network failed.
      // Reconnecting with the same credential would loop forever, so the
      // session is cleared and the app re-authenticates from the top.
      if (event.code === 4401) {
        clearTokens();
        this.setStatus("dead");
        location.reload();
        return;
      }
      this.scheduleReconnect();
    };

    ws.onerror = () => {
      /* onclose always follows; the retry is handled there */
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) return;
    this.setStatus("reconnecting");

    // Exponential backoff with jitter. The jitter matters more than it looks:
    // a cell tower coming back hands every client the network at once, and
    // without it they would all reconnect in the same millisecond.
    const base = Math.min(MAX_BACKOFF_MS, 500 * 2 ** this.attempts);
    const delay = base / 2 + Math.random() * (base / 2);
    this.attempts += 1;

    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = window.setInterval(() => {
      this.raw({ type: "ping", data: {} });
    }, PING_INTERVAL_MS);
  }

  private stopPing(): void {
    if (this.pingTimer !== null) {
      window.clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private setStatus(status: SocketStatus): void {
    if (this.status === status) return;
    this.status = status;
    this.statusHandlers.forEach((handler) => handler(status));
  }

  private raw(frame: unknown): void {
    const text = JSON.stringify(frame);
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(text);
    else this.outbox.push(text);
  }

  // -- public API --------------------------------------------------------

  send(type: string, data: Record<string, unknown>): void {
    this.raw({ type, data });
    // Anything queued while offline goes out on the next open. Sends carry a
    // client_id, so a frame that was actually delivered before the drop is
    // recognised as a duplicate by the server rather than posted twice.
    if (this.ws?.readyState !== WebSocket.OPEN) this.connect();
  }

  subscribe(conversationId: string): void {
    this.subscriptions.add(conversationId);
    this.raw({ type: "conv.subscribe", data: { conversation_id: conversationId } });
  }

  unsubscribe(conversationId: string): void {
    this.subscriptions.delete(conversationId);
    this.raw({ type: "conv.unsubscribe", data: { conversation_id: conversationId } });
  }

  onEvent(handler: EventHandler): () => void {
    this.eventHandlers.add(handler);
    return () => this.eventHandlers.delete(handler);
  }

  onStatus(handler: StatusHandler): () => void {
    this.statusHandlers.add(handler);
    handler(this.status);
    return () => this.statusHandlers.delete(handler);
  }

  onResume(handler: () => void): () => void {
    this.resumeHandlers.add(handler);
    return () => this.resumeHandlers.delete(handler);
  }

  close(): void {
    this.closedOnPurpose = true;
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.stopPing();
    this.ws?.close();
    this.ws = null;
    this.setStatus("idle");
  }
}

export const socket = new AppSocket();

// Reachable from the console in development so connection loss can actually be
// exercised: `__ftSocket.close()` then `__ftSocket.connect()` reproduces a
// tunnel dropping, which is otherwise awkward to trigger on demand.
if (import.meta.env.DEV) {
  (window as unknown as { __ftSocket: AppSocket }).__ftSocket = socket;
}
