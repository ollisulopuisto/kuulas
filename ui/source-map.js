// The inspector's Source section, pure parts: the numbers behind the mini map of a
// recording (GET /api/source-map), the one-line summary, the other clips, and the fetcher
// that keeps answers by (recording, history head) and drops stale ones. No DOM here;
// inspector-source.js draws what these return.
//
// The server speaks flicks on the recording's own clock: { clips: [[track, clip, from,
// to, muted]], used, cut, unused: [[from, to]], parts: { clip: [n, of] } }.

export const FLICKS_PER_SECOND = 705_600_000;

/** The kinds of stretch a recording has, in drawing order. Each has a non-colour twin. */
export const KINDS = ["used", "cut", "unused"];

const rangesOf = (map, kind) => map?.[kind] ?? [];

/** The recording's length in flicks: the end of the last stretch the map names. */
export function totalFlicks(map) {
  let end = 0;
  for (const kind of KINDS) for (const [, to] of rangesOf(map, kind)) end = Math.max(end, to);
  return end;
}

const percent = (value, total) =>
  total > 0 ? Math.min(100, Math.max(0, (value / total) * 100)) : 0;

/** The stretches as { kind, from, to, left, width } with left/width in percent of the whole. */
export function segments(map) {
  const total = totalFlicks(map);
  const out = [];
  for (const kind of KINDS) {
    for (const [from, to] of rangesOf(map, kind)) {
      if (to <= from) continue;
      out.push({ kind, from, to, left: percent(from, total), width: percent(to - from, total) });
    }
  }
  return out.sort((a, b) => a.from - b.from);
}

/** Where one clip sits in the recording, as { left, width } in percent; null if it is not in the map. */
export function clipSpan(map, clipId) {
  const total = totalFlicks(map);
  const row = (map?.clips ?? []).find((entry) => entry[1] === clipId);
  if (!row) return null;
  return { left: percent(row[2], total), width: percent(row[3] - row[2], total) };
}

/** How much of the recording the edit plays, as a whole percent (0 for an empty map). */
export function usedPercent(map) {
  const total = totalFlicks(map);
  const used = rangesOf(map, "used").reduce((sum, [from, to]) => sum + (to - from), 0);
  return Math.round(percent(used, total));
}

/** The clip's part as { n, of }, else null. */
export function partOf(map, clipId) {
  const pair = map?.parts?.[clipId];
  return pair ? { n: pair[0], of: pair[1] } : null;
}

/**
 * The summary on the section heading: "Used 62% · 3 parts". `t` translates; the key is
 * counted by the number of parts. Empty until the map is here.
 */
export function summaryText(map, t) {
  if (!map) return "";
  const count = (map.clips ?? []).length;
  return t("ui.inspector.source.summary", { percent: usedPercent(map), count });
}

/** The other clips of the recording in source order: { clip, track, n, of, from, to, muted }. */
export function otherClips(map, clipId) {
  return (map?.clips ?? [])
    .filter((entry) => entry[1] !== clipId)
    .map(([track, clip, from, to, muted]) => ({
      clip,
      track,
      from,
      to,
      muted: Boolean(muted),
      ...(partOf(map, clip) ?? { n: 0, of: 0 }),
    }));
}

/** The clip before (-1) or after (+1) this one in the recording, or null at the ends. */
export function neighbourClip(map, clipId, direction) {
  const clips = map?.clips ?? [];
  const at = clips.findIndex((entry) => entry[1] === clipId);
  if (at < 0) return null;
  const next = clips[at + direction];
  return next ? next[1] : null;
}

/**
 * Fetches a recording's map when asked, one answer per (recording, history head). A
 * newer request cancels the older one (its answer is ignored even if the network was
 * not abortable). `fetchMap(sha, signal)` -> Promise; `onChange()` runs when `get` would
 * now answer differently.
 */
export function createSourceMaps({ fetchMap, onChange, onError = () => {} }) {
  const cache = new Map();
  let wanted = "";
  let controller = null;
  let ticket = 0;

  const keyOf = (sha, head) => `${sha}|${head}`;

  return {
    /** The map for this recording at this head, or null while it is on its way. */
    get: (sha, head) => cache.get(keyOf(sha, head)) ?? null,
    /** Make sure the map is cached or coming; null/empty `sha` cancels. */
    want(sha, head) {
      const key = sha ? keyOf(sha, head) : "";
      if (key === wanted) return;
      controller?.abort();
      controller = null;
      wanted = key;
      if (!key || cache.has(key)) return;
      const mine = ++ticket;
      controller = new AbortController();
      fetchMap(sha, controller.signal).then(
        (map) => {
          if (mine !== ticket || key !== wanted) return; // stale: a newer request exists
          cache.set(key, map);
          if (cache.size > 16) cache.delete(cache.keys().next().value);
          onChange();
        },
        (error) => {
          if (mine === ticket && error?.name !== "AbortError") onError(error);
        },
      );
    },
  };
}
