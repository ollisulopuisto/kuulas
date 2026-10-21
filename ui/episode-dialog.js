// File > Series > New episode from series… (docs/design/SERIES.md): a new project with the
// series' tracks and settings. The server makes it (src/kuulas/series_actions.py); the checks
// are series-model.js.

import { enhanceDialog } from "./dialog-keys.js";
import { button, el, row, seriesSelect } from "./series-dialog.js";
import { episodeDefaults, newEpisodeRequest } from "./series-model.js";

/**
 * File > Series > New episode from series…: series, name (the next episode's) and folder
 * (beside this project). `openFolder(path)`: the desktop window opens it in a window of its
 * own; null in a plain browser, where the server starts a tab. Returns { element, open() }.
 */
export function createNewEpisodeDialog({ api, t, openFolder, notify }) {
  const dialog = el("dialog", "cheatsheet automix-dialog series-dialog");
  dialog.setAttribute("aria-labelledby", "episode-title");
  const heading = el("h2", "", t("ui.series.episode_title"));
  heading.id = "episode-title";
  const note = el("p", "form-note", t("ui.series.episode_note"));
  const error = el("p", "form-msg");
  error.setAttribute("role", "alert");
  error.hidden = true;
  const choose = seriesSelect(t);
  const input = () => {
    const field = document.createElement("input");
    field.type = "text";
    field.autocomplete = "off";
    field.spellcheck = false;
    return field;
  };
  const name = input();
  const parent = input();
  const form = el("form", "form-grid");
  form.method = "dialog";
  form.append(
    row(t("ui.series.choose"), choose.select),
    row(t("ui.series.episode_name"), name),
    row(t("ui.series.episode_folder"), parent),
  );
  const cancel = button(t("ui.series.cancel"), () => dialog.close());
  cancel.dataset.icon = "close";
  cancel.dataset.dialogCancel = "";
  const go = el("button", "button block primary", t("ui.series.episode_create"));
  go.type = "submit";
  go.dataset.dialogPrimary = "";
  const footer = el("div", "cheatsheet-footer");
  footer.append(cancel, go);
  form.append(footer);
  dialog.append(heading, note, form, error);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const request = newEpisodeRequest({
      parent: parent.value,
      name: name.value,
      seriesId: choose.select.value,
    });
    if (!request.ok) {
      error.textContent = t(request.key);
      error.hidden = false;
      return;
    }
    try {
      const answer = await api.seriesNewEpisode({ ...request.body, open: !openFolder });
      if (openFolder) await openFolder(answer.path);
      dialog.close();
      notify(t("ui.series.episode_done", { path: answer.path }));
    } catch (e) {
      error.textContent = e.message;
      error.hidden = false;
    }
  });

  return {
    element: dialog,
    async open() {
      error.hidden = true;
      if (!dialog.open) dialog.showModal();
      try {
        const status = await api.seriesStatus(null);
        const defaults = episodeDefaults(status.project);
        choose.fill(status.list, status.link?.id ?? status.list?.[0]?.id ?? "", false);
        name.value = defaults.name;
        parent.value = defaults.parent;
        if (!status.list?.length) {
          error.textContent = t("ui.series.no_series_yet");
          error.hidden = false;
        }
      } catch (e) {
        error.textContent = e.message;
        error.hidden = false;
      }
      name.focus();
      name.select();
    },
  };
}
