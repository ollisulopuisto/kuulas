// Auto-Silence options: the values, their limits and the preview text, pure (the dialog is
// silence-dialog.js). The defaults and ranges mirror src/kuulas/silence_options.py; the
// server clamps again, this keeps the form honest before it asks.

export const SILENCE_DEFAULTS = Object.freeze({
  margin_db: 12,
  dominance_db: 6,
  min_open_s: 0.4,
  min_closed_s: 0.3,
  open_before_s: 0.15,
  open_after_s: 0.4,
  method: "threshold",
});

export const SILENCE_RANGES = Object.freeze({
  margin_db: [3, 20],
  dominance_db: [0, 30],
  min_open_s: [0, 5],
  min_closed_s: [0, 5],
  open_before_s: [0, 3],
  open_after_s: [0, 5],
});

export const SILENCE_METHODS = ["threshold", "compensated"];

/** A number from what was typed ("0,4" and "0.4" both work), or null. */
export function parseNumber(text) {
  if (typeof text === "number") return Number.isFinite(text) ? text : null;
  const clean = String(text ?? "")
    .trim()
    .replace(",", ".");
  if (clean === "" || !/^[+-]?(\d+\.?\d*|\.\d+)$/.test(clean)) return null;
  return Number(clean);
}

const clamp = (value, [low, high]) => Math.min(high, Math.max(low, value));

/** Options from anything stored: what is not valid falls back to the default. */
export function normaliseSilence(raw) {
  const source = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  const out = { ...SILENCE_DEFAULTS };
  for (const [name, range] of Object.entries(SILENCE_RANGES)) {
    const number = parseNumber(source[name]);
    if (number !== null) out[name] = clamp(number, range);
  }
  if (SILENCE_METHODS.includes(source.method)) out.method = source.method;
  return out;
}

/**
 * The form (strings, as typed) -> { ok, errors: {name: messageKey}, options }. A field that
 * is not a number, or outside its range, is an error: the form never clamps silently what the
 * person typed.
 */
export function validateSilence(form) {
  const errors = {};
  const options = { ...SILENCE_DEFAULTS };
  for (const [name, [low, high]] of Object.entries(SILENCE_RANGES)) {
    const number = parseNumber(form[name]);
    if (number === null) errors[name] = "ui.silence.error_number";
    else if (number < low || number > high) errors[name] = "ui.silence.error_range";
    else options[name] = number;
  }
  options.method = SILENCE_METHODS.includes(form.method) ? form.method : "threshold";
  return { ok: Object.keys(errors).length === 0, errors, options };
}

/** Does any speech track carry a clip muted by hand? The compensated method learns from them. */
export function hasHandMutes(project) {
  return (project?.tracks ?? []).some(
    (track) => track.kind === "speech" && (track.clips ?? []).some((clip) => clip.muted),
  );
}

/** Which method may be chosen: the compensated one needs hand mutes to learn from. */
export function methodAvailable(method, project) {
  return method !== "compensated" || hasHandMutes(project);
}

const seconds = (value) => (Math.round(value * 10) / 10).toString();

/** One line per track of a finished preview job's result: "Anna: would close 41.2 s in 12 ...". */
export function previewLines(result, t) {
  return (result?.tracks ?? []).map((row) =>
    t("ui.silence.preview_row", {
      name: row.name,
      close: seconds(row.close_s),
      stretches: row.stretches,
      now: seconds(row.now_s),
    }),
  );
}
