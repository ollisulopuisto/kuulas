// "Mix with the automixer…" (WP68): a modal dialog. The checking and the request bodies are
// pure (automix-model.js); this file is the DOM. Mix closes the dialog and hands the request
// to `onStart`; the job is followed in the notice area by app.js (unchanged).

import {
  advancedBody,
  DEFAULT_AUTOMIX,
  fileNamePreview,
  formatWords,
  LUFS_PRESETS,
  migrateForm,
  validateAutomix,
} from "./automix-model.js";
import {
  groupSpecs,
  optionEnabled,
  optionsToForm,
  validateOptions,
} from "./automix-options-model.js";

const KEY = "kuulas.automix";

function loadForm(storage = globalThis.localStorage) {
  try {
    return migrateForm(JSON.parse(storage.getItem(KEY) ?? "null"));
  } catch {
    return migrateForm(null); // Blocked or damaged: the defaults apply.
  }
}

function saveForm(form, storage = globalThis.localStorage) {
  try {
    storage.setItem(KEY, JSON.stringify(form));
  } catch {
    // Not remembered; it still applies to this run.
  }
}

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/**
 * `api`: { automixerSettings, saveAutomixerSettings }; `t` translates;
 * `onStart(body)` -> Promise queues the job; `pickFolder()` -> Promise<string|null> is the
 * desktop window's folder chooser (null in a plain browser: the folder is typed).
 * Returns { element, open() }.
 */
export function createAutomixDialog({ api, t, onStart, pickFolder = null }) {
  const dialog = el("dialog", "cheatsheet automix-dialog");
  dialog.setAttribute("aria-labelledby", "automix-title");
  const heading = el("h2", "", t("ui.automix.title"));
  heading.id = "automix-title";

  const inputs = {};
  const messages = {};
  const defaults = { dir: "" };

  /** A label cell + control cell row; `control` is any node. Its message sits below. */
  const row = (name, labelKey, control, hintKey) => {
    const wrap = el("div", "automix-row");
    const label = el("label", "automix-label", t(labelKey));
    const cell = el("div", "automix-cell");
    const input = control.matches?.("input") ? control : control.querySelector("input");
    input.id = `automix-${name}`;
    input.name = name;
    input.autocomplete = "off";
    input.spellcheck = false;
    label.htmlFor = input.id;
    const message = el("p", "automix-msg");
    message.id = `automix-${name}-msg`;
    message.hidden = true;
    input.setAttribute("aria-describedby", message.id);
    cell.append(control, message);
    if (hintKey) cell.append(el("p", "automix-hint", t(hintKey)));
    wrap.append(label, cell);
    inputs[name] = input;
    messages[name] = message;
    return wrap;
  };
  const text = (name, inputMode) => {
    const input = el("input");
    input.type = "text";
    if (inputMode) input.inputMode = inputMode;
    inputs[name] = input;
    return input;
  };
  const withButton = (input, button) => {
    const group = el("div", "automix-inline");
    group.append(input, ...(button ? [button] : []));
    return group;
  };
  const chooseButton = (target) => {
    if (!pickFolder) return null;
    const button = el("button", "button block", t("ui.automix.choose"));
    button.type = "button";
    button.dataset.icon = "folder";
    button.addEventListener("click", async () => {
      const picked = await pickFolder();
      if (picked) {
        target.value = picked;
        refresh();
      }
    });
    return button;
  };
  const section = (titleKey) => {
    const wrap = el("section", "automix-section");
    wrap.append(el("h3", "automix-heading", t(titleKey)));
    return wrap;
  };

  // -- Mix ---------------------------------------------------------------------------------
  const summary = el("p", "automix-summary", t("ui.automix.summary"));
  const mix = section("ui.automix.section_mix");
  const lufs = text("targetLufs", "decimal");
  lufs.classList.add("automix-short");
  const presets = el("div", "automix-presets");
  presets.setAttribute("role", "group");
  presets.setAttribute("aria-label", t("ui.automix.presets"));
  const presetButtons = LUFS_PRESETS.map((preset) => {
    const button = el("button", "button", t(preset.key));
    button.type = "button";
    button.addEventListener("click", () => {
      lufs.value = preset.lufs;
      refresh();
    });
    return [preset, button];
  });
  presets.append(...presetButtons.map(([, button]) => button));
  const lufsControl = el("div", "automix-stack");
  lufsControl.append(withButton(lufs), presets);
  const lufsRow = row("targetLufs", "ui.automix.target_lufs", lufsControl, "ui.automix.lufs_hint");

  const adBox = el("input");
  adBox.type = "checkbox";
  adBox.name = "adBreak";
  adBox.id = "automix-adBreak";
  inputs.adBreak = adBox;
  const adLabel = el("label", "automix-check");
  adLabel.append(adBox, el("span", "", t("ui.automix.ad_break")));
  const adGroup = el("div", "automix-ad");
  const spot = text("adSpot", "text");
  spot.placeholder = t("ui.automix.ad_spot_placeholder");
  const duration = text("adDuration", "decimal");
  duration.placeholder = t("ui.automix.ad_duration_placeholder");
  duration.classList.add("automix-short");
  adGroup.append(
    el("p", "automix-hint", t("ui.automix.ad_hint")),
    row("adSpot", "ui.automix.ad_spot", spot, "ui.automix.ad_spot_hint"),
    row("adDuration", "ui.automix.ad_duration", duration, "ui.automix.ad_duration_hint"),
  );
  mix.append(lufsRow, adLabel, adGroup, summary);

  // -- Processing: the automixer's switches, drawn from the server's list (open()) ---------
  const processing = section("ui.automix.section_options");
  processing.hidden = true;
  const optionControls = {};
  let optionSpecs = [];

  const boolControl = (spec) => {
    const wrap = el("div", "automix-optcheck");
    const label = el("label", "automix-check");
    const box = el("input");
    box.type = "checkbox";
    box.name = spec.key;
    box.id = `automix-${spec.key}`;
    label.append(box, el("span", "", t(`ui.automix.opt.${spec.key}`)));
    wrap.append(label, el("p", "automix-hint", t(`ui.automix.opt.${spec.key}.hint`)));
    optionControls[spec.key] = { input: box, wrap };
    return wrap;
  };
  const fieldControl = (spec) => {
    const input = text(spec.key, spec.kind === "number" ? "decimal" : "text");
    if (spec.kind === "number") input.classList.add("automix-short");
    input.placeholder =
      spec.default === null ? t("ui.automix.opt_tool_default") : String(spec.default);
    const wrap = row(
      spec.key,
      `ui.automix.opt.${spec.key}`,
      input,
      `ui.automix.opt.${spec.key}.hint`,
    );
    optionControls[spec.key] = { input, wrap };
    return wrap;
  };
  function buildOptions(specs) {
    optionSpecs = specs;
    processing.replaceChildren(processing.firstChild);
    for (const { id, specs: members } of groupSpecs(specs)) {
      const controls = members.map((spec) =>
        spec.kind === "bool" ? boolControl(spec) : fieldControl(spec),
      );
      if (id === "minimal") {
        processing.append(...controls);
        continue;
      }
      const group = el("details", "automix-group");
      group.dataset.group = id;
      group.append(el("summary", "", t(`ui.automix.group.${id}`)), ...controls);
      processing.append(group);
    }
    processing.hidden = specs.length === 0;
  }
  const optionValues = () => {
    const values = {};
    for (const spec of optionSpecs) {
      const { input } = optionControls[spec.key];
      values[spec.key] = spec.kind === "bool" ? input.checked : input.value;
    }
    return values;
  };
  const setOptionValues = (options) => {
    const values = optionsToForm(optionSpecs, options);
    for (const spec of optionSpecs) {
      const { input } = optionControls[spec.key];
      if (spec.kind === "bool") input.checked = values[spec.key];
      else input.value = values[spec.key];
    }
    // Open a group that holds a changed value, so nothing set is hidden.
    for (const group of processing.querySelectorAll("details")) {
      const keys = optionSpecs.filter((s) => s.group === group.dataset.group).map((s) => s.key);
      group.open = keys.some((key) => options && key in options);
    }
  };

  // -- Output ------------------------------------------------------------------------------
  const out = section("ui.automix.section_output");
  const outputDir = text("outputDir");
  const outRow = row(
    "outputDir",
    "ui.automix.output_dir",
    withButton(outputDir, chooseButton(outputDir)),
  );
  const preview = el("p", "automix-preview");
  const formatNote = el("p", "automix-hint", t("ui.automix.format_note"));
  out.append(outRow, preview, formatNote);

  // -- Advanced ----------------------------------------------------------------------------
  const advanced = el("details", "automix-advanced");
  advanced.append(el("summary", "", t("ui.automix.section_advanced")));
  const tempDir = text("tempDir");
  const cwd = text("cwd");
  advanced.append(
    el("p", "automix-hint", t("ui.automix.advanced_note")),
    row("command", "ui.automix.command", text("command"), "ui.automix.command_hint"),
    row("cwd", "ui.automix.cwd", withButton(cwd, chooseButton(cwd)), "ui.automix.cwd_hint"),
    row(
      "tempDir",
      "ui.automix.temp_dir",
      withButton(tempDir, chooseButton(tempDir)),
      "ui.automix.temp_dir_hint",
    ),
    row("extra", "ui.automix.extra_args", text("extra"), "ui.automix.extra_args_hint"),
  );

  // -- buttons -----------------------------------------------------------------------------
  const error = el("p", "automix-msg automix-error");
  error.setAttribute("role", "alert");
  error.hidden = true;
  const buttons = el("div", "cheatsheet-footer");
  const cancel = el("button", "button block", t("ui.automix.close"));
  cancel.type = "button";
  cancel.dataset.icon = "close";
  cancel.addEventListener("click", () => dialog.close());
  const start = el("button", "button block primary", t("ui.automix.start"));
  start.type = "submit";
  start.dataset.icon = "check";
  buttons.append(cancel, start);

  const form = el("form");
  form.method = "dialog";
  form.noValidate = true;
  form.append(mix, processing, out, advanced, error, buttons);
  dialog.append(heading, form);
  document.body.append(dialog);

  // -- state -------------------------------------------------------------------------------
  const values = () => ({
    targetLufs: inputs.targetLufs.value,
    adBreak: adBox.checked ? "1" : "",
    adSpot: inputs.adSpot.value,
    adDuration: inputs.adDuration.value,
  });

  /** Check the form, show each problem next to its field, enable or disable Mix. */
  function refresh() {
    const form_ = values();
    const { ok: mixOk, errors } = validateAutomix(form_);
    const optionForm = optionValues();
    const checked = validateOptions(optionSpecs, optionForm);
    for (const spec of optionSpecs) {
      const { input, wrap } = optionControls[spec.key];
      input.disabled = !optionEnabled(optionSpecs, optionForm, spec.key);
      wrap.classList.toggle("automix-off", input.disabled);
      const key = checked.errors[spec.key];
      const message = messages[spec.key];
      if (message) {
        message.textContent = key ? t(key, { min: spec.min, max: spec.max }) : "";
        message.hidden = !key;
      }
      if (spec.kind !== "bool") input.setAttribute("aria-invalid", key ? "true" : "false");
    }
    const ok = mixOk && checked.ok;
    for (const name of ["targetLufs", "adSpot", "adDuration"]) {
      const key = errors[name];
      messages[name].textContent = key ? t(key) : "";
      messages[name].hidden = !key;
      inputs[name].setAttribute("aria-invalid", key ? "true" : "false");
    }
    adGroup.hidden = !form_.adBreak;
    for (const [preset, button] of presetButtons) {
      button.setAttribute("aria-pressed", String(inputs.targetLufs.value.trim() === preset.lufs));
    }
    outputDir.placeholder = t("ui.automix.output_placeholder", { path: defaults.dir });
    preview.textContent = t("ui.automix.preview", {
      name: fileNamePreview(`<${t("ui.automix.edit_name")}>`),
      folder: outputDir.value.trim() || defaults.dir,
    });
    start.disabled = !ok;
    return ok;
  }
  form.addEventListener("input", refresh);
  form.addEventListener("change", refresh);

  const showError = (message) => {
    error.textContent = message;
    error.hidden = false;
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    if (!refresh()) return;
    const request = validateAutomix(values());
    try {
      await api.saveAutomixerSettings({
        ...advancedBody({
          command: inputs.command.value,
          cwd: cwd.value,
          tempDir: tempDir.value,
          outputDir: outputDir.value,
          extra: inputs.extra.value,
        }),
        // Without the list (the settings did not load) nothing is sent: stored options stay.
        ...(optionSpecs.length > 0
          ? { options: validateOptions(optionSpecs, optionValues()).options }
          : {}),
      });
      saveForm(values());
      dialog.close();
      await onStart(request.body);
    } catch (e) {
      advanced.open = true;
      showError(e.message);
    }
  });

  return {
    element: dialog,
    async open() {
      const remembered = loadForm();
      for (const key of Object.keys(DEFAULT_AUTOMIX)) {
        if (key === "adBreak") adBox.checked = remembered.adBreak !== "";
        else inputs[key].value = remembered[key];
      }
      error.hidden = true;
      try {
        // What is stored fills the fields; what the defaults would be shows as the hint.
        const answer = await api.automixerSettings();
        const stored = answer.settings ?? {};
        const resolved = answer.resolved ?? {};
        defaults.dir = answer.default_output_dir ?? "";
        const specs = answer.option_specs ?? [];
        if (specs.length !== optionSpecs.length) buildOptions(specs);
        setOptionValues(resolved.options ?? stored.options ?? {});
        inputs.command.value = formatWords(stored.command);
        inputs.command.placeholder = formatWords(resolved.command);
        cwd.value = stored.cwd ?? "";
        cwd.placeholder = resolved.cwd ?? t("ui.automix.cwd_none");
        tempDir.value = stored.temp_dir ?? "";
        tempDir.placeholder = t("ui.automix.temp_placeholder");
        outputDir.value = stored.output_dir ?? "";
        inputs.extra.value = formatWords(stored.extra_args);
        inputs.extra.placeholder = t("ui.automix.extra_args_placeholder");
      } catch (e) {
        showError(e.message);
      }
      refresh();
      if (!dialog.open) dialog.showModal();
      inputs.targetLufs.focus();
    },
  };
}
