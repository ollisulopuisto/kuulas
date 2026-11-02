// The transcript dock's "Transcription missing" list (pure): one row per recording of the
// project that has no transcript, with what the background jobs (WP79) are doing with it.

const ACTIVE = new Set(["queued", "running"]);
const FAILED = new Set(["failed", "cancelled", "interrupted"]);
// Which state wins when a recording has several jobs: work in flight, then the newest failure.
const RANK = { running: 3, queued: 2, failed: 1 };

/**
 * `media`: [{ id, name }] the recordings in use; `transcribed`: the ids that have words;
 * `jobs`: /api/jobs. -> { rows: [{ id, name, status: "none"|"queued"|"running"|"failed",
 * progress, backend, error }], all: ids with no job to start together (null below two) }.
 */
export function offerRows({ media, transcribed, jobs }) {
  const done = new Set(transcribed);
  const byMedia = new Map();
  for (const job of jobs) {
    if (job.kind !== "transcribe" || !Array.isArray(job.media)) continue;
    const status = ACTIVE.has(job.state) ? job.state : FAILED.has(job.state) ? "failed" : null;
    if (!status) continue;
    for (const id of job.media) {
      const known = byMedia.get(id);
      if (!known || RANK[status] >= RANK[known.status]) byMedia.set(id, { status, job });
    }
  }
  const rows = media
    .filter((item) => !done.has(item.id))
    .map((item) => {
      const found = byMedia.get(item.id);
      return {
        id: item.id,
        name: item.name,
        status: found?.status ?? "none",
        progress: found?.job.progress ?? 0,
        backend: found?.job.backend ?? null,
        jobId: found?.job.id ?? null,
        message: found?.job.message ?? "",
        error: found?.status === "failed" ? (found.job.error?.text ?? "") : "",
        cancelled: found?.job.state === "cancelled",
      };
    });
  const startable = rows.filter((row) => row.status === "none" || row.status === "failed");
  return { rows, all: startable.length >= 2 ? startable.map((row) => row.id) : null };
}

/** Is any row waiting on a job (the dock then keeps asking /api/jobs)? */
export const anyActive = (rows) => rows.some((row) => ACTIVE.has(row.status));
