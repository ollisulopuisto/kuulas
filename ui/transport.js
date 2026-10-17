// Play, stop and seek. The engine is the clock: the live channel pushes its
// position, and what is set here is only the answer to a request or, for a
// seek, the provisional playhead.

export function createTransport({ post, getState, setState, onError }) {
  async function run(action, at = null) {
    try {
      const status = await post(action, at);
      setState({ playing: status.playing, playhead: status.position });
    } catch (error) {
      onError(error);
    }
  }
  return {
    toggle() {
      const { playing, playhead } = getState();
      return playing ? run("stop") : run("play", playhead);
    },
    play: (at) => run("play", at),
    stop: () => run("stop"),
    /** The playhead moves on screen at once; the engine follows. */
    seek(frame) {
      const at = Math.max(0, Math.round(frame));
      setState({ playhead: at });
      return run("seek", at);
    },
  };
}
