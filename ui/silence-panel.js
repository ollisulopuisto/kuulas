// Track > Auto > "Auto-Silence options…": the live preview panel (owner, 2026-10-21: "you set
// the value, see what parts get silenced, then listen to them"). Not a modal: it docks over the
// sidebar's panels the way Help does, so the lanes, the transcript and the transport stay
// visible and clickable. The sidebar is the one place that never covers a lane and is there at
// the app's minimum window size (900 x 600); a strip over the bottom would take the transcript's
// height, which the smallest window cannot spare. The pure part is silence-panel-model.js; the
// values and their checking are silence-model.js.
//
// The flow: open measures the speech once (a job with progress and Cancel; reused while the
// speech audio is unchanged), then every control change asks the server for the closed ranges
// (debounced, older answers dropped). The server decides them in milliseconds and the engine
// plays them as a listening overlay; the timeline draws them as the preview. Nothing is
// committed until Accept (one undo step). Close, Cancel or Esc discards it.

import {
  methodAvailable,
  normaliseSilence,
  SHOW_METHOD_SELECTOR,
  SILENCE_DEFAULTS,
  SILENCE_RANGES,
  validateSilence,
} from "./silence-model.js";
import {
  createDebouncer,
  createLatest,
  createSeq,
  DEBOUNCE_MS,
  jobProgress,
  overlayFrom,
  panelControls,
  summaryLines,
} from "./silence-panel-model.js";

const POLL_MS = 300;

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

// The panel's actions are normal-height buttons, not the 76 px blocks of the other panels: four
// squares wrapped to two rows in the narrow sidebar (owner, 2026-10-21).
const actionButton = (labelKey, icon, t, primary = false) => {
  const button = el("button", primary ? "button primary" : "button", t(labelKey));
  button.type = "button";
  button.dataset.icon = icon;
  return button;
};

/**
 * `root`: the sidebar section to fill. `api`: { silenceMeasure, silenceRanges, silenceAccept,
 * silenceClose, getJobs, cancelJob }. `setPreview(map | null)` hands the ranges to the
 * timeline. `isPlaying()` / `togglePlay()` are the transport's (Listen is Play from the
 * playhead, with the overlay on). `onAccepted(response, options)` applies the state the server
 * answered. Returns { open, close, isOpen, projectChanged, playingChanged }.
 */
export function createSilencePanel({
  root,
  api,
  t,
  getProject,
  getOptions,
  onRemember,
  onAccepted,
  setPreview,
  isPlaying,
  togglePlay,
  hideSidebar,
}) {
  root.classList.add("panel", "silence-panel");
  root.setAttribute("role", "region");
  root.setAttribute("aria-labelledby", "silence-panel-title");
  root.tabIndex = -1;

  // -- head and action bar ------------------------------------------------------------------
  const head = el("div", "silence-head");
  const title = el("h2", "", t("ui.silence.title"));
  title.id = "silence-panel-title";
  // Hides the whole side panel too (the timeline gets the width); the preview is discarded.
  const hidePanel = el("button", "button ghost icon silence-close");
  hidePanel.type = "button";
  hidePanel.dataset.icon = "close";
  hidePanel.setAttribute("aria-label", t("ui.sidebar.close"));
  hidePanel.title = t("ui.sidebar.close");
  head.append(title, hidePanel);

  const listen = actionButton("ui.silence.listen", "play", t);
  listen.title = t("ui.silence.listen_hint");
  const reset = actionButton("ui.silence.reset", "undo", t);
  const close = actionButton("ui.silence.close", "close", t);
  const accept = actionButton("ui.silence.accept", "check", t, true);
  accept.title = t("ui.silence.accept_hint");
  const bar = el("div", "actionbar");
  bar.setAttribute("role", "group");
  bar.setAttribute("aria-label", t("ui.silence.title"));
  // The primary last (BUTTONS.md).
  bar.append(listen, reset, close, accept);

  // -- measuring ----------------------------------------------------------------------------
  const measuring = el("div", "silence-measuring form-grid");
  const progressLabel = el("p", "form-note", t("ui.silence.measuring"));
  progressLabel.id = "silence-progress-label";
  const progress = el("progress", "silence-progress");
  progress.max = 1;
  progress.value = 0;
  progress.setAttribute("aria-labelledby", progressLabel.id);
  const progressText = el("p", "form-help");
  const cancelMeasure = el("button", "button", t("ui.silence.cancel_measure"));
  cancelMeasure.type = "button";
  cancelMeasure.dataset.icon = "close";
  const progressLine = el("div", "form-inline");
  progressLine.append(progress, cancelMeasure);
  measuring.append(progressLabel, progressLine, progressText);

  // -- the form -----------------------------------------------------------------------------
  const inputs = {};
  const sliders = {};
  const messages = {};
  const row = (name, labelKey, control, hintKey) => {
    const wrap = el("div", "form-row");
    const label = el("label", "form-label", t(labelKey));
    const cell = el("div", "form-field");
    const input = control.matches?.("input,select") ? control : control.querySelector(".form-num");
    input.id = `silence-panel-${name}`;
    input.name = name;
    label.htmlFor = input.id;
    const message = el("p", "form-msg");
    message.id = `silence-panel-${name}-msg`;
    message.hidden = true;
    input.setAttribute("aria-describedby", message.id);
    cell.append(control, message);
    if (hintKey) cell.append(el("p", "form-help", t(hintKey)));
    wrap.append(label, cell);
    inputs[name] = input;
    messages[name] = message;
    return wrap;
  };
  const number = () => {
    const input = el("input", "form-num");
    input.type = "text";
    input.inputMode = "decimal";
    input.autocomplete = "off";
    input.spellcheck = false;
    return input;
  };
  /**
   * A slider and its number field, kept equal: the slider to drag, the field to type. Label and
   * a small number on one line, the slider on its own line at the panel's full width, then the
   * help (owner, 2026-10-21: "input field smaller, slider bigger, maybe on different lines").
   */
  const sliderRow = (name, labelKey, step, hintKey) => {
    const [low, high] = SILENCE_RANGES[name];
    const slider = el("input");
    slider.type = "range";
    slider.min = String(low);
    slider.max = String(high);
    slider.step = String(step);
    slider.setAttribute("aria-label", t(`ui.silence.${name}_slider`));
    const field = number();
    field.id = `silence-panel-${name}`;
    field.name = name;
    const wrap = el("div", "form-row silence-slider-row");
    const label = el("label", "form-label", t(labelKey));
    label.htmlFor = field.id;
    const message = el("p", "form-msg");
    message.id = `silence-panel-${name}-msg`;
    message.hidden = true;
    field.setAttribute("aria-describedby", message.id);
    const cell = el("div", "form-field");
    cell.append(field, message);
    const help = el("p", "form-help", t(hintKey));
    wrap.append(label, cell, slider, help);
    inputs[name] = field;
    messages[name] = message;
    sliders[name] = slider;
    // The form's own input listener asks again (both events bubble to it).
    slider.addEventListener("input", () => {
      field.value = slider.value;
    });
    field.addEventListener("input", () => {
      const { options, errors } = validateSilence({ ...values(), [name]: field.value });
      if (!errors[name]) slider.value = String(options[name]);
    });
    return wrap;
  };

  const method = el("select");
  for (const value of ["threshold", "compensated"]) {
    const option = el("option", "", t(`ui.silence.method_${value}`));
    option.value = value;
    method.append(option);
  }
  const methodNote = el("p", "form-help");

  const section = (titleKey, ...rows) => {
    const wrap = el("section", "form-section");
    wrap.append(el("h3", "form-heading", t(titleKey)), ...rows);
    return wrap;
  };
  const detect = section(
    "ui.silence.section_detect",
    sliderRow("margin_db", "ui.silence.margin", 0.5, "ui.silence.margin_hint"),
    sliderRow("dominance_db", "ui.silence.dominance", 0.5, "ui.silence.dominance_panel_hint"),
  );
  if (SHOW_METHOD_SELECTOR) {
    const methodRow = row("method", "ui.silence.method", method);
    methodRow.lastChild.append(methodNote);
    detect.append(methodRow);
  }
  // The rest, folded: the owner tunes the two above; these are for the odd recording.
  const more = el("details", "silence-more");
  const moreSummary = el("summary", "form-heading", t("ui.silence.more"));
  more.append(
    moreSummary,
    row("min_closed_s", "ui.silence.min_closed", number(), "ui.silence.min_closed_hint"),
    row("min_open_s", "ui.silence.min_open", number(), "ui.silence.min_open_hint"),
    row("open_before_s", "ui.silence.open_before", number()),
    row("open_after_s", "ui.silence.open_after", number()),
  );

  const form = el("form", "form-grid silence-form");
  form.noValidate = true;
  form.addEventListener("submit", (event) => event.preventDefault());
  form.append(detect, more);

  // -- the summary --------------------------------------------------------------------------
  const summary = el("div", "silence-summary");
  summary.setAttribute("role", "status");
  summary.setAttribute("aria-live", "polite");
  const error = el("p", "form-msg silence-error");
  error.setAttribute("role", "alert");
  error.hidden = true;

  root.replaceChildren(head, bar, measuring, form, summary, error);

  // -- state --------------------------------------------------------------------------------
  let open = false;
  let phase = "measuring";
  let jobId = null;
  let key = null;
  let returnFocus = null;
  const latest = createLatest();
  const seq = createSeq();
  const ask = createDebouncer(() => void askRanges(), DEBOUNCE_MS);

  const values = () => ({
    ...Object.fromEntries(Object.keys(SILENCE_RANGES).map((name) => [name, inputs[name].value])),
    method: SHOW_METHOD_SELECTOR ? method.value : "threshold",
  });

  function validate() {
    const result = validateSilence(values());
    for (const name of Object.keys(SILENCE_RANGES)) {
      const messageKey = result.errors[name];
      messages[name].textContent = messageKey
        ? t(messageKey, { low: SILENCE_RANGES[name][0], high: SILENCE_RANGES[name][1] })
        : "";
      messages[name].hidden = !messageKey;
      inputs[name].setAttribute("aria-invalid", messageKey ? "true" : "false");
    }
    return result;
  }

  function sync() {
    const { ok } = validate();
    const state = panelControls({ phase, valid: ok, playing: isPlaying() });
    for (const control of [...Object.values(inputs), ...Object.values(sliders), method]) {
      control.disabled = !state.controls;
    }
    if (SHOW_METHOD_SELECTOR) {
      const usable = methodAvailable("compensated", getProject());
      method.querySelector('option[value="compensated"]').disabled = !usable;
      if (!usable && method.value === "compensated") method.value = "threshold";
      methodNote.textContent = t(
        usable ? "ui.silence.method_hint" : "ui.silence.method_needs_mutes",
      );
    }
    listen.disabled = !state.listen;
    accept.disabled = !state.accept;
    reset.disabled = !state.reset;
    measuring.hidden = !state.progress;
    listen.textContent = t(state.listenKey);
    listen.dataset.icon = isPlaying() ? "stop" : "play";
  }

  function fill(options) {
    for (const name of Object.keys(SILENCE_RANGES)) {
      inputs[name].value = String(options[name]);
      if (sliders[name]) sliders[name].value = String(options[name]);
    }
    method.value = options.method;
  }

  function showError(message) {
    error.textContent = message;
    error.hidden = !message;
  }

  function showRows(rows) {
    const lines = summaryLines(rows, t);
    summary.replaceChildren(
      ...(lines.length
        ? lines.flatMap((line) => {
            const item = el("p", "silence-line", line.text);
            return line.now ? [item, el("p", "silence-line form-help", line.now)] : [item];
          })
        : [el("p", "silence-line", t("ui.silence.preview_none"))]),
    );
  }

  /** The values changed: ask again once they rest. */
  function changed() {
    if (!open || phase === "measuring") return;
    if (!validate().ok) {
      sync();
      return;
    }
    phase = "updating";
    sync();
    ask.call();
  }
  form.addEventListener("input", changed);
  form.addEventListener("change", changed);

  async function askRanges() {
    if (!open) return;
    const { ok, options } = validate();
    if (!ok) return;
    const token = latest.begin();
    try {
      const answer = await api.silenceRanges(options, seq.next());
      if (!open || !latest.isLatest(token)) return;
      key = answer.key;
      phase = "ready";
      showError("");
      showRows(answer.tracks);
      setPreview(overlayFrom(answer.tracks));
    } catch (e) {
      if (!open || !latest.isLatest(token)) return;
      if (e.status === 409) {
        // The speech changed under the measure: measure again, then ask again.
        setPreview(null);
        void measure();
        return;
      }
      phase = "error";
      showError(e.message);
    }
    sync();
  }

  async function measure() {
    phase = "measuring";
    key = null;
    progress.value = 0;
    progressText.textContent = "";
    sync();
    try {
      const answer = await api.silenceMeasure();
      if (!open) return;
      if (!answer.ready) {
        jobId = answer.jobs[0];
        const finished = await waitFor(jobId);
        jobId = null;
        if (!open || !finished) return;
      }
      phase = "updating";
      sync();
      // The Cancel button that had the focus is gone: the first slider takes it, unless the
      // user has gone elsewhere (the timeline) meanwhile.
      const at = document.activeElement;
      if (at === cancelMeasure || at === document.body) sliders.margin_db.focus();
      await askRanges();
    } catch (e) {
      if (!open) return;
      phase = "error";
      showError(e.message);
      sync();
    }
  }

  /** Poll the measuring job; true when it completed. Failure shows its text. */
  async function waitFor(id) {
    while (open && jobId === id) {
      const job = (await api.getJobs()).jobs.find((item) => item.id === id);
      const state = jobProgress(job);
      progress.value = state.fraction;
      progressText.textContent = state.message;
      if (state.done) return true;
      if (state.cancelled) return false;
      if (state.failed) {
        phase = "error";
        showError(job?.error?.text || t("ui.silence.preview_failed"));
        sync();
        return false;
      }
      await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    }
    return false;
  }

  cancelMeasure.addEventListener("click", () => {
    const id = jobId;
    jobId = null;
    if (id) void api.cancelJob(id).catch(() => {});
    hide();
  });

  listen.addEventListener("click", () => togglePlay());
  reset.addEventListener("click", () => {
    fill(SILENCE_DEFAULTS);
    changed();
  });
  close.addEventListener("click", () => hide());
  hidePanel.addEventListener("click", () => {
    hide();
    hideSidebar?.();
  });
  accept.addEventListener("click", () => void commit());

  async function commit() {
    const { ok, options } = validate();
    if (!ok || phase !== "ready") return;
    ask.cancel();
    latest.drop();
    try {
      const response = await api.silenceAccept(options, key, seq.next());
      onRemember(options);
      finish();
      onAccepted(response, options);
    } catch (e) {
      if (e.status === 409) {
        // Stale (an edit came in): show the new preview; Accept again when it is right.
        phase = "updating";
        showError(e.message);
        sync();
        void askRanges();
        return;
      }
      phase = "error";
      showError(e.message);
      sync();
    }
  }

  root.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || event.isComposing) return;
    event.preventDefault();
    event.stopPropagation();
    hide();
  });

  /** Close without committing: the engine plays the project again. */
  function hide() {
    if (!open) return;
    void api.silenceClose(seq.next()).catch(() => {});
    finish();
  }

  function finish() {
    open = false;
    ask.cancel();
    latest.drop();
    const id = jobId;
    jobId = null;
    if (id) void api.cancelJob(id).catch(() => {});
    setPreview(null);
    root.hidden = true;
    root.closest(".sidebar")?.toggleAttribute("data-silence-open", false);
    if (returnFocus?.isConnected) returnFocus.focus();
    returnFocus = null;
  }

  return {
    element: root,
    isOpen: () => open,
    open() {
      if (open) {
        sliders.margin_db.focus();
        return;
      }
      returnFocus = document.activeElement;
      open = true;
      fill(normaliseSilence(getOptions()));
      showError("");
      summary.replaceChildren();
      more.open = false;
      root.hidden = false;
      root.closest(".sidebar")?.toggleAttribute("data-silence-open", true);
      void measure();
      // Measuring disables the controls: Cancel has the focus until they are ready.
      (sliders.margin_db.disabled ? cancelMeasure : sliders.margin_db).focus();
    },
    close: hide,
    /** The project changed (an edit, undo): the preview is asked again on top of it. */
    projectChanged() {
      if (!open || phase === "measuring") return;
      phase = "updating";
      sync();
      ask.call();
    },
    playingChanged() {
      if (open) sync();
    },
  };
}
