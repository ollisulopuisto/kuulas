// ui/time-parse.js
// Parsing a typed time or offset. Plain ES module, no DOM, no imports.

const INTEGER_REGEX = /^\d+$/;
const SECONDS_REGEX = /^\d+([.,]\d+)?$/;

/**
 * Parses text into seconds as a number, or null when the text is not a time.
 * Accepted forms: 83.2, 83,2, 1:23, 1:23.5, 1:02:03, 1:02:03.250.
 * Minutes and seconds must be under 60 when a larger unit is present.
 * Leading minus or plus is rejected (null).
 */
export function parseTime(text) {
  if (typeof text !== "string") {
    return null;
  }
  const trimmed = text.trim();
  if (!trimmed) {
    return null;
  }
  if (trimmed.startsWith("-") || trimmed.startsWith("+")) {
    return null;
  }

  const parts = trimmed.split(":");
  if (parts.length < 1 || parts.length > 3) {
    return null;
  }

  if (parts.length === 3) {
    const [hStr, mStr, sStr] = parts;
    if (!INTEGER_REGEX.test(hStr) || !INTEGER_REGEX.test(mStr) || !SECONDS_REGEX.test(sStr)) {
      return null;
    }
    const h = Number.parseInt(hStr, 10);
    const m = Number.parseInt(mStr, 10);
    const s = Number.parseFloat(sStr.replace(",", "."));
    if (m >= 60 || s >= 60) {
      return null;
    }
    return h * 3600 + m * 60 + s;
  }

  if (parts.length === 2) {
    const [mStr, sStr] = parts;
    if (!INTEGER_REGEX.test(mStr) || !SECONDS_REGEX.test(sStr)) {
      return null;
    }
    const m = Number.parseInt(mStr, 10);
    const s = Number.parseFloat(sStr.replace(",", "."));
    if (s >= 60) {
      return null;
    }
    return m * 60 + s;
  }

  const sStr = parts[0];
  if (!SECONDS_REGEX.test(sStr)) {
    return null;
  }
  return Number.parseFloat(sStr.replace(",", "."));
}

/**
 * Like parseTime but a leading + or - is allowed and returned as the sign:
 * { sign: 1 | -1 | 0, seconds }, sign 0 when there is none.
 * Returns null when invalid.
 */
export function parseOffset(text) {
  if (typeof text !== "string") {
    return null;
  }
  const trimmed = text.trim();
  if (!trimmed) {
    return null;
  }

  let sign = 0;
  let remainder = trimmed;

  if (trimmed.startsWith("+")) {
    sign = 1;
    remainder = trimmed.slice(1).trim();
  } else if (trimmed.startsWith("-")) {
    sign = -1;
    remainder = trimmed.slice(1).trim();
  }

  const seconds = parseTime(remainder);
  if (seconds === null) {
    return null;
  }

  return { sign, seconds };
}
