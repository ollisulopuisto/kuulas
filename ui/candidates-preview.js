// "Play as if cut": one play request with the engine's skip list. The engine plays `from`
// to `to` and jumps over each skipped range with a short crossfade, sample-exact, and the
// playhead jumps with it. Nothing in the project changes.

/**
 * The play request for a preview, `{ at, until, skip }` in whole frames, or null when
 * there is nothing to play (an empty stretch, or one the skipped ranges cover).
 */
export function previewRequest(preview) {
  if (!preview) return null;
  const at = Math.round(preview.from);
  const until = Math.round(preview.to);
  const skip = [...(preview.skip ?? [])]
    .map(([a, b]) => [Math.round(a), Math.round(b)])
    .sort((x, y) => x[0] - y[0]);
  // How far from `at` the skipped ranges reach without a gap: anything left to play?
  let reached = at;
  for (const [a, b] of skip) {
    if (a > reached) break;
    reached = Math.max(reached, b);
  }
  return until <= reached ? null : { at, until, skip };
}
