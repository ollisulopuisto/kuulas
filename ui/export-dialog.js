// File > Export mix (options)… and Export all tracks (options)… (WP11, WP74): a modal dialog.
// The mix dialog asks what to export (the whole mix, the in/out range, or some tracks as
// stems), the format and its quality, a loudness target, a file name and whether to choose the
// folder first, and always says that muted tracks and tracks not soloed come out as silence.
// The choices and rules are pure data (export-dialog-model.js); this file is the DOM, in the
// inspector's two-column form grid. Export closes the dialog and hands the request to `onStart`.

import { enhanceDialog } from "./dialog-keys.js";
import {
  bitrateChoices,
  defaultBitrate,
  depthChoices,
  dialogFormats,
  exportBody,
  hasRange,
  LUFS_PRESETS,
  lufsPresetOf,
  mergeMemory,
  pickBitrate,
  pickDepth,
  silentTracks,
  sizeEstimate,
  startOptions,
  validateOptions,
} from "./export-dialog-model.js";
import { sizeText } from "./media-copy-model.js";

function element(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

/** A form row (FORMS.md): the label, then the field column with its help lines under it. */
function row(label, control, ...help) {
  const field = element("div", { className: "form-row export-row" });
  field.append(element("span", { className: "form-label", textContent: label }), control, ...help);
  return field;
}

/**
 * `t` translates; `formats()` -> [{ id, label }] the server offers (null until known);
 * `canChooseFolder()` -> whether a native folder chooser exists (the desktop window);
 * `context()` -> Promise<{ server, memory, state, frames }>: GET /api/export-settings, the
 * per-project scope memory, { project, inPoint, outPoint } and the length of the edit in frames;
 * `saveMemory(memory)` keeps the scope memory; `onStart({ what, body, ask })` runs the export.
 * Returns { element, open(kind) } with kind "mix" or "tracks" (all tracks).
 */
export function createExportDialog({ t, formats, canChooseFolder, context, saveMemory, onStart }) {
  const dialog = element("dialog", { className: "cheatsheet automix-dialog export-dialog" });
  dialog.setAttribute("aria-labelledby", "export-dialog-title");
  const heading = element("h2", { id: "export-dialog-title" });
  const note = element("p", { className: "form-note" });

  const form = element("form", { method: "dialog", className: "form-grid" });

  // What
  const scopeBox = element("div", { className: "form-choices", role: "radiogroup" });
  scopeBox.setAttribute("aria-label", t("ui.exportdialog.what"));
  const scopeInputs = {};
  const scopeLabels = {};
  for (const id of ["whole", "range", "tracks"]) {
    const input = element("input", { type: "radio", name: "scope", value: id });
    const text = element("span");
    scopeInputs[id] = input;
    scopeLabels[id] = text;
    scopeBox.append(element("label", { className: "form-choice" }, input, text));
  }
  const trackList = element("div", { className: "export-tracks" });
  const allButton = element("button", {
    type: "button",
    className: "button block",
    textContent: t("ui.exportdialog.tracks_all"),
  });
  const noneButton = element("button", {
    type: "button",
    className: "button block",
    textContent: t("ui.exportdialog.tracks_none"),
  });
  const trackTools = element("div", { className: "export-tracks-tools" }, allButton, noneButton);
  const tracksHint = element("p", {
    className: "form-help",
    textContent: t("ui.exportdialog.what_tracks_hint"),
  });
  const tracksBox = element(
    "div",
    { className: "export-tracks-box" },
    tracksHint,
    trackTools,
    trackList,
  );
  // The track list belongs to "What": it opens in the field column, under the choices.
  const whatRow = row(t("ui.exportdialog.what"), scopeBox, tracksBox);

  // Format and quality
  const formatSelect = element("select", { name: "format", className: "inspector-select" });
  const depthSelect = element("select", { name: "depth", className: "inspector-select" });
  const bitrateSelect = element("select", { name: "bitrate", className: "inspector-select" });
  const sizeNote = element("p", { className: "form-help" });
  const formatRow = row(t("ui.exportdialog.format"), formatSelect, sizeNote);
  const depthRow = row(t("ui.exportdialog.depth"), depthSelect);
  const bitrateRow = row(t("ui.exportdialog.bitrate"), bitrateSelect);

  // Loudness
  const lufsSelect = element("select", { name: "lufs", className: "inspector-select" });
  for (const preset of [...LUFS_PRESETS, { id: "custom" }]) {
    lufsSelect.append(
      element("option", { value: preset.id, textContent: t(`ui.exportdialog.lufs_${preset.id}`) }),
    );
  }
  const lufsInput = element("input", { type: "number", name: "lufs_value", step: "0.5" });
  lufsInput.min = "-70";
  lufsInput.max = "0";
  const lufsNote = element("p", {
    className: "form-help",
    textContent: t("ui.exportdialog.lufs_note"),
  });
  const lufsRow = row(t("ui.exportdialog.lufs"), lufsSelect, lufsNote);
  const lufsValueRow = row(t("ui.exportdialog.lufs_value"), lufsInput);

  // Name and folder
  const nameInput = element("input", {
    type: "text",
    name: "name",
    className: "inspector-name",
    autocomplete: "off",
  });
  const nameNote = element("p", {
    className: "form-help",
    textContent: t("ui.exportdialog.name_note"),
  });
  const nameRow = row(t("ui.exportdialog.name"), nameInput, nameNote);
  const ask = element("input", { type: "checkbox", name: "ask" });
  const askRow = row(t("ui.exportdialog.ask"), ask);

  // Mute and solo: always said.
  const silence = element("p", { className: "export-silence", role: "note" });
  const problem = element("p", { className: "form-msg", role: "alert" });

  const buttons = element("div", { className: "cheatsheet-footer" });
  const cancel = element("button", {
    type: "button",
    className: "button block",
    textContent: t("ui.exportdialog.cancel"),
  });
  cancel.dataset.icon = "close";
  cancel.addEventListener("click", () => dialog.close());
  const start = element("button", {
    type: "submit",
    className: "button block primary",
    textContent: t("ui.exportdialog.start"),
  });
  start.dataset.icon = "check";
  cancel.dataset.dialogCancel = "";
  start.dataset.dialogPrimary = "";
  buttons.append(cancel, start);

  form.append(
    whatRow,
    formatRow,
    depthRow,
    bitrateRow,
    lufsRow,
    lufsValueRow,
    nameRow,
    askRow,
    silence,
    problem,
    buttons,
  );
  dialog.append(heading, note, form);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  // The state of the form while the dialog is open.
  let kind = "mix";
  let options = null;
  let ctx = null;

  const stems = () => options.scope === "tracks" || options.scope === "alltracks";
  const marks = () => ({ inPoint: ctx.state.inPoint, outPoint: ctx.state.outPoint });

  function fillSelect(select, items, current) {
    select.replaceChildren(
      ...items.map(({ value, text }) =>
        element("option", { value: String(value), textContent: text }),
      ),
    );
    select.value = String(current);
  }

  function paintQuality() {
    const depths = depthChoices(options.format);
    const rates = bitrateChoices(options.format);
    depthRow.hidden = depths.length === 0;
    bitrateRow.hidden = rates.length === 0;
    if (depths.length > 0) {
      options.bitDepth = pickDepth(options.format, options.bitDepth);
      fillSelect(
        depthSelect,
        depths.map((bits) => ({
          value: bits,
          text:
            bits === 32 && options.format === "wav"
              ? t("ui.exportdialog.depth_float")
              : t("ui.exportdialog.depth_value", { bits }),
        })),
        options.bitDepth,
      );
    }
    if (rates.length > 0) {
      options.kbps = pickBitrate(options.format, options.kbps);
      const standard = defaultBitrate(options.format);
      fillSelect(
        bitrateSelect,
        rates.map((kbps) => ({
          value: kbps,
          text: t(
            kbps === standard ? "ui.exportdialog.bitrate_default" : "ui.exportdialog.bitrate_value",
            {
              kbps,
            },
          ),
        })),
        options.kbps,
      );
    }
    const frames =
      options.scope === "range" && hasRange(marks())
        ? ctx.state.outPoint - ctx.state.inPoint
        : ctx.frames;
    const rate = ctx.state.project?.rate ?? 48000;
    const bytes = stems()
      ? null
      : sizeEstimate({
          format: options.format,
          kbps: options.kbps,
          bitDepth: options.bitDepth,
          seconds: frames / rate,
          rate,
        });
    sizeNote.hidden = bytes === null;
    sizeNote.textContent =
      bytes === null ? "" : t("ui.exportdialog.size", { size: sizeText(bytes) });
  }

  function paintTracks() {
    const tracks = ctx.state.project?.tracks ?? [];
    trackList.replaceChildren(
      ...tracks.map((track) => {
        const box = element("input", { type: "checkbox", value: track.id });
        box.checked = options.trackIds.includes(track.id);
        box.addEventListener("change", () => {
          const chosen = new Set(options.trackIds);
          if (box.checked) chosen.add(track.id);
          else chosen.delete(track.id);
          options.trackIds = tracks.map((item) => item.id).filter((id) => chosen.has(id));
          paintErrors();
        });
        return element(
          "label",
          { className: "form-choice" },
          box,
          element("span", { textContent: track.name }),
        );
      }),
    );
  }

  function paintSilence() {
    const silent = silentTracks(ctx.state.project);
    const rule = t("ui.exportdialog.silent_rule");
    const detail =
      silent.length > 0
        ? t("ui.exportdialog.silent_list", { tracks: silent.map((track) => track.name).join(", ") })
        : t("ui.exportdialog.silent_none");
    silence.textContent = `${rule} ${detail}`;
  }

  function paintErrors() {
    const errors = validateOptions(options, { marks: marks() });
    problem.textContent = errors.map((key) => t(key)).join(" ");
    start.disabled = errors.length > 0;
  }

  function paint() {
    const mix = kind === "mix";
    whatRow.hidden = !mix;
    tracksBox.hidden = !(mix && options.scope === "tracks");
    const rangeOk = hasRange(marks());
    scopeInputs.range.disabled = !rangeOk;
    scopeLabels.whole.textContent = t("ui.exportdialog.what_whole");
    scopeLabels.range.textContent = t(
      rangeOk ? "ui.exportdialog.what_range" : "ui.exportdialog.what_range_none",
    );
    scopeLabels.tracks.textContent = t("ui.exportdialog.what_tracks");
    for (const [id, input] of Object.entries(scopeInputs)) input.checked = options.scope === id;
    const showLufs = !stems();
    lufsRow.hidden = !showLufs;
    lufsNote.hidden = !showLufs;
    const preset = lufsPresetOf(options.lufs);
    const custom = lufsSelect.value === "custom" || preset === "custom";
    lufsSelect.value = custom ? "custom" : preset;
    lufsValueRow.hidden = !(showLufs && custom);
    lufsInput.value = options.lufs === null ? "" : String(options.lufs);
    ask.checked = options.ask;
    askRow.hidden = !canChooseFolder();
    nameInput.placeholder = t("ui.exportdialog.name_placeholder", {
      project: ctx.server?.title ?? "",
    });
    paintQuality();
    paintSilence();
    paintErrors();
  }

  for (const [id, input] of Object.entries(scopeInputs)) {
    input.addEventListener("change", () => {
      options.scope = id;
      paint();
    });
  }
  allButton.addEventListener("click", () => {
    options.trackIds = (ctx.state.project?.tracks ?? []).map((track) => track.id);
    paintTracks();
    paintErrors();
  });
  noneButton.addEventListener("click", () => {
    options.trackIds = [];
    paintTracks();
    paintErrors();
  });
  formatSelect.addEventListener("change", () => {
    options.format = formatSelect.value;
    options.kbps = null;
    paintQuality();
  });
  depthSelect.addEventListener("change", () => {
    options.bitDepth = Number(depthSelect.value);
    paintQuality();
  });
  bitrateSelect.addEventListener("change", () => {
    options.kbps = Number(bitrateSelect.value);
    paintQuality();
  });
  lufsSelect.addEventListener("change", () => {
    const preset = LUFS_PRESETS.find((item) => item.id === lufsSelect.value);
    if (preset) options.lufs = preset.lufs;
    else if (options.lufs === null || lufsPresetOf(options.lufs) !== "custom") options.lufs = -18;
    paint();
  });
  lufsInput.addEventListener("input", () => {
    options.lufs = lufsInput.value === "" ? Number.NaN : Number(lufsInput.value);
    paintErrors();
  });
  nameInput.addEventListener("input", () => {
    options.name = nameInput.value;
  });
  ask.addEventListener("change", () => {
    options.ask = ask.checked;
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (validateOptions(options, { marks: marks() }).length > 0) return;
    const request = exportBody(options, marks());
    saveMemory(mergeMemory(ctx.memory, options));
    dialog.close();
    void onStart(request);
  });

  return {
    element: dialog,
    async open(which) {
      kind = which;
      ctx = await context();
      const server = which === "mix" ? ctx.server : { mix: ctx.server?.tracks };
      options = startOptions({
        formats: formats(),
        server,
        memory: ctx.memory,
        marks: marks(),
        project: ctx.state.project,
      });
      if (which === "tracks") options.scope = "alltracks";
      heading.textContent = t(`ui.exportdialog.${which}_title`);
      note.textContent = t(`ui.exportdialog.${which}_note`);
      fillSelect(
        formatSelect,
        dialogFormats(formats()).map((format) => ({ value: format.id, text: format.label })),
        options.format,
      );
      nameInput.value = "";
      lufsSelect.value = lufsPresetOf(options.lufs);
      paintTracks();
      paint();
      if (!dialog.open) dialog.showModal();
      formatSelect.focus();
    },
  };
}
