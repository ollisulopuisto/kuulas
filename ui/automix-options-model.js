// The automixer's switches in the Mix dialog (pure). The server lists them
// (`option_specs` in GET /api/settings/automixer, from automix.py: names, tool defaults,
// ranges); the dialog draws a control for each and sends back only what differs from the
// tool's default as `options`. The server checks them again.

import { formatWords, parseWords } from "./automix-model.js";

const MAX_TEXT = 20000;

/** A number field's text as a number; null when empty, NaN when it is not a finite number. */
function toNumber(text) {
  const trimmed = String(text ?? "")
    .trim()
    .replace(",", ".");
  if (trimmed === "") return null;
  return /^[-+]?(\d+\.?\d*|\.\d+)$/.test(trimmed) ? Number(trimmed) : Number.NaN;
}

/** Specs grouped in order of first appearance: [{ id, specs }]. */
export function groupSpecs(specs) {
  const groups = [];
  for (const spec of specs) {
    let group = groups.find((g) => g.id === spec.group);
    if (!group) {
      group = { id: spec.group, specs: [] };
      groups.push(group);
    }
    group.specs.push(spec);
  }
  return groups;
}

/** Stored options (only the differences) as the form's values: booleans and texts. */
export function optionsToForm(specs, options) {
  const stored = options && typeof options === "object" ? options : {};
  const form = {};
  for (const spec of specs) {
    const value = stored[spec.key];
    if (spec.kind === "bool") {
      form[spec.key] = typeof value === "boolean" ? value : spec.default;
    } else if (spec.kind === "number") {
      const shown = typeof value === "number" ? value : spec.default;
      form[spec.key] = shown === null || shown === undefined ? "" : String(shown);
    } else if (spec.kind === "list") {
      form[spec.key] = Array.isArray(value) ? formatWords(value) : "";
    } else {
      form[spec.key] = typeof value === "string" ? value : "";
    }
  }
  return form;
}

/** Whether a control can be used: Minimal greys the stages it switches off, and a number
 * follows its stage's checkbox. */
export function optionEnabled(specs, form, key) {
  const spec = specs.find((s) => s.key === key);
  if (!spec) return false;
  if (spec.minimal && form.minimal === true) return false;
  if (spec.parent) return optionEnabled(specs, form, spec.parent) && form[spec.parent] === true;
  return true;
}

const looksLikeSwitch = (text) => text.startsWith("-");
const hasControl = (text) => [...text].some((c) => c < " " || c === "\x7f");

/**
 * The form checked: { ok, errors: { key: messageKey }, options } with only the values that
 * differ from the tool's defaults. A control that is greyed (or a number of an off stage)
 * is neither checked nor sent.
 */
export function validateOptions(specs, form) {
  const errors = {};
  const options = {};
  for (const spec of specs) {
    const value = form[spec.key];
    if (spec.kind === "bool") {
      if (value !== spec.default && !(spec.minimal && form.minimal === true)) {
        options[spec.key] = value;
      }
      continue;
    }
    if (!optionEnabled(specs, form, spec.key)) continue;
    if (spec.kind === "number") {
      const number = toNumber(value);
      if (number === null) continue;
      if (!(number >= spec.min && number <= spec.max))
        errors[spec.key] = "ui.automix.bad_option_number";
      else if (number !== spec.default) options[spec.key] = number;
      continue;
    }
    const items = spec.kind === "list" ? parseWords(value) : [String(value ?? "").trim()];
    const used = items.filter((item) => item !== "");
    if (used.length === 0) continue;
    const bad = used.some(
      (item) => looksLikeSwitch(item) || hasControl(item) || item.length > MAX_TEXT,
    );
    if (bad) errors[spec.key] = "ui.automix.bad_option_text";
    else options[spec.key] = spec.kind === "list" ? used : used[0];
  }
  return { ok: Object.keys(errors).length === 0, errors, options };
}
