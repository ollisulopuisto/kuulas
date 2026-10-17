// Key dispatch. A small map from key presses to actions; WP5 adds the rest of
// the Hindenburg keymap with `keymap.bind(...)` and does not touch this file's
// core. Only these keys are bound here: Space, Esc, Z / Shift+Z / Alt+Z,
// = and -, F6.
//
// Keys are matched by `code` (the key's position) where the layout does not
// change the meaning: Alt+Z is "Ω" on a Mac, and Z stays Z on a Dvorak board.
// Zoom keys match what the key prints, because "+" and "-" sit on different
// keys on a Finnish layout than on a US one.

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

/** Is the focus in something the user types text into? Space and letters belong to it then. */
export function isTextField(target) {
  if (!target) return false;
  if (target.isContentEditable) return true;
  const tag = String(target.tagName ?? "").toUpperCase();
  if (tag === "TEXTAREA") return true;
  if (tag !== "INPUT") return false;
  return !TYPING_INPUTS.has(String(target.type ?? "text").toLowerCase());
}

/**
 * A binding: { code | key | match, shift?, alt?, mod?, inText?, repeat?, run }.
 * Modifiers not named must be up. `inText` lets it fire in a text field (Esc, F6);
 * `repeat` lets a held key fire again (zoom).
 */
function matches(binding, event) {
  if (Boolean(binding.shift) !== Boolean(event.shiftKey)) return false;
  if (Boolean(binding.alt) !== Boolean(event.altKey)) return false;
  if (Boolean(binding.mod) !== Boolean(event.ctrlKey || event.metaKey)) return false;
  if (binding.match) return binding.match(event);
  if (binding.code) return event.code === binding.code;
  return binding.key !== undefined && event.key === binding.key;
}

export function createKeymap() {
  const bindings = [];
  return {
    bind(binding) {
      bindings.push(binding);
    },
    /** Handle a keydown. Returns true when a binding took it. */
    handle(event) {
      const typing = isTextField(event.target);
      for (const binding of bindings) {
        if (typing && !binding.inText) continue;
        if (!matches(binding, event)) continue;
        event.preventDefault();
        if (event.repeat && !binding.repeat) return true;
        binding.run(event);
        return true;
      }
      return false;
    },
  };
}

// "=" and "+" zoom in; "-" zooms out. On a US board "+" is Shift+"=" (code
// "Equal"), which is left to WP5's lane height; on a Finnish board "+" is its
// own key and zooms. `matches` also rules out Alt, Ctrl and Cmd.
const zoomIn = (event) => event.key === "=" || (event.key === "+" && event.code !== "Equal");
const zoomOut = (event) => event.key === "-";

/** The core bindings, wired to `actions` (see app.js). */
export function coreBindings(actions) {
  return [
    { code: "Space", run: () => actions.togglePlay() },
    { code: "Escape", inText: true, run: () => actions.goHome() },
    { code: "F6", inText: true, run: () => actions.cyclePanel(1) },
    { code: "F6", shift: true, inText: true, run: () => actions.cyclePanel(-1) },
    { code: "KeyZ", run: () => actions.toggleView() },
    { code: "KeyZ", shift: true, run: () => actions.fitView() },
    { code: "KeyZ", alt: true, run: () => actions.viewBack() },
    { code: "KeyZ", alt: true, shift: true, run: () => actions.viewForward() },
    { match: zoomIn, repeat: true, run: () => actions.zoomStep(1) },
    { match: zoomOut, repeat: true, run: () => actions.zoomStep(-1) },
  ];
}
