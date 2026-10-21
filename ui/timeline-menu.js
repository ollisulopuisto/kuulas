// The right-click menus of the timeline canvas, as data. Four targets: a clip, the marked
// range (the in/out band), empty lane space and the ruler. Each is sections of command ids;
// labels, keys and tooltips come from the registry and the keymap (shell-keys resolves
// them), so nothing is written twice. A disabled item stays in the menu, dimmed, so the
// menu teaches what exists; inside a section the enabled ones come first. Pure.
import { expandGroups } from "./clip-groups.js";

const PASTE = ["edit.paste", "edit.paste_insert", "edit.paste_track", "edit.paste_same"];

// Section title keys are `ui.ctx.<name>`; the ids are what the menu bar names too.
const SECTIONS = {
  clip: [
    ["gate", ["gate.open_under_clips"]],
    ["clipboard", ["edit.remove", "edit.cut", "edit.copy"]],
    ["paste", PASTE],
    [
      "edit",
      [
        "edit.remove_clips",
        "edit.delete",
        "edit.split",
        "edit.group",
        "edit.ungroup",
        "edit.merge",
        "clip.mute",
        "clip.fade",
      ],
    ],
    [
      "select",
      [
        "select.forward_from_clips",
        "select.forward_all_tracks_from_clips",
        "select.none",
        "select.invert",
      ],
    ],
    [
      "adjust",
      [
        "edit.trim_start",
        "edit.trim_end",
        "edit.nudge_left",
        "edit.nudge_right",
        "clip.gain_up",
        "clip.gain_down",
        "clip.pan_left",
        "clip.pan_right",
      ],
    ],
  ],
  range: [
    ["gate", ["gate.open_under_clips"]],
    ["clipboard", ["edit.remove", "edit.cut", "edit.copy", "edit.delete", "edit.close_gap_all"]],
    ["play", ["transport.play_selection", "transport.rehearse", "transport.loop"]],
    ["select", ["select.clips_in_range", "select.range_all_tracks"]],
    ["marks", ["mark.clear", "region.from_selection", "export.regions"]],
  ],
  lane: [
    ["paste", PASTE],
    ["insert", ["marker.add", "placeholder.add", "mark.in", "mark.out"]],
    ["select", ["select.forward"]],
  ],
  ruler: [
    ["insert", ["marker.add", "mark.in", "mark.out", "mark.clear"]],
    ["zoom", ["view.zoom_in", "view.zoom_out", "view.fit", "view.fit_selection"]],
  ],
};

/** The in/out range as { start, end }, or null (a lone mark is no range). */
function markedRange(state) {
  const { inPoint, outPoint } = state;
  return typeof inPoint === "number" && typeof outPoint === "number" && outPoint > inPoint
    ? { start: inPoint, end: outPoint }
    : null;
}

/**
 * What a pointer hit (from lanes.js hitTest) is, for the menu: { kind, frame, trackId }.
 * The ruler first; then the marked band (it wins over the clips under it, whose menu a
 * selection reaches: "Select clips in range"); then a clip; else empty lane.
 */
export function timelineTarget(hit, state) {
  const frame = hit.frame;
  if (hit.area === "ruler") return { kind: "ruler", frame, trackId: null };
  const trackId = hit.row?.kind === "track" ? hit.row.id : null;
  const range = markedRange(state);
  const gate = Boolean(hit.gate); // the pointer is on a closed (Auto-Silence) stretch
  if (range && frame >= range.start && frame < range.end)
    return { kind: "range", frame, trackId, gate };
  if (hit.clip) return { kind: "clip", frame, trackId, gate };
  return { kind: "lane", frame, trackId, gate };
}

/**
 * Sections for a target: [{ titleKey, items: [{ id, enabled }] }]. `can(id, state)` is the
 * registry's predicate. Only what is possible here is listed (owner, 2026-10-18: the menu was
 * taller than the screen); a section with nothing possible is left out. The menu bar still
 * lists every command, dimmed when it cannot apply.
 */
export function timelineMenuItems(state, target, can) {
  // A closed stretch under the pointer can be opened right there (owner, 21.10.2026).
  const sections = target.gate
    ? [["gate", ["gate.open_stretch", "gate.open_under_clips"]], ...(SECTIONS[target.kind] ?? [])]
    : (SECTIONS[target.kind] ?? []);
  return sections
    .map(([name, ids]) => ({
      titleKey: `ui.ctx.${name}`,
      items: ids.filter((id) => can(id, state)).map((id) => ({ id, enabled: true })),
    }))
    .filter((section) => section.items.length > 0);
}

/** Every command id any of the menus names (the coverage test reads it). */
export function timelineMenuIds() {
  return [...new Set(Object.values(SECTIONS).flatMap((s) => s.flatMap(([, ids]) => ids)))];
}

/**
 * The flat item list openContextMenu draws: a caption per section, a rule between
 * sections. `resolved` maps id -> { label, keys, tooltip } (the menu bar's resolution);
 * `title(key)` translates a section title.
 */
export function menuFromSections(sections, resolved, title) {
  const out = [];
  sections.forEach((section, index) => {
    if (index > 0) out.push({ separator: true });
    out.push({ separator: true, caption: title(section.titleKey) });
    for (const { id, enabled } of section.items) {
      const info = resolved.get(id) ?? {};
      out.push({
        id,
        enabled,
        label: info.label ?? id,
        keys: info.keys ?? "",
        tooltip: info.tooltip ?? "",
      });
    }
  });
  return out;
}

/**
 * What a right press changes before the menu opens, as { kind, seek, selection?, focusTrack? }.
 * A clip outside the selection becomes the selection (with its group), like Finder; inside
 * the marked range nothing moves; empty lane and the ruler put the playhead at the pointer,
 * so "here" commands (marker, in/out, select forward) mean the clicked spot.
 */
export function contextPress(hit, state) {
  const target = timelineTarget(hit, state);
  const gate = hit.gate ? { gate: hit.gate } : {}; // the closed stretch under the pointer
  if (target.kind === "range") return { kind: "range", seek: null, ...gate };
  if (target.kind === "clip") {
    const plan = { kind: "clip", seek: null, ...gate };
    if (!state.selection?.has(hit.clip.id))
      plan.selection = expandGroups(state.project, [hit.clip.id]);
    return plan;
  }
  const plan = { kind: target.kind, seek: hit.frame, ...gate };
  if (target.kind === "lane" && target.trackId) plan.focusTrack = target.trackId;
  return plan;
}
