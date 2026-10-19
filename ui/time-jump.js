// A time typed into the clock, a mark readout or Spot (WP76). Pure, no DOM.
// "1:23.5" and "83,2" are absolute; a leading + or - is relative to `from` (FCP style:
// "+100" is 100 seconds on, "-30" 30 back, "+1:30" 90 on); "500ms" is allowed on a plain number.
import { parseOffset } from "./time-parse.js";

const MS_SUFFIX = /^(.*\d)\s*ms$/i;

/**
 * The frame the text names, clamped to [0, end]; null when the text is not a time (the caller
 * then leaves the value alone). `from` is the frame a relative value counts from.
 */
export function resolveTime(text, { from, end, rate }) {
  if (typeof text !== "string") return null;
  let body = text.trim().replace("−", "-");
  let scale = 1;
  const ms = MS_SUFFIX.exec(body);
  if (ms && !ms[1].includes(":")) {
    body = ms[1];
    scale = 0.001;
  }
  const parsed = parseOffset(body);
  if (parsed === null) return null;
  const frames = Math.round(parsed.seconds * scale * rate);
  const target = parsed.sign === 0 ? frames : from + parsed.sign * frames;
  return Math.min(Math.max(0, end), Math.max(0, target));
}
