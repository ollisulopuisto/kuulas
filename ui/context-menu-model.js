// The right-click menu on a bus or track header, as data. Every item is a command in
// the registry, so its label is the command's (`cmd.<id>`) and its enabled state is
// the registry's `can`. Pure; context-menu.js draws it.

const SEPARATOR = { separator: true };

/** Items for { kind: "bus", collapsed } or { kind: "track" }; `can(id)` asks the registry. */
export function contextMenuItems(target, can) {
  const item = (id) => ({ id, labelKey: `cmd.${id}`, enabled: Boolean(can(id)) });
  if (target.kind === "bus") {
    return [
      item(target.collapsed ? "bus.expand" : "bus.collapse"),
      item("rename"),
      item("bus.mute"),
      SEPARATOR,
      item("bus.ungroup"),
    ];
  }
  return [
    item("rename"),
    item("track.mute"),
    item("track.solo"),
    SEPARATOR,
    item("track.group_into_bus"),
    item("track.remove_from_bus"),
  ];
}

/**
 * The next enabled item from `index` in `direction` (1 or -1), wrapping round; separators
 * and disabled items are skipped. From -1 Down takes the first and Up the last.
 * Returns -1 when nothing is enabled.
 */
export function stepItem(items, index, direction) {
  const count = items.length;
  const from = index < 0 && direction < 0 ? count : index;
  for (let step = 1; step <= count; step += 1) {
    const at = (((from + direction * step) % count) + count) % count;
    if (items[at].enabled) return at;
  }
  return -1;
}
