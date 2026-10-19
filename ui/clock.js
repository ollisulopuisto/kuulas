// The big play-cursor time in the transport corner (WP76).
//   click          copies the shown time to the system clipboard ("Copied")
//   double-click   an inline field with the time selected; Enter jumps, Esc cancels
//   Enter / Cmd+J  (Spot) the same field from the keyboard
// Typed text is absolute ("1:23.5") or relative ("+100", "-30", "+1:30", "500ms"):
// time-jump.js decides, text that is no time keeps the field open and the cursor where it is.
// The field owns the keys while it has focus: + and - type, they do not zoom.
import { browserRoutes, copyText } from "./copy-text.js";
import { resolveTime } from "./time-jump.js";

/**
 * `el` is the #timecode element. `getState()`, `rate()`, `limit()` (end of the edit, frames),
 * `format(frame, rate)`, `seek(frame)`, `notify(text, kind)`, `t(key, values)`.
 * `routes()` gives the clipboard routes (tests pass fakes).
 */
export function createClock({ el, getState, rate, limit, format, seek, notify, t, routes }) {
  let field = null;
  el.tabIndex = 0;
  el.setAttribute("role", "button");
  el.title = t("ui.clock.tip");

  /** Show the time; while the field is open the field stays (playback keeps ticking). */
  function render(text) {
    if (field) return;
    el.textContent = text;
  }

  /** Copy `text` (the clock's own time unless given) and say so. */
  async function copy(text = el.textContent) {
    const ok = await copyText(text, (routes ?? browserRoutes)());
    notify(
      ok ? t("ui.clock.copied", { time: text }) : t("ui.clock.copy_failed"),
      ok ? "ok" : "error",
    );
  }

  function close(focus) {
    if (!field) return;
    const shown = format(getState().playhead ?? 0, rate());
    field = null;
    el.textContent = shown;
    if (focus) el.focus();
  }

  function open() {
    if (field || !getState().project) return;
    const input = document.createElement("input");
    input.type = "text";
    input.className = "clock-edit";
    input.spellcheck = false;
    input.autocomplete = "off";
    input.setAttribute("aria-label", t("ui.clock.field"));
    input.title = t("ui.clock.edit_hint");
    input.value = el.textContent;
    field = input;
    el.textContent = "";
    el.append(input);
    input.focus();
    input.select();
    input.addEventListener("keydown", (event) => {
      // Typing must not reach the keymap: + and - are zoom keys, digits are commands.
      event.stopPropagation();
      if (event.key === "Enter") {
        event.preventDefault();
        const frame = resolveTime(input.value, {
          from: getState().playhead ?? 0,
          end: limit(),
          rate: rate(),
        });
        if (frame === null) {
          input.setAttribute("aria-invalid", "true");
          notify(t("ui.clock.invalid"), "error");
          return;
        }
        seek(frame);
        close(true);
      } else if (event.key === "Escape") {
        event.preventDefault();
        close(true);
      } else {
        input.removeAttribute("aria-invalid");
      }
    });
    // Clicking away cancels: a jump only happens on Enter.
    input.addEventListener("blur", () => {
      if (field === input) close(false);
    });
  }

  el.addEventListener("click", (event) => {
    // Only the first click of a double-click copies (detail 1); the second opens the field.
    if (field || event.detail > 1) return;
    void copy();
  });
  el.addEventListener("dblclick", (event) => {
    event.preventDefault();
    open();
  });
  el.addEventListener("keydown", (event) => {
    if (field || event.target !== el || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      open();
    }
  });

  return { render, open, copy, editing: () => field !== null };
}
