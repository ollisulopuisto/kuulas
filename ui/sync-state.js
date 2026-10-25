// Sync states on the screen (R51, WP19a). The server decides (sync_state.py): a clip is in sync,
// free (the user said its offset is deliberate) or drifting (nobody said so). This file only turns
// the server's list, `[{ clip_id, track_id, start, offset, state }]` (GET /api/sync, offsets in
// frames), into what the timeline and the Markers tab draw. Pure.

/** "+300 ms", "-1.2 s": the offset a clip sits from where its group puts it. */
export function formatOffset(frames, rate, format = (value) => String(value)) {
  const ms = Math.round((frames / rate) * 1000);
  const sign = ms < 0 ? "-" : "+";
  const abs = Math.abs(ms);
  if (abs < 1000) return `${sign}${abs} ms`;
  return `${sign}${format(Math.round(abs / 100) / 10)} s`;
}

/** clip id -> its row, for the timeline's per-clip lookup. */
export function syncIndex(clips) {
  return new Map((clips ?? []).map((row) => [row.clip_id, row]));
}

/**
 * What a clip wears, or null when it is in sync: `{ kind: "free" | "drift", offset }` with the offset in
 * frames. A free clip with no offset still wears the grey icon; a drifting one always has an offset.
 */
export function badgeFor(row) {
  if (!row) return null;
  if (row.state === "free") return { kind: "free", offset: row.offset };
  if (row.state === "drift") return { kind: "drift", offset: row.offset };
  return null;
}

/** The compact timeline mark for a drift/free row, or null when hidden or in sync. */
export function syncMark(row, show) {
  if (!show || !row) return null;
  if (row.state === "drift") return { kind: "drift", tint: "collateral" };
  if (row.state === "free") return { kind: "free", tint: "muted" };
  return null;
}

/** The rows that are drifting (undecided), in timeline order: the list N and Shift+N step through. */
export function driftRows(clips) {
  return (clips ?? [])
    .filter((row) => row.state === "drift")
    .sort((a, b) => a.start - b.start || (a.clip_id < b.clip_id ? -1 : 1));
}

/**
 * The row after (direction 1) or before (-1) the play cursor, wrapping round; null when the list is
 * empty. Stepping lands on a clip that starts after (before) the cursor, so pressing ] again goes on.
 */
export function stepDrift(rows, playhead, direction) {
  if (rows.length === 0) return null;
  if (direction >= 0) return rows.find((row) => row.start > playhead) ?? rows[0];
  for (let i = rows.length - 1; i >= 0; i--) if (rows[i].start < playhead) return rows[i];
  return rows[rows.length - 1];
}

/** Of `ids`, those that are drifting now (after a move, the ones to ask "keep this clip free?" about). */
export function driftingAmong(clips, ids) {
  const wanted = new Set(ids);
  return driftRows(clips)
    .filter((row) => wanted.has(row.clip_id))
    .map((row) => row.clip_id);
}

/** The ids of the anchor clips (pieces of a sync group's main recording), from GET /api/sync. */
export function anchorIds(anchors) {
  return new Set((anchors ?? []).map((anchor) => anchor.clip_id));
}

/** The track the anchor of this clip's sync group sits on, by name; "" when it has no group. */
export function anchorNameFor(project, anchors, clip) {
  const group = project?.sync_groups?.find((g) => clip.media in g.members);
  if (!group) return "";
  return (anchors ?? []).find((anchor) => anchor.group === group.id)?.name ?? "";
}

/** The name of the track a clip was dragged away from, "" while it is on its own track. */
export function homeNameFor(project, clip, trackId) {
  if (!clip?.home || clip.home === trackId) return "";
  return project?.tracks?.find((track) => track.id === clip.home)?.name ?? "";
}
