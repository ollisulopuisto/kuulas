// The status-bar key hints for the focused panel: at most three, from the same
// data as the cheat sheet, showing the user's current keys. While Alt or Shift is
// held, a hint swaps to the command that key has with that modifier.

import { modifierLayers, pickLayer } from "./modifiers.js";

const MAX_HINTS = 3;

export function resolveHints({
  panel,
  hints,
  entries,
  registry,
  state,
  held,
  label,
  format,
  platform,
}) {
  const list = hints[panel] ?? [];
  const layers = modifierLayers(entries, platform);
  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  const rows = [];
  for (const hint of list) {
    const alternate = pickLayer(layers, hint.id, held);
    const target = alternate ?? byId.get(hint.id);
    if (!target || registry.status(target.id) !== "ready") continue;
    if (!registry.can(target.id, state)) continue;
    if (target.raw.length === 0) continue;
    rows.push({
      id: target.id,
      label: alternate ? label(target.labelKey) : label(hint.hintKey),
      keys: format(target.raw[0], platform),
      alternate: Boolean(alternate),
    });
    if (rows.length === MAX_HINTS) break;
  }
  return rows;
}
