// ui/eta-label.js
// Toast label and visibility for long job time estimates.
// Plain ES module, no imports, no DOM.

/**
 * Returns translation key and parameters for an ETA parts tuple from the backend.
 * Returns null for null or invalid inputs.
 */
export function etaLabel(parts) {
  if (!Array.isArray(parts) || parts.length !== 2) {
    return null;
  }

  const [kind, value] = parts;

  if (kind === "under_minute") {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
      return null;
    }
    return { key: "ui.eta.under_minute", params: {} };
  }

  if (kind === "minutes") {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
      return null;
    }
    return { key: "ui.eta.minutes", params: { n: value } };
  }

  if (kind === "hours_minutes") {
    if (!Array.isArray(value) || value.length !== 2) {
      return null;
    }
    const [h, m] = value;
    if (
      typeof h !== "number" ||
      !Number.isFinite(h) ||
      h < 0 ||
      typeof m !== "number" ||
      !Number.isFinite(m) ||
      m < 0
    ) {
      return null;
    }
    return { key: "ui.eta.hours_minutes", params: { h, m } };
  }

  return null;
}

/**
 * Returns true only when percent is a finite number at or above minPercent and below 100.
 */
export function etaVisible(percent, minPercent = 5) {
  if (
    typeof percent !== "number" ||
    !Number.isFinite(percent) ||
    typeof minPercent !== "number" ||
    !Number.isFinite(minPercent)
  ) {
    return false;
  }
  return percent >= minPercent && percent < 100;
}
