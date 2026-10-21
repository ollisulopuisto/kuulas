// Show log while the automixer runs: the pure parts of the live log viewer. The dialog itself
// is automix-live-dialog.js; the lines come from GET /api/automix/live (src/kuulas/server.py).

/** The viewer shows at most this many lines (the server keeps the same number). */
export const LIVE_MAX_LINES = 3000;
/** How often the open viewer asks while the automixer runs. */
export const LIVE_POLL_MS = 1000;

const tail = (lines) => (lines.length > LIVE_MAX_LINES ? lines.slice(-LIVE_MAX_LINES) : lines);

/**
 * What to do with a poll: `{ reset, add }`. `shown`: { lines, started } as on screen; `polled`:
 * the server's { lines, started }, the newest lines of the whole run. With `reset` the view is
 * emptied first, then `add` is appended; without it only the new lines are appended (the
 * longest end of the view that the answer starts with marks where the news begins).
 */
export function mergeLive(shown, polled) {
  const fresh = polled.lines;
  if (shown.lines.length === 0) return { reset: false, add: tail(fresh) };
  if (polled.started !== shown.started) return { reset: true, add: tail(fresh) };
  const last = shown.lines.at(-1);
  for (let i = fresh.length - 1; i >= 0; i -= 1) {
    const overlap = i + 1;
    if (fresh[i] !== last || overlap > shown.lines.length) continue;
    const from = shown.lines.length - overlap;
    let same = true;
    for (let j = 0; j < overlap; j += 1) {
      if (shown.lines[from + j] !== fresh[j]) {
        same = false;
        break;
      }
    }
    if (same) return { reset: false, add: tail(fresh.slice(overlap)) };
  }
  return { reset: true, add: tail(fresh) };
}

/** True when the text area is at (or within a few pixels of) its end: new lines scroll into view. */
export function stickToBottom({ scrollTop, clientHeight, scrollHeight }, slack = 24) {
  return scrollHeight - (scrollTop + clientHeight) <= slack;
}

/** Poll only while the viewer is open and the automixer is running. */
export const shouldPoll = ({ open, running }) => Boolean(open && running);

/** The message key of the status next to the text. */
export const liveStatusKey = (running) =>
  running ? "ui.automix.live_running" : "ui.automix.live_finished";
