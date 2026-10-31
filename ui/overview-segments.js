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

/** One pixel x positions for each visible open candidate span in the whole-edit map. */
export function overviewCandidateTicks(rows, total, width) {
  if (!(total > 0 && width > 0) || !Number.isFinite(total) || !Number.isFinite(width)) return [];
  const ticks = [];
  for (const row of rows ?? []) {
    if (row.state !== "open") continue;
    for (const [start, end] of row.spans ?? []) {
      if (!(end > start) || end <= 0 || start >= total) continue;
      const x = Math.min(width - 1, Math.max(0, Math.floor((Math.max(0, start) / total) * width)));
      ticks.push({ id: row.id, x });
    }
  }
  return ticks;
}

// Round seconds for short edits, then the owner's minute scales: 1, 5, 10,
// 15, 20, 30 and 60. Longer projects extend the scale by whole hours.
const OVERVIEW_STEPS = [1, 5, 10, 15, 20, 30, 60, 300, 600, 900, 1200, 1800, 3600];

/** Interior round ruler marks: at most four, with room for text in narrow strips. */
export function overviewMarks(total, width, rate, formatTime) {
  if (!(total > 0 && width > 0 && rate > 0) || !Number.isFinite(total / rate)) return [];
  const duration = total / rate;
  const limit = Math.min(4, Math.max(1, Math.floor(width / 80)));
  const count = (step) => Math.ceil(duration / step) - 1;
  const step =
    OVERVIEW_STEPS.find((value) => count(value) <= limit) ??
    3600 * Math.ceil(duration / (3600 * (limit + 1)));
  return Array.from({ length: Math.max(0, count(step)) }, (_, index) => {
    const seconds = (index + 1) * step;
    return { x: Math.round((seconds / duration) * width), label: formatTime(seconds) };
  });
}
