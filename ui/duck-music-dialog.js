// The style and sidechain settings for Track > Auto > Duck music.
import { enhanceDialog } from "./dialog-keys.js";
import {
  DEFAULTS,
  normaliseSettings,
  reductionAtReference,
  validateSettings,
} from "./duck-sidechain-model.js";

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/** `getSettings`, `onRemember(settings)`, `onApply(settings)`; returns { element, open() }. */
export function createDuckMusicDialog({ t, fmt, getSettings, onRemember, onApply }) {
  const dialog = el("dialog", "cheatsheet duck-music-dialog");
  dialog.setAttribute("aria-labelledby", "duck-music-title");
  const heading = el("h2", "", t("ui.duck_music.title"));
  heading.id = "duck-music-title";

  const form = el("form", "form-grid");
  form.method = "dialog";
  form.noValidate = true;
  const style = el("select", "inspector-select");
  style.id = "duck-music-style";
  style.name = "style";
  for (const [value, key] of [
    ["gaps", "ui.duck_music.style.gaps"],
    ["sidechain", "ui.duck_music.style.sidechain"],
  ]) {
    const option = el("option", "", t(key));
    option.value = value;
    style.append(option);
  }
  const styleRow = el("div", "form-row");
  const styleLabel = el("label", "form-label", t("ui.duck_music.style"));
  styleLabel.htmlFor = style.id;
  styleRow.append(styleLabel, style);
  form.append(styleRow);

  const fields = new Map();
  const row = (key, labelKey, hintKey) => {
    const input = el("input", "form-num");
    input.type = "text";
    input.inputMode = "decimal";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.name = key;
    input.id = `duck-music-${key}`;
    const label = el("label", "form-label", t(labelKey));
    label.htmlFor = input.id;
    const cell = el("div", "form-field");
    const message = el("p", "form-msg");
    message.hidden = true;
    message.id = `${input.id}-msg`;
    input.setAttribute("aria-describedby", message.id);
    cell.append(input, message, el("p", "form-help", t(hintKey)));
    const fieldRow = el("div", "form-row");
    fieldRow.append(label, cell);
    form.append(fieldRow);
    fields.set(key, { input, message, fieldRow });
    input.addEventListener("input", refresh);
  };
  row("ratio", "ui.duck_music.depth", "ui.duck_music.depth_hint");
  row("threshold_db", "ui.duck_music.threshold", "ui.duck_music.threshold_hint");
  row("attack_ms", "ui.duck_music.attack", "ui.duck_music.attack_hint");
  row("release_ms", "ui.duck_music.release", "ui.duck_music.release_hint");

  const summary = el("p", "form-note");
  summary.setAttribute("role", "status");
  const error = el("p", "form-msg");
  error.hidden = true;
  const buttons = el("div", "cheatsheet-footer");
  const cancel = el("button", "button block", t("ui.duck_music.cancel"));
  cancel.type = "button";
  cancel.dataset.icon = "close";
  cancel.dataset.dialogCancel = "";
  const apply = el("button", "button block primary", t("ui.duck_music.apply"));
  apply.type = "submit";
  apply.dataset.icon = "check";
  apply.dataset.dialogPrimary = "";
  buttons.append(cancel, apply);
  form.append(summary, error, buttons);
  dialog.append(heading, form);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  function values() {
    return {
      style: style.value,
      ...Object.fromEntries([...fields].map(([key, field]) => [key, field.input.value])),
    };
  }

  function refresh() {
    const checked = validateSettings(values());
    for (const [key, field] of fields) {
      const messageKey = checked.errors[key];
      field.message.textContent = messageKey
        ? t(messageKey, {
            low: key === "ratio" ? 1 : key === "threshold_db" ? -60 : key === "attack_ms" ? 1 : 10,
            high:
              key === "ratio" ? 20 : key === "threshold_db" ? 0 : key === "attack_ms" ? 500 : 2000,
          })
        : "";
      field.message.hidden = !messageKey;
      field.input.setAttribute("aria-invalid", messageKey ? "true" : "false");
      field.fieldRow.hidden = style.value !== "sidechain";
    }
    const numberValues = checked.options;
    const reduction = reductionAtReference(numberValues.ratio, numberValues.threshold_db);
    summary.textContent =
      style.value === "sidechain"
        ? t("ui.duck_music.depth_result", { db: fmt(reduction) })
        : t("ui.duck_music.gaps_hint");
    apply.disabled = style.value === "sidechain" && !checked.ok;
    return checked;
  }
  style.addEventListener("change", refresh);
  cancel.addEventListener("click", () => dialog.close());
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const checked = refresh();
    if (!checked.ok) return;
    const selected = normaliseSettings(values());
    onRemember(selected);
    dialog.close();
    onApply(checked.options);
  });

  return {
    element: dialog,
    open() {
      const selected = normaliseSettings(getSettings?.() ?? DEFAULTS);
      style.value = selected.style;
      for (const [key, field] of fields) field.input.value = String(selected[key]);
      error.hidden = true;
      refresh();
      if (!dialog.open) dialog.showModal();
      style.focus();
    },
  };
}
