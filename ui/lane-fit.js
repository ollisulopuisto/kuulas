// Fit track lane heights to available window space. Pure logic, no DOM.

/**
 * Distribute available pixel height among tracks.
 *
 * @param {Object} options
 * @param {number} options.available
 * @param {Array<{id: string, collapsed?: boolean, focused?: boolean, min?: number, max?: number}>} options.tracks
 * @param {number} [options.min=28]
 * @param {number} [options.max=160]
 * @param {number} [options.collapsedHeight=8]
 * @returns {{ heights: Record<string, number>, total: number, overflow: boolean }}
 */
export function fitLaneHeights({ available, tracks, min = 28, max = 160, collapsedHeight = 8 }) {
  if (!tracks || tracks.length === 0) {
    return { heights: {}, total: 0, overflow: false };
  }

  const heights = {};
  let collapsedTotal = 0;
  const visible = [];

  for (const track of tracks) {
    if (track.collapsed) {
      heights[track.id] = collapsedHeight;
      collapsedTotal += collapsedHeight;
    } else {
      visible.push(track);
    }
  }

  if (visible.length === 0) {
    const total = collapsedTotal;
    return { heights, total, overflow: total > available };
  }

  const availableForVisible = available - collapsedTotal;
  const totalMin = visible.reduce((sum, t) => sum + (t.min ?? min), 0);

  if (availableForVisible < totalMin) {
    for (const t of visible) {
      heights[t.id] = t.min ?? min;
    }
    const total = Object.values(heights).reduce((a, b) => a + b, 0);
    return { heights, total, overflow: true };
  }

  let remaining = availableForVisible;
  let unclamped = [...visible];
  const clampedHeights = {};

  while (unclamped.length > 0) {
    const share = remaining / unclamped.length;
    const newlyClamped = [];
    for (const t of unclamped) {
      const tMax = t.max ?? max;
      if (share >= tMax) {
        newlyClamped.push(t);
      }
    }
    if (newlyClamped.length === 0) {
      break;
    }
    for (const t of newlyClamped) {
      const tMax = t.max ?? max;
      clampedHeights[t.id] = tMax;
      remaining -= tMax;
    }
    unclamped = unclamped.filter((t) => !(t.id in clampedHeights));
  }

  for (const id of Object.keys(clampedHeights)) {
    heights[id] = clampedHeights[id];
  }

  if (unclamped.length > 0) {
    const base = Math.floor(remaining / unclamped.length);
    let leftover = remaining - base * unclamped.length;

    for (const t of unclamped) {
      heights[t.id] = Math.max(t.min ?? min, base);
    }

    if (leftover > 0) {
      for (const t of tracks) {
        if (t.focused && !t.collapsed && leftover > 0) {
          const tMax = t.max ?? max;
          const current = heights[t.id] ?? 0;
          const canTake = Math.max(0, tMax - current);
          const add = Math.min(leftover, canTake);
          if (add > 0) {
            heights[t.id] += add;
            leftover -= add;
          }
        }
      }
    }
  }

  const total = Object.values(heights).reduce((a, b) => a + b, 0);
  return { heights, total, overflow: false };
}
