/**
 * Finds all overlapping spans between pairs of clips on a track.
 * Touching clips (where one ends exactly where the next starts) do not overlap.
 * Clips with length <= 0 are ignored.
 *
 * @param {Array<{ id: string, start: number, length: number }>} clips
 * @returns {Array<{ a: string, b: string, start: number, end: number }>}
 */
export function overlapsOf(clips) {
  if (!Array.isArray(clips) || clips.length < 2) {
    return [];
  }

  // Filter to valid clips with positive length and numeric bounds, preserving original index for tie breaking
  const valid = [];
  for (let i = 0; i < clips.length; i++) {
    const c = clips[i];
    if (
      c &&
      typeof c.id === "string" &&
      typeof c.start === "number" &&
      Number.isFinite(c.start) &&
      typeof c.length === "number" &&
      Number.isFinite(c.length) &&
      c.length > 0
    ) {
      valid.push({
        id: c.id,
        start: c.start,
        end: c.start + c.length,
        originalIndex: i,
      });
    }
  }

  const result = [];
  for (let i = 0; i < valid.length; i++) {
    const c1 = valid[i];
    for (let j = i + 1; j < valid.length; j++) {
      const c2 = valid[j];
      const overlapStart = Math.max(c1.start, c2.start);
      const overlapEnd = Math.min(c1.end, c2.end);

      if (overlapStart < overlapEnd) {
        let first = c1;
        let second = c2;

        if (c2.start < c1.start) {
          first = c2;
          second = c1;
        } else if (c1.start === c2.start) {
          if (c2.originalIndex < c1.originalIndex) {
            first = c2;
            second = c1;
          }
        }

        result.push({
          a: first.id,
          b: second.id,
          start: overlapStart,
          end: overlapEnd,
        });
      }
    }
  }

  // Sort by start ascending, then end ascending
  result.sort((x, y) => x.start - y.start || x.end - y.end);
  return result;
}

/**
 * Returns a Set of clip IDs that overlap any other clip.
 *
 * @param {Array<{ id: string, start: number, length: number }>} clips
 * @returns {Set<string>}
 */
export function overlappedIds(clips) {
  const overlaps = overlapsOf(clips);
  const ids = new Set();
  for (let i = 0; i < overlaps.length; i++) {
    ids.add(overlaps[i].a);
    ids.add(overlaps[i].b);
  }
  return ids;
}

/**
 * Picks the clip at the given frame position according to the owner's rule:
 * Among clips whose span holds frame (start inclusive, end exclusive),
 * the shorter one wins, and ties in length go to the later one in the list.
 *
 * @param {Array<{ id: string, start: number, length: number }>} clips
 * @param {number} frame
 * @returns {string | null}
 */
export function topClipAt(clips, frame) {
  if (!Array.isArray(clips) || typeof frame !== "number" || !Number.isFinite(frame)) {
    return null;
  }

  let best = null;
  for (let i = 0; i < clips.length; i++) {
    const c = clips[i];
    if (
      !c ||
      typeof c.id !== "string" ||
      typeof c.start !== "number" ||
      !Number.isFinite(c.start) ||
      typeof c.length !== "number" ||
      !Number.isFinite(c.length) ||
      c.length <= 0
    ) {
      continue;
    }

    if (frame >= c.start && frame < c.start + c.length) {
      if (!best || c.length <= best.length) {
        best = c;
      }
    }
  }

  return best ? best.id : null;
}
