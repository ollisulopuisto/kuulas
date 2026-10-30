// The speed of a ruler drag (WP26): programme seconds per second, negative when the pointer
// moves toward the start. The engine plays the scrub burst at that tape speed (engine.scrub).
// Pure: the caller keeps the recent pointer samples. Not wired to the ruler yet.

/** Samples older than this (ms) before the newest do not count: the speed is "now". */
export const WINDOW_MS = 80;

/**
 * @param {{t: number, frame: number}[]} samples pointer samples, oldest first (t in ms)
 * @param {number} rate project sample rate
 * @returns {number} programme seconds per second; 0 with fewer than two usable samples
 */
export function dragVelocity(samples, rate) {
  const last = samples.at(-1);
  if (!last || !(rate > 0)) return 0;
  const first = samples.find((sample) => last.t - sample.t <= WINDOW_MS);
  if (!first || last.t <= first.t) return 0;
  return (last.frame - first.frame) / rate / ((last.t - first.t) / 1000);
}

/** Fewest ms between two scrub requests: each one plays a ~90 ms burst. */
export const SEND_EVERY_MS = 30;
/** Samples kept: the newest few cover the velocity window. */
const KEEP = 12;

/**
 * One ruler press and drag. `send(frame, velocity)` asks the engine for a burst at the
 * pointer; the press itself already put the play cursor there (lanes.js pointerIntent).
 * @param {{send: (frame: number, velocity: number) => void, rate: number}} options
 */
export function createRulerScrub({ send, rate }) {
  let samples = [];
  let sentAt = Number.NEGATIVE_INFINITY;
  let sentFrame = null;
  return {
    /** The press: where and when. Sends nothing. */
    down(frame, t) {
      samples = [{ t, frame }];
      sentFrame = frame;
      sentAt = t;
    },
    /** A pointer move. Returns true when it asked for a burst. */
    move(frame, t) {
      if (samples.length === 0) return false;
      samples.push({ t, frame });
      if (samples.length > KEEP) samples.shift();
      if (frame === sentFrame || t - sentAt < SEND_EVERY_MS) return false;
      sentFrame = frame;
      sentAt = t;
      send(frame, dragVelocity(samples, rate));
      return true;
    },
    /** Release or cancel. */
    up() {
      samples = [];
      sentFrame = null;
    },
    get active() {
      return samples.length > 0;
    },
  };
}
