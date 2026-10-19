// Pre-roll (WP12c), pure: how many seconds before Record a take starts, and what the record view
// says about the recorder listening. While the view is open and pre-roll is on, the recorder
// keeps the last N seconds in memory only (nothing on disk until Record); record-view.js arms it,
// keeps it armed, and lets it go when the view closes.

/** Seconds offered; 0 is off. The cycle command and the view's select use the same list. */
export const PREROLL_CHOICES = [0, 10, 30, 60, 120];
/** A minute (owner, 2026-10-19). */
export const DEFAULT_PREROLL_S = 60;
/** The recorder lets go of the microphone after 120 s without being armed again. */
export const ARM_KEEPALIVE_MS = 20000;

export function prerollChoice(stored) {
  const seconds = Number(stored);
  if (stored === null || stored === undefined || stored === "") return DEFAULT_PREROLL_S;
  return PREROLL_CHOICES.includes(seconds) ? seconds : DEFAULT_PREROLL_S;
}

export function nextPreroll(current) {
  const at = PREROLL_CHOICES.indexOf(prerollChoice(current));
  return PREROLL_CHOICES[(at + 1) % PREROLL_CHOICES.length];
}

export function prerollLabel(seconds, t) {
  return seconds === 0 ? t("ui.record.preroll.off") : t("ui.record.preroll.seconds", { seconds });
}

/** The body of POST /api/record/arm: the same input and channel the take will use. */
export function armRequest({ device, channel, seconds }) {
  return {
    device: device ? { index: device.index, name: device.name } : null,
    channel: Math.max(1, Math.round(Number(channel)) || 1),
    preroll_s: seconds,
  };
}

/** The line that says whether the microphone is being listened to. `status`: the server's view. */
export function armedNotice(status, seconds, t) {
  if (seconds === 0) return t("ui.record.armed_off");
  if (status?.armed) return t("ui.record.armed", { seconds: status.preroll_s ?? seconds });
  return t("ui.record.armed_starting");
}
