// What the overview strip draws: per track, only the stretches that sound. A gap means
// "nobody is heard here" and it does not matter why (no clip, a muted clip or track, a
// stretch closed by Auto-Silence, or one the Auto-Silence preview would close). Pure
// functions on merged frame ranges, so a 60 minute edit with ~1200 clips costs a sort and
// a few linear passes, never a per-pixel read.

/** Sorted [start, end) pairs merged where they touch or overlap. */
function merge(ranges) {
  const sorted = ranges.filter((r) => r[1] > r[0]).sort((a, b) => a[0] - b[0]);
  const out = [];
  for (const [start, end] of sorted) {
    const last = out.at(-1);
    if (last && start <= last[1]) last[1] = Math.max(last[1], end);
    else out.push([start, end]);
  }
  return out;
}

/** `keep` (merged) minus `cut` (merged). */
function subtract(keep, cut) {
  if (cut.length === 0) return keep;
  const out = [];
  let j = 0;
  for (const [start, end] of keep) {
    let from = start;
    while (j < cut.length && cut[j][1] <= from) j += 1;
    for (let k = j; k < cut.length && cut[k][0] < end; k += 1) {
      if (cut[k][0] > from) out.push([from, cut[k][0]]);
      from = Math.max(from, cut[k][1]);
    }
    if (from < end) out.push([from, end]);
  }
  return out;
}

/**
 * The merged [start, end) frame ranges of `track` that sound: clip present, clip not muted,
 * track not muted, not inside a gate range or a preview range (a clip that keeps the mic
 * open ignores both).
 */
export function audibleSegments(track, preview = null) {
  if (track.mute) return [];
  const audible = [];
  const trackClosed = merge([...(track.gate ?? []), ...(preview ?? [])]);
  for (const clip of track.clips ?? []) {
    if (clip.muted) continue;
    const span = [[clip.start, clip.start + clip.length]];
    if (clip.ungated) {
      audible.push(...span);
      continue;
    }
    const sourceStart = clip.offset ?? 0;
    const sourceEnd = sourceStart + clip.length;
    const clipClosed = merge(
      (clip.auto_silence ?? []).map(([start, end]) => {
        const from = Math.max(start, sourceStart);
        const to = Math.min(end, sourceEnd);
        return [clip.start + from - sourceStart, clip.start + to - sourceStart];
      }),
    );
    audible.push(...subtract(subtract(span, trackClosed), clipClosed));
  }
  return merge(audible);
}

/**
 * Pixel runs [x0, x1, ...] for `segments` over a strip `width` px wide showing `total`
 * frames. A run is at least one pixel wide so short speech still shows, and runs less than
 * one pixel apart become one.
 */
export function overviewRuns(segments, total, width) {
  const out = [];
  if (total <= 0) return out;
  const scale = width / total;
  for (const [start, end] of segments) {
    const x0 = start * scale;
    const x1 = Math.max(x0 + 1, end * scale);
    const n = out.length;
    if (n && x0 - out[n - 1] < 1) out[n - 1] = Math.max(out[n - 1], x1);
    else out.push(x0, x1);
  }
  return out;
}

/** The strip's own times: a quarter, a half and three quarters of the edit (no ends). */
export const OVERVIEW_SHARES = [0.25, 0.5, 0.75];

/**
 * { x, label } for each share of the edit in the strip's `width`; `formatTime(seconds)` gives the
 * label, so the strip reads like the ruler above it.
 */
export function overviewMarks(total, width, rate, formatTime) {
  return OVERVIEW_SHARES.map((share) => ({
    x: Math.round(share * width),
    label: formatTime((share * total) / rate),
  }));
}
