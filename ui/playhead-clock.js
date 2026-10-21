// The playhead between the engine's anchors (precise cursor, 2026-10-20).
//
// The server sends an anchor on every transport change and a correction about every
// 200 ms while playing: { position, t, now, speed, seq, end, skip, loop, rate, playing }.
// `t` is the server's monotonic time (seconds) the position was heard at. The page
// maps it to performance.now() with a clock offset and draws the playhead every
// animation frame from the latest anchor, so the cursor moves with the screen and a
// late reading on the server costs nothing visible.
//
// Clock offset: the page pings the live channel ({type:"ping", c: performance.now()})
// and the server answers {type:"pong", c, s: its monotonic seconds as it sends}. With
// the round trip `received - c`, the server's clock read at about the midpoint, so
// offset = s*1000 - (c + received)/2. The sample with the shortest round trip wins
// (its midpoint error is at most rtt/2; on loopback well under a millisecond). Both
// clocks are monotonic on one machine and do not drift apart. Until there is an
// offset, an anchor is dated by its age when it arrived: `received - (now - t)`.
//
// Smoothing (owner, 2026-10-21: "stutter in playback cursor's location again! jumps a
// few pixels back and then keeps continuing"): during a steady run (the same `seq`, the
// same speed) the drawn position is the extrapolation plus a correction that fades to
// nothing over SLEW_MS. A new anchor that disagrees with what is on screen (jitter in
// the device latency, a late callback, a poll answered with an older reading) therefore
// slows or speeds the cursor for a moment, 40% at the worst, instead of stepping it
// back or freezing it, so the cursor never goes against the playing direction. A
// disagreement of JUMP_S or more, a new `seq` (seek, new run), a speed change or a
// stop is taken at once. A reading older than the one in use (out of order) is dropped.

/** Legacy: backward corrections up to this many seconds used to be held (see JUMP_S). */
export const SNAP_S = 0.05;
/** A correction of this many seconds or more, either way, is a jump and is taken at once. */
export const JUMP_S = 0.15;
/** A smaller correction is slewed in over this many milliseconds. */
export const SLEW_MS = 250;
/** Without a fresh anchor the playhead stops this far past the last one. */
export const MAX_AHEAD_MS = 750;

/** The offset (server ms minus page ms) from ping samples { sent, received, server }. */
export function bestOffset(samples) {
  let best = null;
  for (const { sent, received, server } of samples) {
    const rtt = received - sent;
    if (best === null || rtt < best.rtt)
      best = { rtt, offset: server * 1000 - (sent + received) / 2 };
  }
  return best === null ? null : best.offset;
}

/** The anchor in page time: { frame, at (performance.now() ms), speed, rate, ... }. */
export function anchorFrom(message, { offset, receivedAt }) {
  const at =
    offset === null || offset === undefined
      ? receivedAt - (message.now - message.t) * 1000
      : message.t * 1000 - offset;
  return {
    frame: message.position,
    at,
    speed: message.speed ?? 1,
    rate: message.rate ?? 48_000,
    playing: Boolean(message.playing),
    seq: message.seq ?? null,
    end: message.end ?? null,
    skip: message.skip ?? [],
    loop: message.loop ?? null,
  };
}

/** Move `distance` frames (signed) from `from`, jumping over the skipped ranges. */
function walk(from, distance, skip) {
  const ranges = [...skip].sort((x, y) => x[0] - y[0]);
  let pos = from;
  let left = Math.abs(distance);
  if (distance >= 0) {
    for (const [a, b] of ranges) {
      if (b <= pos) continue;
      if (a <= pos) {
        pos = b;
        continue;
      }
      if (pos + left < a) break;
      left -= a - pos;
      pos = b;
    }
    return pos + left;
  }
  for (const [a, b] of ranges.reverse()) {
    if (a >= pos) continue;
    if (b >= pos) {
      pos = a;
      continue;
    }
    if (pos - left > b) break;
    left -= pos - b;
    pos = a;
  }
  return pos - left;
}

/** The frame heard at page time `now` by the anchor alone. */
export function project(anchor, now) {
  if (!anchor.playing) return anchor.frame;
  const ms = Math.min(Math.max(0, now - anchor.at), MAX_AHEAD_MS);
  let pos = walk(anchor.frame, (ms / 1000) * anchor.speed * anchor.rate, anchor.skip);
  if (anchor.loop && anchor.speed > 0 && pos >= anchor.loop[1]) {
    const [lo, hi] = anchor.loop;
    pos = lo + ((pos - lo) % Math.max(1, hi - lo));
  }
  if (anchor.end !== null)
    pos = anchor.speed > 0 ? Math.min(pos, anchor.end) : Math.max(pos, anchor.end);
  return Math.max(0, pos);
}

/** The page's playhead model: anchors in, a frame for any moment out. */
export function createPlayheadClock() {
  let anchor = null;
  let offset = null;
  let samples = [];
  let newest = null; // the newest seq accepted
  let stopSeq = null; // a local stop: playing anchors must be newer than this
  let slew = null; // { frames, at }: the correction on screen, fading out from `at`
  let snapNext = false; // the next playing anchor is taken at once (a local jump)

  /** The correction (frames) still to fade out at page time `now`. */
  const correction = (now) => {
    if (!slew) return 0;
    const left = 1 - (now - slew.at) / SLEW_MS;
    return left > 0 ? slew.frames * left : 0;
  };
  /** The drawn frame at `now` (not rounded). */
  const display = (now) => {
    const target = project(anchor, now);
    if (!anchor.playing) return target;
    let pos = Math.max(0, target + correction(now));
    if (anchor.end !== null)
      pos = anchor.speed > 0 ? Math.min(pos, anchor.end) : Math.max(pos, anchor.end);
    return pos;
  };

  return {
    setOffset(value) {
      offset = value;
    },
    offset: () => offset,
    /** A pong arrived: keep the sample (the few best are enough). */
    pong(sent, server, received) {
      samples = [...samples, { sent, received, server }]
        .sort((x, y) => x.received - x.sent - (y.received - y.sent))
        .slice(0, 8);
      offset = bestOffset(samples);
    },
    /** An anchor from the server; false when it is older than what is known. */
    accept(message, receivedAt) {
      const seq = message.seq ?? null;
      if (seq !== null && newest !== null && seq < newest) return false;
      if (message.playing && stopSeq !== null && seq !== null && seq <= stopSeq) return false;
      const next = anchorFrom(message, { offset, receivedAt });
      const steady =
        next.playing &&
        anchor?.playing &&
        seq === newest &&
        next.speed === anchor.speed &&
        !snapNext;
      // The same run, but a reading from before the one in use (out of order): the
      // newer one is the better line, keep it.
      if (steady && next.at < anchor.at) return false;
      if (steady) {
        const shown = display(receivedAt);
        anchor = next;
        const diff = shown - project(next, receivedAt);
        const jump = JUMP_S * next.rate * Math.abs(next.speed);
        slew = Math.abs(diff) >= jump ? null : { frames: diff, at: receivedAt };
      } else {
        anchor = next;
        slew = null;
      }
      if (next.playing) snapNext = false;
      if (seq !== null) newest = seq;
      if (!next.playing) stopSeq = null;
      return true;
    },
    /** The frame to draw at page time `now`. */
    frameAt(now) {
      if (!anchor) return 0;
      return Math.round(display(now));
    },
    playing: () => Boolean(anchor?.playing),
    /** Space/Stop: freeze where the cursor is now, before the engine answers. */
    stop(now) {
      const frame = anchor ? this.frameAt(now) : 0;
      stopSeq = newest ?? -1;
      anchor = {
        ...(anchor ?? anchorFrom({ position: 0, t: 0, now: 0 }, { offset: 0, receivedAt: 0 })),
        frame,
        playing: false,
      };
      slew = null;
      return frame;
    },
    /** A seek: the cursor goes to `frame` now (playing on from there if playing). */
    jump(frame, now) {
      if (!anchor) return;
      anchor = { ...anchor, frame, at: now };
      slew = null;
      snapNext = true;
    },
    /** The engine's answer to a stop (or any stopped state): the heard frame. */
    settle(frame) {
      if (anchor) anchor = { ...anchor, frame, playing: false };
      slew = null;
    },
  };
}
