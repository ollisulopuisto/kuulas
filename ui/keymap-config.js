// The keymap a user actually has: the defaults (keymap-default.js) with their
// overrides merged over. Pure functions, plus the localStorage and file edges.
//
// Overrides are one JSON object { commandId: combo | [combo, ...] | null }; null
// frees the command's keys. An override replaces both platform columns, because
// "Mod" already means Cmd or Ctrl. Collisions are reported, never accepted
// silently: validateOverrides drops the entries that have a problem and says why.

import { keyName } from "./i18n.js";
import { canonicalCombo, parseCombo } from "./keys.js";

export const STORAGE_KEY = "kuulas.keymap";

const asList = (value) => (value === null || value === undefined ? [] : [value].flat());
const EVERYWHERE = new Set(["global", "text-field"]);
/** Every panel's keys except the Candidates tab's (K stops the shuttle, but keeps there). */
const NOT_CANDIDATES = "not-candidates";
/** Every panel's keys except the transcript's (X cuts the marked range there, but cuts words in the transcript). */
const NOT_TRANSCRIPT = "not-transcript";

/** Every panel's keys except the Markers tab's (N and Shift+N step the drift list there, Alt+Down/Up candidates elsewhere). */
const NOT_MARKERS = "not-markers";

/** Do two contexts ever have the same key available at once? */
export function contextsOverlap(a, b) {
  if (a === NOT_CANDIDATES) return b !== "candidates";
  if (b === NOT_CANDIDATES) return a !== "candidates";
  if (a === NOT_MARKERS) return b !== "markers";
  if (b === NOT_MARKERS) return a !== "markers";
  // The Markers tab also has the side panels' keys.
  if ((a === "markers" && b === "side") || (a === "side" && b === "markers")) return true;
  if (a === NOT_TRANSCRIPT) return b !== "transcript";
  if (b === NOT_TRANSCRIPT) return a !== "transcript";
  return a === b || EVERYWHERE.has(a) || EVERYWHERE.has(b);
}

/** The defaults with overrides applied: [{ id, context, labelKey, repeat, raw, overridden }]. */
export function resolveKeymap(defaults, overrides = {}, platform = "other") {
  return defaults.map((entry) => {
    const overridden = Object.hasOwn(overrides, entry.id);
    const raw = asList(overridden ? overrides[entry.id] : entry.keys[platform]);
    return {
      id: entry.id,
      context: entry.context,
      labelKey: entry.labelKey,
      repeat: Boolean(entry.repeat),
      platform,
      raw,
      overridden,
    };
  });
}

/** [{ combo, ids, contexts }]: two commands on one key where both can fire. */
export function findCollisions(entries, platform = entries[0]?.platform ?? "other") {
  const byKey = new Map();
  for (const entry of entries) {
    for (const raw of entry.raw) {
      const combo = canonicalCombo(raw, platform);
      if (!combo) continue;
      if (!byKey.has(combo)) byKey.set(combo, []);
      byKey.get(combo).push(entry);
    }
  }
  const found = [];
  for (const [combo, list] of byKey) {
    const clashing = new Set();
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        if (list[i].id === list[j].id) continue;
        if (!contextsOverlap(list[i].context, list[j].context)) continue;
        clashing.add(list[i]);
        clashing.add(list[j]);
      }
    }
    if (clashing.size > 0) {
      found.push({
        combo,
        ids: [...clashing].map((e) => e.id),
        contexts: [...new Set([...clashing].map((e) => e.context))],
      });
    }
  }
  return found;
}

/**
 * Check an override file against the defaults.
 * -> { accepted, problems: [{ id, code, combo?, with? }] }
 * codes: not-object, unknown-command, bad-value, malformed-combo, collision.
 * `accepted` holds only the clean entries; colliding ones are dropped (and the
 * check repeated, since dropping one can free another).
 */
export function validateOverrides(file, defaults, platform = "other") {
  if (file === null || typeof file !== "object" || Array.isArray(file)) {
    return { accepted: {}, problems: [{ id: null, code: "not-object" }] };
  }
  const known = new Set(defaults.map((entry) => entry.id));
  const problems = [];
  const accepted = {};
  for (const [id, value] of Object.entries(file)) {
    if (!known.has(id)) {
      problems.push({ id, code: "unknown-command" });
      continue;
    }
    const isCombo = (v) => typeof v === "string";
    if (!(value === null || isCombo(value) || (Array.isArray(value) && value.every(isCombo)))) {
      problems.push({ id, code: "bad-value" });
      continue;
    }
    const bad = asList(value).find((combo) => parseCombo(combo) === null);
    if (bad !== undefined) {
      problems.push({ id, code: "malformed-combo", combo: bad });
      continue;
    }
    accepted[id] = value;
  }
  for (;;) {
    const collisions = findCollisions(resolveKeymap(defaults, accepted, platform), platform);
    const dropped = new Set();
    for (const collision of collisions) {
      for (const id of collision.ids) {
        if (!Object.hasOwn(accepted, id) || dropped.has(id)) continue;
        dropped.add(id);
        problems.push({
          id,
          code: "collision",
          combo: collision.combo,
          with: collision.ids.filter((other) => other !== id),
        });
      }
    }
    if (dropped.size === 0) break;
    for (const id of dropped) delete accepted[id];
  }
  return { accepted, problems };
}

// -- storage and files ----------------------------------------------------------------

/** Overrides from localStorage; any failure (blocked, garbage) is "no overrides". */
export function loadOverrides(storage = safeStorage()) {
  try {
    const parsed = JSON.parse(storage?.getItem(STORAGE_KEY) ?? "null");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

/** Returns whether it was stored. An empty set removes the key. */
export function saveOverrides(storage, overrides) {
  try {
    if (Object.keys(overrides).length === 0) storage.removeItem(STORAGE_KEY);
    else storage.setItem(STORAGE_KEY, JSON.stringify(overrides));
    return true;
  } catch {
    return false;
  }
}

export function safeStorage() {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export const serializeOverrides = (overrides) => `${JSON.stringify(overrides, null, 2)}\n`;

export function parseOverrideText(text) {
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch (error) {
    return { ok: false, error: String(error?.message ?? error) };
  }
}

// -- showing keys -------------------------------------------------------------------------

const MAC_GLYPH = { ctrl: "⌃", alt: "⌥", shift: "⇧", mod: "⌘" };
const ORDER = ["ctrl", "alt", "shift", "mod"];

/**
 * A combo as the user reads it: "⇧⌘Z" on a Mac (Apple's order), "Ctrl+Shift+Z" elsewhere,
 * named keys in the UI language.
 */
export function formatCombo(text, platform = "other") {
  const p = parseCombo(text);
  if (!p) return String(text);
  const mac = platform === "mac";
  const flags = { ctrl: mac && p.ctrl, alt: p.alt, shift: p.shift, mod: p.mod || (!mac && p.ctrl) };
  const mods = (mac ? ORDER : ["mod", "alt", "shift"]).filter((m) => flags[m]);
  if (mac) return mods.map((m) => MAC_GLYPH[m]).join("") + keyName(p.key, platform);
  const names = mods.map((m) => keyName(m === "mod" ? "Mod" : capitalise(m), platform));
  return [...names, keyName(p.key, platform)].join("+");
}
const capitalise = (word) => word[0].toUpperCase() + word.slice(1);
