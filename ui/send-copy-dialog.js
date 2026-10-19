// File > Send a copy… (WP32): a copy of the project for someone else, with a choice of audio:
// none, the parts that are used (2 s either side, the default), or all of it. The server
// writes it (src/kuulas/send_copy.py); the pure parts are in media-copy-model.js.

import {
  choiceRows,
  DEFAULT_MEDIA_CHOICE,
  MEDIA_CHOICES,
  sendCopyRequest,
} from "./media-copy-model.js";

const KEY = "kuulas.send_copy";

function loadForm(storage = globalThis.localStorage) {
  const form = { folder: "", media: DEFAULT_MEDIA_CHOICE };
  try {
    const stored = JSON.parse(storage.getItem(KEY) ?? "{}") ?? {};
    if (typeof stored.folder === "string") form.folder = stored.folder;
    if (MEDIA_CHOICES.includes(stored.media)) form.media = stored.media;
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
 * `api`: { getSendCopyPlan, sendCopy }; `t` translates; `pickFolder()` -> Promise<string|null>
 * is the desktop window's folder chooser (omit it in a plain browser); `onDone(report)` is
 * called after the copy was written. Returns { element, open() }.
 */
export function createSendCopyDialog({ api, t, pickFolder = null, onDone = () => {} }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet media-dialog";
  dialog.setAttribute("aria-labelledby", "send-copy-title");

  const heading = document.createElement("h2");
  heading.id = "send-copy-title";
  heading.textContent = t("ui.send_copy.title");
  const intro = document.createElement("p");
  intro.className = "media-note";
  intro.textContent = t("ui.send_copy.intro");

  const form = document.createElement("form");
  form.method = "dialog";
  const choices = document.createElement("fieldset");
  const legend = document.createElement("legend");
  legend.textContent = t("ui.send_copy.media");
  choices.append(legend);
  const radios = {};
  const sizes = {};
  for (const id of MEDIA_CHOICES) {
    const label = document.createElement("label");
    label.className = "media-choice";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "media";
    radio.value = id;
    radios[id] = radio;
    const text = document.createElement("span");
    const name = document.createElement("strong");
    name.textContent = t(`ui.send_copy.${id}`, { seconds: 2 });
    const size = document.createElement("span");
    size.className = "media-size";
    sizes[id] = size;
    const hint = document.createElement("span");
    hint.className = "media-note";
    hint.textContent = t(`ui.send_copy.${id}_hint`);
    text.append(name, size, hint);
    label.append(radio, text);
    choices.append(label);
  }

  const folderLabel = document.createElement("label");
  folderLabel.className = "media-field";
  const folderText = document.createElement("span");
  folderText.textContent = t("ui.send_copy.folder");
  const folderInput = document.createElement("input");
  folderInput.type = "text";
  folderInput.name = "folder";
  folderInput.autocomplete = "off";
  folderInput.spellcheck = false;
  folderLabel.append(folderText, folderInput);

  const status = document.createElement("p");
  status.className = "media-note";
  status.setAttribute("aria-live", "polite");
  const error = document.createElement("p");
  error.className = "media-error";
  error.setAttribute("role", "alert");
  error.hidden = true;

  const button = (labelKey, onClick, extra = "", type = "button") => {
    const b = document.createElement("button");
    b.type = type;
    b.className = `button block ${extra}`.trim();
    b.textContent = t(labelKey);
    if (onClick) b.addEventListener("click", onClick);
    return b;
  };
  const choose = pickFolder
    ? button("ui.send_copy.choose", async () => {
        const picked = await pickFolder();
        if (picked) folderInput.value = picked;
      })
    : null;
  const start = button("ui.send_copy.start", null, "primary", "submit");
  const close = button("ui.send_copy.close", () => dialog.close());
  const buttons = document.createElement("div");
  buttons.className = "cheatsheet-footer";
  buttons.append(...(choose ? [choose] : []), close, start);

  form.append(choices, folderLabel, status, error, buttons);
  dialog.append(heading, intro, form);
  document.body.append(dialog);

  const chosen = () => MEDIA_CHOICES.find((id) => radios[id].checked) ?? DEFAULT_MEDIA_CHOICE;
  const showError = (message) => {
    error.textContent = message;
    error.hidden = false;
  };

  function showSizes(plan) {
    for (const row of choiceRows(plan)) {
      sizes[row.id].textContent = row.size
        ? ` (${t("ui.send_copy.size", { size: row.size })})`
        : "";
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const request = sendCopyRequest({ folder: folderInput.value, media: chosen() });
    if (!request.ok) {
      showError(t(request.key));
      folderInput.focus();
      return;
    }
    saveForm(request.body);
    start.disabled = true;
    status.textContent = t("ui.send_copy.working");
    try {
      const report = await api.sendCopy(request.body);
      const offline = report.unavailable ?? [];
      status.textContent = t("ui.send_copy.done", { path: report.path });
      if (offline.length > 0) {
        showError(
          t("ui.send_copy.offline", {
            count: offline.length,
            names: offline.map((m) => m.name).join(", "),
          }),
        );
      }
      onDone(report);
    } catch (e) {
      status.textContent = "";
      showError(e.message);
    } finally {
      start.disabled = false;
    }
  });

  return {
    element: dialog,
    async open() {
      const saved = loadForm();
      radios[saved.media].checked = true;
      folderInput.value = saved.folder;
      status.textContent = "";
      error.hidden = true;
      showSizes(null);
      if (!dialog.open) dialog.showModal();
      folderInput.focus();
      try {
        showSizes(await api.getSendCopyPlan());
      } catch {
        // The sizes are a help: without them the choices still work.
      }
    },
  };
}
