// Help > Record a performance report… (src/kuulas/profiler.py): the pure parts of its dialog.

/** The spans offered, in seconds. */
export const DURATIONS = [10, 30, 60];
export const DEFAULT_SECONDS = 30;

/** Whether the server says a recording is in progress (`status` is GET /api/profile). */
export const isRunning = (status) => status?.state === "running";

/** -> { fraction: 0..1, left: whole seconds still to go } for a progress bar. */
export function progressOf(status) {
  if (status?.state === "done") return { fraction: 1, left: 0 };
  if (!isRunning(status) || !(status.seconds > 0)) return { fraction: 0, left: 0 };
  const elapsed = Math.max(0, Number(status.elapsed) || 0);
  return {
    fraction: Math.min(1, elapsed / status.seconds),
    left: Math.max(0, Math.ceil(status.seconds - elapsed)),
  };
}

/** The folder a report lives in, as the server shows it (`~/Library/Logs/Kuulas`). */
export function reportFolder(report) {
  if (!report) return "";
  const cut = report.lastIndexOf("/");
  return cut < 0 ? "" : report.slice(0, cut);
}
