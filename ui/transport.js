// Play, stop and seek. The engine is the clock: the live channel pushes its
// position, and what is set here is only the answer to a request or, for a
// seek, the provisional playhead.

/**
 * `onUserAction()` is called before every request the user makes (play, stop, seek,
 * toggle) so a candidate preview in progress can end; `playSegment` is the preview's own
 * request and does not call it.
 */
export function createTransport({ post, getState, setState, onError, onUserAction = () => {} }) {
  async function run(action, at = null, until = null) {
    try {
      const status = await post(action, at, until);
      setState({ playing: status.playing, playhead: status.position });
    } catch (error) {
      onError(error);
    }
  }
  const user = (action, at) => {
    onUserAction();
    return run(action, at);
  };
  return {
    toggle() {
      const { playing, playhead } = getState();
      return playing ? user("stop") : user("play", playhead);
    },
    play: (at) => user("play", at),
    stop: () => user("stop"),
    /** Play `at` to `until` (frames); the engine stops at `until`. */
    playSegment: (at, until) => run("play", at, until),
    /** The playhead moves on screen at once; the engine follows. */
    seek(frame) {
      const at = Math.max(0, Math.round(frame));
      onUserAction();
      setState({ playhead: at });
      return run("seek", at);
    },
  };
}
