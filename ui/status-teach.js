// Teaching the two-step panel keys in the status bar (owner, 2026-11-17): when Markers or
// Clipboard opens, say what a bare number now does; when a bare number pressed away from its
// panel does nothing, say where numbers act. Both borrow the status bar's menu-hint spot,
// briefly covering the key hints (the Nov 16 tooltip home), and both stop once the
// core-loop row for the pattern has ticked: the user has done it.

const OPEN_HINT = {
  "panel.show_markers": "ui.teach.open_markers",
  "panel.show_clipboard": "ui.teach.open_clipboard",
};

// Panels whose bare digits already act: a dead digit there is no lesson (an empty slot and
// a missing marker say their own thing), and "open the panel first" would be wrong.
const NUMBER_PANELS = ["markers", "clipboard"];

/** Still teaching? The core-loop row ticks when the pattern has really been done. */
export const teaching = (coreLoop) => !coreLoop?.tried?.includes("panelkeys");

/** The message for a command that just ran, or null. */
export function teachForCommand(id, coreLoop) {
  if (!teaching(coreLoop)) return null;
  return OPEN_HINT[id] ?? null;
}

/**
 * The corrective message for a keydown no command took, or null. Only a fresh, bare digit
 * (1-9) outside text fields, modal dialogs and the number panels teaches; a modified,
 * repeated or typing keypress is none of this lesson.
 */
export function teachForDeadDigit(event, coreLoop) {
  if (!teaching(coreLoop)) return null;
  if (event.mod || event.alt || event.shift || event.repeat || event.typing || event.modal)
    return null;
  if (NUMBER_PANELS.includes(event.context)) return null;
  return /^Digit[1-9]$/.test(String(event.code ?? "")) ? "ui.teach.dead_digit" : null;
}

export const TEACH_MS = 5000;

/**
 * Shows a teaching message for TEACH_MS, then brings the key hints back. A menu hint that
 * replaced the message meanwhile is not ours: the timer never clears it.
 */
export function createStatusTeacher({ menuHint, keyhints, t, timers = globalThis }) {
  if (!menuHint) return { show() {}, clear() {}, active: () => false };
  let timer = null;
  let own = null;
  function clear() {
    timers.clearTimeout(timer);
    timer = null;
    if (own !== null && menuHint.textContent === own) {
      menuHint.textContent = "";
      menuHint.hidden = true;
      if (keyhints) keyhints.hidden = false;
    }
    own = null;
  }
  function show(messageKey, values) {
    timers.clearTimeout(timer);
    own = t(messageKey, values);
    menuHint.textContent = own;
    menuHint.hidden = false;
    if (keyhints) keyhints.hidden = true;
    timer = timers.setTimeout(clear, TEACH_MS);
  }
  return { show, clear, active: () => own !== null };
}
