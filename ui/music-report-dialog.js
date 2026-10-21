// File > Export > Music report… (WP25): what music this edit plays, for Teosto / Gramex.
// The server builds the report from a snapshot of the edit (GET /api/music-report; it does not
// hold the session lock while it analyses speech), so the dialog stays responsive and shows
// "Building the report…" meanwhile. The rows, summary, warnings and the copied table are pure
// (music-report-model.js); Save CSV / Save HTML are the server's own files, downloaded.

import { enhanceDialog } from "./dialog-keys.js";
import {
  COLUMNS,
  emptyReasonKey,
  headerText,
  previewRows,
  summaryOf,
  toTsv,
  warningsOf,
} from "./music-report-model.js";

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/**
 * `api`: { musicReport }; `t` translates; `getProject()` the open edit (for the empty state's
 * reason); `copyText(text)` copies; `saveFile(format)` downloads the CSV or HTML ("csv" |
 * "html"). Returns { element, open() }; open() asks the server afresh every time.
 */
export function createMusicReportDialog({ api, t, getProject, copyText, saveFile }) {
  const dialog = el("dialog", "cheatsheet music-report-dialog");
  dialog.setAttribute("aria-labelledby", "music-report-title");
  const heading = el("h2", "", t("ui.music_report.title"));
  heading.id = "music-report-title";
  const scope = el("p", "form-note", t("ui.music_report.scope"));
  const status = el("p", "music-report-summary");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const warnings = el("div", "music-report-warnings");
  warnings.hidden = true;
  const error = el("p", "form-msg");
  error.setAttribute("role", "alert");
  error.hidden = true;
  // A focusable scroller, so the keyboard can scroll a long report.
  const scroller = el("div", "music-report-scroll");
  scroller.tabIndex = 0;
  scroller.setAttribute("role", "region");
  scroller.setAttribute("aria-label", t("ui.music_report.table_label"));

  const buttons = el("div", "cheatsheet-footer");
  const button = (labelKey, onClick, extra = "") => {
    const b = el("button", `button block ${extra}`.trim(), t(labelKey));
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  };
  let rows = [];
  const copy = button("ui.music_report.copy", () => void copyText(toTsv(rows, t)));
  const saveCsv = button("ui.music_report.save_csv", () => void saveFile("csv"));
  const saveHtml = button("ui.music_report.save_html", () => void saveFile("html"));
  const close = button("ui.music_report.close", () => dialog.close(), "primary");
  copy.dataset.icon = "copy";
  saveCsv.dataset.icon = "save";
  saveHtml.dataset.icon = "save";
  close.dataset.icon = "close";
  close.dataset.dialogCancel = "";
  close.dataset.dialogPrimary = "";
  // Copy and Save keep the dialog open: the left edge; Close (the primary) last.
  for (const b of [copy, saveCsv, saveHtml]) b.classList.add("footer-start");
  buttons.append(copy, saveCsv, saveHtml, close);
  dialog.append(heading, scope, status, warnings, error, scroller, buttons);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  const setEnabled = (on) => {
    for (const b of [copy, saveCsv, saveHtml]) b.disabled = !on;
  };

  function tableOf(items) {
    const table = el("table", "music-report-table");
    const top = table.createTHead().insertRow();
    for (const column of COLUMNS) {
      const th = el("th", column.numeric ? "num" : "", headerText(column.header, t));
      th.scope = "col";
      top.append(th);
    }
    const body = table.createTBody();
    for (const item of items) {
      const tr = body.insertRow();
      if (item.missing) tr.className = "missing";
      item.cells.forEach((text, index) => {
        const cell = tr.insertCell();
        if (COLUMNS[index].numeric) cell.className = "num";
        cell.textContent = text;
      });
    }
    return table;
  }

  function warningsView(list) {
    warnings.replaceChildren();
    warnings.hidden = list.length === 0;
    if (list.length === 0) return;
    warnings.append(
      el("p", "music-report-warn-head", t("ui.music_report.warnings_head", { count: list.length })),
    );
    const ul = el("ul", "music-report-warn-list");
    for (const { order, label, missing } of list) {
      const key = missing.length === 2 ? "both" : missing[0];
      ul.append(el("li", "", t(`ui.music_report.warn_${key}`, { order, label })));
    }
    warnings.append(ul);
  }

  function render(answer) {
    rows = answer.rows ?? [];
    error.hidden = true;
    if (rows.length === 0) {
      status.textContent = t("ui.music_report.empty");
      const why = el("p", "form-note", t(emptyReasonKey(getProject())));
      scroller.replaceChildren(why);
      warningsView([]);
      setEnabled(false);
      return;
    }
    const sum = summaryOf(rows);
    status.textContent = t("ui.music_report.summary", { count: sum.pieces, time: sum.time });
    scroller.replaceChildren(tableOf(previewRows(rows, t)));
    warningsView(warningsOf(rows));
    setEnabled(true);
  }

  // Bumped on every open and close: an answer that arrives after that is dropped.
  let round = 0;
  dialog.addEventListener("close", () => {
    round += 1;
  });

  return {
    element: dialog,
    async open() {
      round += 1;
      const mine = round;
      rows = [];
      status.textContent = t("ui.music_report.loading");
      scroller.replaceChildren();
      warningsView([]);
      error.hidden = true;
      setEnabled(false);
      if (!dialog.open) dialog.showModal();
      close.focus();
      try {
        const answer = await api.musicReport();
        if (mine === round) render(answer);
      } catch (e) {
        if (mine !== round) return;
        status.textContent = "";
        error.textContent = e.message;
        error.hidden = false;
      }
    },
  };
}
