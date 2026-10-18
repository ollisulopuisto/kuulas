/**
 * Calculates the preview of clips remaining on a track after a moved clip overwrites what is under it.
 * Mirror of the server rule in `src/kuulas/ops.py` `_overwrite_under`.
 *
 * @param {Array<{ id: string, start: number, length: number }>} clips - The other clips on the destination track
 * @param {{ id: string, start: number, length: number }} moved - The moved clip
 * @returns {Array<{ id: string, start: number, length: number, trimmed?: "start" | "end", moved?: boolean }>}
 */
export function overwriteResult(clips, moved) {
  const safeClips = Array.isArray(clips) ? clips : [];

  if (
    !moved ||
    typeof moved.start !== "number" ||
    !Number.isFinite(moved.start) ||
    typeof moved.length !== "number" ||
    !Number.isFinite(moved.length) ||
    moved.length <= 0
  ) {
    return safeClips.map((c) => ({ ...c }));
  }

  const mStart = moved.start;
  const mEnd = moved.start + moved.length;
  const result = [];

  for (let i = 0; i < safeClips.length; i++) {
    const c = safeClips[i];
    if (
      !c ||
      typeof c.start !== "number" ||
      !Number.isFinite(c.start) ||
      typeof c.length !== "number" ||
      !Number.isFinite(c.length) ||
      c.length <= 0
    ) {
      if (c) result.push({ ...c });
      continue;
    }

    const cStart = c.start;
    const cEnd = c.start + c.length;

    // Fully covered: dropped
    if (mStart <= cStart && mEnd >= cEnd) {
      continue;
    }

    // Touching clips (cEnd <= mStart or cStart >= mEnd) do not overlap
    if (cEnd <= mStart || cStart >= mEnd) {
      result.push({ ...c });
    } else if (mStart <= cStart) {
      // Front is covered
      result.push({
        ...c,
        start: mEnd,
        length: cEnd - mEnd,
        trimmed: "start",
      });
    } else if (mEnd >= cEnd) {
      // End is covered
      result.push({
        ...c,
        length: mStart - cStart,
        trimmed: "end",
      });
    } else {
      // Strictly contains the moved clip: split into left and right pieces
      result.push({
        ...c,
        length: mStart - cStart,
        trimmed: "end",
      });
      result.push({
        ...c,
        id: `${c.id}~r`,
        start: mEnd,
        length: cEnd - mEnd,
        trimmed: "start",
      });
    }
  }

  // Add the moved clip flagged with moved: true
  result.push({
    ...moved,
    moved: true,
  });

  // Sort by start ascending
  result.sort((a, b) => a.start - b.start);
  return result;
}

/**
 * Returns a Set of IDs from `clips` that are dropped, trimmed, or split by the moved clip.
 *
 * @param {Array<{ id: string, start: number, length: number }>} clips
 * @param {{ id: string, start: number, length: number }} moved
 * @returns {Set<string>}
 */
export function affectedIds(clips, moved) {
  const ids = new Set();
  if (
    !Array.isArray(clips) ||
    !moved ||
    typeof moved.start !== "number" ||
    !Number.isFinite(moved.start) ||
    typeof moved.length !== "number" ||
    !Number.isFinite(moved.length) ||
    moved.length <= 0
  ) {
    return ids;
  }

  const mStart = moved.start;
  const mEnd = moved.start + moved.length;

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

    const cStart = c.start;
    const cEnd = c.start + c.length;

    // Overlaps if not completely before or after
    if (!(cEnd <= mStart || cStart >= mEnd)) {
      ids.add(c.id);
    }
  }

  return ids;
}
