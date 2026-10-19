// How a take is stopped (owner, 2026-10-19): a PREFERENCE with three modes.
//   "two_step" (default): the first press (Space or a click on Stop) only asks, "Stop
//     recording? Press again"; a second press within the confirm window (4 s) stops. When the
//     window runs out the view quietly returns to recording: a stray tap leaves nothing in limbo.
//   "one_click": the first press stops.
//   "hold": hold for 2 s (hold-stop.js); releasing early cancels.
// The recording goes on in every state until "stopped". Esc, closing the window and clicks
// elsewhere are not presses: the view never feeds them in. Pure: time is passed in.
import { createHoldStop } from "./hold-stop.js";

export const STOP_MODES = ["two_step", "one_click", "hold"];
export const DEFAULT_STOP_MODE = "two_step";
export const CONFIRM_MS = 4000;
export const HOLD_MS = 2000;

export const stopModeChoice = (stored) =>
  STOP_MODES.includes(stored) ? stored : DEFAULT_STOP_MODE;
export const nextStopMode = (mode) =>
  STOP_MODES[(STOP_MODES.indexOf(stopModeChoice(mode)) + 1) % STOP_MODES.length];

/**
 * One stop gesture for one take. press/release/tick(t) answer the view:
 *   { state: "recording" | "confirming" | "holding" | "stopped", stopped, secondsLeft,
 *     progress, heldMs }
 * `stopped` is true exactly once, on the call that stops (then send the stop request).
 * `secondsLeft` counts the confirm window down (two steps); `progress` fills 0..1 (hold).
 * A press while the key or button is still down (auto-repeat) is not a second press.
 */
export function createStopGesture({
  mode = DEFAULT_STOP_MODE,
  confirmMs = CONFIRM_MS,
  holdMs = HOLD_MS,
} = {}) {
  const chosen = stopModeChoice(mode);
  const hold = createHoldStop({ holdMs });
  let state = "recording";
  let confirmAt = null;
  let down = false;

  const view = (extra = {}) => {
    let secondsLeft = 0;
    if (state === "confirming") {
      secondsLeft = Math.max(1, Math.ceil((confirmMs - (extra.elapsed ?? 0)) / 1000));
    }
    return {
      state,
      stopped: false,
      secondsLeft,
      progress: 0,
      heldMs: 0,
      ...extra,
      elapsed: undefined,
    };
  };

  // The confirm window, measured from where the clock is; a clock that went backwards
  // moves the start back with it (never a stop, never stuck).
  const elapsedAt = (t) => {
    if (confirmAt === null) return 0;
    if (t < confirmAt) confirmAt = t;
    return t - confirmAt;
  };

  const stop = (extra = {}) => {
    state = "stopped";
    confirmAt = null;
    return view({ stopped: true, ...extra });
  };

  return {
    mode: chosen,
    press(t) {
      if (state === "stopped") return view();
      if (down) return state === "confirming" ? view({ elapsed: elapsedAt(t) }) : view();
      down = true;
      if (chosen === "one_click") return stop();
      if (chosen === "hold") {
        hold.press(t);
        state = "holding";
        return view();
      }
      if (state === "confirming") {
        const before = confirmAt;
        const elapsed = elapsedAt(t);
        if (before !== null && t >= before && elapsed <= confirmMs) return stop();
        // Too late (the window ended without a tick) or the clock jumped: ask again.
        confirmAt = t;
        return view({ elapsed: 0 });
      }
      state = "confirming";
      confirmAt = t;
      return view({ elapsed: 0 });
    },
    release(t) {
      down = false;
      if (chosen === "hold" && state === "holding") {
        hold.release(t);
        state = "recording";
      }
      return state === "confirming" ? view({ elapsed: elapsedAt(t) }) : view();
    },
    tick(t) {
      if (state === "confirming") {
        const elapsed = elapsedAt(t);
        if (elapsed > confirmMs) {
          state = "recording";
          confirmAt = null;
          return view();
        }
        return view({ elapsed });
      }
      if (state === "holding") {
        const h = hold.tick(t);
        if (h.stopped) return stop({ progress: 1, heldMs: holdMs });
        return view({ progress: h.progress });
      }
      return view();
    },
    reset() {
      hold.reset();
      state = "recording";
      confirmAt = null;
      down = false;
    },
  };
}
