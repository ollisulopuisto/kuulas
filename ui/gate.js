// The Auto-Silence gate on the timeline (WP44): pure helpers. A track's gate
// is a sorted list of non-overlapping [start, end) frame pairs. Drawing and
// hit testing both start here so the numbers are tested without a canvas.
// Spec: docs/design/GUI-DESIGN.md, 5.4 "Mute, gate and soft cut".

/** The command id of "Open this stretch"; the keymap binds to this id. */
export const GATE_OPEN_COMMAND = "gate.open_stretch";
/** A band narrower than this many pixels is still easy to point at. */
export const MIN_HIT_PX = 4;

/** Index of the first range whose end is after `frame` (binary search). */
function firstEndingAfter(ranges, frame) {
  let low = 0;
  let high = ranges.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (ranges[mid][1] > frame) high = mid;
    else low = mid + 1;
  }
  return low;
}

/**
 * Pixel runs [x0, x1, x0, x1, ...] of the gate inside a view of `width` px
 * (integers, clipped to 0..width). Ranges less than one pixel apart become one
 * run, so thousands of ranges at low zoom cost a handful of rectangles; a
 * sliver still gets one pixel. Fills and returns `out` (cleared) so a caller
 * can reuse one array; the work is the number of visible ranges, not the total.
 */
export function gatePixelRuns(ranges, scroll, zoom, width, out = []) {
  out.length = 0;
  if (!ranges || ranges.length === 0) return out;
  let from = null;
  let to = 0;
  const flush = () => {
    if (from === null) return;
    const x0 = Math.max(0, Math.floor(from));
    const x1 = Math.min(width, Math.max(x0 + 1, Math.ceil(to)));
    if (x1 > x0) out.push(x0, x1);
  };
  for (let i = firstEndingAfter(ranges, scroll); i < ranges.length; i += 1) {
    const x0 = (ranges[i][0] - scroll) / zoom;
    if (x0 >= width) break;
    const x1 = (ranges[i][1] - scroll) / zoom;
    if (from !== null && x0 - to < 1) {
      to = Math.max(to, x1);
      continue;
    }
    flush();
    from = x0;
    to = x1;
  }
  flush();
  return out;
}

/**
 * The index of the range under `frame`, or -1. A range narrower than
 * MIN_HIT_PX is widened around its middle so slivers can be pointed at.
 */
export function gateAt(ranges, frame, zoom) {
  if (!ranges || ranges.length === 0) return -1;
  const minSpan = MIN_HIT_PX * zoom;
  const near = firstEndingAfter(ranges, frame - minSpan);
  for (let i = near; i < Math.min(ranges.length, near + 3); i += 1) {
    const [start, end] = ranges[i];
    const pad = Math.max(0, (minSpan - (end - start)) / 2);
    if (frame >= start - pad && frame < end + pad) return i;
    if (start - pad > frame) break;
  }
  return -1;
}

/** [top, bottom] of the flat 1 px floor line the waveform shows under a gate. */
export function flatBar(mode, height) {
  if (mode === "full") return [height / 2 - 0.5, height / 2 + 0.5];
  return [height - 1, height];
}

/** The one edit "Open this stretch" makes: the whole range, one undo step. */
export function openStretchEdit(trackId, [start, end]) {
  return { op: "remove_gate_range", args: { track_id: trackId, start, end } };
}

/** { trackId, index, range } for the gate range on `trackId` at `frame`, else null. */
export function stretchAt(project, trackId, frame, zoom = 1) {
  const track = project?.tracks?.find((candidate) => candidate.id === trackId);
  const index = gateAt(track?.gate, frame, zoom);
  return index < 0 ? null : { trackId, index, range: track.gate[index] };
}

/**
 * Whether any of the selected clips lies over a closed stretch of its track's gate: the
 * condition for "Open the muted stretches under the selected clips". `selection` is a Set
 * (or array) of clip ids.
 */
export function gateUnderClips(project, selection) {
  const wanted = selection instanceof Set ? selection : new Set(selection ?? []);
  if (wanted.size === 0) return false;
  for (const track of project?.tracks ?? []) {
    if (!track.gate?.length) continue;
    for (const clip of track.clips ?? []) {
      if (!wanted.has(clip.id)) continue;
      const end = clip.start + clip.length;
      if (track.gate.some(([a, b]) => a < end && clip.start < b)) return true;
    }
  }
  return false;
}

/** Whether every one of the clips (ids) is flagged to keep the mic open (Clip.ungated). */
export function ungatedAll(project, ids) {
  const wanted = new Set(ids);
  let seen = 0;
  for (const track of project?.tracks ?? [])
    for (const clip of track.clips ?? [])
      if (wanted.has(clip.id)) {
        seen += 1;
        if (!clip.ungated) return false;
      }
  return seen > 0;
}
