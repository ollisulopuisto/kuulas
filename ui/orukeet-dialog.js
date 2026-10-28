import { enhanceDialog } from "./dialog-keys.js";
import { formatNumber } from "./i18n.js";
import { setupView } from "./orukeet-setup.js";

const make = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
};

/** Install/select before the requested transcription; downloads remain regular cancellable jobs. */
export function createOrukeetDialog({ api, t, pickFolder = null }) {
  const dialog = make("dialog", "cheatsheet automix-dialog orukeet-dialog");
  dialog.setAttribute("aria-labelledby", "orukeet-title");
  const heading = make("h2", "", t("ui.orukeet.title"));
  heading.id = "orukeet-title";
  const note = make("p", "form-note");
  const source = make("a", "form-note", t("ui.orukeet.source"));
  source.target = "_blank";
  source.rel = "noreferrer";
  const message = make("p", "form-msg");
  message.setAttribute("role", "status");
  const progress = make("progress");
  progress.max = 1;
  progress.setAttribute("aria-label", t("ui.orukeet.install"));
  const selected = make("p", "form-note orukeet-path");
  const pathLabel = make("label", "form-row");
  const pathInput = make("input");
  pathInput.type = "text";
  pathInput.autocomplete = "off";
  pathInput.spellcheck = false;
  pathLabel.append(make("span", "form-label", t("ui.orukeet.path")), pathInput);
  const footer = make("div", "cheatsheet-footer");
  const button = (key, kind = "button block") => {
    const node = make("button", kind, t(key));
    node.type = "button";
    return node;
  };
  const choose = button("ui.orukeet.choose");
  choose.hidden = !pickFolder;
  const use = button("ui.orukeet.use");
  const install = button("ui.orukeet.install", "button block primary");
  install.dataset.dialogPrimary = "";
  const cancel = button("ui.orukeet.cancel");
  const close = button("ui.orukeet.close");
  close.dataset.dialogCancel = "";
  const existingActions = make("div", "orukeet-existing-actions");
  existingActions.append(choose, use);
  footer.append(cancel, close, install);
  dialog.append(
    heading,
    note,
    source,
    selected,
    message,
    progress,
    pathLabel,
    existingActions,
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

  function draw() {
    const view = setupView(info, job);
    note.textContent = t("ui.orukeet.note", {
      size: formatNumber((info.bytes || 0) / 1e9, { digits: 2 }),
    });
    source.href = info.source;
    selected.textContent = info.ready ? info.path : "";
    selected.hidden = !info.ready;
    progress.hidden = !view.busy;
    progress.value = view.progress;
    install.disabled = !view.canInstall;
    install.textContent = t(info.ready ? "ui.orukeet.reinstall" : "ui.orukeet.install");
    close.textContent = t(view.busy ? "ui.orukeet.background" : "ui.orukeet.close");
    choose.disabled = !view.canSelect;
    use.disabled = !view.canSelect;
    pathInput.disabled = !view.canSelect;
    cancel.hidden = !view.busy;
    message.classList.toggle("tx-error", Boolean(view.error));
    message.textContent =
      view.error ||
      (view.busy
        ? job?.message || t("ui.orukeet.progress", { percent: Math.round(100 * view.progress) })
        : view.cancelled
          ? t("ui.orukeet.cancelled")
          : t(info.ready ? "ui.orukeet.ready" : "ui.orukeet.missing"));
    if (info.eligible === false) message.textContent = t("error.orukeet.memory");
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
        if (info.ready && info.eligible !== false && continueWhenReady) dialog.close();
        return;
      }
      draw();
      timer = setTimeout(poll, 250);
    } catch (error) {
      showError(error);
    }
  }

  async function applyFolder(path) {
    try {
      info = await api.selectLocalModel(path);
      job = null;
      draw();
      if (continueWhenReady) dialog.close();
    } catch (error) {
      showError(error);
    }
  }
  use.addEventListener("click", () => void applyFolder(pathInput.value));
  pathInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      void applyFolder(pathInput.value);
    }
  });
  choose.addEventListener("click", async () => {
    try {
      const path = await pickFolder?.();
      if (path) {
        pathInput.value = path;
        await applyFolder(path);
      }
    } catch (error) {
      showError(error);
    }
  });
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
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    clearTimeout(timer);
    resolve?.(Boolean(info.ready && info.eligible !== false));
    resolve = null;
    pending = null;
  });

  async function open(ensure) {
    if (pending) return pending;
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
