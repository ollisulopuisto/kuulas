// File > Locate media… (WP39): choose a folder, kuulas finds the missing audio files in it
// by SHA-256 and says what it found and what is still missing. The matching is done by the
// server (MediaStore.relink); the pure parts are in media-copy-model.js.

import { enhanceDialog } from "./dialog-keys.js";
import { folderOf, locateSummary } from "./media-copy-model.js";

const KEY = "kuulas.locate.folder";

function remembered(storage = globalThis.localStorage) {
  try {
    return storage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

function remember(folder, storage = globalThis.localStorage) {
  try {
    storage.setItem(KEY, folder);
  } catch {
    // Not remembered; the search still runs.
  }
}

/**
 * `api`: { getMediaStatus, locateMedia }; `t` translates; `pickFolder()` -> Promise<string|null>
 * is the desktop window's folder chooser (omit it in a plain browser: the folder is typed);
 * `onChanged()` is called when files were found, so the page fetches the state again.
 * Returns { element, open() }.
 */
export function createLocateDialog({ api, t, pickFolder = null, onChanged = () => {} }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet media-dialog";
  dialog.setAttribute("aria-labelledby", "locate-title");

  const heading = document.createElement("h2");
  heading.id = "locate-title";
  heading.textContent = t("ui.locate.title");
  const intro = document.createElement("p");
  intro.className = "media-note";
  intro.textContent = t("ui.locate.intro");

  const body = document.createElement("div");
  body.className = "media-body";
  body.setAttribute("aria-live", "polite");

  const folderLabel = document.createElement("label");
  folderLabel.className = "media-field";
  const folderText = document.createElement("span");
  folderText.textContent = t("ui.locate.folder");
  const folderInput = document.createElement("input");
  folderInput.type = "text";
  folderInput.name = "folder";
  folderInput.autocomplete = "off";
  folderInput.spellcheck = false;
  folderLabel.append(folderText, folderInput);

  const error = document.createElement("p");
  error.className = "media-error";
  error.setAttribute("role", "alert");
  error.hidden = true;

  const button = (labelKey, onClick, extra = "") => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `button block ${extra}`.trim();
    b.textContent = t(labelKey);
    b.addEventListener("click", onClick);
    return b;
  };
  const choose = pickFolder
    ? button("ui.locate.choose", async () => {
        const picked = await pickFolder();
        if (picked) folderInput.value = picked;
      })
    : null;
  const find = button("ui.locate.search", () => void search(), "primary");
  const close = button("ui.locate.close", () => dialog.close());
  const buttons = document.createElement("div");
  buttons.className = "cheatsheet-footer";
  close.dataset.dialogCancel = "";
  find.dataset.dialogPrimary = "";
  buttons.append(...(choose ? [choose] : []), find, close);

  dialog.append(heading, intro, body, folderLabel, error, buttons);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  const section = (titleKey, rows, note = null) => {
    const wrap = document.createElement("section");
    wrap.className = "media-group";
    const title = document.createElement("h3");
    title.textContent = t(titleKey);
    const list = document.createElement("ul");
    for (const [name, detail] of rows) {
      const li = document.createElement("li");
      const strong = document.createElement("strong");
      strong.textContent = name;
      li.append(strong);
      if (detail) li.append(document.createTextNode(` ${detail}`));
      list.append(li);
    }
    wrap.append(title);
    if (note) {
      const p = document.createElement("p");
      p.className = "media-note";
      p.textContent = note;
      wrap.append(p);
    }
    wrap.append(list);
    return wrap;
  };

  const partialRows = (partial) =>
    partial.map((p) => [p.name, p.can_complete ? "" : `(${t("ui.locate.partial_stuck")})`]);

  function renderStatus(status) {
    body.replaceChildren();
    const hasWork = status.missing.length > 0 || status.partial.some((p) => p.can_complete);
    find.disabled = !hasWork;
    if (status.missing.length === 0 && status.partial.length === 0) {
      body.textContent = t("ui.locate.nothing");
      return;
    }
    if (status.missing.length > 0) {
      body.append(
        section(
          "ui.locate.missing_title",
          status.missing.map((m) => [m.name, ""]),
        ),
      );
    }
    if (status.partial.length > 0) {
      body.append(
        section(
          "ui.locate.partial_title",
          partialRows(status.partial),
          t("ui.locate.partial_note"),
        ),
      );
    }
  }

  function renderReport(report) {
    body.replaceChildren();
    const summary = locateSummary(report);
    const line = document.createElement("p");
    line.className = "media-summary";
    line.textContent = t(summary.key, summary.values);
    body.append(line);
    if (report.found.length > 0) {
      body.append(
        section(
          "ui.locate.found_title",
          report.found.map((f) => [f.name, f.path]),
        ),
      );
    }
    if (report.still_missing.length > 0) {
      body.append(
        section(
          "ui.locate.still_title",
          report.still_missing.map((m) => [m.name, ""]),
        ),
      );
    }
    if (report.partial.length > 0) {
      body.append(
        section(
          "ui.locate.partial_title",
          partialRows(report.partial),
          t("ui.locate.partial_note"),
        ),
      );
    }
    find.disabled =
      report.still_missing.length === 0 && !report.partial.some((p) => p.can_complete);
  }

  const showError = (message) => {
    error.textContent = message;
    error.hidden = false;
  };

  async function search() {
    error.hidden = true;
    const folder = folderOf(folderInput.value);
    if (folder === null) {
      showError(t("ui.locate.pick_folder"));
      folderInput.focus();
      return;
    }
    remember(folder);
    find.disabled = true;
    body.textContent = t("ui.locate.searching");
    try {
      const report = await api.locateMedia(folder);
      renderReport(report);
      if (report.found.length > 0) onChanged();
    } catch (e) {
      showError(e.message);
      find.disabled = false;
    }
  }

  return {
    element: dialog,
    async open() {
      error.hidden = true;
      body.textContent = t("ui.locate.loading");
      if (!folderInput.value) folderInput.value = remembered();
      if (!dialog.open) dialog.showModal();
      folderInput.focus();
      try {
        renderStatus(await api.getMediaStatus());
      } catch (e) {
        body.textContent = e.message;
      }
    },
  };
}
