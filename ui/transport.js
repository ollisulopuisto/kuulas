// Play, stop and seek. The engine is the clock: the live channel pushes its
// position, and what is set here is only the answer to a request or, for a
// seek, the provisional playhead.

//
// `speed` in the state is the engine's tape speed (signed; 1 at rest). Every answer
// sets it: what the engine says while playing, 1 when it is not.

import { activeLoop } from "./loop-range.js";
import { press } from "./shuttle.js";

export function createTransport({ post, getState, setState, onError }) {
  // Quick J/K/L presses arrive before the engine has answered the last one: the ladder
  // climbs from the speed asked for (`intended`), and the requests go out in order.
  let intended = null;
  let pending = 0;
  let queue = Promise.resolve();

  async function run(action, at = null, until = null, skip = null, options = null) {
    try {
      const status = await (options
        ? post(action, at, until, skip, options)
        : post(action, at, until, skip));
      setState({
        playing: status.playing,
        playhead: status.position,
        speed: status.playing ? (status.speed ?? 1) : 1,
      });
    } catch (error) {
      onError(error);
    }
  }
  // Normal-speed play carries the loop while it is on and has a range (WP50).
  const playOptions = () => {
    const loop = activeLoop(getState());
    return loop ? { loop } : null;
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
      const { playing, playhead, speed = 1 } = getState();
      if (!playing || speed !== 1) return Promise.resolve();
      return run("play", playhead, null, null, playOptions());
    },
    stop: () => run("stop"),
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
      setState({ playhead: at });
      return run("seek", at);
    },
  };
}
