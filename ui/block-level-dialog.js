// Track > Auto > "Level blocks…": a modal dialog. Opening it starts a measuring job on the
// server (it changes nothing); the result lists, per speaker, the blocks that are off with
// their span, how far off and the gain Apply would add to the clips, each with a tick; the
// very loud spots are listed apart (never changed) with a checkbox for markers. Apply hands
// { measured, skip, markers } to `onApply` (one undo step, made by the caller). Cancel, Esc or
// closing stops a measurement still running. The rows and numbers are pure
// (block-level-model.js); this file is the DOM.

import {
  allChangedIds,
  blockText,
  changedBySpeaker,
  leftAloneCount,
  loudBySpeaker,
  loudText,
  measureError,
  ruleText,
  skipIds,
} from "./block-level-model.js";
import { enhanceDialog } from "./dialog-keys.js";

const POLL_MS = 400;

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/**
 * `api`: { blockLevelMeasure, getJobs, cancelJob }; `t` translates; `fmt(value)` formats one
 * decimal; `clock(seconds)` a position; `onApply({ measured, skip, markers })`.
 * Returns { element, open() }.
 */
export function createBlockLevelDialog({ api, t, fmt, clock, onApply }) {
  const dialog = el("dialog", "cheatsheet block-level-dialog");
  dialog.setAttribute("aria-labelledby", "block-level-title");
  const heading = el("h2", "", t("ui.block_level.title"));
  heading.id = "block-level-title";

  const rule = el("p", "form-note");
  rule.hidden = true;
  const status = el("div", "form-note block-level-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const error = el("p", "form-msg");
  error.setAttribute("role", "alert");
  error.hidden = true;
  const lists = el("div", "form-grid block-level-lists");

  const markersBox = el("input");
  markersBox.type = "checkbox";
  markersBox.id = "block-level-markers";
  markersBox.name = "markers";
  const markersRow = el("label", "check-row");
  markersRow.append(markersBox, el("span", "", t("ui.block_level.markers")));
  markersRow.hidden = true;

  const buttons = el("div", "cheatsheet-footer");
  const cancel = el("button", "button block", t("ui.block_level.cancel"));
  cancel.type = "button";
  cancel.dataset.icon = "close";
  cancel.dataset.dialogCancel = "";
  const apply = el("button", "button block primary", t("ui.block_level.apply"));
  apply.type = "submit";
  apply.dataset.icon = "check";
  apply.dataset.dialogPrimary = "";
  apply.disabled = true;
  buttons.append(cancel, apply);

  const form = el("form", "form-grid");
  form.method = "dialog";
  form.noValidate = true;
  form.append(rule, status, error, lists, markersRow, buttons);
  dialog.append(heading, form);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  // -- state ------------------------------------------------------------------------------
  let watching = 0; // which measurement is being waited for; a newer one or a close ends it
  let jobId = null;
  let measured = null;
  let ticked = new Set();

  const group = (legendText) => {
    const set = el("fieldset", "form-fieldset");
    set.append(el("legend", "form-label", legendText));
    return set;
  };

  function show() {
    lists.replaceChildren();
    const rate = measured.rate;
    const changed = changedBySpeaker(measured);
    rule.textContent = ruleText(measured, t, fmt);
    rule.hidden = false;
    if (changed.length === 0) {
      status.textContent = t("ui.block_level.none");
    } else {
      const left = leftAloneCount(measured);
      status.textContent =
        left > 0
          ? t("ui.block_level.left", { count: left, threshold: fmt(measured.threshold_db) })
          : "";
    }
    for (const speaker of changed) {
      const set = group(speaker.name);
      const choices = el("div", "form-choices");
      for (const row of speaker.rows) {
        const box = el("input");
        box.type = "checkbox";
        box.name = row.id;
        box.checked = ticked.has(row.id);
        box.addEventListener("change", () => {
          if (box.checked) ticked.add(row.id);
          else ticked.delete(row.id);
        });
        const choice = el("label", "form-choice");
        choice.append(box, el("span", "", blockText(row, rate, t, fmt, clock)));
        choices.append(choice);
      }
      set.append(choices);
      lists.append(set);
    }
    const loud = loudBySpeaker(measured);
    if (loud.length > 0) {
      const set = group(t("ui.block_level.loud"));
      const field = el("div", "form-field");
      for (const speaker of loud) {
        for (const spot of speaker.spots) {
          field.append(
            el(
              "p",
              "form-help block-level-line",
              `${speaker.name}, ${loudText(spot, rate, t, fmt, clock)}`,
            ),
          );
        }
      }
      set.append(field);
      lists.append(set);
    }
    markersRow.hidden = loud.length === 0;
    apply.disabled = false;
  }

  const showError = (text) => {
    status.textContent = "";
    error.textContent = text;
    error.hidden = false;
  };

  function stop() {
    watching += 1;
    if (jobId) void api.cancelJob(jobId).catch(() => {});
    jobId = null;
  }
  cancel.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", stop);

  async function measure() {
    stop();
    const mine = watching;
    measured = null;
    error.hidden = true;
    rule.hidden = true;
    lists.replaceChildren();
    markersRow.hidden = true;
    markersBox.checked = false;
    apply.disabled = true;
    status.textContent = t("ui.block_level.measuring");
    try {
      const { jobs } = await api.blockLevelMeasure({});
      jobId = jobs[0];
      while (watching === mine) {
        const job = (await api.getJobs()).jobs.find((item) => item.id === jobId);
        if (!job) break;
        if (job.state === "completed") {
          jobId = null;
          const key = measureError(job.result);
          if (key) {
            showError(t(key));
            return;
          }
          measured = job.result;
          ticked = allChangedIds(measured);
          show();
          return;
        }
        if (job.state === "failed" || job.state === "cancelled") {
          jobId = null;
          showError(job.error?.text || t("ui.block_level.failed"));
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      }
    } catch (e) {
      if (watching === mine) showError(e.message);
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (apply.disabled || !measured) return;
    const chosen = measured;
    const skip = skipIds(chosen, ticked);
    const markers = markersBox.checked;
    dialog.close();
    onApply({ measured: chosen, skip, markers });
  });

  return {
    element: dialog,
    open() {
      if (!dialog.open) dialog.showModal();
      void measure();
    },
  };
}
