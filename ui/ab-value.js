// Default/custom A/B for one value (owner, 2026-10-18). Double-click a slider
// or numeric field (double-tap on touch, Shift+Enter with the keyboard) to
// flip between the default (0 dB, centre, 0 ms) and the last custom value;
// Alt+double-click resets and forgets. The remembered value is UI state: it
// lives in memory and is lost on reload. Each flip is one edit with the
// field's coalesce key, so flipping back and forth never piles up history.
// Spec: docs/design/GUI-DESIGN.md, "Default/custom toggle".

const EPSILON = 1e-4;
const same = (a, b) => Math.abs(a - b) < EPSILON;

/** Flip: custom -> default (remembering custom); default -> remembered. */
export function toggleValue(value, fallback, stored) {
  if (!same(value, fallback)) return { value: fallback, stored: value, changed: true };
  if (stored === null || stored === undefined) return { value, stored: null, changed: false };
  return { value: stored, stored, changed: true };
}

/** Alt: back to the default, and forget the custom value. */
export function resetValue(value, fallback) {
  return { value: fallback, stored: null, changed: !same(value, fallback) };
}

/** The remembered custom values, by field key (e.g. "clip-gain-<id>"). */
export function createAbStore() {
  const values = new Map();
  return {
    get: (key) => (values.has(key) ? values.get(key) : null),
    set(key, value) {
      if (value === null) values.delete(key);
      else values.set(key, value);
    },
    toggle(key, value, fallback) {
      const result = toggleValue(value, fallback, this.get(key));
      this.set(key, result.stored);
      return result;
    },
    reset(key, value, fallback) {
      const result = resetValue(value, fallback);
      this.set(key, null);
      return result;
    },
  };
}

/** One store for the whole page: the remembered values are page state. */
export const abValues = createAbStore();

/**
 * Wire a slider or numeric input: double-click / double-tap toggles,
 * Alt+double-click resets, Shift+Enter toggles from the keyboard. `read()`
 * gives the model value now, `write(value)` sends it (with the field's
 * coalesce key, so flips are one undo step each and never pile up),
 * `marker(stored)` shows or hides the remembered value on the control.
 */
export function bindToggle(input, { key, fallback, read, write, marker }) {
  const act = (reset) => {
    const result = reset
      ? abValues.reset(key, read(), fallback)
      : abValues.toggle(key, read(), fallback);
    marker?.(abValues.get(key));
    if (result.changed) {
      write(result.value);
      return;
    }
    // Nothing to flip to: a brief flash says "noted, nothing stored".
    input.classList.remove("ab-flash");
    void input.offsetWidth;
    input.classList.add("ab-flash");
  };
  input.addEventListener("dblclick", (event) => {
    event.preventDefault();
    act(event.altKey);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.shiftKey && !event.metaKey && !event.ctrlKey) {
      event.preventDefault();
      act(event.altKey);
    }
  });
  marker?.(abValues.get(key));
}
