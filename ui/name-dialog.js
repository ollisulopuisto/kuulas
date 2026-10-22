// Shift+Mod+S asks for the name of a saved version: one text field, Save and Cancel. Enter
// saves and Esc cancels (dialog-keys.js). A name left empty counts as cancelled.

import { enhanceDialog } from "./dialog-keys.js";

/**
 * `t` translates. Returns { element, ask(suggestion) -> Promise<string | null> }: the typed
 * name, or null when the dialog was cancelled.
 */
export function createNameDialog({ t }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet automix-dialog";
  dialog.setAttribute("aria-labelledby", "name-dialog-title");

  const heading = document.createElement("h2");
  heading.id = "name-dialog-title";
  heading.textContent = t("ui.save.name_title");
  const note = document.createElement("p");
  note.className = "form-note";
  note.textContent = t("ui.save.name_note");

  const label = document.createElement("label");
  label.className = "form-row";
  const text = document.createElement("span");
  text.className = "form-label";
  text.textContent = t("ui.save.name_label");
  const input = document.createElement("input");
  input.type = "text";
  input.name = "name";
  input.autocomplete = "off";
  input.spellcheck = false;
  label.append(text, input);

  const form = document.createElement("form");
  form.className = "form-grid";
  form.method = "dialog";
  const buttons = document.createElement("div");
  buttons.className = "cheatsheet-footer";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "button block";
  cancel.textContent = t("ui.save.name_cancel");
  cancel.dataset.icon = "close";
  cancel.dataset.dialogCancel = "";
  const save = document.createElement("button");
  save.type = "submit";
  save.className = "button block primary";
  save.textContent = t("ui.save.name_ok");
  save.dataset.dialogPrimary = "";
  buttons.append(cancel, save);
  form.append(label, buttons);
  dialog.append(heading, note, form);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  let answer = null;
  let finish = () => {};
  cancel.addEventListener("click", () => dialog.close());
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    answer = input.value.trim() || null;
    dialog.close();
  });
  // Esc, Cancel, the form and a second ask all end here; the promise settles once.
  dialog.addEventListener("close", () => {
    const done = finish;
    finish = () => {};
    done(answer);
  });

  return {
    element: dialog,
    ask(suggestion) {
      finish(null);
      return new Promise((resolve) => {
        answer = null;
        finish = resolve;
        // Said again each time: the language may have changed since the dialog was made.
        heading.textContent = t("ui.save.name_title");
        note.textContent = t("ui.save.name_note");
        text.textContent = t("ui.save.name_label");
        cancel.textContent = t("ui.save.name_cancel");
        save.textContent = t("ui.save.name_ok");
        input.value = suggestion;
        if (!dialog.open) dialog.showModal();
        input.focus();
        input.select();
      });
    },
  };
}
