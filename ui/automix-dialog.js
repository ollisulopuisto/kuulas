// "Mix with the automixer…" (WP68): a small modal dialog. The form is pure data
// (automix-model.js); this file is the DOM. Start closes the dialog and hands the request
// to `onStart`; the job is followed in the notice area by app.js.

import { automixRequest, DEFAULT_AUTOMIX, formatWords, parseWords } from "./automix-model.js";

const KEY = "kuulas.automix";

function loadForm(storage = globalThis.localStorage) {
  const form = { ...DEFAULT_AUTOMIX };
  try {
    const stored = JSON.parse(storage.getItem(KEY) ?? "{}") ?? {};
    for (const key of Object.keys(form))
      if (typeof stored[key] === "string") form[key] = stored[key];
  } catch {
    // Blocked or damaged: the defaults apply.
  }
  return form;
}

function saveForm(form, storage = globalThis.localStorage) {
  try {
    storage.setItem(KEY, JSON.stringify(form));
  } catch {
    // Not remembered; it still applies to this run.
  }
}

/**
 * `api`: { automixerSettings, saveAutomixerSettings }; `t` translates;
 * `onStart(body)` -> Promise queues the job. Returns { element, open() }.
 */
export function createAutomixDialog({ api, t, onStart }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet automix-dialog";
  dialog.setAttribute("aria-labelledby", "automix-title");

  const heading = document.createElement("h2");
  heading.id = "automix-title";
  heading.textContent = t("ui.automix.title");
  const note = document.createElement("p");
  note.className = "automix-note";
  note.textContent = t("ui.automix.scope_note");
  const error = document.createElement("p");
  error.className = "automix-error";
  error.setAttribute("role", "alert");
  error.hidden = true;

  const fields = {};
  const field = (name, labelKey, hintKey) => {
    const label = document.createElement("label");
    label.className = "automix-field";
    const text = document.createElement("span");
    text.textContent = t(labelKey);
    const input = document.createElement("input");
    input.type = "text";
    input.name = name;
    if (hintKey) input.title = t(hintKey);
    label.append(text, input);
    fields[name] = input;
    return label;
  };
  const form = document.createElement("form");
  form.method = "dialog";
  const settings = document.createElement("fieldset");
  const legend = document.createElement("legend");
  legend.textContent = t("ui.automix.settings");
  settings.append(
    legend,
    field("command", "ui.automix.command", "ui.automix.command_hint"),
    field("cwd", "ui.automix.cwd"),
    field("extra", "ui.automix.extra_args"),
  );
  const buttons = document.createElement("div");
  buttons.className = "cheatsheet-footer";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "button";
  cancel.textContent = t("ui.automix.close");
  cancel.addEventListener("click", () => dialog.close());
  const start = document.createElement("button");
  start.type = "submit";
  start.className = "button primary";
  start.textContent = t("ui.automix.start");
  buttons.append(cancel, start);
  form.append(
    field("targetLufs", "ui.automix.target_lufs"),
    field("adSpot", "ui.automix.ad_spot"),
    field("adDuration", "ui.automix.ad_duration"),
    settings,
    error,
    buttons,
  );
  dialog.append(heading, note, form);
  document.body.append(dialog);

  const showError = (message, name) => {
    error.textContent = message;
    error.hidden = false;
    fields[name]?.focus();
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const values = Object.fromEntries(
      Object.keys(DEFAULT_AUTOMIX).map((key) => [key, fields[key].value]),
    );
    const request = automixRequest(values);
    if (!request.ok) {
      showError(t(request.key), request.field);
      return;
    }
    try {
      const words = parseWords(fields.command.value);
      await api.saveAutomixerSettings({
        command: words.length > 0 ? words : undefined,
        cwd: fields.cwd.value.trim() || undefined,
        extra_args: parseWords(fields.extra.value),
      });
      saveForm(values);
      dialog.close();
      await onStart(request.body);
    } catch (e) {
      showError(e.message, "command");
    }
  });

  return {
    element: dialog,
    async open() {
      const remembered = loadForm();
      for (const key of Object.keys(DEFAULT_AUTOMIX)) fields[key].value = remembered[key];
      error.hidden = true;
      try {
        const { resolved } = await api.automixerSettings();
        fields.command.value = formatWords(resolved.command);
        fields.cwd.value = resolved.cwd ?? "";
        fields.extra.value = formatWords(resolved.extra_args);
      } catch (e) {
        showError(e.message, "command");
      }
      if (!dialog.open) dialog.showModal();
      fields.targetLufs.focus();
    },
  };
}
