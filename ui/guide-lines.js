/**
 * Compares edges of a moved clip with activity edges on other tracks to generate guide lines.
 *
 * @param {number[]} movedEdges - List of frames (the moved clip's edges at its new place)
 * @param {Array<{ track: string, frame: number }>} otherEdges - List of activity edges on other tracks
 * @param {number} zoom - Frames per pixel
 * @param {object} [options]
 * @param {number} [options.show=40] - Pixel threshold to show guide
 * @param {number} [options.snap=8] - Pixel threshold to trigger snap
 * @returns {Array<{ frame: number, edgeFrame: number, track: string, px: number, strength: number, snap: boolean }>}
 */
export function guides(movedEdges, otherEdges, zoom, { show = 40, snap = 8 } = {}) {
  if (
    typeof zoom !== "number" ||
    !Number.isFinite(zoom) ||
    zoom <= 0 ||
    !Array.isArray(movedEdges) ||
    !Array.isArray(otherEdges)
  ) {
    return [];
  }

  const validMoved = [];
  for (let i = 0; i < movedEdges.length; i++) {
    const f = movedEdges[i];
    if (typeof f === "number" && Number.isFinite(f)) {
      validMoved.push(f);
    }
  }

  const validOther = [];
  for (let i = 0; i < otherEdges.length; i++) {
    const o = otherEdges[i];
    if (o && typeof o.frame === "number" && Number.isFinite(o.frame)) {
      validOther.push(o);
    }
  }

  if (validMoved.length === 0 || validOther.length === 0 || show <= 0) {
    return [];
  }

  const candidates = [];
  for (let i = 0; i < validMoved.length; i++) {
    const m = validMoved[i];
    let bestOther = null;
    let minDiff = Number.POSITIVE_INFINITY;

    for (let j = 0; j < validOther.length; j++) {
      const o = validOther[j];
      const diff = Math.abs(o.frame - m);
      if (diff < minDiff) {
        minDiff = diff;
        bestOther = o;
      }
    }

    if (!bestOther) continue;

    const px = minDiff / zoom;
    if (px <= show) {
      const strength = Math.max(0, Math.min(1, 1 - px / show));
      candidates.push({
        frame: m,
        edgeFrame: bestOther.frame,
        track: bestOther.track,
        px,
        strength,
        snap: px <= snap,
        other: bestOther,
      });
    }
  }

  // Sort by px ascending
  candidates.sort((a, b) => a.px - b.px);

  // At most one entry per other edge
  const seenOther = new Set();
  const deduped = [];
  for (let i = 0; i < candidates.length; i++) {
    const c = candidates[i];
    if (!seenOther.has(c.other)) {
      seenOther.add(c.other);
      deduped.push({
        frame: c.frame,
        edgeFrame: c.edgeFrame,
        track: c.track,
        px: c.px,
        strength: c.strength,
        snap: c.snap,
      });
    }
  }

  // At most 4 entries
  return deduped.slice(0, 4);
}

/**
 * Returns the edgeFrame of the first entry with snap true, or null.
 *
 * @param {Array<{ edgeFrame: number, snap: boolean }>} guideList
 * @returns {number | null}
 */
export function snapTarget(guideList) {
  if (!Array.isArray(guideList)) return null;
  for (let i = 0; i < guideList.length; i++) {
    if (guideList[i]?.snap) {
      return guideList[i].edgeFrame;
    }
  }
  return null;
}

/**
 * Returns the frames the moved clip should shift to land on that edge (edgeFrame - frame), or 0.
 *
 * @param {Array<{ frame: number, edgeFrame: number, snap: boolean }>} guideList
 * @returns {number}
 */
export function snapDelta(guideList) {
  if (!Array.isArray(guideList)) return 0;
  for (let i = 0; i < guideList.length; i++) {
    if (guideList[i]?.snap) {
      return guideList[i].edgeFrame - guideList[i].frame;
    }
  }
  return 0;
}
