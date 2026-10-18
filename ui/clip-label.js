/**
 * Shortening and layout calculations for clip labels.
 */

export function fitLabel(text, maxChars) {
  if (typeof text !== "string" || text.length === 0 || maxChars < 1) {
    return "";
  }
  if (maxChars === 1) {
    return "…";
  }
  if (text.length <= maxChars) {
    return text;
  }
  const avail = maxChars - 1;
  const startLen = Math.ceil(avail / 2);
  const endLen = Math.floor(avail / 2);
  const startPart = text.slice(0, startLen);
  const endPart = endLen > 0 ? text.slice(-endLen) : "";
  return `${startPart}…${endPart}`;
}

export function charsThatFit(widthPx, charPx) {
  if (
    typeof widthPx !== "number" ||
    typeof charPx !== "number" ||
    !Number.isFinite(widthPx) ||
    !Number.isFinite(charPx) ||
    widthPx <= 0 ||
    charPx <= 0
  ) {
    return 0;
  }
  return Math.max(0, Math.floor(widthPx / charPx));
}
