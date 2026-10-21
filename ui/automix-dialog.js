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
  parseWords,
  remoteBody,
  remoteNote,
  remoteRows,
  validateAutomix,
} from "./automix-model.js";
import {
  balanceChoice,
  balanceValue,
  changedItems,
  DONE_IN_KUULAS,
  doneStatus,
  groupSpecs,
  initialOpen,
  optionEnabled,
  optionsToForm,
  prefillOptions,
  requestOptions,
  savedOptions,
  summaryText,
  unsupportedChanged,
  validateOptions,
} from "./automix-options-model.js";
import { enhanceDialog } from "./dialog-keys.js";
import { createPluginField } from "./plugin-field.js";

const KEY = "kuulas.automix";
// The two options whose items are plug-ins: a field with suggestions and chips. Their hint
// is a placeholder only (never a value), so an empty field still means the tool's default.
const PLUGIN_FIELDS = {
  speech_plugins: "ui.automix.plugin_placeholder_speech",
  music_plugins: "ui.automix.plugin_placeholder_music",
};

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
 * `prefs` (ui/prefs.js) remembers which option groups the user opened or closed.
 * Returns { element, open() }.
 */
export function createAutomixDialog({
  api,
  t,
  onStart,
  pickFolder = null,
  prefs = null,
  onSetMusicLevel = null,
  onLevelBlocks = null,
  onDuckMusic = null,
}) {
  const dialog = el("dialog", "cheatsheet automix-dialog");
  dialog.setAttribute("aria-labelledby", "automix-title");
  const heading = el("h2", "", t("ui.automix.title"));
  heading.id = "automix-title";

  const inputs = {};
  const messages = {};
  const defaults = { dir: "" };

  /** A label cell + control cell row; `control` is any node. Its message sits below. */
  const row = (name, labelKey, control, hintKey) => {
    const wrap = el("div", "automix-row form-row");
    const label = el("label", "automix-label form-label", t(labelKey));
    const cell = el("div", "automix-cell form-field");
    const input = control.matches?.("input,select")
      ? control
      : control.querySelector("input,select");
    input.id = `automix-${name}`;
    input.name = name;
    input.autocomplete = "off";
    input.spellcheck = false;
    label.htmlFor = input.id;
    const message = el("p", "automix-msg form-msg");
    message.id = `automix-${name}-msg`;
    message.hidden = true;
    input.setAttribute("aria-describedby", message.id);
    cell.append(control, message);
    if (hintKey) cell.append(el("p", "automix-hint form-help", t(hintKey)));
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
    const group = el("div", "automix-inline form-inline");
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
    const wrap = el("section", "automix-section form-section");
    wrap.append(el("h3", "automix-heading form-heading", t(titleKey)));
    return wrap;
  };

  // -- Mix ---------------------------------------------------------------------------------
  const summary = el("p", "automix-summary form-note", t("ui.automix.summary"));
  const mix = section("ui.automix.section_mix");
  const lufs = text("targetLufs", "decimal");
  lufs.classList.add("automix-short", "form-num");
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
  const adLabel = el("label");
  adLabel.append(adBox, el("span", "", t("ui.automix.ad_break")));
  // The check row: the box on the field column, its description under its text (FORMS.md).
  const adRow = el("div", "check-row");
  adRow.append(adLabel, el("p", "automix-hint form-help", t("ui.automix.ad_hint")));
  const adGroup = el("div", "automix-ad form-sub");
  const spot = text("adSpot", "text");
  spot.placeholder = t("ui.automix.ad_spot_placeholder");
  const duration = text("adDuration", "decimal");
  duration.placeholder = t("ui.automix.ad_duration_placeholder");
  duration.classList.add("automix-short", "form-num");
  adGroup.append(
    row("adSpot", "ui.automix.ad_spot", spot, "ui.automix.ad_spot_hint"),
    row("adDuration", "ui.automix.ad_duration", duration, "ui.automix.ad_duration_hint"),
  );
  // One line when the render runs on another Mac (the "Run on another Mac" group below).
  const remoteLine = el("p", "automix-remote-note form-note");
  remoteLine.hidden = true;
  mix.append(lufsRow, adRow, adGroup, remoteLine, summary);

  // -- Processing: the automixer's switches, drawn from the server's list (open()) ---------
  const processing = section("ui.automix.section_options");
  processing.hidden = true;
  // The other Mac's plug-ins could not be listed: the fields stay plain text.
  const pluginNote = el("p", "form-note", t("ui.automix.remote_plugins_failed"));
  pluginNote.hidden = true;
  const optionControls = {};
  let installedPlugins = [];
  let optionSpecs = [];
  let capabilities = {}; // what the installed automixer accepts (server probe)
  let doneData = {}; // what Kuulas already did (server: done_in_kuulas)
  let offered = []; // option keys where a saved value differs from Kuulas's
  let doneNow = {}; // doneStatus of the live form

  const boolControl = (spec) => {
    const wrap = el("div", "automix-optcheck check-row");
    const label = el("label");
    const box = el("input");
    box.type = "checkbox";
    box.name = spec.key;
    box.id = `automix-${spec.key}`;
    label.append(box, el("span", "", t(`ui.automix.opt.${spec.key}`)));
    wrap.append(label, el("p", "automix-hint form-help", t(`ui.automix.opt.${spec.key}.hint`)));
    optionControls[spec.key] = { input: box, wrap };
    // A stage Kuulas can have done (Level blocks): the same badge, a line that says why, Reset.
    if (spec.key in DONE_IN_KUULAS) {
      const done = doneBlock(spec, box);
      wrap.append(done.node);
      optionControls[spec.key].done = done;
    }
    return wrap;
  };
  const pluginControl = (spec) => {
    const field = createPluginField({
      t,
      placeholder: t(PLUGIN_FIELDS[spec.key]),
      onChange: () => refresh(),
    });
    field.setInstalled(installedPlugins);
    const wrap = row(
      spec.key,
      `ui.automix.opt.${spec.key}`,
      field.element,
      `ui.automix.opt.${spec.key}.hint`,
    );
    optionControls[spec.key] = { input: field.input, wrap, field };
    return wrap;
  };
  const fieldControl = (spec) => {
    if (spec.key in PLUGIN_FIELDS) return pluginControl(spec);
    if (spec.key === "balance_speakers_max_db") {
      const select = el("select", "automix-balance-choice");
      for (const choice of ["automatic", "fine_tune", "keep"]) {
        const option = el("option", "", t(`ui.automix.balance_choice.${choice}`));
        option.value = choice;
        select.append(option);
      }
      const wrap = row(
        spec.key,
        `ui.automix.opt.${spec.key}`,
        select,
        `ui.automix.opt.${spec.key}.hint`,
      );
      const note = el("p", "automix-msg form-msg", t("ui.automix.balance_capability_missing"));
      note.hidden = true;
      wrap.lastChild.append(note);
      optionControls[spec.key] = {
        input: select,
        wrap,
        note,
        hint: wrap.querySelector(".automix-hint"),
      };
      return wrap;
    }
    const input = text(spec.key, spec.kind === "number" ? "decimal" : "text");
    if (spec.kind === "number") input.classList.add("automix-short", "form-num");
    input.placeholder =
      spec.default === null ? t("ui.automix.opt_tool_default") : String(spec.default);
    const wrap = row(
      spec.key,
      `ui.automix.opt.${spec.key}`,
      input,
      `ui.automix.opt.${spec.key}.hint`,
    );
    // A warning (not an error: Mix still works) when the installed tool lacks this switch.
    const note = el("p", "automix-msg form-msg", t("ui.automix.capability_missing"));
    note.hidden = true;
    wrap.lastChild.append(note);
    optionControls[spec.key] = { input, wrap, note };
    if (spec.key in DONE_IN_KUULAS) {
      const done = doneBlock(spec, input);
      wrap.lastChild.append(done.node);
      optionControls[spec.key].done = done;
    }
    return wrap;
  };
  // What Kuulas already did for this option (docs/FORMAT.md, mix_done): a badge, a line that
  // says why, Reset; or an offer when a saved value differs; or a hint that it went stale.
  const smallButton = (label, onClick) => {
    const button = el("button", "button small", label);
    button.type = "button";
    button.addEventListener("click", onClick);
    return button;
  };
  const doneBlock = (spec, input) => {
    const node = el("div", "automix-done form-help");
    node.hidden = true;
    const badge = el("span", "automix-badge", t("ui.automix.done_badge"));
    // A number option (the music level) is a field; a stage (block levelling) is a checkbox
    // that Kuulas leaves unticked. Each has its own words and its own "do it again".
    const stage = spec.kind === "bool";
    const musicDuck = spec.key === "music_duck";
    const set = (value) => {
      if (stage) input.checked = value;
      else input.value = String(value);
      refresh();
    };
    const text = el(
      "span",
      "automix-done-text",
      stage
        ? t(musicDuck ? "ui.automix.done_text_duck" : "ui.automix.done_text_block")
        : t("ui.automix.done_text", { default: spec.default }),
    );
    const reset = smallButton(t("ui.automix.done_reset"), () => set(spec.default));
    const offer = el("span", "automix-done-text");
    const use = smallButton("", () => set(offerValue.offset));
    const stale = el(
      "span",
      "automix-done-text",
      t(
        musicDuck
          ? "ui.automix.done_stale_duck"
          : stage
            ? "ui.automix.done_stale_block"
            : "ui.automix.done_stale",
      ),
    );
    const again = smallButton(
      t(
        musicDuck
          ? "ui.automix.done_again_duck"
          : stage
            ? "ui.automix.done_again_block"
            : "ui.automix.done_again",
      ),
      () => {
        dialog.close();
        (musicDuck ? onDuckMusic : stage ? onLevelBlocks : onSetMusicLevel)?.();
      },
    );
    const lacking = el("span", "automix-done-text", t("ui.automix.done_unsupported"));
    const offerValue = { offset: 0 };
    const parts = { badge, text, reset, offer, use, stale, again, lacking };
    node.append(badge, text, reset, offer, use, stale, again, lacking);
    return { node, parts, offerValue };
  };
  function showDone(status) {
    for (const spec of optionSpecs) {
      const done = optionControls[spec.key].done;
      if (!done) continue;
      const s = status[spec.key];
      const { badge, text, reset, offer, use, stale, again, lacking } = done.parts;
      done.node.hidden = !s;
      const is = (state) => s?.state === state;
      for (const part of [badge, text, reset]) part.hidden = !is("done");
      lacking.hidden = !(is("done") && s.unsupported);
      for (const part of [offer, use]) part.hidden = !is("offer");
      for (const part of [stale, again]) part.hidden = !is("stale");
      if (is("offer")) {
        done.offerValue.offset = s.offset;
        offer.textContent = t("ui.automix.done_offer", { value: s.offset });
        use.textContent = t("ui.automix.done_use", { value: s.offset });
      }
    }
  }
  // Each group is a disclosure: one full-width header button (chevron, title, a badge with
  // the number of changed settings, and while folded the names of the changed ones) over a
  // body that animates its height. Open/closed is remembered (prefs) and wins over the
  // automatic "open when something is changed".
  const GROUPS_KEY = "automixGroups";
  const groups = new Map(); // id -> { node, head, body, badge, names, open }
  const remembered = () => prefs?.getJson(GROUPS_KEY, {}) ?? {};
  const MAX_NAMES = 40;
  const setGroupOpen = (group, open, { remember = false } = {}) => {
    group.open = open;
    group.head.setAttribute("aria-expanded", String(open));
    group.body.inert = !open;
    group.node.classList.toggle("is-open", open);
    if (remember) prefs?.setJson(GROUPS_KEY, { ...remembered(), [group.id]: open });
    updateGroupSummaries();
  };
  const optionWords = {
    label: (spec) => t(`ui.automix.opt.${spec.key}`),
    on: t("ui.automix.state_on"),
    off: t("ui.automix.state_off"),
  };
  function updateGroupSummaries() {
    const changed = changedItems(optionSpecs, optionValues(), optionWords);
    for (const group of groups.values()) {
      const items = changed[group.id] ?? [];
      group.badge.hidden = items.length === 0;
      group.badge.textContent = t("ui.automix.changed_count", { n: items.length });
      group.node.classList.toggle("has-changes", items.length > 0);
      group.names.textContent = summaryText(items, !group.open, MAX_NAMES);
      group.names.title = items.join(", ");
    }
  }
  const allGroups = (open) => {
    for (const group of groups.values()) setGroupOpen(group, open, { remember: true });
  };
  const toggles = el("div", "automix-group-tools");
  for (const [key, open] of [
    ["ui.automix.expand_all", true],
    ["ui.automix.collapse_all", false],
  ]) {
    const button = el("button", "button ghost", t(key));
    button.type = "button";
    button.addEventListener("click", () => allGroups(open));
    toggles.append(button);
  }
  function buildOptions(specs) {
    optionSpecs = specs;
    groups.clear();
    processing.replaceChildren(processing.firstChild, pluginNote);
    const cards = [];
    for (const { id, specs: members } of groupSpecs(specs)) {
      const controls = members.map((spec) =>
        spec.kind === "bool" ? boolControl(spec) : fieldControl(spec),
      );
      if (id === "minimal") {
        processing.append(...controls);
        continue;
      }
      const node = el("div", "automix-group form-card");
      node.dataset.group = id;
      const heading = el("h4", "automix-group-heading");
      const head = el("button", "automix-group-head");
      head.type = "button";
      const chevron = el("span", "automix-chevron", "\u25B8");
      chevron.setAttribute("aria-hidden", "true");
      const names = el("span", "automix-group-names");
      const badge = el("span", "automix-badge");
      badge.hidden = true;
      head.append(chevron, el("span", "automix-group-title", t(`ui.automix.group.${id}`)));
      head.append(badge, names);
      heading.append(head);
      const body = el("div", "automix-group-body");
      body.id = `automix-group-${id}`;
      head.setAttribute("aria-controls", body.id);
      const inner = el("div", "automix-group-inner form-section");
      inner.append(...controls);
      body.append(inner);
      node.append(heading, body);
      const group = { id, node, head, body, badge, names, open: false };
      head.addEventListener("click", () => setGroupOpen(group, !group.open, { remember: true }));
      groups.set(id, group);
      cards.push(node);
    }
    if (cards.length > 0) processing.append(toggles, ...cards);
    processing.hidden = specs.length === 0;
  }
  const optionValues = () => {
    const values = {};
    for (const spec of optionSpecs) {
      const { input, field } = optionControls[spec.key];
      if (field) values[spec.key] = formatWords(field.items());
      else if (spec.key === "balance_speakers_max_db") {
        values[spec.key] = String(balanceValue(input.value));
      } else values[spec.key] = spec.kind === "bool" ? input.checked : input.value;
    }
    return values;
  };
  const setOptionValues = (options) => {
    const values = optionsToForm(optionSpecs, options);
    for (const spec of optionSpecs) {
      const { input, field } = optionControls[spec.key];
      if (field) field.setItems(parseWords(values[spec.key]));
      else if (spec.kind === "bool") input.checked = values[spec.key];
      else if (spec.key === "balance_speakers_max_db") {
        input.value = balanceChoice(values[spec.key]);
      } else input.value = values[spec.key];
    }
    // Open a group that holds a changed value, so nothing set is hidden, unless the user
    // opened or closed it themselves.
    const kept = remembered();
    for (const group of groups.values()) {
      const hasChanged = optionSpecs.some(
        (s) => s.group === group.id && options && s.key in options,
      );
      setGroupOpen(group, initialOpen(hasChanged, kept[group.id]));
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
  const preview = el("p", "automix-preview form-help");
  const formatNote = el("p", "automix-hint form-help", t("ui.automix.format_note"));
  // Both say where the file goes: under the folder field, at its left edge.
  outRow.lastChild.append(preview, formatNote);
  out.append(outRow);

  // -- Run on another Mac ------------------------------------------------------------------
  const remote = el("details", "automix-advanced automix-remote");
  remote.append(el("summary", "", t("ui.automix.remote_section")));
  const remoteBox = el("input");
  remoteBox.type = "checkbox";
  remoteBox.name = "remoteEnabled";
  remoteBox.id = "automix-remoteEnabled";
  const remoteCheck = el("div", "check-row");
  const remoteLabel = el("label");
  remoteLabel.append(remoteBox, el("span", "", t("ui.automix.remote_enabled")));
  remoteCheck.append(
    remoteLabel,
    el("p", "automix-hint form-help", t("ui.automix.remote_enabled_hint")),
  );
  const remoteTest = el("button", "button", t("ui.automix.remote_test"));
  remoteTest.type = "button";
  remoteTest.dataset.icon = "check";
  const remoteResult = el("ul", "automix-remote-result form-help");
  remoteResult.setAttribute("aria-live", "polite");
  remoteResult.hidden = true;
  const remoteRowsEl = el("div", "form-section");
  remote.append(remoteRowsEl);
  remoteRowsEl.append(
    remoteCheck,
    row("remoteHost", "ui.automix.remote_host", text("remoteHost"), "ui.automix.remote_host_hint"),
    row("remoteCwd", "ui.automix.remote_cwd", text("remoteCwd"), "ui.automix.remote_cwd_hint"),
    row(
      "remoteWorkDir",
      "ui.automix.remote_work_dir",
      text("remoteWorkDir"),
      "ui.automix.remote_work_dir_hint",
    ),
  );
  const remoteActions = el("div", "form-actions");
  remoteActions.append(remoteTest);
  remoteRowsEl.append(remoteActions, remoteResult);
  const remoteFields = () => ({
    enabled: remoteBox.checked,
    host: inputs.remoteHost.value,
    cwd: inputs.remoteCwd.value,
    workDir: inputs.remoteWorkDir.value,
  });
  remoteTest.addEventListener("click", async () => {
    remoteTest.disabled = true;
    remoteTest.textContent = t("ui.automix.remote_testing");
    remoteResult.replaceChildren();
    try {
      const { enabled: _enabled, ...fields } = remoteBody(remoteFields());
      const rows = remoteRows(await api.testAutomixerRemote(fields), t);
      for (const { label, status, statusText, detail } of rows) {
        const item = el("li", `automix-remote-${status}`);
        item.append(el("strong", "", `${statusText}: `), label);
        if (detail) item.append(el("span", "", ` — ${detail}`));
        remoteResult.append(item);
      }
    } catch (e) {
      remoteResult.append(el("li", "automix-remote-failed", e.message));
    }
    remoteResult.hidden = false;
    remoteTest.textContent = t("ui.automix.remote_test");
    remoteTest.disabled = false;
  });

  // -- Advanced ----------------------------------------------------------------------------
  const advanced = el("details", "automix-advanced");
  advanced.append(el("summary", "", t("ui.automix.section_advanced")));
  const tempDir = text("tempDir");
  const cwd = text("cwd");
  const advancedRows = el("div", "form-section");
  advanced.append(advancedRows);
  advancedRows.append(
    el("p", "form-note", t("ui.automix.advanced_note")),
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
  const error = el("p", "automix-msg automix-error form-msg");
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
  cancel.dataset.dialogCancel = "";
  start.dataset.dialogPrimary = "";
  buttons.append(cancel, start);

  const form = el("form", "form-grid");
  form.method = "dialog";
  form.noValidate = true;
  form.append(mix, processing, out, remote, advanced, error, buttons);
  dialog.append(heading, form);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  // -- state -------------------------------------------------------------------------------
  const values = () => ({
    targetLufs: inputs.targetLufs.value,
    adBreak: adBox.checked ? "1" : "",
    adSpot: inputs.adSpot.value,
    adDuration: inputs.adDuration.value,
  });

  /** The installed plug-ins for the suggestions; none (a plain text field) when the scan
   * fails or finds nothing. */
  async function installed() {
    try {
      const answer = await api.plugins?.();
      pluginNote.hidden = !answer?.remote_failed;
      return Array.isArray(answer?.plugins) ? answer.plugins : [];
    } catch {
      return [];
    }
  }

  /** Check the form, show each problem next to its field, enable or disable Mix. */
  function refresh() {
    const form_ = values();
    const { ok: mixOk, errors } = validateAutomix(form_);
    const optionForm = optionValues();
    const checked = validateOptions(optionSpecs, optionForm);
    let pluginsOk = true;
    for (const spec of optionSpecs) {
      const { input, wrap, field } = optionControls[spec.key];
      const off = !optionEnabled(optionSpecs, optionForm, spec.key);
      if (field) field.setDisabled(off);
      else input.disabled = off;
      wrap.classList.toggle("automix-off", off);
      // A typed name no installed plug-in matches is a warning, and Mix waits for it.
      const unmatched = field && !off && field.unmatched();
      if (unmatched) pluginsOk = false;
      const key = checked.errors[spec.key] ?? (unmatched ? "ui.automix.plugin_unmatched" : null);
      const message = messages[spec.key];
      if (message) {
        message.textContent = key ? t(key, { min: spec.min, max: spec.max }) : "";
        message.hidden = !key;
      }
      if (spec.kind !== "bool") input.setAttribute("aria-invalid", key ? "true" : "false");
    }
    const lacking = unsupportedChanged(optionSpecs, optionForm, capabilities);
    for (const spec of optionSpecs) {
      const { note } = optionControls[spec.key];
      if (note) note.hidden = !lacking.includes(spec.key);
    }
    doneNow = doneStatus(optionSpecs, doneData, optionForm, offered, capabilities);
    showDone(doneNow);
    updateGroupSummaries();
    const ok = mixOk && checked.ok && pluginsOk;
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
    remoteLine.textContent = remoteNote(
      { enabled: remoteBox.checked, host: inputs.remoteHost.value.trim() },
      t,
    );
    remoteLine.hidden = remoteLine.textContent === "";
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
          remote: remoteFields(),
        }),
        // Without the list (the settings did not load) nothing is sent: stored options stay.
        // A value that is only Kuulas's is sent with this run, not saved as the user's own.
        ...(optionSpecs.length > 0
          ? { options: savedOptions(optionSpecs, optionValues(), doneNow) }
          : {}),
      });
      saveForm(values());
      dialog.close();
      const sent = requestOptions(optionSpecs, optionValues(), doneNow);
      await onStart(sent ? { ...request.body, options: sent } : request.body);
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
        capabilities = answer.capabilities ?? {};
        installedPlugins = await installed();
        for (const { field } of Object.values(optionControls)) {
          field?.setInstalled(installedPlugins);
        }
        if (specs.length !== optionSpecs.length) buildOptions(specs);
        doneData = answer.done_in_kuulas ?? {};
        const savedOptions = resolved.options ?? stored.options ?? {};
        const withBalanceDefault = { ...savedOptions };
        if (!("balance_speakers_max_db" in withBalanceDefault)) {
          withBalanceDefault.balance_speakers_max_db = answer.balance_cap ?? 6;
        }
        const filled = prefillOptions(specs, doneData, withBalanceDefault);
        offered = filled.offered;
        setOptionValues(filled.options);
        const balance = optionControls.balance_speakers_max_db;
        if (balance?.hint) {
          balance.hint.hidden = answer.balance_hand_adjusted !== true;
        }
        inputs.command.value = formatWords(stored.command);
        inputs.command.placeholder = formatWords(resolved.command);
        cwd.value = stored.cwd ?? "";
        cwd.placeholder = resolved.cwd ?? t("ui.automix.cwd_none");
        tempDir.value = stored.temp_dir ?? "";
        tempDir.placeholder = t("ui.automix.temp_placeholder");
        outputDir.value = stored.output_dir ?? "";
        const savedRemote = stored.remote ?? {};
        remoteBox.checked = savedRemote.enabled === true;
        inputs.remoteHost.value = savedRemote.host ?? "";
        inputs.remoteCwd.value = savedRemote.cwd ?? "";
        inputs.remoteWorkDir.value = savedRemote.work_dir ?? "";
        inputs.remoteWorkDir.placeholder = resolved.remote?.work_dir ?? "";
        remoteResult.hidden = true;
        remote.open = remoteBox.checked;
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
