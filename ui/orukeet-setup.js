// The setup dialog's states: keep a usable model while an optional install fails.
export function setupView(status, job = null) {
  const busy = job?.state === "queued" || job?.state === "running";
  const failed = job?.state === "failed";
  return {
    ready: Boolean(status.ready),
    busy,
    canInstall: Boolean(status.supported) && !busy,
    canSelect: !busy,
    progress: Math.max(0, Math.min(1, Number(job?.progress) || 0)),
    error: failed ? job.error?.text || "" : "",
    cancelled: job?.state === "cancelled",
  };
}
