// Track > Auto > "Auto-Silence options…": a modal dialog. The checking and the preview text
// are pure (silence-model.js); this file is the DOM. Preview asks the server for a job that
// changes nothing and lists, per track, what would be closed; Apply hands the options to
// `onApply` (one undo step, made by the caller) and they are remembered per project by the
// caller through `onRemember`.

import { enhanceDialog } from "./dialog-keys.js";
import {
  methodAvailable,
  normaliseSilence,
  previewLines,
  SHOW_METHOD_SELECTOR,
  SILENCE_DEFAULTS,
  SILENCE_RANGES,
  validateSilence,
} from "./silence-model.js";

const POLL_MS = 400;

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/**
 * `api`: { autoSilencePreview, getJobs, cancelJob }; `t` translates; `getProject()` the
 * current project; `getOptions()` the options remembered for it; `onApply(options)` and
 * `onRemember(options)`. Returns { element, open() }.
 */
export function createSilenceDialog({ api, t, getProject, getOptions, onApply, onRemember }) {
  const dialog = el("dialog", "cheatsheet silence-dialog");
  dialog.setAttribute("aria-labelledby", "silence-title");
  const heading = el("h2", "", t("ui.silence.title"));
  heading.id = "silence-title";

  const inputs = {};
  const messages = {};

  const row = (name, labelKey, control, hintKey) => {
    const wrap = el("div", "silence-row");
    const label = el("label", "silence-label", t(labelKey));
    const cell = el("div", "silence-cell");
    const input = control.matches?.("input,select") ? control : control.querySelector("input");
    input.id = `silence-${name}`;
    input.name = name;
    label.htmlFor = input.id;
    const message = el("p", "silence-msg");
    message.id = `silence-${name}-msg`;
    message.hidden = true;
    input.setAttribute("aria-describedby", message.id);
    cell.append(control, message);
    if (hintKey) cell.append(el("p", "silence-hint", t(hintKey)));
    wrap.append(label, cell);
    inputs[name] = input;
    messages[name] = message;
    return wrap;
  };
  const number = () => {
    const input = el("input");
    input.type = "text";
    input.inputMode = "decimal";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.className = "silence-short";
    return input;
  };

  // -- sensitivity: the slider and its value ----------------------------------------------
  const [lowMargin, highMargin] = SILENCE_RANGES.margin_db;
  const slider = el("input");
  slider.type = "range";
  slider.min = String(lowMargin);
  slider.max = String(highMargin);
  slider.step = "1";
  const readout = el("output", "silence-readout");
  const sliderBox = el("div", "silence-inline");
  sliderBox.append(slider, readout);
  const marginRow = row("margin_db", "ui.silence.margin", sliderBox, "ui.silence.margin_hint");
  slider.addEventListener("input", () => {
    readout.textContent = t("ui.silence.margin_value", { db: slider.value });
  });

  const dominance = number();
  const method = el("select");
  for (const value of ["threshold", "compensated"]) {
    const option = el("option", "", t(`ui.silence.method_${value}`));
    option.value = value;
    method.append(option);
  }
  const methodNote = el("p", "silence-hint");

  const section = (titleKey, ...rows) => {
    const wrap = el("section", "silence-section");
    wrap.append(el("h3", "silence-heading", t(titleKey)), ...rows);
    return wrap;
  };
  const sensitivity = section(
    "ui.silence.section_detect",
    marginRow,
    row("dominance_db", "ui.silence.dominance", dominance, "ui.silence.dominance_hint"),
    ...(SHOW_METHOD_SELECTOR ? [row("method", "ui.silence.method", method), methodNote] : []),
  );
  const timing = section(
    "ui.silence.section_timing",
    row("min_closed_s", "ui.silence.min_closed", number(), "ui.silence.min_closed_hint"),
    row("min_open_s", "ui.silence.min_open", number(), "ui.silence.min_open_hint"),
    row("open_before_s", "ui.silence.open_before", number()),
    row("open_after_s", "ui.silence.open_after", number()),
  );

  // -- preview and buttons ----------------------------------------------------------------
  const result = el("div", "silence-preview");
  result.setAttribute("role", "status");
  result.setAttribute("aria-live", "polite");
  const error = el("p", "silence-msg silence-error");
  error.setAttribute("role", "alert");
  error.hidden = true;

  const buttons = el("div", "cheatsheet-footer");
  const reset = el("button", "button block", t("ui.silence.reset"));
  reset.type = "button";
  reset.dataset.icon = "undo";
  const cancel = el("button", "button block", t("ui.silence.cancel"));
  cancel.type = "button";
  cancel.dataset.icon = "close";
  const preview = el("button", "button block", t("ui.silence.preview"));
  preview.type = "button";
  preview.dataset.icon = "play";
  const apply = el("button", "button block primary", t("ui.silence.apply"));
  apply.type = "submit";
  apply.dataset.icon = "check";
  cancel.dataset.dialogCancel = "";
  apply.dataset.dialogPrimary = "";
  buttons.append(reset, cancel, preview, apply);

  const form = el("form");
  form.method = "dialog";
  form.noValidate = true;
  form.append(sensitivity, timing, result, error, buttons);
  dialog.append(heading, form);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  // -- state ------------------------------------------------------------------------------
  let watching = 0; // which preview is being waited for; a newer one or a close ends the old

  const values = () => ({
    ...Object.fromEntries(Object.keys(SILENCE_RANGES).map((name) => [name, inputs[name].value])),
    margin_db: slider.value,
    method: SHOW_METHOD_SELECTOR ? method.value : "threshold",
  });

  function refresh() {
    const { ok, errors } = validateSilence(values());
    for (const name of Object.keys(SILENCE_RANGES)) {
      const key = errors[name];
      messages[name].textContent = key
        ? t(key, { low: SILENCE_RANGES[name][0], high: SILENCE_RANGES[name][1] })
        : "";
      messages[name].hidden = !key;
      inputs[name].setAttribute("aria-invalid", key ? "true" : "false");
    }
    const usable = methodAvailable("compensated", getProject());
    method.querySelector('option[value="compensated"]').disabled = !usable;
    if (!usable && method.value === "compensated") method.value = "threshold";
    methodNote.textContent = t(usable ? "ui.silence.method_hint" : "ui.silence.method_needs_mutes");
    preview.disabled = !ok;
    apply.disabled = !ok;
    return ok;
  }
  form.addEventListener("input", () => {
    watching += 1; // the numbers changed: an old preview no longer answers the question
    result.textContent = "";
    refresh();
  });
  form.addEventListener("change", refresh);

  function fill(options) {
    for (const name of Object.keys(SILENCE_RANGES)) inputs[name].value = String(options[name]);
    slider.value = String(options.margin_db);
    readout.textContent = t("ui.silence.margin_value", { db: slider.value });
    method.value = options.method;
  }
  reset.addEventListener("click", () => {
    fill(SILENCE_DEFAULTS);
    result.textContent = "";
    refresh();
  });
  cancel.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    watching += 1;
  });

  const showError = (message) => {
    error.textContent = message;
    error.hidden = false;
  };

  preview.addEventListener("click", async () => {
    if (!refresh()) return;
    error.hidden = true;
    const { options } = validateSilence(values());
    watching += 1;
    const mine = watching;
    result.textContent = t("ui.silence.previewing");
    try {
      const { jobs } = await api.autoSilencePreview(options);
      const id = jobs[0];
      while (watching === mine) {
        const job = (await api.getJobs()).jobs.find((item) => item.id === id);
        if (!job) break;
        if (job.state === "completed") {
          const lines = previewLines(job.result, t);
          result.replaceChildren(
            ...(lines.length
              ? lines.map((line) => el("p", "silence-line", line))
              : [el("p", "silence-line", t("ui.silence.preview_none"))]),
          );
          return;
        }
        if (job.state === "failed" || job.state === "cancelled") {
          result.textContent = "";
          showError(job.error?.text || t("ui.silence.preview_failed"));
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      }
    } catch (e) {
      result.textContent = "";
      showError(e.message);
    }
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!refresh()) return;
    const { options } = validateSilence(values());
    onRemember(options);
    dialog.close();
    onApply(options);
  });

  return {
    element: dialog,
    open() {
      fill(normaliseSilence(getOptions()));
      result.textContent = "";
      error.hidden = true;
      refresh();
      if (!dialog.open) dialog.showModal();
      slider.focus();
    },
  };
}
