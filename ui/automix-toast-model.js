import { automixNotice } from "./automix-model.js";
import { etaLabel, etaVisible } from "./eta-label.js";

// The running automix toast, structured (docs/design/TOAST.md): a pure function from the job
// (/api/jobs, with the server's `detail`) to what the toast draws. Without a usable `detail`
// (older server, the stems-only path, a finished job) it says `rich: false` and the caller
// shows the old single line (`text`), which is also kept for the rich case.

/** The stages per track, in order (TRACK_STAGES in src/kuulas/automix.py; a test compares). */
export const TRACK_STAGES = Object.freeze([
  "read",
  "debleed",
  "plugin",
  "cleanup",
  "measure",
  "dynamics",
  "lag",
  "duck",
  "write",
]);
const PHASES = new Set(["stems", "upload", "analysis", "tracks", "mastering", "download"]);
/** The step prefix the server puts on every line ("3/4 "): the toast says it on its own row. */
const STEP_PREFIX = /^\d+\/\d+\s+/;

const whole = (value) => Number.isInteger(value) && value > 0;

function usable(detail) {
  return Boolean(
    detail &&
      typeof detail === "object" &&
      whole(detail.phase) &&
      whole(detail.phases) &&
      typeof detail.phase_name === "string",
  );
}

/** 0..99 while the job runs: 100 % is what "done" says, never a bar still waiting. */
function percentOf(progress) {
  const value = Number.isFinite(progress) ? progress : 0;
  return Math.min(99, Math.max(0, Math.round(value * 100)));
}

/** The nine stage pips: done before the current one, its own state, pending after; a stage
 * switched off is skipped wherever it sits. */
function pipsOf(stage, t) {
  if (!stage || typeof stage !== "object") return [];
  const off = new Set(Array.isArray(stage.off) ? stage.off : []);
  const n = Number.isInteger(stage.n) ? stage.n : 0;
  const now = { working: "working", done: "done", skipped: "skipped" }[stage.state] ?? "working";
  return TRACK_STAGES.map((name, i) => {
    let state;
    if (i + 1 === n) state = now;
    else if (off.has(name)) state = "skipped";
    else state = i + 1 < n ? "done" : "pending";
    return { name, label: t(`ui.automix.toast.stage.${name}`), state };
  });
}

function stageText(stage, t) {
  if (!stage || typeof stage.name !== "string") return "";
  const name = t(`ui.automix.toast.stage.${stage.name}`);
  if (stage.state === "done") return t("ui.automix.toast.stage_done", { stage: name });
  if (stage.state === "skipped") return t("ui.automix.toast.stage_skipped", { stage: name });
  return name;
}

/**
 * The toast's view data: { rich, text, notice, title, percent, percentText, indeterminate, eta,
 * phase, step, track, trackName, stage, stageCount, note, pips, bar: { now, fraction,
 * valuetext }, announce }. `announce` changes with the phase only (the live region).
 */
export function automixToast(job, t) {
  const notice = automixNotice(job, t);
  const running = job.state === "running" || job.state === "queued";
  const detail = job.detail;
  if (!running || !usable(detail)) return { rich: false, text: notice.text, notice };

  const indeterminate = Boolean(job.indeterminate);
  const percent = indeterminate ? null : percentOf(job.progress);
  const percentText = percent === null ? "" : `${percent} %`;
  let eta = "";
  if (job.paused) eta = job.message ?? "";
  else if (percent !== null && etaVisible(percent)) {
    const label = etaLabel(job.eta);
    if (label) eta = t(label.key, label.params);
  }
  const phase = PHASES.has(detail.phase_name)
    ? t(`ui.automix.toast.phase.${detail.phase_name}`)
    : "";
  const step = t("ui.automix.toast.step", { n: detail.phase, total: detail.phases });
  const track = detail.track && typeof detail.track === "object" ? detail.track : null;
  const stage = detail.stage && typeof detail.stage === "object" ? detail.stage : null;
  const note =
    track || job.paused
      ? ""
      : String(job.message ?? "")
          .replace(STEP_PREFIX, "")
          .trim();
  return {
    rich: true,
    text: notice.text,
    notice,
    title: t("ui.automix.toast.title"),
    percent,
    percentText,
    indeterminate,
    eta,
    phase,
    step,
    track: track ? t("ui.automix.toast.track", { index: track.index, total: track.total }) : "",
    trackName: track ? String(track.name ?? "") : "",
    stage: stageText(stage, t),
    stageCount: stage && whole(stage.n) && whole(stage.of) ? `${stage.n}/${stage.of}` : "",
    note,
    pips: pipsOf(stage, t),
    bar: {
      now: percent,
      // Indeterminate keeps the bar where it got to (the stems' share) and shimmers there.
      fraction: Math.min(1, Math.max(0, Number(job.progress) || 0)),
      valuetext: [percentText, eta].filter(Boolean).join(", "),
    },
    announce: t("ui.automix.toast.announce", { phase, step }),
  };
}
