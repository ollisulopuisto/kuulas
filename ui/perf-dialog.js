// Help > Record a performance report… (src/kuulas/profiler.py): ask for a span, show the
// progress, say where the report went. The server samples the app's own threads and writes a
// plain-text file next to the log (and shows it in Finder); this file only drives that.

import { DEFAULT_SECONDS, DURATIONS, isRunning, progressOf, reportFolder } from "./perf-model.js";

const POLL_MS = 500;

/**
 * `api`: { getProfile, startProfile, stopProfile }; `t` translates; `notify(text, kind)` shows a
 * toast (the dialog may be closed when the recording ends). Returns { element, open() }.
 */
export function createPerfDialog({ api, t, notify }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet perf-dialog";
  dialog.setAttribute("aria-labelledby", "perf-title");

  const heading = document.createElement("h2");
  heading.id = "perf-title";
  heading.textContent = t("ui.perf.title");
  const intro = document.createElement("p");
  intro.textContent = t("ui.perf.intro");

  const choice = document.createElement("label");
  choice.className = "perf-choice";
  const choiceText = document.createElement("span");
  choiceText.textContent = t("ui.perf.length");
  const select = document.createElement("select");
  for (const seconds of DURATIONS) {
    const option = document.createElement("option");
    option.value = String(seconds);
    option.textContent = t("ui.perf.seconds", { n: seconds });
    option.selected = seconds === DEFAULT_SECONDS;
    select.append(option);
  }
  choice.append(choiceText, select);

  const progress = document.createElement("progress");
  progress.max = 1;
  progress.value = 0;
  progress.hidden = true;
  progress.setAttribute("aria-label", t("ui.perf.title"));
  const message = document.createElement("p");
  message.className = "perf-message";
  message.setAttribute("role", "status");
  message.setAttribute("aria-live", "polite");

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
  const start = button("ui.perf.start", () => void begin(), "primary");
  const stop = button("ui.perf.stop", () => void end());
  const close = button("ui.perf.close", () => dialog.close());
  start.dataset.icon = "play";
  close.dataset.icon = "close";
  buttons.append(start, stop, close);
  dialog.append(heading, intro, choice, progress, message, buttons);
  document.body.append(dialog);

  let timer = null;
  // True from Start until the toast for that recording: opening the dialog on an old result
  // must not announce it again.
  let watching = false;

  function show(status) {
    const running = isRunning(status);
    start.disabled = running;
    select.disabled = running;
    stop.hidden = !running;
    progress.hidden = !running;
    if (running) {
      const { fraction, left } = progressOf(status);
      progress.value = fraction;
      message.textContent = t("ui.perf.running", { n: left });
    } else if (status?.state === "done") {
      message.textContent = t("ui.perf.done", {
        folder: reportFolder(status.report),
        samples: status.samples,
      });
    } else if (status?.state === "failed") {
      message.textContent = t("ui.perf.failed", { error: status.error ?? "" });
    } else {
      message.textContent = "";
    }
  }

  function finished(status) {
    // One toast per recording, whether or not the dialog is still open.
    if (!watching) return;
    watching = false;
    if (status.state === "done") {
      notify(t("ui.perf.toast_done", { folder: reportFolder(status.report) }), "ok");
    } else {
      notify(t("ui.perf.failed", { error: status.error ?? "" }));
    }
  }

  async function poll() {
    let status = null;
    try {
      status = await api.getProfile();
    } catch (error) {
      message.textContent = error.message;
      timer = null;
      return;
    }
    show(status);
    if (isRunning(status)) {
      timer = setTimeout(() => void poll(), POLL_MS);
      return;
    }
    timer = null;
    if (status.state === "done" || status.state === "failed") finished(status);
  }

  function watch() {
    if (timer !== null) clearTimeout(timer);
    timer = setTimeout(() => void poll(), 0);
  }

  async function begin() {
    start.disabled = true;
    try {
      show(await api.startProfile(Number(select.value)));
    } catch (error) {
      start.disabled = false;
      message.textContent = error.message;
      return;
    }
    watching = true;
    watch();
  }

  async function end() {
    stop.disabled = true;
    try {
      await api.stopProfile();
    } catch (error) {
      message.textContent = error.message;
    }
    stop.disabled = false;
    watch();
  }

  return {
    element: dialog,
    async open() {
      message.textContent = "";
      if (!dialog.open) dialog.showModal();
      start.focus();
      await poll();
    },
  };
}
