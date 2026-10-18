// "Play as if cut" without a skip option in the engine (engine.play takes only `at` and
// `until`): a jump preview. The segments around the skipped ranges are played one after
// the other, each with its own `until`; a timer of the segment's length starts the next.
// Nothing in the project changes. The jump is not sample-exact (a request goes through
// HTTP between segments), which is fine for judging whether a cut sounds right; the real
// cut is sample-exact. If the engine ever gets a skip list, only this file changes.

/** [{ at, until }]: the stretches to play, in order, with the skipped ranges left out. */
export function previewSegments({ from, to, skip }) {
  const segments = [];
  let at = from;
  for (const [a, b] of [...skip].sort((x, y) => x[0] - y[0])) {
    if (a > at) segments.push({ at, until: a });
    at = Math.max(at, b);
  }
  if (to > at) segments.push({ at, until: to });
  return segments;
}

/** Wait this much longer than a segment lasts, so the engine has stopped at its end. */
const SLACK_MS = 40;

/**
 * `playSegment(at, until)` asks the engine to play that stretch; `stop()`; `schedule` and
 * `cancel` are setTimeout and clearTimeout (injected for tests). Any stop or seek the user
 * does while a preview runs must call `cancel()`.
 */
export function createPreviewPlayer({
  rate,
  playSegment,
  stop,
  schedule = setTimeout,
  cancel = clearTimeout,
}) {
  let timer = null;
  let generation = 0;

  function cancelAll() {
    generation += 1;
    if (timer !== null) cancel(timer);
    timer = null;
  }

  async function runFrom(segments, index, mine) {
    if (mine !== generation) return;
    const { at, until } = segments[index];
    await playSegment(at, until);
    if (mine !== generation) return;
    if (index + 1 >= segments.length) {
      timer = null;
      return; // the engine stops at the last `until` by itself
    }
    timer = schedule(
      () => {
        timer = null;
        return runFrom(segments, index + 1, mine);
      },
      ((until - at) / rate) * 1000 + SLACK_MS,
    );
  }

  return {
    /** Start (or restart) a preview; false when there was nothing to play. */
    async start(preview) {
      cancelAll();
      if (!preview) return false;
      const segments = previewSegments(preview);
      if (segments.length === 0) return false;
      await runFrom(segments, 0, generation);
      return true;
    },
    /** Stop the chain of segments (the user stopped or moved); it does not stop the engine. */
    cancel: cancelAll,
    active: () => timer !== null,
    stop() {
      cancelAll();
      stop();
    },
  };
}
