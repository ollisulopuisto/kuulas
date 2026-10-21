// The Auto-Silence live preview panel, the pure part (the DOM is silence-panel.js): asking the
// server again only after the controls rest a moment, dropping answers that a newer question
// has overtaken, the summary lines, and what can be pressed in each phase.

/** How long the controls must rest before the ranges are asked for again, ms. Short enough
 * that a slider feels live; long enough that a drag does not queue a request per pixel. */
export const DEBOUNCE_MS = 80;

/**
 * `fn` runs `ms` after the last `call`, with that call's arguments. `cancel` forgets a waiting
 * call, `flush` runs it now. `timers` is for tests.
 */
export function createDebouncer(fn, ms, timers = globalThis) {
  let handle = null;
  let waiting = null;
  const fire = () => {
    handle = null;
    const args = waiting;
    waiting = null;
    if (args) fn(...args);
  };
  return {
    call(...args) {
      waiting = args;
      if (handle !== null) timers.clearTimeout(handle);
      handle = timers.setTimeout(fire, ms);
    },
    cancel() {
      if (handle !== null) timers.clearTimeout(handle);
      handle = null;
      waiting = null;
    },
    flush() {
      if (handle !== null) timers.clearTimeout(handle);
      fire();
    },
  };
}

/** Tokens for "is this answer still the newest question's?". `drop` makes none current. */
export function createLatest() {
  let current = 0;
  return {
    begin() {
      current += 1;
      return current;
    },
    isLatest(token) {
      return token === current;
    },
    drop() {
      current += 1;
    },
  };
}

/**
 * The rising number the server orders the listening overlay by (a late answer must not
 * replace a newer one, or bring it back after Close). It starts from the clock, so it keeps
 * rising after the page is loaded again.
 */
export function createSeq(now = Date.now) {
  let last = 0;
  return {
    next() {
      last = Math.max(last + 1, Math.floor(now()));
      return last;
    },
  };
}

/** Seconds as "m:ss", or "h:mm:ss" from an hour on. */
export function clockText(seconds) {
  const whole = Math.max(0, Math.round(Number(seconds) || 0));
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  const s = String(whole % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/**
 * One line per track of an answer: "Aame: 12:34 of 45:10 silenced, 28 %, 41 stretches", and
 * what its gate closes now ("" when nothing).
 */
export function summaryLines(rows, t) {
  return (rows ?? []).map((row) => {
    const percent = row.total_s > 0 ? Math.round((100 * row.close_s) / row.total_s) : 0;
    return {
      trackId: row.track_id,
      text: t("ui.silence.panel_row", {
        name: row.name,
        closed: clockText(row.close_s),
        total: clockText(row.total_s),
        percent,
        stretches: row.stretches,
      }),
      now: row.now_s > 0 ? t("ui.silence.panel_now", { now: clockText(row.now_s) }) : "",
    };
  });
}

/** The preview ranges by track, for the timeline's overlay. */
export function overlayFrom(rows) {
  return new Map((rows ?? []).map((row) => [row.track_id, row.ranges]));
}

/** The measuring job as the progress bar reads it; a job that is gone counts as failed. */
export function jobProgress(job) {
  return {
    fraction: Number(job?.progress) || 0,
    message: job?.message ?? "",
    done: job?.state === "completed",
    failed: !job || job.state === "failed",
    cancelled: job?.state === "cancelled",
  };
}

/**
 * What can be pressed. `phase`: "measuring" (the job runs: only Cancel), "updating" (a new
 * answer is on its way: the controls stay live, Accept waits for it), "ready", "error" (the
 * last question failed: change something and it is asked again).
 */
export function panelControls({ phase, valid, playing }) {
  const measuring = phase === "measuring";
  return {
    controls: !measuring,
    listen: !measuring,
    accept: phase === "ready" && valid,
    reset: !measuring,
    progress: measuring,
    listenKey: playing ? "ui.silence.listen_stop" : "ui.silence.listen",
  };
}
