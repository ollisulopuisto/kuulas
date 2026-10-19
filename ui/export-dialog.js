// File > Export mix (options)… and Export all tracks (options)… (WP74): a small modal dialog
// asking for the format and whether to choose the folder first. The choices are pure data
// (export-dialog-model.js); this file is the DOM. Export closes the dialog and hands the request
// to `onStart`, which runs the usual export (the folder chooser comes next, in the desktop window).

import { dialogFormats, exportDialogRequest, pickFormat } from "./export-dialog-model.js";

const KEY = "kuulas.exportdialog";

function remembered(storage = globalThis.localStorage) {
  try {
    return JSON.parse(storage.getItem(KEY) ?? "{}") ?? {};
  } catch {
    return {};
  }
}

function remember(what, choice, storage = globalThis.localStorage) {
  try {
    storage.setItem(KEY, JSON.stringify({ ...remembered(storage), [what]: choice }));
  } catch {
    // Not remembered; it still applies to this run.
  }
}

/**
 * `t` translates; `formats()` -> [{ id, label }] the server offers (null until known);
 * `canChooseFolder()` -> whether a native folder chooser exists (the desktop window);
 * `onStart({ what, format, ask })` runs the export. Returns { element, open(what) }.
 */
export function createExportDialog({ t, formats, canChooseFolder, onStart }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet automix-dialog";
  dialog.setAttribute("aria-labelledby", "export-dialog-title");

  const heading = document.createElement("h2");
  heading.id = "export-dialog-title";
  const note = document.createElement("p");
  note.className = "automix-note";

  const form = document.createElement("form");
  form.method = "dialog";
  const formatLabel = document.createElement("label");
  formatLabel.className = "automix-field";
  const formatText = document.createElement("span");
  formatText.textContent = t("ui.exportdialog.format");
  const select = document.createElement("select");
  select.name = "format";
  formatLabel.append(formatText, select);

  const askLabel = document.createElement("label");
  const ask = document.createElement("input");
  ask.type = "checkbox";
  ask.name = "ask";
  const askText = document.createElement("span");
  askText.textContent = ` ${t("ui.exportdialog.ask")}`;
  askLabel.append(ask, askText);

  const buttons = document.createElement("div");
  buttons.className = "cheatsheet-footer";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "button";
  cancel.textContent = t("ui.exportdialog.cancel");
  cancel.addEventListener("click", () => dialog.close());
  const start = document.createElement("button");
  start.type = "submit";
  start.className = "button primary";
  start.textContent = t("ui.exportdialog.start");
  buttons.append(cancel, start);
  form.append(formatLabel, askLabel, buttons);
  dialog.append(heading, note, form);
  document.body.append(dialog);

  let what = "mix";
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const request = exportDialogRequest(what, { format: select.value, ask: ask.checked });
    remember(what, { format: request.format, ask: request.ask });
    dialog.close();
    void onStart(request);
  });

  return {
    element: dialog,
    open(kind) {
      what = kind;
      heading.textContent = t(`ui.exportdialog.${kind}_title`);
      note.textContent = t(`ui.exportdialog.${kind}_note`);
      const list = dialogFormats(formats());
      select.replaceChildren(
        ...list.map((format) => {
          const option = document.createElement("option");
          option.value = format.id;
          option.textContent = format.label;
          return option;
        }),
      );
      const last = remembered()[kind] ?? {};
      select.value = pickFormat(list, last.format);
      const chooser = canChooseFolder();
      askLabel.hidden = !chooser;
      ask.checked = chooser && last.ask !== false;
      if (!dialog.open) dialog.showModal();
      select.focus();
    },
  };
}
