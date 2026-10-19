// The menu bar as data, and the pure functions that resolve it for a state.
// Items name command ids; labels, keys, enabled state and tooltips come from
// the registry and the keymap the user has, so a remapped key shows at once.
// Holding Alt or Shift swaps an item for its alternate (modifiers.js).

import { ALWAYS_AVAILABLE, EXPORT_FORMAT_IDS } from "./export-commands.js";
import { formatCombo } from "./keymap-config.js";
import { modifierLayers, pickLayer } from "./modifiers.js";

const item = (id) => ({ kind: "item", id });
const SEP = { kind: "separator" };
// A submenu whose items are one command per export format the server offers:
// `formatPrefix` + the format id (resolveMenu's `formats` lists the ids).
const formatMenu = (labelKey, formatPrefix) => ({ kind: "submenu", labelKey, formatPrefix });

/**
 * Menu items that are switches: base command id -> whether it is on in a state. The menu
 * shows them checked (aria-checked); other items carry no `checked` at all.
 */
export const CHECKED = {
  "view.clip_words": (state) => state?.showClipWords !== false,
};

export const MENU = [
  {
    id: "file",
    labelKey: "menu.file",
    items: [
      item("app.import"),
      item("app.export"),
      formatMenu("menu.export_mix", "export.mix_"),
      item("export.tracks"),
      item("export.tracks_quick"),
      item("export.automix"),
      formatMenu("menu.export_tracks_as", "export.tracks_"),
      SEP,
      item("export.subtitles_srt"),
      item("export.subtitles_vtt"),
      item("export.transcript_txt"),
      item("export.transcript_md"),
      SEP,
      item("export.chapters_text"),
      item("export.chapters_json"),
      item("export.regions"),
      item("export.narration_script_txt"),
      item("export.narration_script_md"),
      SEP,
      item("app.save"),
      item("app.save_named"),
    ],
  },
  {
    id: "edit",
    labelKey: "menu.edit",
    items: [
      item("edit.undo"),
      item("edit.redo"),
      SEP,
      item("edit.remove_clips"),
      item("edit.remove"),
      item("edit.remove_track"),
      item("edit.cut"),
      item("edit.cut_track"),
      item("edit.lift_cut"),
      item("edit.close_gap_all"),
      item("edit.copy"),
      item("edit.paste"),
      item("edit.paste_overwrite"),
      item("edit.paste_track"),
      item("edit.paste_same"),
      item("edit.paste_overwrite_track"),
      item("edit.preview_clipboard"),
      item("edit.clear_old_clipboard"),
      {
        kind: "submenu",
        labelKey: "menu.clipboard",
        items: [
          item("edit.share_clipboard"),
          SEP,
          item("clipboard.view_project"),
          item("clipboard.view_shared"),
          item("clipboard.view_others"),
          item("clipboard.open_project"),
        ],
      },
      item("edit.delete"),
      item("rename"),
      SEP,
      {
        kind: "submenu",
        labelKey: "menu.trim_nudge",
        items: [
          item("edit.trim_start"),
          item("edit.trim_end"),
          SEP,
          item("edit.nudge_left"),
          item("edit.nudge_right"),
          SEP,
          item("edit.move_up"),
          item("edit.move_down"),
        ],
      },
      SEP,
      item("edit.split"),
      item("edit.split_all"),
      item("edit.merge"),
      SEP,
      item("edit.group"),
      item("edit.ungroup"),
      SEP,
      item("edit.select_all"),
      item("edit.select_all_track"),
      {
        kind: "submenu",
        labelKey: "menu.select",
        items: [
          item("select.range_all_tracks"),
          item("select.clips_in_range"),
          item("select.range_from_clips"),
          SEP,
          item("select.forward"),
          item("select.forward_from_clips"),
          item("select.forward_all_tracks_from_clips"),
          SEP,
          SEP,
          item("select.to_start"),
          item("select.to_end"),
          item("select.to_start_all"),
          item("select.to_end_all"),
          SEP,
          item("select.invert"),
          item("select.none"),
        ],
      },
      SEP,
      item("transcript.find"),
      item("spot"),
    ],
  },
  {
    id: "track",
    labelKey: "menu.track",
    items: [
      item("track.add"),
      item("track.add_music"),
      item("track.delete_empty"),
      item("track.reset_gains"),
      SEP,
      item("track.mute"),
      item("track.solo"),
      item("track.solo_add"),
      item("track.cycle_kind"),
      SEP,
      item("track.group_into_bus"),
      item("track.new_bus"),
      item("track.remove_from_bus"),
      item("group.toggle"),
      {
        kind: "submenu",
        labelKey: "menu.bus",
        items: [item("bus.collapse"), item("bus.expand"), item("bus.mute"), item("bus.ungroup")],
      },
      SEP,
      item("clip.mute"),
      item("clip.fade"),
      item("clip.match_loudness"),
      {
        kind: "submenu",
        labelKey: "menu.level_pan",
        items: [
          item("clip.gain_up"),
          item("clip.gain_down"),
          SEP,
          item("clip.pan_left"),
          item("clip.pan_right"),
        ],
      },
      SEP,
      {
        kind: "submenu",
        labelKey: "menu.sync",
        items: [
          item("sync.mark"),
          item("sync.point1"),
          item("sync.point2"),
          item("sync.resync"),
          item("sync.resync_end"),
          SEP,
          item("sync.free"),
          item("sync.resync_all"),
          item("sync.free_all"),
          item("sync.drift_next"),
          item("sync.drift_previous"),
        ],
      },
      SEP,
      item("app.automix"),
      item("app.auto_silence"),
      item("gate.open_stretch"),
      item("app.transcribe"),
    ],
  },
  {
    id: "markers",
    labelKey: "menu.markers",
    items: [
      item("marker.add"),
      item("region.from_selection"),
      SEP,
      item("mark.in"),
      item("mark.out"),
      item("mark.clear"),
      item("mark.clear_in"),
      item("mark.clear_out"),
      SEP,
      item("marker.next"),
      item("marker.prev"),
      item("marker.delete"),
    ],
  },
  {
    id: "transport",
    labelKey: "menu.transport",
    items: [
      item("transport.play"),
      item("transport.play_before"),
      item("transport.play_selection"),
      item("transport.rehearse"),
      SEP,
      item("transport.loop"),
      item("transport.speed"),
      item("transport.speed_down"),
      item("transport.speed_up"),
      item("transport.speed_reset"),
      {
        kind: "submenu",
        labelKey: "menu.shuttle",
        items: [
          item("transport.shuttle_back"),
          item("transport.shuttle_forward"),
          item("transport.shuttle_stop"),
        ],
      },
    ],
  },
  {
    id: "go",
    labelKey: "menu.go",
    items: [
      item("nav.home"),
      item("nav.start"),
      item("nav.end"),
      item("nav.to_in"),
      item("nav.to_out"),
      item("nav.to_resume"),
      SEP,
      {
        kind: "submenu",
        labelKey: "menu.steps",
        items: [
          item("nav.back"),
          item("nav.forward"),
          SEP,
          item("nav.back_far"),
          item("nav.forward_far"),
          SEP,
          item("nav.back_fine"),
          item("nav.forward_fine"),
        ],
      },
      item("nav.prev_stop"),
      item("nav.next_stop"),
      item("transcript.prev_stop"),
      item("transcript.next_stop"),
      item("nav.tab_target_cycle"),
      SEP,
      item("track.prev"),
      item("track.next"),
      item("panel.previous"),
      item("panel.next"),
      SEP,
      item("history.open"),
      item("history.restore"),
    ],
  },
  {
    id: "transcript",
    labelKey: "menu.transcript",
    items: [
      item("transcript.delete_words"),
      item("transcript.remove_words"),
      item("transcript.cut_words"),
      item("transcript.correct"),
      item("transcript.mark_candidate"),
    ],
  },
  {
    id: "candidates",
    labelKey: "menu.candidates",
    items: [
      item("candidate.find"),
      item("candidate.mark"),
      item("candidate.mark_range"),
      SEP,
      item("candidate.next"),
      item("candidate.previous"),
      item("candidate.preview"),
      item("candidate.filter"),
      SEP,
      item("candidate.apply"),
      item("candidate.apply_ripple"),
      item("candidate.reject"),
    ],
  },
  {
    id: "narration",
    labelKey: "menu.narration",
    items: [
      item("placeholder.add"),
      item("placeholder.edit"),
      item("placeholder.take"),
      item("placeholder.delete"),
    ],
  },
  {
    id: "view",
    labelKey: "menu.view",
    items: [
      item("view.zoom_in"),
      item("view.zoom_out"),
      item("view.drag_mode"),
      item("view.clip_words"),
      item("view.toggle"),
      item("view.fit"),
      item("view.fit_selection"),
      item("view.fit_tracks"),
      item("view.auto_fit_tracks"),
      item("view.collapse_all_buses"),
      item("view.expand_all_buses"),
      item("view.back"),
      item("view.forward"),
      item("view.reset_remembered"),
      SEP,
      {
        kind: "submenu",
        labelKey: "menu.pause_break",
        items: [
          item("view.pause_1_5"),
          item("view.pause_3"),
          item("view.pause_6"),
          item("view.pause_never"),
        ],
      },
      item("transport.loop"),
      SEP,
      item("palette.open"),
    ],
  },
  {
    id: "help",
    labelKey: "menu.help",
    items: [
      item("help.open"),
      item("help.keys"),
      {
        kind: "submenu",
        labelKey: "menu.keymap",
        items: [item("keymap.import"), item("keymap.export"), item("keymap.reset")],
      },
    ],
  },
];

/** Every command id the menu names. */
export function menuTargets(menu) {
  const ids = [];
  const walk = (items) => {
    for (const entry of items) {
      if (entry.kind === "item") ids.push(entry.id);
      else if (entry.formatPrefix) {
        for (const format of EXPORT_FORMAT_IDS) ids.push(entry.formatPrefix + format);
      } else if (entry.kind === "submenu") walk(entry.items);
    }
  };
  for (const top of menu) walk(top.items);
  return ids;
}

/**
 * -> [{ id, label, items: [{ kind: "item", id, baseId, label, keys, enabled, planned,
 *    alternate, hint, tooltip } | { kind: "separator" } | { kind: "submenu", label, items }] }]
 * `keys` is the first key of the command ("" when it has none), `held` the modifiers down.
 * `formats`: the export format ids the server offers, in its order (the always-available
 * ones while that is not known yet), for the submenus that list one command per format.
 */
export function resolveMenu({ menu, entries, registry, state, label, platform, held, formats }) {
  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  const layers = modifierLayers(entries, platform);
  const none = { alt: false, shift: false, mod: false };

  function resolveItem(baseId) {
    const alternateEntry = pickLayer(layers, baseId, held ?? none);
    const entry = alternateEntry ?? byId.get(baseId);
    const id = entry?.id ?? baseId;
    const name = entry ? label(entry.labelKey) : baseId;
    const planned = registry.status(id) !== "ready";
    const keys = entry?.raw.length ? formatCombo(entry.raw[0], platform) : "";
    const hintKey = registry.hintKey(id);
    const hint = hintKey ? label(hintKey) : name;
    return {
      kind: "item",
      id,
      baseId,
      label: name,
      keys,
      enabled: !planned && registry.can(id, state),
      checked: CHECKED[baseId] ? CHECKED[baseId](state) : undefined,
      planned,
      alternate: Boolean(alternateEntry),
      hint,
      tooltip: keys ? `${hint} · ${keys}` : hint,
    };
  }

  function resolveItems(items) {
    return items.map((entry) => {
      if (entry.kind === "separator") return entry;
      if (entry.formatPrefix) {
        const ids = (formats ?? ALWAYS_AVAILABLE).filter((id) => EXPORT_FORMAT_IDS.includes(id));
        return {
          kind: "submenu",
          label: label(entry.labelKey),
          items: ids.map((id) => resolveItem(entry.formatPrefix + id)),
        };
      }
      if (entry.kind === "submenu") {
        return { kind: "submenu", label: label(entry.labelKey), items: resolveItems(entry.items) };
      }
      return resolveItem(entry.id);
    });
  }

  return menu.map((top) => ({
    id: top.id,
    label: label(top.labelKey),
    items: resolveItems(top.items),
  }));
}

/** Up/Down: the next item that is not a separator, wrapping. From -1 (nothing) Down is first. */
export function moveItem(items, index, direction) {
  const usable = items
    .map((entry, i) => (entry.kind === "separator" ? -1 : i))
    .filter((i) => i >= 0);
  if (usable.length === 0) return -1;
  if (index < 0) return direction > 0 ? usable[0] : usable[usable.length - 1];
  const at = usable.indexOf(index);
  const next = (at + direction + usable.length) % usable.length;
  return usable[next];
}

/** Left/Right between the top-level menus, wrapping. */
export function moveMenu(count, index, direction) {
  return (index + direction + count) % count;
}

/**
 * How many top-level menus fit in `available` px. Everything fits -> all of them;
 * otherwise as many as leave room for the "…" overflow button after them.
 * widths: each title's width; gap: space between two; overflowWidth: the "…" button.
 */
export function fitMenus(widths, available, { gap, overflowWidth }) {
  const used = (count) =>
    widths.slice(0, count).reduce((sum, w) => sum + w, 0) + Math.max(0, count - 1) * gap;
  if (used(widths.length) <= available) return widths.length;
  for (let count = widths.length - 1; count > 0; count--) {
    if (used(count) + gap + overflowWidth <= available) return count;
  }
  return 0;
}

/**
 * The "…" menu: the hidden menus' items one after another, each group under a
 * caption (a separator that carries its menu's name). Submenus stay submenus.
 */
export function overflowMenu(hidden, label) {
  const items = hidden.flatMap((menu) => [
    { kind: "separator", caption: menu.label },
    ...menu.items.filter((item) => item.kind !== "separator"),
  ]);
  return { id: "overflow", label, items };
}
