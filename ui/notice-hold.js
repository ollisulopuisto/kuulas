// Closing a toast with its X keeps the next ones quiet (owner, 2026-10-23, BUGS #110): a long
// job (a Colab transcription) sends a new message every few seconds, and each one popped the
// toast up again. While held, a message only updates the status-bar button (a dot and the
// latest text, so progress can be read at a glance); clicking the button shows the latest
// message as a toast again and ends the hold. Pure: the page decides what to draw.

/** The longest the button's text gets. */
export const CHIP_CHARS = 48;

/** A message on one line, cut with an ellipsis when it is longer than `max`. */
export function chipText(text, max = CHIP_CHARS) {
  const line = String(text ?? "")
    .replace(/\s+/g, " ")
    .trim();
  return line.length <= max ? line : `${line.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

export function createNoticeHold() {
  let held = false;
  let latest = null;
  return {
    get held() {
      return held;
    },
    /** The user closed a toast: from now on messages are held. */
    hold() {
      held = true;
    },
    /** A message arrives: true to show it now, false when it was held (and remembered). */
    offer(notice) {
      if (!held) return true;
      latest = notice;
      return false;
    },
    /** The latest held message (null when none arrived since the hold began). */
    latest: () => latest,
    /** Whether something arrived while held (the dot on the button). */
    pending: () => held && latest !== null,
    /** Show it again: hands back the latest held message and ends the hold. */
    release() {
      const out = latest;
      held = false;
      latest = null;
      return out;
    },
  };
}
