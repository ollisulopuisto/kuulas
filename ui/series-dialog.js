// File > Series (docs/design/SERIES.md): the Series… dialog (name, choose, leave, save, apply,
// the series music); New episode from series… is episode-dialog.js. The server does the work
// (src/kuulas/series_actions.py); the words and checks are series-model.js.

import { enhanceDialog } from "./dialog-keys.js";
import { sectionsText, seriesSaveRequest } from "./series-model.js";

export function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

export function button(label, onClick, extra = "") {
  const b = el("button", `button block ${extra}`.trim(), label);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

export function row(labelText, control) {
  const label = el("label", "form-row");
  label.append(el("span", "form-label", labelText), control);
  return label;
}

export function seriesSelect(t) {
  const select = document.createElement("select");
  return {
    select,
    fill(list, chosen, withNew) {
      select.replaceChildren();
      if (withNew) {
        const none = document.createElement("option");
        none.value = "";
        none.textContent = t("ui.series.new_series");
        select.append(none);
      }
      for (const item of list ?? []) {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = item.name;
        select.append(option);
      }
      select.value = chosen ?? "";
    },
  };
}

/**
 * `api`: the series calls of api.js; `t` translates; `getAutoSilence()` the page's options now;
 * `onChanged(response)` takes an answer that carries the project (and `settings` after Apply);
 * `notify(text)` says what happened. Returns { element, open() }.
 */
export function createSeriesDialog({ api, t, getAutoSilence, onChanged, notify }) {
  const dialog = el("dialog", "cheatsheet automix-dialog series-dialog");
  dialog.setAttribute("aria-labelledby", "series-title");
  const heading = el("h2", "", t("ui.series.title"));
  heading.id = "series-title";
  const status = el("p", "form-note");
  status.setAttribute("aria-live", "polite");
  const error = el("p", "form-msg");
  error.setAttribute("role", "alert");
  error.hidden = true;

  const name = document.createElement("input");
  name.type = "text";
  name.autocomplete = "off";
  name.spellcheck = false;
  const choose = seriesSelect(t);
  const music = el("p", "form-note");
  const form = el("div", "form-grid");
  form.append(row(t("ui.series.name"), name), row(t("ui.series.choose"), choose.select));

  let current = null;
  const run = async (work) => {
    error.hidden = true;
    try {
      await work();
    } catch (e) {
      error.textContent = e.message;
      error.hidden = false;
    }
  };
  const take = (response) => {
    if (response.project) onChanged(response);
    render(response.series ?? response);
  };

  const save = button(t("ui.series.save"), () =>
    run(async () => {
      const linked = Boolean(current?.link?.id);
      const request = seriesSaveRequest({
        linked,
        name: name.value,
        seriesId: linked ? "" : choose.select.value,
        autoSilence: getAutoSilence(),
      });
      if (!request.ok) throw new Error(t(request.key));
      take(await api.seriesSave(request.body));
      notify(t("ui.series.saved", { name: current?.link?.name ?? "" }));
    }),
  );
  const applyButton = button(t("ui.series.apply"), () =>
    run(async () => {
      take(await api.seriesApply());
      notify(t("ui.series.applied", { name: current?.link?.name ?? "" }));
    }),
  );
  const attach = button(t("ui.series.attach"), () =>
    run(async () => {
      if (!choose.select.value) throw new Error(t("ui.series.need_series"));
      take(await api.seriesAttach(choose.select.value));
    }),
  );
  const rename = button(t("ui.series.rename"), () =>
    run(async () => take(await api.seriesRename(name.value))),
  );
  const detach = button(t("ui.series.detach"), () =>
    run(async () => take(await api.seriesDetach())),
  );
  const close = button(t("ui.series.close"), () => dialog.close(), "primary");
  close.dataset.icon = "close";
  close.dataset.dialogCancel = "";
  close.dataset.dialogPrimary = "";
  const actions = el("div", "series-actions");
  actions.append(save, applyButton, attach, rename, detach);
  const footer = el("div", "cheatsheet-footer");
  footer.append(close);
  dialog.append(heading, status, form, music, actions, error, footer);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  function render(answer) {
    current = answer;
    const link = answer?.link ?? null;
    const linked = Boolean(link?.id);
    if (!linked) status.textContent = t("ui.series.none");
    else if (answer.found === false) status.textContent = t("ui.series.missing");
    else if (answer.differs?.length)
      status.textContent = t("ui.series.status_differs", {
        name: link.name,
        sections: sectionsText(answer.differs, t),
      });
    else status.textContent = t("ui.series.status_same", { name: link.name });
    name.value = linked ? link.name : "";
    choose.fill(answer?.list, linked ? link.id : "", !linked);
    choose.select.disabled = linked;
    music.textContent = linked ? t("ui.series.music_count", { count: answer.music ?? 0 }) : "";
    applyButton.disabled = !linked || answer.found === false;
    attach.hidden = linked;
    rename.hidden = !linked;
    detach.hidden = !linked;
  }

  return {
    element: dialog,
    async open() {
      error.hidden = true;
      if (!dialog.open) dialog.showModal();
      await run(async () => render(await api.seriesStatus(getAutoSilence())));
      (current?.link?.id ? save : name).focus();
    },
  };
}
