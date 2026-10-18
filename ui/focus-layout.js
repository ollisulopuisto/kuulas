/**
 * Pure logic and state management for focus mode lane layout.
 */

export function focusSet(tracks, trackId) {
  if (!tracks || !trackId) return [];
  const target = tracks.find((t) => t.id === trackId);
  if (!target) return [];
  const speaker = target.speaker ? target.speaker.trim() : "";
  if (speaker) {
    return tracks.filter((t) => (t.speaker ? t.speaker.trim() : "") === speaker).map((t) => t.id);
  }
  return [trackId];
}

export function focusLayout(tracks, focusIds, options = {}) {
  const { available = 0, strip = 16, min = 28, max = 400 } = options;
  if (!tracks || tracks.length === 0) {
    return { heights: {}, total: 0 };
  }

  const focusSetIds = new Set(focusIds || []);
  const focusedTracks = tracks.filter((t) => focusSetIds.has(t.id));
  const nonFocusedTracks = tracks.filter((t) => !focusSetIds.has(t.id));

  if (focusedTracks.length === 0) {
    const h = Math.max(min, Math.min(max, Math.floor(available / tracks.length)));
    const heights = {};
    let total = 0;
    for (const t of tracks) {
      heights[t.id] = h;
      total += h;
    }
    return { heights, total };
  }

  const heights = {};
  for (const t of nonFocusedTracks) {
    heights[t.id] = strip;
  }

  const nonFocusedTotal = nonFocusedTracks.length * strip;
  const spaceForFocused = available - nonFocusedTotal;

  const base = Math.floor(spaceForFocused / focusedTracks.length);
  const rem = spaceForFocused % focusedTracks.length;

  for (let i = 0; i < focusedTracks.length; i++) {
    const allocated = base + (i < rem ? 1 : 0);
    heights[focusedTracks[i].id] = Math.max(min, Math.min(max, allocated));
  }

  let total = 0;
  for (const t of tracks) {
    total += heights[t.id];
  }

  return { heights, total };
}

export function walkFocus(tracks, focusIds, direction) {
  if (!tracks || tracks.length === 0 || !focusIds || focusIds.length === 0) {
    return focusIds || [];
  }
  const focusSetIds = new Set(focusIds);
  const matchingIndices = [];
  for (let i = 0; i < tracks.length; i++) {
    if (focusSetIds.has(tracks[i].id)) {
      matchingIndices.push(i);
    }
  }
  if (matchingIndices.length === 0) {
    return focusIds;
  }
  if (direction === 1) {
    const lastIdx = Math.max(...matchingIndices);
    if (lastIdx + 1 < tracks.length) {
      return focusSet(tracks, tracks[lastIdx + 1].id);
    }
    return focusIds;
  }
  if (direction === -1) {
    const firstIdx = Math.min(...matchingIndices);
    if (firstIdx - 1 >= 0) {
      return focusSet(tracks, tracks[firstIdx - 1].id);
    }
    return focusIds;
  }
  return focusIds;
}

export function enterFocus(state, trackId, tracks, soloSet) {
  const newFocus = focusSet(tracks, trackId);
  const soloBefore = soloSet ? [...soloSet] : (state?.soloBefore ?? null);
  return {
    focus: newFocus,
    soloBefore,
  };
}

export function leaveFocus(state) {
  return {
    state: { focus: null, soloBefore: null },
    restoreSolo: state?.soloBefore ?? null,
  };
}
