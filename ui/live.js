// The live channel (WS /api/live): positions while playing, state changes,
// notices. It reconnects by itself and says so: "connecting", "open",
// "reconnecting" go to onStatus so the toolbar can show it.

const BASE_DELAY_MS = 500;
const MAX_DELAY_MS = 8000;

/** Wait before reconnect attempt number `attempt` (0 is the first): doubling, capped. */
export function reconnectDelay(attempt) {
  return Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** attempt);
}

/**
 * Connect and keep connected. `onOpen(send)` gets a sender for each new connection. The environment is injectable for tests.
 * Returns a function that closes the channel for good.
 */
export function connectLive({
  url,
  onMessage,
  onStatus,
  onOpen = () => {},
  WebSocketImpl = globalThis.WebSocket,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
}) {
  let socket = null;
  let timer = null;
  let attempt = 0;
  let stopped = false;

  const connect = () => {
    timer = null;
    socket = new WebSocketImpl(url);
    socket.addEventListener("open", () => {
      attempt = 0;
      onStatus("open");
      const open = socket;
      // A sender for this connection (pings for the playhead clock's offset).
      onOpen((message) => {
        if (open.readyState === undefined || open.readyState === 1)
          open.send(JSON.stringify(message));
      });
    });
    socket.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return; // A garbled push is not worth dropping the connection for.
      }
      onMessage(message);
    });
    socket.addEventListener("close", () => {
      if (stopped || timer !== null) return;
      onStatus("reconnecting");
      timer = setTimer(connect, reconnectDelay(attempt));
      attempt += 1;
    });
    // An error is always followed by a close, which does the reconnecting.
  };

  onStatus("connecting");
  connect();
  return () => {
    stopped = true;
    if (timer !== null) clearTimer(timer);
    socket?.close();
  };
}
