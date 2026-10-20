// Track > Auto > "Set music level…": a small modal dialog. Opening it starts a measuring job
// on the server (it changes nothing); the result shows the speech level, the beds' loudest
// 3 s and the gain Apply would set, which follows the offset field as it is typed. Apply hands
// { offset_db, measured } to `onApply` (one undo step, made by the caller) and the offset to
// `onRemember` (Preferences). Cancel, Esc or closing stops a measurement still running.
// The numbers and the checking are pure (music-level-model.js); this file is the DOM.

import { enhanceDialog } from "./dialog-keys.js";
import {
  MAX_MUSIC_UNDER_DB,
  MIN_MUSIC_UNDER_DB,
  measureError,
  summaryLines,
  validateMusicUnder,
} from "./music-level-model.js";

const POLL_MS = 400;

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/**
 * `api`: { musicLevelMeasure, getJobs, cancelJob }; `t` translates; `fmt(value)` formats one
 * decimal; `getOffset()` the remembered offset; `onApply({ offset_db, measured })` and
 * `onRemember(offset)`. Returns { element, open() }.
 */
export function createMusicLevelDialog({ api, t, fmt, getOffset, onApply, onRemember }) {
  const dialog = el("dialog", "cheatsheet music-level-dialog");
  dialog.setAttribute("aria-labelledby", "music-level-title");
  const heading = el("h2", "", t("ui.music_level.title"));
  heading.id = "music-level-title";

  const input = el("input", "form-num");
  input.type = "text";
  input.inputMode = "decimal";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.id = "music-level-offset";
  input.name = "offset_db";
  const row = el("div", "form-row");
  const label = el("label", "form-label", t("ui.music_level.offset"));
  label.htmlFor = input.id;
  const cell = el("div", "form-field");
  const message = el("p", "form-msg");
  message.id = "music-level-offset-msg";
  message.hidden = true;
  input.setAttribute("aria-describedby", message.id);
  cell.append(input, message, el("p", "form-help", t("ui.music_level.offset_hint")));
  row.append(label, cell);

  const result = el("div", "form-note music-level-result");
  result.setAttribute("role", "status");
  result.setAttribute("aria-live", "polite");
  const error = el("p", "form-msg");
  error.setAttribute("role", "alert");
  error.hidden = true;

  const buttons = el("div", "cheatsheet-footer");
  const cancel = el("button", "button block", t("ui.music_level.cancel"));
  cancel.type = "button";
  cancel.dataset.icon = "close";
  cancel.dataset.dialogCancel = "";
  const apply = el("button", "button block primary", t("ui.music_level.apply"));
  apply.type = "submit";
  apply.dataset.icon = "check";
  apply.dataset.dialogPrimary = "";
  buttons.append(cancel, apply);

  const form = el("form", "form-grid");
  form.method = "dialog";
  form.noValidate = true;
  form.append(row, result, error, buttons);
  dialog.append(heading, form);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  // -- state ------------------------------------------------------------------------------
  let watching = 0; // which measurement is being waited for; a newer one or a close ends it
  let jobId = null;
  let measured = null;

  function refresh() {
    const { ok, error: key, value } = validateMusicUnder(input.value);
    message.textContent = key ? t(key, { low: MIN_MUSIC_UNDER_DB, high: MAX_MUSIC_UNDER_DB }) : "";
    message.hidden = !key;
    input.setAttribute("aria-invalid", key ? "true" : "false");
    if (measured) {
      const lines = ok ? summaryLines(measured, value, t, fmt) : [];
      result.replaceChildren(...lines.map((line) => el("p", "music-level-line", line)));
    }
    apply.disabled = !(ok && measured && !measureError(measured));
    return ok;
  }
  input.addEventListener("input", refresh);

  const showError = (text) => {
    result.textContent = "";
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
    result.textContent = t("ui.music_level.measuring");
    refresh();
    try {
      const { jobs } = await api.musicLevelMeasure({});
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
          refresh();
          return;
        }
        if (job.state === "failed" || job.state === "cancelled") {
          jobId = null;
          showError(job.error?.text || t("ui.music_level.failed"));
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
    if (!refresh() || apply.disabled) return;
    const { value } = validateMusicUnder(input.value);
    onRemember(value);
    const chosen = measured;
    dialog.close();
    onApply({ offset_db: value, measured: chosen });
  });

  return {
    element: dialog,
    open() {
      input.value = String(getOffset());
      if (!dialog.open) dialog.showModal();
      input.focus();
      input.select();
      void measure();
    },
  };
}
