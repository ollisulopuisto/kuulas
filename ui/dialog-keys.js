// Esc and Enter in every modal dialog (owner, 2026-10-20: "make ESC close all modal windows and
// ENTER accept, so I don't have to click on buttons"). One helper for all of them.
//
// Rules (dialogKeyAction decides, handleDialogKey does):
//  - Only the topmost open dialog hears the key; a second Esc closes the one below.
//  - Esc: cancels the dialog (its own "cancel" event runs first, so a dialog that vetoes it, like the
//    record view, keeps its say). In a text field with unsaved typing, the first Esc only leaves the
//    field ("blur"); the next one cancels. Esc during IME composition does nothing.
//  - Enter: presses the dialog's primary button (data-dialog-primary; the first one that is shown and
//    enabled). It does nothing in a textarea (a new line; Mod+Enter submits), on a focused button
//    (the browser presses that button), in a select, during IME composition, or with Shift/Alt held
//    (reserved). Mod+Enter (Cmd or Ctrl) presses the primary from anywhere, even a textarea or button.
//  - Safe default (dialogs that destroy or upload): Enter means Cancel, Mod+Enter does nothing, and a
//    visible hint says so. The destructive button is only ever pressed by clicking it or by Enter on
//    it when focused (rulebook: destructive buttons are never the default).
// Buttons are marked data-dialog-primary / data-dialog-cancel, never guessed by their text.

/** Which kind of control has the focus: "text", "textarea", "select", "button" or "none". */
export function fieldKind(target) {
  const tag = (target?.tagName ?? "").toLowerCase();
  if (tag === "textarea" || target?.isContentEditable) return "textarea";
  if (tag === "select") return "select";
  if (tag === "button" || tag === "a" || tag === "summary") return "button";
  if (tag === "input") {
    const type = (target.type ?? "text").toLowerCase();
    if (["button", "submit", "reset", "image", "file"].includes(type)) return "button";
    // A checkbox or radio has no Enter of its own: it just submits the form.
    if (["checkbox", "radio", "range", "color"].includes(type)) return "none";
    return "text";
  }
  return "none";
}

/**
 * What a key does in a modal dialog: "cancel" | "accept" | "blur" | "none".
 * `event`: { key, shiftKey, altKey, metaKey, ctrlKey, isComposing, defaultPrevented }.
 * `ctx`: { field: fieldKind(), dirty: typed-in field, hasPrimary: an enabled primary is shown,
 * safeDefault: Enter means Cancel }.
 */
export function dialogKeyAction(event, ctx) {
  if (event.isComposing || event.keyCode === 229 || event.defaultPrevented) return "none";
  const mod = Boolean(event.metaKey || event.ctrlKey);
  if (event.key === "Escape") {
    if (mod || event.shiftKey || event.altKey) return "none";
    if ((ctx.field === "text" || ctx.field === "textarea") && ctx.dirty) return "blur";
    return "cancel";
  }
  if (event.key !== "Enter") return "none";
  if (event.shiftKey || event.altKey) return "none";
  const ownsEnter = ["textarea", "button", "select"].includes(ctx.field);
  if (ctx.safeDefault) return mod || ownsEnter ? "none" : "cancel";
  if (!ctx.hasPrimary) return "none";
  if (mod) return "accept";
  return ownsEnter ? "none" : "accept";
}

// -- the stack of open dialogs ------------------------------------------------------------

const stack = [];
const dirty = new WeakSet();
const options = new WeakMap();

/** The open dialogs, oldest first. */
export const openDialogs = () => stack.filter((d) => d.open);
/** The one that hears the keys. */
export const topDialog = () => openDialogs().at(-1) ?? null;

function usable(button) {
  if (button.disabled || button.hidden) return false;
  return !(button.closest?.("[hidden]") ?? null);
}

/** The primary button to press: the first marked one that is shown and enabled. */
export function primaryOf(dialog) {
  return [...dialog.querySelectorAll("[data-dialog-primary]")].find(usable) ?? null;
}

/** Cancel the way Esc does: the dialog's own "cancel" listener may veto, else it closes. */
export function requestCancel(dialog) {
  const event = new Event("cancel", { cancelable: true });
  dialog.dispatchEvent(event);
  if (!event.defaultPrevented && dialog.open) dialog.close();
}

/**
 * Do what a key means for the topmost dialog. Returns the action taken ("none" leaves the event
 * alone). `active` is the focused element.
 */
export function handleDialogKey(event, active = event.target) {
  const dialog = topDialog();
  if (!dialog) return "none";
  const primary = primaryOf(dialog);
  const action = dialogKeyAction(event, {
    field: fieldKind(active),
    dirty: dirty.has(active),
    hasPrimary: primary !== null,
    safeDefault: options.get(dialog)?.safe ?? false,
  });
  if (action === "none") return action;
  event.preventDefault();
  event.stopPropagation();
  if (action === "blur") active.blur();
  else if (action === "cancel") requestCancel(dialog);
  else primary.click();
  return action;
}

/**
 * Listen once on `root` (the window) in the capture phase, before the keymap sees the key. Typing
 * into a field marks it dirty, so the first Esc only leaves it.
 */
export function installDialogKeys(root) {
  root.addEventListener("keydown", (event) => void handleDialogKey(event), true);
  root.addEventListener("input", (event) => void (event.target && dirty.add(event.target)), true);
  root.addEventListener(
    "focusin",
    (event) => void (event.target && dirty.delete(event.target)),
    true,
  );
}

/**
 * Make `dialog` part of the stack and mark its keys. Call once after the dialog is built.
 * `t` translates; `safe: true` makes Enter mean Cancel and shows why. Buttons are found by
 * data-dialog-primary / data-dialog-cancel; a button can be both (a Close-only dialog).
 */
export function enhanceDialog(dialog, { t, safe = false } = {}) {
  options.set(dialog, { safe });
  const show = dialog.showModal.bind(dialog);
  dialog.showModal = () => {
    show();
    const at = stack.indexOf(dialog);
    if (at !== -1) stack.splice(at, 1);
    stack.push(dialog); // the one opened last is on top
  };
  dialog.addEventListener("close", () => {
    const at = stack.indexOf(dialog);
    if (at !== -1) stack.splice(at, 1);
  });
  const cancels = [...dialog.querySelectorAll("[data-dialog-cancel]")];
  const primaries = [...dialog.querySelectorAll("[data-dialog-primary]")];
  const esc = t("key.escape");
  const enter = "↵";
  for (const button of cancels) {
    const hint = safe || primaries.includes(button) ? `${esc} ${enter}` : esc;
    button.dataset.keyHint = hint;
  }
  if (!safe) {
    for (const button of primaries) {
      if (!cancels.includes(button)) button.dataset.keyHint = enter;
    }
  } else {
    const note = document.createElement("p");
    note.className = "dialog-hint";
    note.textContent = t("ui.dialog.safe_hint");
    dialog.querySelector(".cheatsheet-footer")?.before(note);
  }
}
