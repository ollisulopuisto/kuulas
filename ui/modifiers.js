// Held modifiers, and the "alternate" commands they reveal. Like Option in a
// macOS menu: while Alt or Shift is held, an item whose key also exists with
// that modifier swaps to that command, and swaps back on release.
//
// Layers are derived from the current keymap (so user overrides count): command
// B is a layer of command A when B's key is A's key plus Alt and/or Shift. Mod
// is never a layer (Mod+Z is undo, not a variant of Z). Shift+Alt+Z hangs under Z
// (both held), under Alt+Z (Shift held) and under Shift+Z (Alt held).

import { contextsOverlap } from "./keymap-config.js";
import { parseCombo } from "./keys.js";

const NONE = Object.freeze({ alt: false, shift: false, mod: false });

/** The modifiers an event says are down. AltGr (Ctrl+Alt on Windows) is none of them. */
export function heldFromEvent(event, platform = "other") {
  const altGr = Boolean(event.getModifierState?.("AltGraph"));
  const mac = platform === "mac";
  return {
    alt: Boolean(event.altKey) && !altGr,
    shift: Boolean(event.shiftKey),
    mod: mac ? Boolean(event.metaKey) : Boolean(event.ctrlKey) && !altGr,
  };
}

const same = (a, b) => a.alt === b.alt && a.shift === b.shift && a.mod === b.mod;

/**
 * Tracks the held modifiers. Every key and pointer event carries the truth in its flags,
 * so a missed keyup (window lost focus, a Cmd chord swallowing it) is fixed by the next
 * event; reset() covers blur and a hidden tab, where no event follows.
 */
export function createModifierTracker({ platform = "other" } = {}) {
  let held = NONE;
  const listeners = new Set();
  const set = (next) => {
    if (same(held, next)) return false;
    held = next;
    for (const listener of listeners) listener({ ...held });
    return true;
  };
  return {
    held: () => ({ ...held }),
    update: (event) => set(heldFromEvent(event, platform)),
    reset: () => set(NONE),
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

function flagsOf(p, mac) {
  return {
    ctrl: mac && p.ctrl,
    mod: p.mod || (!mac && p.ctrl),
    alt: p.alt,
    shift: p.kind === "char" ? false : p.shift,
  };
}

const layerName = ({ alt, shift }) => [alt && "alt", shift && "shift"].filter(Boolean).join("+");

/** Map baseId -> [{ modifier: "shift" | "alt" | "alt+shift", entry }]. */
export function modifierLayers(entries, platform = "other") {
  const mac = platform === "mac";
  const items = [];
  for (const entry of entries) {
    for (const raw of entry.raw) {
      const p = parseCombo(raw);
      if (p) items.push({ entry, p, flags: flagsOf(p, mac) });
    }
  }
  const layers = new Map();
  for (const upper of items) {
    for (const base of items) {
      if (base.entry.id === upper.entry.id) continue;
      if (base.p.key !== upper.p.key || base.p.kind !== upper.p.kind) continue;
      if (!contextsOverlap(base.entry.context, upper.entry.context)) continue;
      const a = base.flags;
      const b = upper.flags;
      if (a.ctrl !== b.ctrl || a.mod !== b.mod) continue;
      if ((a.alt && !b.alt) || (a.shift && !b.shift)) continue;
      const modifier = layerName({ alt: b.alt && !a.alt, shift: b.shift && !a.shift });
      if (!modifier) continue;
      const id = base.entry.id;
      if (!layers.has(id)) layers.set(id, []);
      const list = layers.get(id);
      if (!list.some((l) => l.modifier === modifier && l.entry.id === upper.entry.id)) {
        list.push({ modifier, entry: upper.entry });
      }
    }
  }
  const order = ["shift", "alt", "alt+shift"];
  for (const list of layers.values()) {
    list.sort((x, y) => order.indexOf(x.modifier) - order.indexOf(y.modifier));
  }
  return layers;
}

/** The entry that replaces `baseId` while `held` is down, or null (the base stays). */
export function pickLayer(layers, baseId, held) {
  const modifier = layerName(held);
  if (!modifier) return null;
  return (layers.get(baseId) ?? []).find((layer) => layer.modifier === modifier)?.entry ?? null;
}
