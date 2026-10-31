// Track > Auto > "Level blocks…": a side panel docked over the sidebar like Auto-Silence's, so
// you can keep editing while it measures. Opening it starts a measuring job on the server (it
// changes nothing); the result lists, per speaker, the blocks that are off with their span, how
// far off and the gain Apply would add to the clips, each with a tick; the very loud spots are
// listed apart (never changed) with a checkbox for markers. An edit while it measures, or after,
// makes the result stale: it says so and Apply stays off until "Measure again" (the server
// refuses a stale Apply too). Apply hands { measured, skip, markers } to `onApply` (one undo
// step, made by the caller). Closing stops a measurement still running. The rows and numbers
// are pure (block-level-model.js); this file is the DOM.

import {
  allChangedIds,
  blockText,
  canApply,
  changedBySpeaker,
  impactSummary,
  loudBySpeaker,
  loudText,
  measureError,
  phaseAfterEdit,
  ruleText,
  skipIds,
} from "./block-level-model.js";
import { progressView } from "./job-progress.js";

const POLL_MS = 400;

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/**
 * `root`: the sidebar section to fill. `api`: { blockLevelMeasure, getJobs, cancelJob }; `t`
 * translates; `fmt(value)` formats one decimal; `clock(seconds)` a position;
 * `onApply({ measured, skip, markers })`. Returns { element, open, close, isOpen,
 * projectChanged }.
 */
export function createBlockLevelPanel({ root, api, t, fmt, clock, onApply }) {
  root.setAttribute("aria-labelledby", "block-level-title");
  root.tabIndex = -1;
  const head = el("div", "silence-head");
  const heading = el("h2", "", t("ui.block_level.title"));
  heading.id = "block-level-title";
  const hidePanel = el("button", "button ghost icon silence-close");
  hidePanel.type = "button";
  hidePanel.dataset.icon = "close";
  hidePanel.setAttribute("aria-label", t("ui.block_level.close"));
  hidePanel.title = t("ui.block_level.close");
  head.append(heading, hidePanel);

  const rule = el("p", "form-note");
  rule.hidden = true;
  const status = el("div", "form-note block-level-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  // How far the measuring is (job-progress.js): a bar that moves when the job says how far it
  // is, and the job's own message beside it ("Reading track 2 of 5…").
  const bar = el("progress", "job-progress");
  bar.max = 1;
  bar.hidden = true;
  bar.setAttribute("aria-label", t("ui.block_level.measuring"));
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

  const body = el("div", "form-grid");
  body.append(rule, status, bar, error, lists, markersRow);

  const again = el("button", "button", t("ui.block_level.measure_again"));
  again.type = "button";
  again.dataset.icon = "reset";
  const close = el("button", "button", t("ui.block_level.close"));
  close.type = "button";
  close.dataset.icon = "close";
  const apply = el("button", "button primary", t("ui.block_level.apply"));
  apply.type = "button";
  apply.dataset.icon = "check";
  apply.disabled = true;
  const buttons = el("div", "actionbar");
  buttons.setAttribute("role", "group");
  buttons.setAttribute("aria-label", t("ui.block_level.title"));
  buttons.append(again, close, apply); // the primary last (BUTTONS.md)
  root.append(head, body, buttons);

  // -- state ------------------------------------------------------------------------------
  let isOpen = false;
  let phase = "idle";
  let returnFocus = null;
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
    const updateImpact = () => {
      if (changed.length === 0) {
        status.textContent = t("ui.block_level.none");
        return;
      }
      const impact = impactSummary(measured, ticked);
      apply.disabled = impact.blocks === 0;
      const left = impact.unchanged;
      status.replaceChildren(
        el("span", "block-level-impact", t("ui.block_level.summary", impact)),
      );
      if (left > 0) {
        status.append(
          el(
            "span",
            "block-level-unchanged",
            t("ui.block_level.left", { count: left, threshold: fmt(measured.threshold_db) }),
          ),
        );
      }
    };
    updateImpact();
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
          updateImpact();
        });
        const choice = el("label", "form-choice block-level-choice");
        choice.append(box, el("span", "block-level-line", blockText(row, rate, t, fmt, clock)));
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
    setPhase("ready");
  }

  function paintProgress(job) {
    const view = progressView(job, t("ui.block_level.measuring"));
    status.textContent = view.text;
    if (view.value === null) bar.removeAttribute("value");
    else bar.value = view.value;
    bar.hidden = false;
  }

  const showError = (text) => {
    bar.hidden = true;
    status.textContent = "";
    error.textContent = text;
    error.hidden = false;
  };

  function setPhase(next) {
    phase = next;
    apply.disabled = !canApply(phase) ||
      (phase === "ready" && impactSummary(measured, ticked).blocks === 0);
    again.disabled = phase === "measuring";
    if (phase === "stale") {
      bar.hidden = true;
      status.textContent = t("ui.block_level.stale");
    }
  }

  function stop() {
    watching += 1;
    bar.hidden = true;
    if (jobId) void api.cancelJob(jobId).catch(() => {});
    jobId = null;
  }

  function hide() {
    if (!isOpen) return;
    isOpen = false;
    stop();
    phase = "idle";
    root.hidden = true;
    root.closest(".sidebar")?.toggleAttribute("data-silence-open", false);
    if (returnFocus?.isConnected) returnFocus.focus();
    returnFocus = null;
  }
  close.addEventListener("click", hide);
  hidePanel.addEventListener("click", hide);
  again.addEventListener("click", () => void measure());
  root.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !event.defaultPrevented) {
      event.preventDefault();
      hide();
    }
  });

  async function measure() {
    stop();
    const mine = watching;
    measured = null;
    error.hidden = true;
    rule.hidden = true;
    lists.replaceChildren();
    markersRow.hidden = true;
    markersBox.checked = false;
    setPhase("measuring");
    paintProgress(null);
    try {
      const { jobs } = await api.blockLevelMeasure({});
      jobId = jobs[0];
      while (watching === mine) {
        if (phase === "stale") {
          stop(); // edited while it measured: stop measuring a result nobody can apply
          return;
        }
        const job = (await api.getJobs()).jobs.find((item) => item.id === jobId);
        if (!job) break;
        if (job.state === "completed") {
          jobId = null;
          bar.hidden = true;
          const key = measureError(job.result);
          if (key) {
            showError(t(key));
            return;
          }
          if (phase === "stale") return; // edited while it measured: this result no longer fits
          measured = job.result;
          ticked = allChangedIds(measured);
          show();
          return;
        }
        if (job.state === "failed" || job.state === "cancelled") {
          jobId = null;
          setPhase("failed");
          showError(job.error?.text || t("ui.block_level.failed"));
          return;
        }
        paintProgress(job);
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      }
    } catch (e) {
      if (watching === mine) {
        setPhase("failed");
        showError(e.message);
      }
    }
  }

  apply.addEventListener("click", () => {
    if (!canApply(phase) || !measured) return;
    const chosen = measured;
    const skip = skipIds(chosen, ticked);
    const markers = markersBox.checked;
    hide();
    onApply({ measured: chosen, skip, markers });
  });

  return {
    element: root,
    isOpen: () => isOpen,
    close: hide,
    /** The project changed (an edit, undo): the measured result no longer fits. */
    projectChanged() {
      if (!isOpen) return;
      const next = phaseAfterEdit(phase);
      if (next !== phase) setPhase(next);
    },
    open() {
      if (isOpen) {
        again.focus();
        return;
      }
      returnFocus = document.activeElement;
      isOpen = true;
      root.hidden = false;
      root.closest(".sidebar")?.toggleAttribute("data-silence-open", true);
      void measure();
      close.focus();
    },
  };
}
