// Sending edits: show the result at once, send the latest value, apply the
// server's answer only when nothing newer is waiting.
//
// A slider drag fires dozens of `input` events. Each one updates the screen
// through its `provisional` function straight away. Requests go out one at a
// time (the server commits each to the history before it answers), and a queued
// request with the same coalesce key is replaced by the newer one, so a drag
// costs a handful of round trips, not dozens, and the server merges them into
// one undo step by the key. The answers to all but the last are stale; showing
// them would make the slider jump back.

export function createEditor({ send, getProject, setProject, acceptServer, onError }) {
  let queue = [];
  let inFlight = false;

  async function pump() {
    if (inFlight || queue.length === 0) return;
    const request = queue.shift();
    inFlight = true;
    try {
      const response = await send({
        op: request.op,
        args: request.args,
        label: request.label ?? null,
        coalesce: request.coalesce ?? null,
      });
      if (queue.length === 0) acceptServer(response);
    } catch (error) {
      queue = [];
      onError(error);
    } finally {
      inFlight = false;
    }
    void pump();
  }

  return {
    /** change({ op, args, coalesce?, label?, provisional? }) */
    change(change) {
      if (change.provisional) setProject(change.provisional(getProject()));
      const entry = {
        op: change.op,
        args: change.args,
        label: change.label,
        coalesce: change.coalesce,
      };
      const queued = change.coalesce
        ? queue.findIndex((item) => item.coalesce === change.coalesce)
        : -1;
      if (queued >= 0) queue[queued] = entry;
      else queue.push(entry);
      void pump();
    },
    get busy() {
      return inFlight || queue.length > 0;
    },
  };
}
