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

/**
 * The settings that differ from the tool's defaults, as short readable texts per group:
 * { groupId: ["Debleed off", "Ducking depth -12"] }. `words`: { label(spec), on, off }.
 * A value that does not validate is not listed (it is not sent either).
 */
export function changedItems(specs, form, words) {
  const { options } = validateOptions(specs, form);
  const byGroup = {};
  for (const spec of specs) {
    if (!(spec.key in options)) continue;
    const value = options[spec.key];
    let shown = value;
    if (typeof value === "boolean") shown = value ? words.on : words.off;
    else if (Array.isArray(value)) shown = value.join(", ");
    const list = byGroup[spec.group] ?? [];
    list.push(`${words.label(spec)} ${shown}`);
    byGroup[spec.group] = list;
  }
  return byGroup;
}

/**
 * The keys of changed options the installed automixer is known not to accept
 * (`capabilities[key] === false`, from GET /api/settings/automixer). An unknown capability
 * is not a warning: the server decides again when the run starts.
 */
export function unsupportedChanged(specs, form, capabilities) {
  if (!capabilities || typeof capabilities !== "object") return [];
  const { options } = validateOptions(specs, form);
  return specs.filter((s) => s.key in options && capabilities[s.key] === false).map((s) => s.key);
}

/**
 * What Kuulas can already have done in the edit, by automixer option: the option key -> the
 * name of the project's `mix_done` entry (server: automix.DONE_IN_KUULAS). The music duck
 * joins by being listed here and on the server (docs/FORMAT.md). An entry's `value` is what the
 * option is sent as: the offset for a number, `false` for a stage switch (block level), which
 * Kuulas did, so the automixer's own stage is switched off.
 */
export const DONE_IN_KUULAS = { bed_under_speech_db: "bed_level", block_level: "block_level" };

/** What the option is set to when Kuulas did the work: `value`, else the older `offset_db`. */
const doneValue = (entry) => entry.value ?? entry.offset_db;

/** `done` (GET /api/settings/automixer `done_in_kuulas`) by option key: [{ key, entry }]. */
function doneEntries(specs, done) {
  if (!done || typeof done !== "object") return [];
  const found = [];
  for (const spec of specs) {
    const name = DONE_IN_KUULAS[spec.key];
    const entry = name ? done[name] : undefined;
    const value = entry ? doneValue(entry) : undefined;
    if (typeof value === "number" || typeof value === "boolean") found.push({ spec, entry });
  }
  return found;
}

/**
 * The stored options with what Kuulas did filled in: `{ options, offered }`. Only a stored
 * value at the tool's default (absent) is replaced; a different stored value is the user's
 * and stays, and its key is `offered` (the dialog offers Kuulas's value). A stale record
 * (`current` false) changes nothing.
 */
export function prefillOptions(specs, done, stored) {
  const options = { ...(stored && typeof stored === "object" ? stored : {}) };
  const offered = [];
  for (const { spec, entry } of doneEntries(specs, done)) {
    if (!entry.current) continue;
    const value = doneValue(entry);
    const have = options[spec.key];
    if (typeof have !== typeof value || have === spec.default) options[spec.key] = value;
    else if (have !== value) offered.push(spec.key);
  }
  return { options, offered };
}

/**
 * Per option, what the dialog says about Kuulas's work, from the live form:
 * { key: { state: "done" | "offer" | "stale", offset, unsupported } }. "done": the value is
 * Kuulas's (badge); "offer": the user's saved value differs and `offered` has the key; "stale":
 * the music level was set earlier but the project changed since. An edited-away value has none.
 */
export function doneStatus(specs, done, form, offered, capabilities) {
  const status = {};
  for (const { spec, entry } of doneEntries(specs, done)) {
    const offset = doneValue(entry);
    const shown = spec.kind === "bool" ? form[spec.key] : toNumber(form[spec.key]);
    let state = null;
    if (!entry.current) state = "stale";
    else if (shown === offset) state = "done";
    else if ((offered ?? []).includes(spec.key)) state = "offer";
    if (state) {
      status[spec.key] = {
        state,
        offset,
        unsupported: state === "done" && capabilities?.[spec.key] === false,
      };
    }
  }
  return status;
}

const doneKeys = (status) => Object.keys(status).filter((k) => status[k].state === "done");

/** The options to remember as the user's settings: the form's, without a value that is only
 * Kuulas's (it is not their choice, and the next project may not have it). */
export function savedOptions(specs, form, status) {
  const { options } = validateOptions(specs, form);
  for (const key of doneKeys(status)) delete options[key];
  return options;
}

/** The options to send with this run when some are Kuulas's (they replace the saved ones);
 * undefined when none is, so the saved options apply as before. */
export function requestOptions(specs, form, status) {
  if (doneKeys(status).length === 0) return undefined;
  return validateOptions(specs, form).options;
}

/** The names of the changed items for a collapsed group's header; open groups show none
 * (the controls are right there). Cut to `max` characters with an ellipsis. */
export function summaryText(items, collapsed, max) {
  if (!collapsed || items.length === 0) return "";
  const joined = items.join(", ");
  return joined.length <= max ? joined : `${joined.slice(0, max - 1)}…`;
}

/** Whether a group starts open: what the user last chose wins, else open when it holds a
 * changed value (so nothing set is hidden). */
export function initialOpen(hasChanged, remembered) {
  return typeof remembered === "boolean" ? remembered : hasChanged;
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
