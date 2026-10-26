// File > Import Hindenburg session… in a plain browser: a browser cannot hand the page the path
// of a file, and the session's recordings are found next to it by the server, so the page asks for
// the path. (The desktop window uses its native file dialog instead; see app.js.) The checks are
// pure (nhsx-import.js).
import { enhanceDialog } from "./dialog-keys.js";
import { nhsxRequest } from "./nhsx-import.js";

/** `onPath(path)` is called with a checked path; the dialog closes first. Returns { open }. */
export function createNhsxDialog({ t, onPath }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet automix-dialog";
  dialog.setAttribute("aria-labelledby", "nhsx-dialog-title");
  const heading = document.createElement("h2");
  heading.id = "nhsx-dialog-title";
  heading.textContent = t("ui.nhsx.title");
  const note = document.createElement("p");
  note.className = "form-note";
  note.textContent = t("ui.nhsx.note");
  const error = document.createElement("p");
  error.className = "form-msg";
  error.setAttribute("role", "alert");
  error.hidden = true;

  const form = document.createElement("form");
  form.className = "form-grid";
  form.method = "dialog";
  const label = document.createElement("label");
  label.className = "form-row";
  const text = document.createElement("span");
  text.className = "form-label";
  text.textContent = t("ui.nhsx.path");
  const input = document.createElement("input");
  input.type = "text";
  input.name = "path";
  input.autocomplete = "off";
  input.spellcheck = false;
  label.append(text, input);
  const buttons = document.createElement("div");
  buttons.className = "cheatsheet-footer";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "button block";
  cancel.textContent = t("ui.project.cancel");
  cancel.dataset.icon = "close";
  cancel.dataset.dialogCancel = "";
  cancel.addEventListener("click", () => dialog.close());
  const go = document.createElement("button");
  go.type = "submit";
  go.className = "button block primary";
  go.textContent = t("ui.nhsx.go");
  go.dataset.dialogPrimary = "";
  buttons.append(cancel, go);
  form.append(label, error, buttons);
  dialog.append(heading, note, form);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const request = nhsxRequest(input.value);
    if (!request.ok) {
      error.textContent = t(request.key);
      error.hidden = false;
      input.focus();
      return;
    }
    dialog.close();
    onPath(request.body.path);
  });

  return {
    open() {
      error.hidden = true;
      if (!dialog.open) dialog.showModal();
      input.focus();
      input.select();
    },
  };
}
