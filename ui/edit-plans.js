// What each editing key sends: one plan per command, a pure function of the store's
// state (selection.js says what the selection and the range mean). A plan is
//   { op, args, label: { key }, toast: { key, values } | null, coalesce?, combine? }
// or null when there is nothing to act on, which is also what `can()` asks.
// Which tracks a range operation acts on is range-scope.js (WP83); a plan sends them as
// track_ids. Sync never widens it, and an explicit clip group is expanded by the server.

import { busOfFocus } from "./bus-collapse.js";
import { implicitPortionAt } from "./clip-silence.js";
import {
  autoName,
  clipsInRange,
  describeClips,
  pasteChoice,
  pasteTargets,
  sourceTargets,
} from "./clipboard.js";
import { editRange } from "./intent.js";
import { clipEnd } from "./lanes.js";
import { splitClipsProvisional } from "./provisional.js";
import { quickMuteStretch } from "./quick-mute.js";
import { resolveScope } from "./range-scope.js";
import { clipsAround, currentTrack, selectedClips } from "./selection.js";

export const GAIN_STEP_DB = 0.5;
export const GAIN_BURST_MS = 600;
export const DEFAULT_NUDGE_MS = 10;

/**
 * What a range command returns when the scope is "selected tracks only" and no track is
 * selected: not null (the command stays enabled) but a refusal, so the user is told why
 * nothing happens instead of getting a silent no-op (WP83).
 */
export const scopeRefusal = () => ({ refuse: { key: "ui.scope.none_selected" } });
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
  const at = state.playhead;
  // The split shows at once: the server's answer replaces this guess.
  return plan(
    "split_clips",
    { at, clip_ids: ids },
    "split",
    { count: ids.length },
    {
      more: { provisional: (project) => splitClipsProvisional(project, at, ids) },
    },
  );
}

/**
 * The tracks a range edit acts on: the one scope function of range-scope.js (all tracks by
 * default; the lanes of a mouse-painted range; the selected tracks while any are selected).
 * Empty when the mode is "selected tracks only" and none is selected.
 */
export function rangeTracks(state) {
  return resolveScope(state).tracks;
}

/**
 * The frames an edit covers and the tracks it starts from: the range, else the selected
 * clips' span. With both, the one touched last (intent.js `editRange`), so selecting clips
 * after the marks were set makes the clips the target.
 */
function span(state) {
  const range = editRange(state);
  if (range) {
    const scope = resolveScope(state);
    if (scope.none) return { refused: true };
    return { ...range, tracks: scope.tracks, fromRange: true };
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

/** Backspace and Delete: mute in place (the range, else the selected clips: the latest intent); the gap stays. */
export function deletePlan(state) {
  if (!state?.project) return null;
  const range = editRange(state);
  if (range) {
    const scope = resolveScope(state);
    if (scope.none) return scopeRefusal();
    return plan(
      "mute_range",
      { ...range, track_ids: scope.tracks },
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

/**
 * Quick mute: a short stretch centred on the play cursor (the setting `quickMuteS`, seconds) is
 * muted on the range scope's tracks (WP83), whatever range is marked. It is a soft cut
 * (`mute_range`: the clips are split at the two edges, the middle piece is muted, one undo step);
 * `ops.mute_ranges` splits only inside clips, so nothing outside a clip is touched. Null when no
 * clip lies under the stretch; a notice (refusal) when what lies there is muted already.
 */
export function quickMutePlan(state) {
  if (!state?.project || !Number.isFinite(state.playhead)) return null;
  const scope = resolveScope(state);
  if (scope.none) return scopeRefusal();
  const { start, end } = quickMuteStretch(state.playhead, rateOf(state), state.quickMuteS);
  const under = state.project.tracks
    .filter((track) => scope.tracks.includes(track.id))
    .flatMap((track) => track.clips)
    .filter((clip) => clip.start < end && clipEnd(clip) > start);
  if (under.length === 0) return null;
  if (under.every((clip) => clip.muted)) return { refuse: { key: "ui.quick_mute.already" } };
  return plan(
    "mute_range",
    { start, end, track_ids: scope.tracks },
    "quick_mute",
    { seconds: secondsOf(state, end - start) },
    { tracks: true },
  );
}

/**
 * "Add a track" / "Add a music track" (owner, 2026-10-19: create the track first, then put audio
 * on it). An empty track at the bottom, named by its kind and a number.
 */
export function addTrackPlan(state, kind, { t } = {}) {
  if (!state?.project) return null;
  const n = state.project.tracks.length + 1;
  const name = t(kind === "music" ? "ui.track.new_music" : "ui.track.new_speech", { n });
  return plan("add_track", { name, kind }, "add_track", { name });
}

/** Delete every track that holds no clip (after moving its clips elsewhere). */
export function deleteEmptyTracksPlan(state) {
  const empty = (state?.project?.tracks ?? []).filter((track) => track.clips.length === 0);
  if (empty.length === 0) return null;
  return plan("delete_empty_tracks", {}, "delete_empty_tracks", { count: empty.length });
}

/**
 * Every track and bus fader to 0 dB (owner, 2026-10-19: unity gain before export). The master,
 * clip gains and pan stay. Null when all are at 0, so the menu dims it.
 */
export function resetGainsPlan(state) {
  const project = state?.project;
  if (!project) return null;
  const count = [...project.tracks, ...(project.buses ?? [])].filter(
    (x) => (x.gain_db ?? 0) !== 0,
  ).length;
  if (count === 0) return null;
  return plan("reset_gains", {}, "reset_gains", { count });
}

/**
 * Cmd+Backspace: really delete the selected clips and leave every other clip where it was
 * (owner, 2026-10-18); the gap stays. Backspace only mutes.
 */
export function removeClipsPlan(state) {
  if (!state?.project) return null;
  const chosen = selectedClips(state);
  if (chosen.length === 0) return null;
  return plan("delete_clips", { clip_ids: chosen.map((e) => e.clip.id) }, "remove_clips", {
    count: chosen.length,
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

/** The explicit "this track only" commands name the current track; else the scope's tracks. */
function onlyThisTrack(state, tracks, thisTrackOnly) {
  if (!thisTrackOnly) return tracks;
  const track = currentTrack(state);
  return track === null ? tracks : [track];
}

/** X and Shift+X: ripple-delete the range or the selected clips' span; the cut audio goes to the clipboard. */
export function cutPlan(state, { thisTrackOnly = false, t } = {}) {
  return cutToClipboard(state, { op: "clipboard_cut", key: "cut", thisTrackOnly, t });
}

/**
 * X and Shift+X: ripple-delete the range or the selected clips' span and close the gap. The
 * clipboard is left alone (owner, 2026-10-18: every clip deleted with X must not land there);
 * Cut (Mod+X) is the one that keeps what it removes.
 */
export function removePlan(state, { thisTrackOnly = false } = {}) {
  if (!state?.project) return null;
  const covered = span(state);
  if (!covered) return null;
  if (covered.refused) return scopeRefusal();
  const tracks = onlyThisTrack(state, covered.tracks, thisTrackOnly);
  return plan(
    "cut_range",
    { start: covered.start, end: covered.end, track_ids: tracks },
    "remove",
    { seconds: secondsOf(state, covered.end - covered.start) },
    { tracks: true },
  );
}

/** Alt+X: the same target as X, copied to the clipboard, but soft-deleted in place (the gap stays). */
export function liftCutPlan(state, { t } = {}) {
  return cutToClipboard(state, { op: "clipboard_lift_cut", key: "lift_cut", t });
}

/** Alt+Mod+X: ripple-delete the range or the selected clips' span on every track of the sync group; no clipboard. */
export function closeGapPlan(state) {
  if (!state?.project) return null;
  const covered = span(state);
  if (!covered) return null;
  if (covered.refused) return scopeRefusal();
  return plan(
    "ripple_delete",
    { start: covered.start, end: covered.end, track_ids: covered.tracks },
    "close_gap",
    { seconds: secondsOf(state, covered.end - covered.start) },
    { tracks: true },
  );
}

function cutToClipboard(state, { op, key, thisTrackOnly = false, t }) {
  if (!state?.project) return null;
  const covered = span(state);
  if (!covered) return null;
  if (covered.refused) return scopeRefusal();
  const tracks = onlyThisTrack(state, covered.tracks, thisTrackOnly);
  const name = autoName(describeClips(coveredParts(state, covered), rateOf(state)), t);
  return plan(
    op,
    {
      start: covered.start,
      end: covered.end,
      track_ids: tracks,
      name,
    },
    key,
    { seconds: secondsOf(state, covered.end - covered.start) },
    {
      tracks: true,
      // A copy that failed does not undo the cut, but the user is told (WP46).
      variant: (response) =>
        response?.clipboard?.ok === false
          ? { key: `ui.edit.toast.${key}_uncopied`, values: { error: response.clipboard.error } }
          : null,
    },
  );
}

/** Mod+C: copy the range (as Cut would take it), else the selected clips. No edit, so no undo step. */
export function copyPlan(state, t) {
  if (!state?.project) return null;
  const range = editRange(state);
  let body;
  let parts;
  if (range) {
    const scope = resolveScope(state);
    if (scope.none) return scopeRefusal();
    parts = clipsInRange(state.project, scope.tracks, range.start, range.end);
    body = { ...range, track_ids: scope.tracks };
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
 * The track a paste anchors on: the topmost header-selected track (WP83), else the current
 * track (focus, or the one track of the selected clips): the notion split and mute use.
 */
export function pasteAnchor(state) {
  const picked = state?.trackSelection;
  const ids = (state?.project?.tracks ?? []).map((track) => track.id);
  const chosen = picked ? ids.find((id) => picked.has(id)) : undefined;
  return chosen ?? currentTrack(state);
}

/**
 * Mod+V (overwrite), Alt+Mod+V (insert): paste an entry at the play cursor. With In and Out
 * marked (In before Out) the paste starts at In instead and is cut at Out (`out`); a shorter
 * paste keeps its own length. `target`:
 * "auto" (default: the anchor track, else the source tracks), "current" (the anchor track
 * and the ones below it; null without one) or "same" (the source tracks). The entry's slots
 * keep their layout from the anchor downwards; extra slots fold onto the last track.
 */
export function pastePlan(state, { mode, target } = {}) {
  const choice = pasteChoice({ pasteMode: mode, pasteTarget: target });
  const entry = pasteEntry(state);
  if (!state?.project || !entry || !Number.isFinite(state.playhead)) return null;
  const tracks = state.project.tracks;
  const ids = tracks.map((track) => track.id);
  const anchor = choice.target === "same" ? null : pasteAnchor(state);
  let targetTracks;
  if (anchor !== null) {
    targetTracks = pasteTargets(entry.slots, ids, anchor);
  } else if (choice.target === "current") {
    return null;
  } else {
    targetTracks = sourceTargets(
      entry.slots,
      ids,
      tracks.map((track) => track.name),
      entry.tracks,
    );
  }
  if (targetTracks === null || ids.length === 0) return null;
  const key = choice.mode === "insert" ? "paste_insert" : "paste";
  const { inPoint, outPoint } = state;
  const marked = Number.isFinite(inPoint) && Number.isFinite(outPoint) && inPoint < outPoint;
  return plan(
    "clipboard_paste",
    {
      entry_id: entry.id,
      at: marked ? inPoint : state.playhead,
      mode: choice.mode,
      target_tracks: targetTracks,
      ...(marked ? { out: outPoint } : {}),
    },
    key,
    { count: entry.clips },
    { variant: pasteVariant },
  );
}

/** A paste's toast once the answer is in: nothing placed, or recordings that were missing. */
function pasteVariant(response) {
  const done = response?.clipboard;
  if (!done) return null;
  if (done.placed === 0) {
    return { key: "ui.edit.toast.paste_nothing", values: {}, undo: false };
  }
  return done.missing.length > 0
    ? { key: "ui.edit.toast.paste_missing", values: { count: done.missing.length } }
    : null;
}

/**
 * A clipboard entry dropped on the timeline (clipboard-drag.js): the same paste as Mod+V, at the
 * drop's frame and tracks, in `mode` (the panel's paste choice). In/Out play no part in a drop.
 */
export function dropPastePlan(entry, target, mode) {
  const insert = mode === "insert";
  return plan(
    "clipboard_paste",
    {
      entry_id: entry.id,
      at: target.at,
      mode: insert ? "insert" : "overwrite",
      target_tracks: target.targetTracks,
    },
    insert ? "paste_insert" : "paste",
    { count: entry.clips },
    { variant: pasteVariant },
  );
}

/** N: mute the selected clips, or unmute them when they all are muted already. */
export function mutePlan(state) {
  const chosen = selectedClips(state);
  // Nothing selected: the current track's portion under the cursor is the target.
  if (chosen.length === 0) return cursorPortionPlan(state, []);
  // A click on an implicit region is an explicit edit target even when selecting the clip
  // expands its group. Materialize only that source clip/range, never the expanded group.
  const region = targetedGatedRegionPlan(state, chosen);
  if (region) return region;
  // The play cursor inside an implicit portion (closed or audible) of a selected clip: M acts
  // on that portion alone, also when the selection is a whole group (owner, 2026-10-24).
  const cursorRegion = cursorPortionPlan(state, chosen);
  if (cursorRegion) return cursorRegion;
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
 * The selected clip whose implicit portion holds the play cursor (the focused track's first,
 * and only when one is unambiguous); with no selection the focused track's clip there.
 */
function cursorPortionPlan(state, chosen) {
  if (!state?.project || !Number.isFinite(state.playhead)) return null;
  const at = state.playhead;
  const trackOf = (id) => state.project.tracks.find((x) => x.id === id);
  let entries = chosen;
  if (entries.length === 0) {
    const track = trackOf(currentTrack(state));
    const clip = (track?.clips ?? [])
      .filter((c) => c.start <= at && at < clipEnd(c))
      .sort((x, y) => x.length - y.length)[0];
    entries = clip ? [{ clip, trackId: track.id }] : [];
  }
  const hits = entries.filter(
    ({ clip, trackId }) => implicitPortionAt(clip, at, trackOf(trackId)?.gate) !== null,
  );
  if (hits.length === 0) return null;
  const focus = hits.filter((entry) => entry.trackId === currentTrack(state));
  const pick = focus.length === 1 ? focus[0] : hits.length === 1 ? hits[0] : null;
  return pick ? gatedRegionPlan(state, pick) : null;
}

function targetedGatedRegionPlan(state, chosen) {
  const target = state.implicitRangeTarget;
  if (!target?.implicit || !Array.isArray(target.range)) return null;
  const entry = chosen.find(
    ({ clip, trackId }) => clip.id === target.clipId && trackId === target.trackId,
  );
  if (!entry || entry.clip.muted) return null;
  const [start, end] = target.range;
  const at = Math.floor((start + end) / 2);
  const gate = state.project.tracks.find((track) => track.id === target.trackId)?.gate;
  const portion = implicitPortionAt(entry.clip, at, gate);
  if (!portion || portion.range[0] !== start || portion.range[1] !== end) return null;
  return portionMutePlan(target.trackId, entry.clip, at, portion);
}

/**
 * The clip M just opened: the one on `trackId` holding `at` in `project` (the response after
 * open_gated_region). It is selected afterwards, so the next M mutes just that stretch, not
 * the left-over piece of the parent clip that kept the old selection (owner, 2026-10-24).
 */
export function openedRegionClip(project, trackId, at, sourceClip = null, legacyGate = []) {
  const track = project?.tracks?.find((x) => x.id === trackId);
  if (sourceClip) {
    const portion = implicitPortionAt(sourceClip, at, legacyGate);
    if (!portion) return null;
    const [start, end] = portion.range;
    return (
      track?.clips?.find(
        (clip) =>
          clip.start === start &&
          clipEnd(clip) === end &&
          clip.media === sourceClip.media &&
          (clip.offset ?? 0) === (sourceClip.offset ?? 0) + start - sourceClip.start,
      )?.id ?? null
    );
  }
  return track?.clips?.find((c) => c.start <= at && at < clipEnd(c))?.id ?? null;
}

function portionMutePlan(trackId, clip, at, portion) {
  return plan(
    "open_gated_region",
    { track_id: trackId, clip_id: clip.id, at, ...(!portion.closed ? { muted: true } : {}) },
    portion.closed ? "unmute_region" : "mute",
    portion.closed ? {} : { count: 1 },
  );
}

function gatedRegionPlan(state, { clip, trackId }) {
  const at = state.playhead;
  if (!Number.isFinite(at)) return null;
  const gate = state.project?.tracks?.find((x) => x.id === trackId)?.gate;
  const portion = implicitPortionAt(clip, at, gate);
  return portion ? portionMutePlan(trackId, clip, at, portion) : null;
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

/** Mod+Left / Mod+Right: direction -1 or 1, one nudge step; an explicit group goes together. */
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
    },
    "nudge",
    {},
    { silent: true },
  );
}

/**
 * Mod+Up / Mod+Down: the selected clips one track up (`direction` -1) or down (+1), at the
 * same time. Null when nothing is selected or the selection already sits on the first (last)
 * track, so the command is greyed instead of making an empty step.
 */
export function moveTrackPlan(state, direction) {
  if (!state?.project) return null;
  const chosen = selectedClips(state);
  if (chosen.length === 0) return null;
  const index = new Map(state.project.tracks.map((track, i) => [track.id, i]));
  const rows = chosen.map((entry) => index.get(entry.trackId)).filter((i) => i !== undefined);
  if (rows.length === 0) return null;
  const last = state.project.tracks.length - 1;
  if (direction < 0 ? Math.min(...rows) <= 0 : Math.max(...rows) >= last) return null;
  return plan(
    "move_clips_to_track",
    {
      clip_ids: chosen.map((e) => e.clip.id),
      direction: direction < 0 ? -1 : 1,
      delta: 0,
    },
    "move_track",
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

/** Mute the bus in focus (the focused bus, else the bus of the focused track). */
export function busMutePlan(state) {
  const id = busOfFocus(state);
  const bus = (state?.project?.buses ?? []).find((item) => item.id === id);
  if (!bus) return null;
  return plan("set_bus", { bus_id: bus.id, mute: !bus.mute }, "bus_mute", {}, { silent: true });
}

/** Ungroup: delete the bus in focus; ops.delete_bus puts all its tracks on no bus, in one step. */
export function ungroupPlan(state) {
  const id = busOfFocus(state);
  if (id === null || !(state?.project?.buses ?? []).some((bus) => bus.id === id)) return null;
  return plan("delete_bus", { bus_id: id }, "ungroup", {}, { silent: true });
}

/** Take the current track off its bus. */
export function removeFromBusPlan(state) {
  const track = trackOf(state);
  if (!track?.bus) return null;
  return plan(
    "set_track",
    { track_id: track.id, bus: null },
    "remove_from_bus",
    {},
    { silent: true },
  );
}

/** Ids of the tracks whose clips differ between two projects. */
export function changedTracks(before, after) {
  const was = new Map((before?.tracks ?? []).map((t) => [t.id, JSON.stringify(t.clips)]));
  return (after?.tracks ?? [])
    .filter((t) => was.get(t.id) !== JSON.stringify(t.clips))
    .map((t) => t.id);
}
