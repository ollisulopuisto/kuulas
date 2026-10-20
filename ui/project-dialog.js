// File > New project… / Open project… in a plain browser (WP74): a small dialog with a path
// field. (The desktop window uses its native dialogs instead; see app.js.) The checks are pure
// (project-name.js); the server makes the project and opens it in a new tab.

import { enhanceDialog } from "./dialog-keys.js";
import { newProjectRequest, openProjectRequest } from "./project-name.js";

/**
 * `api`: { newProject(body), openProject(body) } -> Promise<{ path }>; `t` translates;
 * `onDone(path)` is told after the server started the new tab. Returns { element, open(kind) }
 * with kind "new" or "open".
 */
export function createProjectDialog({ api, t, onDone }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet automix-dialog";
  dialog.setAttribute("aria-labelledby", "project-dialog-title");

  const heading = document.createElement("h2");
  heading.id = "project-dialog-title";
  const note = document.createElement("p");
  note.className = "automix-note";
  note.textContent = t("ui.project.note");
  const error = document.createElement("p");
  error.className = "automix-error";
  error.setAttribute("role", "alert");
  error.hidden = true;

  const fields = {};
  const field = (name, labelKey) => {
    const label = document.createElement("label");
    label.className = "automix-field";
    const text = document.createElement("span");
    text.textContent = t(labelKey);
    const input = document.createElement("input");
    input.type = "text";
    input.name = name;
    input.autocomplete = "off";
    input.spellcheck = false;
    label.append(text, input);
    fields[name] = { label, input };
    return label;
  };
  const form = document.createElement("form");
  form.method = "dialog";
  const buttons = document.createElement("div");
  buttons.className = "cheatsheet-footer";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "button block";
  cancel.textContent = t("ui.project.cancel");
  cancel.addEventListener("click", () => dialog.close());
  const go = document.createElement("button");
  go.type = "submit";
  go.className = "button block primary";
  cancel.dataset.dialogCancel = "";
  go.dataset.dialogPrimary = "";
  buttons.append(cancel, go);
  form.append(
    field("name", "ui.project.name"),
    field("parent", "ui.project.parent"),
    field("path", "ui.project.path"),
    error,
    buttons,
  );
  dialog.append(heading, note, form);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  let kind = "new";
  const fail = (message, name) => {
    error.textContent = message;
    error.hidden = false;
    fields[name]?.input.focus();
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const request =
      kind === "new"
        ? newProjectRequest({ parent: fields.parent.input.value, name: fields.name.input.value })
        : openProjectRequest(fields.path.input.value);
    if (!request.ok) {
      fail(t(request.key), request.field);
      return;
    }
    try {
      const { path } = await (kind === "new"
        ? api.newProject(request.body)
        : api.openProject(request.body));
      dialog.close();
      onDone(path);
    } catch (e) {
      fail(e.message, kind === "new" ? "name" : "path");
    }
  });

  return {
    element: dialog,
    open(which) {
      kind = which;
      heading.textContent = t(which === "new" ? "ui.project.new_title" : "ui.project.open_title");
      go.textContent = t(which === "new" ? "ui.project.create" : "ui.project.open");
      fields.name.label.hidden = which !== "new";
      fields.parent.label.hidden = which !== "new";
      fields.path.label.hidden = which !== "open";
      error.hidden = true;
      if (!dialog.open) dialog.showModal();
      (which === "new" ? fields.name : fields.path).input.focus();
    },
  };
}
