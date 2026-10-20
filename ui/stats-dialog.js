import { enhanceDialog } from "./dialog-keys.js";
// File > Statistics… (WP70): a read-only dialog. The server counts and words everything
// (src/kuulas/project_stats.py), in the UI language and with Helsinki times, so this file
// only lays the groups out. "Copy as text" and "Save as JSON" hand over to app.js.

/**
 * `api`: { getStats }; `t` translates; `copyText(text)` and `saveJson()` do the two
 * actions. Returns { element, open() }; open() asks the server afresh every time.
 */
export function createStatsDialog({ api, t, copyText, saveJson }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet stats-dialog";
  dialog.setAttribute("aria-labelledby", "stats-title");

  const heading = document.createElement("h2");
  heading.id = "stats-title";
  heading.textContent = t("ui.stats.title");
  const body = document.createElement("div");
  body.className = "stats-body";
  body.setAttribute("aria-live", "polite");
  const note = document.createElement("p");
  note.className = "stats-note form-note";
  note.textContent = `${t("ui.stats.muted_note")} ${t("ui.stats.no_undo")}`;

  const buttons = document.createElement("div");
  buttons.className = "cheatsheet-footer";
  const button = (labelKey, onClick, extra = "") => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `button block ${extra}`.trim();
    b.textContent = t(labelKey);
    b.addEventListener("click", onClick);
    return b;
  };
  let text = "";
  const copy = button("ui.stats.copy", () => void copyText(text));
  const save = button("ui.stats.save", () => void saveJson());
  const close = button("ui.stats.close", () => dialog.close(), "primary");
  save.dataset.icon = "save";
  close.dataset.icon = "close";
  copy.disabled = true;
  save.disabled = true;
  close.dataset.dialogCancel = "";
  close.dataset.dialogPrimary = "";
  // Copy and Save keep the dialog open: the left edge; Close (the primary) last.
  copy.classList.add("footer-start");
  save.classList.add("footer-start");
  buttons.append(copy, save, close);
  dialog.append(heading, body, note, buttons);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  function listOf(rows) {
    const list = document.createElement("dl");
    for (const [label, value] of rows) {
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      list.append(dt, dd);
    }
    return list;
  }

  // The per-track durations: one row per track, the first column is the row header.
  function tableOf({ head, rows }) {
    const table = document.createElement("table");
    table.className = "stats-table";
    const top = table.createTHead().insertRow();
    for (const text of head) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = text;
      top.append(th);
    }
    const bodyRows = table.createTBody();
    for (const row of rows) {
      const tr = bodyRows.insertRow();
      row.forEach((text, index) => {
        const cell = document.createElement(index === 0 ? "th" : "td");
        if (index === 0) cell.scope = "row";
        cell.textContent = text;
        tr.append(cell);
      });
    }
    return table;
  }

  function render(groups) {
    body.replaceChildren();
    for (const group of groups) {
      const section = document.createElement("section");
      section.className = "stats-group";
      const title = document.createElement("h3");
      title.textContent = group.title;
      section.append(title);
      if (group.table) section.append(tableOf(group.table));
      if (group.rows.length) section.append(listOf(group.rows));
      body.append(section);
    }
  }

  return {
    element: dialog,
    async open() {
      body.textContent = t("ui.stats.loading");
      copy.disabled = true;
      save.disabled = true;
      if (!dialog.open) dialog.showModal();
      close.focus();
      try {
        const answer = await api.getStats();
        text = answer.text;
        render(answer.groups);
        copy.disabled = false;
        save.disabled = false;
      } catch (e) {
        body.textContent = e.message;
      }
    },
  };
}
