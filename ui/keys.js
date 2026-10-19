// Key dispatch. The default keys are data (keymap-default.js), the user's
// overrides are merged over them (keymap-config.js), commands are looked up by
// id in the registry that app.js fills (commands.js). This file turns a
// keydown into one of those commands.
//
// How a key is matched, and why:
//  - Letters, digits and named keys (Space, Enter, arrows, F-keys) by
//    `event.code`, the key's position: Alt+Z is "Ω" on a Mac and Z stays Z on
//    a Dvorak board.
//  - [ ] ` by position too (BracketLeft, BracketRight, Backquote): on a
//    Finnish keyboard they need AltGr/Option, but the Å and ¨ keys sit where
//    the US brackets are. What AltGr/Option types ("[" from Digit8) works too.
//  - = - + ? . , / by what the key prints, because they sit on different keys
//    on a Finnish layout than on a US one. Shift is then part of the character
//    and is not compared.
//  - Mod is Cmd on a Mac and Ctrl elsewhere.
//  - AltGr is not Ctrl+Alt: Windows reports it as both, and the AltGraph
//    modifier tells them apart. An AltGr press only ever matches a symbol it
//    typed, never a letter or a Ctrl/Alt binding.

const TYPING_INPUTS = new Set([
  "button",
  "checkbox",
  "radio",
  "range",
  "color",
  "file",
  "reset",
  "submit",
  "image",
]);

/** Is the focus in something the user types text into (or picks from with the keys)? */
export function isTextField(target) {
  if (!target) return false;
  if (target.isContentEditable) return true;
  const tag = String(target.tagName ?? "").toUpperCase();
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag !== "INPUT") return false;
  return !TYPING_INPUTS.has(String(target.type ?? "text").toLowerCase());
}

/** "mac" or "other". */
export function detectPlatform(nav = globalThis.navigator ?? {}) {
  const platform = nav.userAgentData?.platform ?? nav.platform ?? "";
  return /mac/i.test(platform) ? "mac" : "other";
}

// -- combos --------------------------------------------------------------------------

const MODIFIERS = {
  mod: "mod",
  ctrl: "ctrl",
  control: "ctrl",
  alt: "alt",
  option: "alt",
  shift: "shift",
};
const NAMED = [
  "Space",
  "Enter",
  "Escape",
  "Backspace",
  "Delete",
  "Tab",
  "Comma", // by position, for Mod+Comma (Preferences): the same key on a US and a Finnish board
  "Home",
  "End",
  "PageUp",
  "PageDown",
  "ArrowLeft",
  "ArrowRight",
  "ArrowUp",
  "ArrowDown",
  ...Array.from({ length: 12 }, (_, i) => `F${i + 1}`),
];
const NAMED_BY_LOWER = new Map(NAMED.map((name) => [name.toLowerCase(), name]));
for (const [alias, name] of Object.entries({
  esc: "Escape",
  return: "Enter",
  del: "Delete",
  left: "ArrowLeft",
  right: "ArrowRight",
  up: "ArrowUp",
  down: "ArrowDown",
  pgup: "PageUp",
  pgdn: "PageDown",
})) {
  NAMED_BY_LOWER.set(alias, name);
}
const PHYSICAL = { "[": "BracketLeft", "]": "BracketRight", "`": "Backquote", "\\": "Backslash" };
const CHARS = new Set(["=", "+", "-", "?", ".", ",", "/", ";", "'"]);
// With Alt held, a char key is matched by position: Option+. types "≥" on a Mac.
const CHAR_CODES = { ".": "Period", ",": "Comma" };
const MOD_ORDER = ["ctrl", "alt", "shift", "mod"];

/**
 * "Alt+Mod+ArrowLeft" -> { mod, ctrl, alt, shift, key, kind, code, char } or null when malformed.
 * kind: "code" (matched by position) | "physical" ([ ] ` by position, typed form accepted) | "char".
 * Modifier and key names are case-insensitive; a single letter is upper-cased.
 */
export function parseCombo(text) {
  if (typeof text !== "string") return null;
  const s = text.trim();
  if (!s) return null;
  let keyToken;
  let modTokens;
  if (s === "+") {
    keyToken = "+";
    modTokens = [];
  } else if (s.endsWith("++")) {
    keyToken = "+";
    modTokens = s.slice(0, -2).split("+");
  } else {
    modTokens = s.split("+");
    keyToken = modTokens.pop();
  }
  const mods = { mod: false, ctrl: false, alt: false, shift: false };
  for (const token of keyToken === "+" && s === "+" ? [] : modTokens) {
    const name = MODIFIERS[token.trim().toLowerCase()];
    if (!name || mods[name]) return null;
    mods[name] = true;
  }
  const base = { ...mods, key: "", kind: "code", code: "", char: "" };
  if (keyToken.length === 1) {
    const upper = keyToken.toUpperCase();
    if (/^[A-Z]$/.test(upper)) return { ...base, key: upper, code: `Key${upper}` };
    if (/^[0-9]$/.test(keyToken)) return { ...base, key: keyToken, code: `Digit${keyToken}` };
    if (keyToken in PHYSICAL) {
      return { ...base, key: keyToken, kind: "physical", code: PHYSICAL[keyToken], char: keyToken };
    }
    if (CHARS.has(keyToken)) return { ...base, key: keyToken, kind: "char", char: keyToken };
    return null;
  }
  const named = NAMED_BY_LOWER.get(keyToken.trim().toLowerCase());
  return named ? { ...base, key: named, code: named } : null;
}

/** The same key spelled one way: modifiers in a fixed order, Ctrl folded into Mod off the Mac. */
export function canonicalCombo(text, platform = detectPlatform()) {
  const p = typeof text === "string" ? parseCombo(text) : text;
  if (!p) return null;
  const mac = platform === "mac";
  const flags = {
    ctrl: mac && p.ctrl,
    alt: p.alt,
    // Shift is part of the character for = - + ? . and so on.
    shift: p.kind === "char" ? false : p.shift,
    mod: p.mod || (!mac && p.ctrl),
  };
  return [...MOD_ORDER.filter((m) => flags[m]).map(capitalise), p.key].join("+");
}
const capitalise = (word) => word[0].toUpperCase() + word.slice(1);

/** Does this keydown press this combo? */
export function matchesCombo(event, p, platform = detectPlatform()) {
  const mac = platform === "mac";
  const altGr = Boolean(event.getModifierState?.("AltGraph"));
  // Windows reports AltGr as Ctrl+Alt; it is neither.
  const ctrl = Boolean(event.ctrlKey) && !altGr;
  const meta = Boolean(event.metaKey);
  let alt = Boolean(event.altKey) && !altGr;
  if (!mac && meta) return false;
  const symbolic = p.kind !== "code";
  // "[" typed through AltGr (Windows, Linux) or Option (Mac) from another key.
  const typedSymbol =
    symbolic &&
    event.key === p.char &&
    event.code !== (CHAR_CODES[p.char] ?? p.code) &&
    (altGr || (mac && Boolean(event.altKey)));
  if (altGr && !typedSymbol) return false;
  if (typedSymbol) alt = false;
  const wantMod = p.mod || (!mac && p.ctrl);
  const wantCtrl = mac && p.ctrl;
  if (wantMod !== (mac ? meta : ctrl)) return false;
  if (wantCtrl !== (mac ? ctrl : false)) return false;
  if (p.alt !== alt) return false;
  if (p.kind !== "char" && p.shift !== Boolean(event.shiftKey)) return false;
  if (typedSymbol) return true;
  if (p.kind === "char") {
    if (p.alt && CHAR_CODES[p.char]) return event.code === CHAR_CODES[p.char];
    // US Shift+= types "+", but the key is still the Equal key: lane height, not zoom.
    if (p.char === "+" && event.code === "Equal") return false;
    return event.key === p.char;
  }
  if (!event.code) return String(event.key ?? "").toUpperCase() === p.key.toUpperCase();
  if (p.code === "Enter" && event.code === "NumpadEnter") return true;
  return event.code === p.code;
}

// -- the dispatcher ---------------------------------------------------------------------

/** A legacy ad hoc binding: { code | key | match, shift?, alt?, mod?, inText?, repeat?, run }. */
function legacyMatches(binding, event) {
  if (Boolean(binding.shift) !== Boolean(event.shiftKey)) return false;
  if (Boolean(binding.alt) !== Boolean(event.altKey)) return false;
  if (Boolean(binding.mod) !== Boolean(event.ctrlKey || event.metaKey)) return false;
  if (binding.match) return binding.match(event);
  if (binding.code) return event.code === binding.code;
  return binding.key !== undefined && event.key === binding.key;
}

const EVERYWHERE = new Set(["global", "text-field"]);

/**
 * options: platform; getContext() -> "timeline" | "transcript" | "side" (the focused panel);
 * registry (commands.js); getState() (for each command's `can`).
 * setEntries(resolved) takes the output of resolveKeymap.
 */
export function createKeymap({
  platform = detectPlatform(),
  getContext = () => "timeline",
  registry = null,
  getState = null,
} = {}) {
  const bindings = [];
  let entries = [];
  return {
    platform,
    bind(binding) {
      bindings.push(binding);
    },
    setEntries(resolved) {
      entries = resolved.map((entry) => ({
        ...entry,
        parsed: entry.raw.map(parseCombo).filter(Boolean),
      }));
    },
    /** Handle a keydown. Returns true when a binding took it. */
    handle(event) {
      const typing = isTextField(event.target);
      for (const binding of bindings) {
        if (typing && !binding.inText) continue;
        if (!legacyMatches(binding, event)) continue;
        event.preventDefault();
        if (event.repeat && !binding.repeat) return true;
        binding.run(event);
        return true;
      }
      if (!registry) return false;
      const context = getContext();
      for (const entry of entries) {
        if (typing && entry.context !== "text-field") continue;
        if (entry.context === "not-candidates") {
          if (context === "candidates") continue;
        } else if (entry.context === "not-transcript") {
          if (context === "transcript") continue;
        } else if (entry.context === "not-markers") {
          if (context === "markers") continue;
        } else if (
          !EVERYWHERE.has(entry.context) &&
          entry.context !== context &&
          // The Markers tab is a side panel with keys of its own: the side panels' keys work in it too.
          !(entry.context === "side" && context === "markers")
        )
          continue;
        if (!entry.parsed.some((p) => matchesCombo(event, p, platform))) continue;
        // A planned command is only listed; its key stays the browser's.
        if (registry.status(entry.id) === "planned") continue;
        const state = getState ? getState() : undefined;
        if (state !== undefined && !registry.can(entry.id, state)) continue;
        event.preventDefault();
        if (event.repeat && !entry.repeat) return true;
        registry.run(entry.id, event);
        return true;
      }
      return false;
    },
  };
}
