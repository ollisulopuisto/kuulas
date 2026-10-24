// What a running background job shows in a dialog: a bar and the job's own message (the jobs
// list gives `progress` 0..1, `indeterminate` and `message`; docs: jobs.py). Pure; the dialog
// draws it (block-level-dialog.js). Owner, 2026-10-24: a progress bar on Level blocks, like the
// structured progress of the podcast tools.

/**
 * { value, text, percent } for a job: `value` 0..1 for a bar that knows how far it is, or null
 * for one that does not (queued, or the job says indeterminate); `text` the job's message, else
 * `fallback`; `percent` a whole number, 99 at most until the job is completed.
 */
export function progressView(job, fallback = "") {
  if (!job) return { value: null, text: fallback, percent: null };
  const text = job.message || fallback;
  if (job.indeterminate || job.state === "queued") return { value: null, text, percent: null };
  const value = Math.min(1, Math.max(0, Number(job.progress) || 0));
  const whole = Math.round(value * 100);
  const percent = job.state === "completed" ? 100 : Math.min(99, whole);
  return { value, text, percent };
}
