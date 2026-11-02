import { enhanceDialog } from "./dialog-keys.js";
import { setupView } from "./orukeet-setup.js";

const make = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
};

/** Install or repair the runtime before local transcription; work remains cancellable. */
export function createOrukeetDialog({ api, t }) {
  const dialog = make("dialog", "cheatsheet automix-dialog orukeet-dialog");
  dialog.setAttribute("aria-labelledby", "orukeet-title");
  const heading = make("h2", "", t("ui.orukeet.title"));
  heading.id = "orukeet-title";
  const note = make("p", "form-note");
  const source = make("a", "form-note", t("ui.orukeet.source"));
  source.target = "_blank";
  source.rel = "noreferrer";
  const message = make("p", "form-msg");
  const location = make("p", "form-note orukeet-path");
  message.setAttribute("role", "status");
  const progress = make("progress");
  progress.max = 1;
  progress.setAttribute("aria-label", t("ui.orukeet.install"));
  const footer = make("div", "cheatsheet-footer");
  const button = (key, kind = "button block") => {
    const node = make("button", kind, t(key));
    node.type = "button";
    return node;
  };
  const install = button("ui.orukeet.install", "button block primary");
  install.dataset.dialogPrimary = "";
  const cancel = button("ui.orukeet.cancel");
  const close = button("ui.orukeet.close");
  const runAnyway = button("ui.orukeet.run_anyway");
  close.dataset.dialogCancel = "";
  footer.append(cancel, close, runAnyway, install);
  dialog.append(
    heading,
    note,
    source,
    location,
    message,
    progress,
    footer,
  );
  document.body.append(dialog);
  enhanceDialog(dialog, { t });
  let info = { ready: false, supported: false };
  let job = null;
  let jobId = null;
  let timer = null;
  let resolve = null;
  let pending = null;
  let continueWhenReady = false;
  let memoryOverride = false;

  function draw() {
    const view = setupView(memoryOverride ? { ...info, eligible: true } : info, job);
    runAnyway.hidden = info.eligible !== false || memoryOverride || !continueWhenReady;
    note.textContent = t("ui.orukeet.note");
    source.href = info.source;
    location.textContent = info.ready ? t("ui.orukeet.location", { path: info.path }) : "";
    location.hidden = !info.ready;
    progress.hidden = !view.busy;
    progress.value = view.progress;
    install.disabled = !view.canInstall;
    install.textContent = t(info.ready ? "ui.orukeet.reinstall" : "ui.orukeet.install");
    close.textContent = t(view.busy ? "ui.orukeet.background" : "ui.orukeet.close");
    cancel.hidden = !view.busy;
    message.classList.toggle("tx-error", Boolean(view.error));
    message.textContent =
      view.error ||
      (view.busy
        ? job?.message || t("ui.orukeet.progress", { percent: Math.round(100 * view.progress) })
        : view.cancelled
          ? t("ui.orukeet.cancelled")
          : t(info.ready ? "ui.orukeet.ready" : "ui.orukeet.missing"));
    if (info.eligible === false) message.textContent = t("ui.orukeet.memory_warning");
    else if (!info.supported && !info.ready) message.textContent = t("error.orukeet.platform");
  }

  const showError = (error) => {
    message.textContent = error.message;
    message.classList.add("tx-error");
  };

  async function poll() {
    if (!dialog.open || !jobId) return;
    try {
      const result = await api.getJobs();
      job = result.jobs.find((item) => item.id === jobId) || null;
      if (job && !["queued", "running"].includes(job.state)) {
        info = await api.localModel();
        jobId = null;
        draw();
        if (info.ready && (info.eligible !== false || memoryOverride) && continueWhenReady)
          dialog.close();
        return;
      }
      draw();
      timer = setTimeout(poll, 250);
    } catch (error) {
      showError(error);
    }
  }

  install.addEventListener("click", async () => {
    install.disabled = true;
    try {
      const result = await api.installLocalModel();
      jobId = result.job;
      job = { state: "queued", progress: 0 };
      draw();
      void poll();
    } catch (error) {
      draw();
      showError(error);
    }
  });
  cancel.addEventListener("click", async () => {
    try {
      await api.cancelJob(jobId);
      void poll();
    } catch (error) {
      showError(error);
    }
  });
  runAnyway.addEventListener("click", () => {
    memoryOverride = true;
    if (info.ready) dialog.close();
    else draw();
  });
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    clearTimeout(timer);
    resolve?.(
      info.ready && (info.eligible !== false || memoryOverride)
        ? { allow_low_memory: memoryOverride }
        : false,
    );
    resolve = null;
    pending = null;
  });

  async function open(ensure) {
    if (pending) return pending;
    memoryOverride = false;
    info = await api.localModel();
    if (ensure && info.ready && info.eligible !== false) return true;
    continueWhenReady = ensure;
    jobId = info.job;
    job = jobId ? { state: "running", progress: 0 } : null;
    pending = new Promise((done) => {
      resolve = done;
    });
    draw();
    dialog.showModal();
    if (jobId) void poll();
    return pending;
  }
  return { ensure: () => open(true), open: () => open(false) };
}
