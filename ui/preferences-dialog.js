// File > Preferences… (Cmd+,): the user's settings in one place, in the form-grid look of the
// automixer dialog. Nothing is stored here: each control hands its change to the setter of the
// original menu command (preferences-model.js applyField), so the same setting stays in its own
// menu and the two always agree. The dialog redraws from the live values every time it opens.

import { enhanceDialog } from "./dialog-keys.js";
import {
  applyField,
  currentValues,
  PREFERENCE_FIELDS,
  PREFERENCE_LINKS,
} from "./preferences-model.js";

const make = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/**
 * `t` translates; `read()` -> { state, record } (what currentValues reads); `setters` as in
 * applyField; `run(command)` runs a command by id (the link buttons); `canRun(command)` says
 * whether it applies now. Returns { element, open(), refresh() }.
 */
export function createPreferencesDialog({ t, read, setters, run, canRun }) {
  const dialog = make("dialog", "cheatsheet automix-dialog");
  dialog.setAttribute("aria-labelledby", "prefs-title");
  const title = make("h2", "", t("ui.prefs.title"));
  title.id = "prefs-title";
  const form = make("form");
  form.method = "dialog";
  const grid = make("div", "automix-section");
  const more = make("div", "automix-section");
  const footer = make("div", "cheatsheet-footer");
  const close = make("button", "button block primary", t("ui.prefs.close"));
  close.type = "button";
  close.dataset.icon = "check";
  close.addEventListener("click", () => dialog.close());
  close.dataset.dialogCancel = "";
  close.dataset.dialogPrimary = "";
  footer.append(close);
  form.append(grid, more, footer);
  dialog.append(title, form);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    dialog.close();
  });
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  const controls = new Map();
  const linkButtons = [];

  function build() {
    title.textContent = t("ui.prefs.title");
    close.textContent = t("ui.prefs.close");
    controls.clear();
    linkButtons.length = 0;
    grid.replaceChildren();
    for (const field of PREFERENCE_FIELDS) {
      const row = make("label", "automix-row");
      row.append(make("span", "automix-label", t(field.labelKey)));
      const cell = make("span", "automix-cell");
      let control;
      if (field.kind === "choice") {
        control = make("select");
        for (const option of field.options) {
          control.append(new Option(t(option.labelKey, option.params), option.value));
        }
      } else if (field.kind === "switch") {
        control = make("input");
        control.type = "checkbox";
      } else {
        control = make("input");
        control.type = "range";
        control.min = String(field.min);
        control.max = String(field.max);
        control.step = String(field.step);
      }
      control.name = field.id;
      const readout = field.kind === "range" ? make("output", "automix-note") : null;
      control.addEventListener("change", () => {
        const value = field.kind === "switch" ? control.checked : control.value;
        const { state, record } = read();
        applyField(field.id, value, currentValues(state, record), setters);
        refresh();
      });
      if (readout) {
        control.addEventListener("input", () => {
          readout.textContent = `${control.value}${field.unit === "s" ? " s" : "×"}`;
        });
      }
      cell.append(control);
      if (readout) cell.append(readout);
      row.append(cell);
      grid.append(row);
      controls.set(field.id, { field, control, readout });
    }
    more.replaceChildren(make("h3", "automix-heading", t("ui.prefs.more")));
    for (const link of PREFERENCE_LINKS) {
      const button = make("button", "button block", t(link.labelKey));
      button.type = "button";
      button.addEventListener("click", () => {
        dialog.close();
        run(link.command);
      });
      linkButtons.push({ button, command: link.command });
      more.append(button);
    }
  }

  function refresh() {
    const { state, record } = read();
    const values = currentValues(state, record);
    for (const { field, control, readout } of controls.values()) {
      const value = values[field.id];
      if (field.kind === "switch") control.checked = Boolean(value);
      else control.value = String(value);
      if (readout) readout.textContent = `${control.value}${field.unit === "s" ? " s" : "×"}`;
    }
    for (const { button, command } of linkButtons) button.disabled = !canRun(command);
  }

  return {
    element: dialog,
    refresh,
    open() {
      build(); // rebuilt each time: the language may have changed since the last one
      refresh();
      if (!dialog.open) dialog.showModal();
      controls.get("language")?.control.focus();
    },
  };
}
