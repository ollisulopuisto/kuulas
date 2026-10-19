// Play, stop and seek. The engine is the clock: the live channel pushes its
// position, and what is set here is only the answer to a request or, for a
// seek, the provisional playhead.

//
// `speed` in the state is the engine's tape speed (signed; 1 at rest). Every answer
// sets it: what the engine says while playing, 1 when it is not.

import { effective } from "./fast-speed.js";
import { activeLoop } from "./loop-range.js";
import { press } from "./shuttle.js";

export function createTransport({ post, getState, setState, onError }) {
  // Quick J/K/L presses arrive before the engine has answered the last one: the ladder
  // climbs from the speed asked for (`intended`), and the requests go out in order.
  let intended = null;
  let pending = 0;
  let queue = Promise.resolve();

  // The newest seek asked for. Quick Alt+arrow presses send many seeks; their answers can
  // arrive out of order, and an older answer must not pull the playhead back.
  let seekSeq = 0;

  async function run(action, at = null, until = null, skip = null, options = null, mine = null) {
    try {
      const status = await (options
        ? post(action, at, until, skip, options)
        : post(action, at, until, skip));
      if (mine !== null && mine !== seekSeq) return; // a newer seek is on its way
      setState({
        playing: status.playing,
        playhead: status.position,
        speed: status.playing ? (status.speed ?? 1) : 1,
      });
    } catch (error) {
      onError(error);
    }
  }
  // Normal play carries the loop while it is on and has a range (WP50), and the fast
  // listening speed while that is on (WP26: the engine keeps the pitch).
  const playOptions = () => {
    const state = getState();
    const loop = activeLoop(state);
    const speed = state.fast ? effective(state.fast) : 1;
    if (!loop && speed === 1) return null;
    return { ...(loop ? { loop } : {}), ...(speed === 1 ? {} : { speed, preserve_pitch: true }) };
  };
  return {
    toggle() {
      const { playing, playhead } = getState();
      return playing ? run("stop") : run("play", playhead, null, null, playOptions());
    },
    play: (at) => run("play", at, null, null, playOptions()),
    /**
     * The loop or its range changed while playing: tell the engine without stopping.
     * It plays on from the playhead; the engine takes the new range at the next wrap.
     */
    resendLoop() {
      const state = getState();
      const { playing, playhead, speed = 1 } = state;
      // Only a plain or fast run takes a loop; a shuttle (any other speed) does not.
      if (!playing || speed !== (state.fast ? effective(state.fast) : 1)) return Promise.resolve();
      return run("play", playhead, null, null, playOptions());
    },
    stop: () => run("stop"),
    /**
     * Fast listening was switched on or off, or its speed nudged. Playing: a switch restarts
     * from the playhead at the new speed; a nudge while fast is on changes the speed of the
     * running stretch without restarting (stepless, no click). Stopped: nothing to tell the
     * engine, the next play uses the state.
     */
    fastChanged(before, after) {
      const { playing, playhead, speed = 1 } = getState();
      if (!playing) return Promise.resolve();
      if (before.active !== after.active) return run("play", playhead, null, null, playOptions());
      // `speed` is the engine's last answer and lags a held key; any speed but 1 means the
      // running stretch is there to be told.
      if (after.active && before.fast !== after.fast && speed !== 1) {
        return run("rate", null, null, null, { speed: after.fast });
      }
      return Promise.resolve();
    },
    /**
     * Play `at` to `until` (frames), jumping over each `[a, b)` in `skip` (the engine
     * crossfades the joins and stops at `until`): the candidate preview.
     */
    preview: (at, until, skip) => run("play", at, until, skip),
    /**
     * Tape-style playback at a signed `speed` (negative is backward) from the playhead;
     * 0 stops. The pitch follows the speed: the engine does not keep it yet.
     */
    shuttle(speed) {
      if (speed === 0) return run("stop");
      const { playhead } = getState();
      return run("play", playhead, null, null, { speed, preserve_pitch: false });
    },
    /**
     * Slow hold-to-play: tape-style at a signed `speed` from the playhead (the pitch follows
     * the speed). Queued, so a release right after the key went down stops after it started.
     */
    slowStart(speed) {
      const next = queue.then(() => this.shuttle(speed));
      queue = next.catch(() => {});
      return next;
    },
    /** The key was let go: stop where the audio is (the answer sets the playhead). */
    slowStop() {
      const next = queue.then(() => run("stop"));
      queue = next.catch(() => {});
      return next;
    },
    /** A J, K or L press: the next speed on the ladder from what is playing now. */
    press(key) {
      const { playing, speed = 1 } = getState();
      const next = press(intended ?? (playing ? speed : 0), key);
      intended = next;
      pending += 1;
      queue = queue
        .then(() => this.shuttle(next))
        .finally(() => {
          pending -= 1;
          if (pending === 0) intended = null;
        });
      return queue;
    },
    /** The playhead moves on screen at once; the engine follows. */
    seek(frame) {
      const at = Math.max(0, Math.round(frame));
      seekSeq += 1;
      setState({ playhead: at });
      return run("seek", at, null, null, null, seekSeq);
    },
  };
}
