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
      // Radio-style: the bus's current role is marked.
      ...["speech", "music", "none"].map((role) => ({
        ...item(`bus.role_${role}`),
        checked: (target.role ?? "none") === role,
      })),
      item("bus.reapply_role"),
      SEPARATOR,
      item("bus.ungroup"),
    ];
  }
  return [
    item("rename"),
    item("track.mute"),
    item("track.solo"),
    SEPARATOR,
    item("track.move_up"),
    item("track.move_down"),
    SEPARATOR,
    item("edit.select_all_track"),
    item("view.focus"),
    SEPARATOR,
    // Radio-style Role: the first follows the bus, shown with the bus's current role.
    {
      ...item("track.match_role"),
      checked: target.choice === "match",
      ...(target.busRole ? { values: { role: { key: `ui.role.${target.busRole}` } } } : {}),
      ...(target.busRole ? { labelKey: "cmd.track.match_role.with" } : {}),
    },
    { ...item("track.role_speech"), checked: target.choice === "speech" },
    { ...item("track.role_music"), checked: target.choice === "music" },
    SEPARATOR,
    // Only the one that can apply: a track on a bus leaves it, any other joins a new one.
    item(target.inBus ? "track.remove_from_bus" : "track.group_into_bus"),
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
