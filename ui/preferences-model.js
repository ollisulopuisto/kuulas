// The Preferences dialog (Cmd+,) as data. It gathers settings that already exist and keep
// themselves in their own stores (language on the server, the rest in prefs.js); nothing here
// stores anything. `applyField` hands a change to the setter the original menu command uses.
// Pure, no DOM.

import { DEFAULT_FAST, MAX_FAST, MIN_FAST, STEP } from "./fast-speed.js";
import { PREROLL_CHOICES } from "./preroll.js";
import {
  DEFAULT_QUICK_MUTE_S,
  MAX_QUICK_MUTE_S,
  MIN_QUICK_MUTE_S,
  QUICK_MUTE_STEP_S,
} from "./quick-mute.js";
import { STOP_MODES } from "./stop-mode.js";

const LANGUAGES = ["auto", "fi", "en"];

/** The settings, in the order the dialog shows them. */
export const PREFERENCE_FIELDS = [
  {
    id: "language",
    kind: "choice",
    labelKey: "ui.prefs.language",
    options: LANGUAGES.map((value) => ({ value, labelKey: `ui.prefs.language.${value}` })),
  },
  {
    id: "stopMode",
    kind: "choice",
    labelKey: "ui.record.stop_mode",
    options: STOP_MODES.map((value) => ({ value, labelKey: `ui.record.stop_mode.${value}` })),
  },
  {
    id: "preroll",
    kind: "choice",
    labelKey: "ui.record.preroll",
    options: PREROLL_CHOICES.map((seconds) => ({
      value: String(seconds),
      labelKey: seconds === 0 ? "ui.record.preroll.off" : "ui.record.preroll.seconds",
      params: { seconds },
    })),
  },
  { id: "confirmSync", kind: "switch", labelKey: "cmd.sync.confirm" },
  { id: "clipboardLimit", kind: "switch", labelKey: "cmd.view.clipboard_limit" },
  {
    id: "fast",
    kind: "range",
    labelKey: "ui.prefs.fast_speed",
    min: MIN_FAST,
    max: MAX_FAST,
    step: STEP,
  },
  {
    id: "quickMute",
    kind: "range",
    labelKey: "ui.prefs.quick_mute",
    min: MIN_QUICK_MUTE_S,
    max: MAX_QUICK_MUTE_S,
    step: QUICK_MUTE_STEP_S,
    unit: "s",
  },
];

/** Buttons that open the settings dialogs that already exist: the command each one runs. */
export const PREFERENCE_LINKS = [
  { command: "app.colab_settings", labelKey: "cmd.app.colab_settings" },
  { command: "export.automix", labelKey: "cmd.export.automix" },
  { command: "help.keys", labelKey: "cmd.help.keys" },
];

/**
 * The value of each field now: `state` is app.js's state (language, confirm, clipboard, fast
 * listening), `record` the record view's { stopMode, preroll }.
 */
export function currentValues(state, record) {
  return {
    language: state?.languageChoice ?? "auto",
    stopMode: record?.stopMode ?? STOP_MODES[0],
    preroll: String(record?.preroll ?? 60),
    confirmSync: state?.confirmSync !== false,
    clipboardLimit: state?.clipboardLimit !== false,
    fast: state?.fast?.fast ?? DEFAULT_FAST,
    quickMute: state?.quickMuteS ?? DEFAULT_QUICK_MUTE_S,
  };
}

const optionValues = (id) =>
  PREFERENCE_FIELDS.find((field) => field.id === id).options.map((option) => option.value);

/**
 * Set field `id` to `value` through `setters` ({ language(choice), stopMode(mode),
 * preroll(seconds), confirmSync(on), clipboardLimit(on), fast(speed) }), unless it is the value
 * it already has or not a valid one. -> whether a setter was called.
 */
export function applyField(id, value, current, setters) {
  if (!(id in current)) return false;
  let typed = value;
  if (id === "language" || id === "stopMode" || id === "preroll") {
    if (!optionValues(id).includes(String(value))) return false;
    typed = id === "preroll" ? Number(value) : String(value);
  } else if (id === "fast" || id === "quickMute") {
    const { min, max } = PREFERENCE_FIELDS.find((field) => field.id === id);
    typed = Number(value);
    if (!Number.isFinite(typed) || typed < min || typed > max) return false;
  } else {
    typed = Boolean(value);
  }
  if (String(typed) === String(current[id])) return false;
  setters[id](typed);
  return true;
}
