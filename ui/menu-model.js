// The menu bar as data, and the pure functions that resolve it for a state.
// Items name command ids; labels, keys, enabled state and tooltips come from
// the registry and the keymap the user has, so a remapped key shows at once.
// Holding Alt or Shift swaps an item for its alternate (modifiers.js).

import { formatCombo } from "./keymap-config.js";
import { modifierLayers, pickLayer } from "./modifiers.js";

const item = (id) => ({ kind: "item", id });
const SEP = { kind: "separator" };

export const MENU = [
  {
    id: "file",
    labelKey: "menu.file",
    items: [
      item("app.import"),
      item("app.export"),
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
      item("edit.cut"),
      item("edit.cut_track"),
      item("edit.copy"),
      item("edit.paste"),
      item("edit.paste_overwrite"),
      item("edit.paste_track"),
      item("edit.delete"),
      SEP,
      item("edit.split"),
      item("edit.split_all"),
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
      item("track.mute"),
      item("track.solo"),
      item("track.group_into_bus"),
      item("track.new_bus"),
      item("group.toggle"),
      SEP,
      item("clip.mute"),
      item("clip.fade"),
      item("clip.match_loudness"),
      SEP,
      item("sync.mark"),
      item("sync.resync"),
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
      SEP,
      item("marker.next"),
      item("marker.prev"),
      item("marker.delete"),
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
      item("view.toggle"),
      item("view.fit"),
      item("view.fit_selection"),
      item("view.fit_tracks"),
      item("view.auto_fit_tracks"),
      item("view.back"),
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
      else if (entry.kind === "submenu") walk(entry.items);
    }
  };
  for (const top of menu) walk(top.items);
  return ids;
}

/**
 * -> [{ id, label, items: [{ kind: "item", id, baseId, label, keys, enabled, planned,
 *    alternate, hint, tooltip } | { kind: "separator" } | { kind: "submenu", label, items }] }]
 * `keys` is the first key of the command ("" when it has none), `held` the modifiers down.
 */
export function resolveMenu({ menu, entries, registry, state, label, platform, held }) {
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
      planned,
      alternate: Boolean(alternateEntry),
      hint,
      tooltip: keys ? `${hint} · ${keys}` : hint,
    };
  }

  function resolveItems(items) {
    return items.map((entry) => {
      if (entry.kind === "separator") return entry;
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
