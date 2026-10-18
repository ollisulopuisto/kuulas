// What each editing key sends: one plan per command, a pure function of the store's
// state (selection.js says what the selection and the range mean). A plan is
//   { op, args, label: { key }, toast: { key, values } | null, coalesce?, combine? }
// or null when there is nothing to act on, which is also what `can()` asks.
// Group editing is decided by the server (ops.py with edit_scope.py); a plan only
// says whether it is on.
import { autoName, clipsInRange, describeClips, pasteChoice, pasteTargets } from "./clipboard.js";
import { clipEnd } from "./lanes.js";
import { clipsAround, currentTrack, markedRange, selectedClips } from "./selection.js";

export const GAIN_STEP_DB = 0.5;
export const GAIN_BURST_MS = 600;
export const DEFAULT_NUDGE_MS = 10;

const groupOn = (state) => state?.groupEditing !== false;
const rateOf = (state) => state.project?.rate ?? 48000;
const plan = (op, args, key, values = {}, extra = {}) => ({
  op,
  args,
  label: { key: `ui.edit.label.${key}` },
  toast: extra.silent
    ? null
    : { key: `ui.edit.toast.${key}`, values, tracks: extra.tracks, variant: extra.variant },
  ...extra.more,
});

const unique = (list) => [...new Set(list)];

/** The clips a "this clip" command acts on: the selected ones holding the frame, else the current track's. */
function clipsHolding(state) {
  const at = state.playhead;
  const selected = selectedClips(state)
    .filter(({ clip }) => clip.start < at && at < clipEnd(clip))
    .map(({ clip }) => clip.id);
  if (selected.length > 0) return selected;
  const track = currentTrack(state);
  return track === null ? [] : clipsAround(state.project, at, track);
}

/** B and Shift+B. */
export function splitPlan(state, { all = false } = {}) {
  if (!state?.project || !Number.isFinite(state.playhead)) return null;
  const ids = all ? clipsAround(state.project, state.playhead, null) : clipsHolding(state);
  if (ids.length === 0) return null;
  return plan("split_clips", { at: state.playhead, clip_ids: ids }, "split", { count: ids.length });
}

/**
 * Where a range edit lands: the tracks chosen with Select > Range on all tracks (those
 * still in the project), else this track, else the tracks the selection sits on.
 */
export function rangeTracks(state) {
  const chosen = state?.rangeTracks;
  if (Array.isArray(chosen)) {
    const live = new Set((state.project?.tracks ?? []).map((track) => track.id));
    const kept = chosen.filter((id) => live.has(id));
    if (kept.length > 0) return kept;
  }
  const track = currentTrack(state);
  if (track !== null) return [track];
  return unique(selectedClips(state).map((entry) => entry.trackId));
}

/** The frames an edit covers and the tracks it starts from: the range, else the selected clips' span. */
function span(state) {
  const range = markedRange(state);
  if (range) {
    const tracks = rangeTracks(state);
    return tracks.length === 0 ? null : { ...range, tracks, fromRange: true };
  }
  const chosen = selectedClips(state);
  if (chosen.length === 0) return null;
  return {
    start: Math.min(...chosen.map((e) => e.clip.start)),
    end: Math.max(...chosen.map((e) => clipEnd(e.clip))),
    tracks: unique(chosen.map((e) => e.trackId)),
    fromRange: false,
  };
}

const secondsOf = (state, frames) => frames / rateOf(state);

/** Backspace and Delete: mute in place (the range, else the selected clips); the gap stays. */
export function deletePlan(state) {
  if (!state?.project) return null;
  const range = markedRange(state);
  if (range) {
    const tracks = rangeTracks(state);
    if (tracks.length === 0) return null;
    return plan(
      "mute_range",
      { ...range, track_ids: tracks, group_editing: groupOn(state) },
      "delete_range",
      { seconds: secondsOf(state, range.end - range.start) },
      { tracks: true },
    );
  }
  const live = selectedClips(state).filter((entry) => !entry.clip.muted);
  if (live.length === 0) return null;
  return plan("set_clips", { clip_ids: live.map((e) => e.clip.id), muted: true }, "delete_clips", {
    count: live.length,
  });
}

/** The trimmed clips an edit over `covered` (see span) touches, for naming its clipboard entry. */
function coveredParts(state, covered) {
  if (covered.fromRange)
    return clipsInRange(state.project, covered.tracks, covered.start, covered.end);
  return selectedClips(state).map(({ clip, trackId }) => ({
    trackId,
    trackName: state.project.tracks.find((track) => track.id === trackId)?.name,
    start: clip.start,
    end: clipEnd(clip),
  }));
}

/** X and Shift+X: ripple-delete the range or the selected clips' span; the cut audio goes to the clipboard. */
export function cutPlan(state, { thisTrackOnly = false, t } = {}) {
  if (!state?.project) return null;
  const covered = span(state);
  if (!covered) return null;
  const name = autoName(describeClips(coveredParts(state, covered), rateOf(state)), t);
  return plan(
    "clipboard_cut",
    {
      start: covered.start,
      end: covered.end,
      track_ids: covered.tracks,
      group_editing: groupOn(state) && !thisTrackOnly,
      name,
    },
    "cut",
    { seconds: secondsOf(state, covered.end - covered.start) },
    {
      tracks: true,
      // A copy that failed does not undo the cut, but the user is told (WP46).
      variant: (response) =>
        response?.clipboard?.ok === false
          ? { key: "ui.edit.toast.cut_uncopied", values: { error: response.clipboard.error } }
          : null,
    },
  );
}

/** Mod+C: copy the range (as Cut would take it), else the selected clips. No edit, so no undo step. */
export function copyPlan(state, t) {
  if (!state?.project) return null;
  const range = markedRange(state);
  let body;
  let parts;
  if (range) {
    const tracks = rangeTracks(state);
    if (tracks.length === 0) return null;
    parts = clipsInRange(state.project, tracks, range.start, range.end);
    body = { ...range, track_ids: tracks, group_editing: groupOn(state) };
  } else {
    const chosen = selectedClips(state);
    if (chosen.length === 0) return null;
    parts = coveredParts(state, { fromRange: false });
    body = { clip_ids: chosen.map((entry) => entry.clip.id) };
  }
  if (parts.length === 0) return null;
  const described = describeClips(parts, rateOf(state));
  return {
    path: "copy",
    body: { ...body, name: autoName(described, t) },
    toast: { key: "ui.edit.toast.copy", values: { count: parts.length } },
  };
}

/** The entry a paste uses: the one picked in the panel, else the newest. */
export function pasteEntry(state) {
  const list = state?.clipboard ?? [];
  return list.find((entry) => entry.id === state?.clipboardSelected) ?? list[0] ?? null;
}

/**
 * Mod+V (insert), Alt+Mod+V (overwrite): paste an entry at the play cursor. `target` is
 * "same" (the source tracks) or "current" (the current track and the ones below it).
 * Defaults come from the panel's remembered choice only when the caller passes it in.
 */
export function pastePlan(state, { mode, target } = {}) {
  const choice = pasteChoice({ pasteMode: mode, pasteTarget: target });
  const entry = pasteEntry(state);
  if (!state?.project || !entry || !Number.isFinite(state.playhead)) return null;
  let targetTracks = null;
  if (choice.target === "current") {
    const ids = state.project.tracks.map((track) => track.id);
    targetTracks = pasteTargets(entry.slots, ids, currentTrack(state));
    if (targetTracks === null) return null;
  }
  const key = choice.mode === "overwrite" ? "paste_overwrite" : "paste";
  return plan(
    "clipboard_paste",
    {
      entry_id: entry.id,
      at: state.playhead,
      mode: choice.mode,
      target_tracks: targetTracks,
      // An insert shifts time: the sync group follows unless group editing is off (WP19a).
      group_editing: groupOn(state),
    },
    key,
    { count: entry.clips },
    {
      variant: (response) => {
        const done = response?.clipboard;
        if (!done) return null;
        if (done.placed === 0) {
          return { key: "ui.edit.toast.paste_nothing", values: {}, undo: false };
        }
        return done.missing.length > 0
          ? { key: "ui.edit.toast.paste_missing", values: { count: done.missing.length } }
          : null;
      },
    },
  );
}

/** N: mute the selected clips, or unmute them when they all are muted already. */
export function mutePlan(state) {
  const chosen = selectedClips(state);
  if (chosen.length === 0) return null;
  const muted = !chosen.every((entry) => entry.clip.muted);
  return plan(
    "set_clips",
    { clip_ids: chosen.map((e) => e.clip.id), muted },
    muted ? "mute" : "unmute",
    {
      count: chosen.length,
    },
  );
}

/**
 * G: fade at the play cursor (the server fades the nearer end of the clip). The clip is a
 * selected one holding the cursor, else the current track's clip under it.
 */
export function fadePlan(state) {
  if (!state?.project || !Number.isFinite(state.playhead)) return null;
  const at = state.playhead;
  const holds = (clip) => clip.start <= at && at < clipEnd(clip);
  let id = selectedClips(state).find((entry) => holds(entry.clip))?.clip.id ?? null;
  if (id === null) {
    const track = currentTrack(state);
    id = state.project.tracks.find((x) => x.id === track)?.clips.find(holds)?.id ?? null;
  }
  return id === null ? null : plan("set_fade_at", { clip_id: id, frame: at }, "fade");
}

/** Q (edge "start") and W (edge "end"): trim to the playhead. */
export function trimPlan(state, edge) {
  if (!state?.project || !Number.isFinite(state.playhead)) return null;
  const ids = clipsHolding(state);
  if (ids.length === 0) return null;
  return plan("trim_clips", { clip_ids: ids, [edge]: state.playhead }, `trim_${edge}`, {
    count: ids.length,
  });
}

/** Mod+Left / Mod+Right: direction -1 or 1, one nudge step; the group follows when on. */
export function nudgePlan(state, direction) {
  const chosen = selectedClips(state);
  if (chosen.length === 0) return null;
  const step = Math.max(
    1,
    Math.round((rateOf(state) * (state.nudgeMs ?? DEFAULT_NUDGE_MS)) / 1000),
  );
  return plan(
    "nudge_clips",
    {
      clip_ids: chosen.map((e) => e.clip.id),
      delta: direction * step,
      group_editing: groupOn(state),
    },
    "nudge",
    {},
    { silent: true },
  );
}

/** Presses closer together than `gapMs` are one burst, which the server undoes as one step. */
export function createBurst(gapMs = GAIN_BURST_MS) {
  let id = 0;
  let last = Number.NEGATIVE_INFINITY;
  return {
    key(now) {
      if (now - last > gapMs) id += 1;
      last = now;
      return `burst${id}`;
    },
  };
}

/** Shift+Mod+Up / Down: direction 1 or -1, 0.5 dB per press. */
export function gainPlan(state, direction, burstKey) {
  const chosen = selectedClips(state);
  if (chosen.length === 0) return null;
  const ids = chosen.map((e) => e.clip.id);
  return plan(
    "adjust_clip_gain",
    { clip_ids: ids, delta_db: direction * GAIN_STEP_DB },
    "gain",
    {},
    {
      silent: true,
      more: {
        coalesce: `gain:${burstKey}:${ids.join(",")}`,
        combine: (older, newer) => ({
          ...newer,
          delta_db: Math.round((older.delta_db + newer.delta_db) * 100) / 100,
        }),
      },
    },
  );
}

function trackOf(state) {
  const id = currentTrack(state);
  return id === null ? null : (state.project?.tracks.find((t) => t.id === id) ?? null);
}

/** Shift+M. */
export function trackMutePlan(state) {
  const track = trackOf(state);
  if (!track) return null;
  return plan(
    "set_track",
    { track_id: track.id, mute: !track.mute },
    "track_mute",
    {},
    { silent: true },
  );
}

/** Shift+S (exclusive) and Shift+Alt+S (added to the solo set). */
export function soloPlan(state, exclusive) {
  const track = trackOf(state);
  if (!track) return null;
  return plan("solo", { track_id: track.id, exclusive }, "solo", {}, { silent: true });
}

/**
 * "Group the selected tracks into a new bus": the tracks holding selected clips (in track
 * order), else the focused track. Null when there is none.
 */
export function groupBusPlan(state) {
  const held = new Set(selectedClips(state).map((entry) => entry.trackId));
  const focus = currentTrack(state);
  const ids = held.size > 0 ? [...held] : focus === null ? [] : [focus];
  if (ids.length === 0) return null;
  return plan("add_bus", { track_ids: ids }, "group_bus", {}, { silent: true });
}

/** "New empty bus". */
export function newBusPlan(state) {
  if (!state?.project) return null;
  return plan("add_bus", {}, "new_bus", {}, { silent: true });
}

/** Ids of the tracks whose clips differ between two projects. */
export function changedTracks(before, after) {
  const was = new Map((before?.tracks ?? []).map((t) => [t.id, JSON.stringify(t.clips)]));
  return (after?.tracks ?? [])
    .filter((t) => was.get(t.id) !== JSON.stringify(t.clips))
    .map((t) => t.id);
}
