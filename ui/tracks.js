// Track and bus headers beside the timeline: name, kind, M, S, bus, gain, pan.
// Rows are built once and updated in place, never rebuilt while a slider is
// dragged (rebuilding would drop the pointer capture). Slider drags go through
// the editor: the value shows at once, the edit carries a coalesce key and the
// whole drag is one undo step.

import { bindToggle } from "./ab-value.js";
import { busRoleStatus, roleDiffers } from "./bus-role.js";
import { inactiveTracks } from "./focus-layout.js";
import { busHues, busLetter } from "./grammar.js";
import { detectPlatform, formatDb, formatNumber, t } from "./i18n.js";
import { addBusForTrack, NEW_BUS } from "./inspector-track.js";
import { truncateMiddle } from "./labels.js";
import { dragLaneHeight, dragStarted } from "./lane-sizing.js";
import { layoutFor } from "./lanes.js";
import { readoutText, trackReadout } from "./loudness-readout.js";
import { modClick } from "./modifiers.js";
import { monoTag } from "./mono-ask.js";
import { MUSIC_HUE, trackHues } from "./paint.js";
import { coalesceKey, patchBus, patchSolo, patchTrack } from "./provisional.js";
import { parseDbText, parsePanText } from "./value-edit.js";

const GAIN = { min: -60, max: 12, step: 0.1 };
const PAN = { min: -100, max: 100, step: 1 };
const COMPACT_BELOW_PX = 40;
/** Below the smallest lane a user can size (lanes.js MIN_LANE) a header is a focus-mode strip
 *  (WP28): the name only, small. */
const STRIP_BELOW_PX = 24;

/** "L 30", "R 30" or "C" for a pan in -1..1. */
export function panText(pan) {
  const percent = Math.round(pan * 100);
  if (percent === 0) return t("ui.pan.center");
  return t(percent < 0 ? "ui.pan.left" : "ui.pan.right", {
    value: formatNumber(Math.abs(percent)),
  });
}

function kindLabel(kind) {
  const key = `ui.track.kind.${kind}`;
  const text = t(key);
  return text === key ? kind : text;
}

/** The kind tag's icon class, text (for screen readers) and tooltip. */
function paintTag(tag, kind) {
  tag.className = `tag kind-${kind}`;
  tag.textContent = kindLabel(kind);
  tag.title = t("ui.track.kind.cycle", { kind: kindLabel(kind) });
}

function el(tag, className, attrs = {}) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  return node;
}

function toggle(label, shortLabel, kind) {
  const button = el("button", `ms-button ${kind}`, {
    type: "button",
    "aria-pressed": "false",
    title: label,
  });
  button.textContent = shortLabel;
  button.setAttribute("aria-label", label);
  return button;
}

function slider(label, range) {
  const wrap = el("label", "slider-control");
  const input = el("input", "", {
    type: "range",
    min: range.min,
    max: range.max,
    step: range.step,
    "aria-label": label,
  });
  const output = el("output");
  wrap.append(input, output);
  return { wrap, input, output };
}

/**
 * Double-click a gain or pan readout to type an exact value (owner, 2026-10-18): Enter or leaving the
 * field applies it, Esc keeps the old value, and text that is not a value keeps it too.
 * (The slider's own double-click flips between the default and the last custom value, and
 * Alt+double-click on either resets: ab-value.js.)
 * `parse(text)` -> the value or null; `current()` the value now; `text(value)` what to show in the
 * field; `scale` converts the value to the slider's units.
 */
function editableReadout(control, { parse, current, text, format, write, scale = 1 }) {
  const { input, output } = control;
  output.title = t("ui.readout.type_hint");
  output.addEventListener("dblclick", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (output.querySelector("input")) return;
    if (event.altKey) {
      // Alt+double-click resets to the default and forgets the custom value, here as on the slider.
      input.dispatchEvent(new MouseEvent("dblclick", { altKey: true }));
      return;
    }
    const field = el("input", "readout-edit", {
      type: "text",
      inputmode: "decimal",
      "aria-label": output.getAttribute("aria-label") ?? "",
    });
    field.value = text(current());
    const shown = output.textContent;
    output.textContent = "";
    output.append(field);
    field.focus();
    field.select();
    let done = false;
    const finish = (apply) => {
      if (done) return;
      done = true;
      const value = apply ? parse(field.value) : null;
      field.remove();
      if (value === null) {
        output.textContent = shown;
        return;
      }
      input.value = String(value * scale);
      output.textContent = format(value);
      write(value);
    };
    field.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") finish(true);
      else if (e.key === "Escape") finish(false);
    });
    field.addEventListener("blur", () => finish(true));
  });
}

/**
 * Default/custom toggle on a slider (ab-value.js): a tick on the track marks
 * the remembered value, and the tooltip says what it was.
 */
function toggleable(control, { key, fallback, read, write, format, scale = 1 }) {
  const { input, wrap, output } = control;
  bindToggle(input, {
    key,
    fallback,
    read,
    write(value) {
      // The focused slider is not refreshed by update(): show the new value now.
      input.value = String(value * scale);
      output.textContent = format(value);
      write(value);
    },
    marker(stored) {
      wrap.classList.toggle("has-ab", stored !== null);
      if (stored === null) {
        input.title = "";
        return;
      }
      const min = Number(input.min);
      const max = Number(input.max);
      wrap.style.setProperty("--ab-at", `${((stored * scale - min) / (max - min)) * 100}%`);
      input.title = t("ui.ab.was", { value: format(stored) });
    },
  });
}

/**
 * Show a long name shortened in the middle (Finnish names run long, and the
 * end often tells tracks apart: "Anna · varam…foni"); the tooltip and the
 * accessible name keep it whole.
 */
function fitName(node, full) {
  node.textContent = full;
  node.title = full;
  node.setAttribute("aria-label", full);
  if (node.clientWidth === 0 || node.scrollWidth <= node.clientWidth) return;
  let low = 4;
  let high = full.length - 1;
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    node.textContent = truncateMiddle(full, mid);
    if (node.scrollWidth <= node.clientWidth) low = mid;
    else high = mid - 1;
  }
  node.textContent = truncateMiddle(full, low);
}

/**
 * The loudness readout: "−21,3 / −19 LUFS" tinted ok / notice / warn. The tooltip says what it is
 * and carries the numbers, which is all a compact header shows (a tinted dot, see style.css).
 */
function paintLoudness(node, readout) {
  const text = readoutText(readout, formatNumber, t);
  node.hidden = readout.phase === "none";
  node.textContent = text;
  node.dataset.state = readout.phase === "value" ? readout.state : "none";
  node.classList.toggle("stale", Boolean(readout.stale));
  const tip = t("ui.loudness.readout.tip");
  node.title = readout.phase === "value" ? `${text}. ${tip}` : tip;
}

export function createTrackHeaders({ root, editor, actions, onBusCreated = () => {} }) {
  let signature = "";
  let rows = new Map();

  // Rows follow the lane layout: a bus header above its member tracks.
  function build(state) {
    root.replaceChildren();
    rows = new Map();
    for (const row of layoutFor(state).rows) {
      let parts;
      if (row.kind === "track") {
        parts = buildTrack(state.project.tracks[row.index], state.project);
        // A one-track bus merged into its track (owner, 2026-10-18): the bus
        // badge before the name and a bus fader with the levels.
        if (row.merged) mergeBus(parts, busIndexOf(state.project, row.bus));
      } else if (row.kind === "bus") parts = buildBus(state.project.buses[row.index], row.index);
      // A group gap: plain space, so each bus reads as its own block.
      else parts = { node: el("div", "group-gap", { "aria-hidden": "true" }), kind: "gap" };
      rows.set(row.id, parts);
      root.append(parts.node);
    }
  }

  const busIndexOf = (project, id) => project.buses.findIndex((bus) => bus.id === id);

  function mergeBus(parts, index) {
    const bus = latestProject().buses[index];
    const id = bus.id;
    parts.node.classList.add("merged");
    const badge = el("span", "bus-badge", { title: t("ui.bus.name", { name: bus.name }) });
    badge.textContent = busLetter(index);
    parts.node.querySelector(".th-top").prepend(badge);
    const label = el("span", "fader-label", { "aria-hidden": "true" });
    label.textContent = t("ui.bus.fader");
    const fader = slider(t("ui.bus.gain"), GAIN);
    fader.wrap.classList.add("bus-fader");
    fader.input.addEventListener("input", () => {
      const value = Number(fader.input.value);
      fader.output.textContent = formatDb(value);
      editor.change({
        op: "set_bus",
        args: { bus_id: id, gain_db: value },
        coalesce: coalesceKey("bus", "gain", id),
        provisional: (p) => patchBus(p, id, { gain_db: value }),
      });
    });
    parts.node.querySelector(".th-controls").append(label, fader.wrap);
    parts.busFader = { control: fader, id };
  }

  function buildTrack(track, project) {
    const node = el("section", "track-header");
    node.dataset.track = track.id;
    const top = el("div", "th-top");
    // The name is a label, not a tab stop (rename: double-click; Enter on the
    // current track arrives with WP5), which keeps the resting view's controls few.
    const name = el("button", "track-name", {
      type: "button",
      title: t("ui.track.rename"),
      tabindex: "-1",
    });
    // The kind tag is a button: a click cycles speech / music (Alt+Mod+K).
    const tag = el("button", `tag kind-${track.kind}`, { type: "button", tabindex: "-1" });
    paintTag(tag, track.kind);
    // Flag beside the kind tag when the track's kind differs from its bus's role; a click
    // gives it the role (bus-role.js). Shown by update().
    const roleBadge = el("button", "role-badge", { type: "button", tabindex: "-1" });
    roleBadge.textContent = "!";
    roleBadge.hidden = true;
    const channelTag = el("span", "channel-tag");
    // Integrated loudness against the target (WP49); filled in by update() from the analysis.
    const loudness = el("span", "loudness-readout");
    loudness.hidden = true;
    const mute = toggle(t("ui.track.mute"), t("ui.track.mute.short"), "mute");
    const solo = toggle(t("ui.track.solo"), t("ui.track.solo.short"), "solo");
    const buttons = el("span", "ms");
    buttons.append(mute, solo);
    // The bus picker is compact: its option text starts with the bus letter,
    // which is what shows in the narrow select (the badge of the group).
    const bus = el("select", "bus-select", { "aria-label": t("ui.track.bus") });
    const none = el("option");
    none.value = "";
    none.textContent = t("ui.bus.option_none");
    bus.append(none);
    project.buses.forEach((item, i) => {
      const option = el("option");
      option.value = item.id;
      option.textContent = t("ui.bus.option", { letter: busLetter(i), name: item.name });
      bus.append(option);
    });
    const newBus = el("option");
    newBus.value = NEW_BUS;
    newBus.textContent = t("ui.bus.option_new");
    bus.append(newBus);
    top.append(name, tag, roleBadge, channelTag, loudness, bus, buttons);
    const controls = el("div", "th-controls");
    const gain = slider(t("ui.track.gain"), GAIN);
    const pan = slider(t("ui.track.pan"), PAN);
    pan.wrap.classList.add("pan");
    controls.append(gain.wrap, pan.wrap);
    // A thin grab zone on the bottom edge: drag to size this lane, double-click to reset it.
    const grip = el("div", "lane-grip", { title: t("ui.track.resize"), "aria-hidden": "true" });
    node.append(top, controls, grip);
    const id = track.id;
    grip.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      const startY = event.clientY;
      const startHeight = node.getBoundingClientRect().height;
      grip.setPointerCapture(event.pointerId);
      // Only a real drag sizes the lane: a click or a slip on the 6 px border does nothing.
      let dragging = false;
      const move = (e) => {
        dragging = dragging || dragStarted({ startY, y: e.clientY });
        if (dragging)
          actions.setLaneHeight(id, dragLaneHeight({ startHeight, startY, y: e.clientY }));
      };
      const done = () => {
        grip.removeEventListener("pointermove", move);
        grip.removeEventListener("pointerup", done);
        grip.removeEventListener("pointercancel", done);
      };
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", done);
      grip.addEventListener("pointercancel", done);
    });
    grip.addEventListener("dblclick", () => actions.setLaneHeight(id, null));
    const send = (field, value, patch, key) =>
      editor.change({
        op: "set_track",
        args: { track_id: id, [field]: value },
        coalesce: key ?? null,
        provisional: (p) => patchTrack(p, id, patch ?? { [field]: value }),
      });

    // Pressing the header itself (not its buttons, sliders or name field) makes the track
    // current AND selects it: range operations then act on it alone; Cmd+click adds (WP83).
    // One handler, on press: the header re-lays out once it is current, so a later "click"
    // could be lost and leave the selection on the previous track.
    node.addEventListener("pointerdown", (event) => {
      const inside = event.target.closest?.("button, input, select, textarea, .lane-grip");
      const add = modClick(event, detectPlatform());
      actions.currentTrack(id, { mode: inside ? "follow" : add ? "add" : "select" });
    });
    node.addEventListener("focusin", () => actions.currentTrack(id, { mode: "follow" }));
    node.addEventListener("contextmenu", (event) => actions.contextMenu("track", id, event));
    name.addEventListener("dblclick", () => rename(name, id));
    tag.addEventListener("click", () => actions.cycleKind(id));
    roleBadge.addEventListener("click", () => actions.matchRole(id));
    mute.addEventListener("click", () => {
      const now = !lookup(id).mute;
      send("mute", now);
    });
    solo.addEventListener("click", (event) => {
      const exclusive = !event.shiftKey;
      editor.change({
        op: "solo",
        args: { track_id: id, exclusive },
        provisional: (p) => patchSolo(p, id, exclusive),
      });
    });
    bus.addEventListener("change", () => {
      if (bus.value !== NEW_BUS) return send("bus", bus.value || null);
      // Create the bus and put this track on it in one step.
      bus.value = lookup(id).bus ?? "";
      addBusForTrack(editor, id, onBusCreated);
    });
    gain.input.addEventListener("input", () => {
      const value = Number(gain.input.value);
      gain.output.textContent = formatDb(value);
      send("gain_db", value, undefined, coalesceKey("track", "gain", id));
    });
    editableReadout(gain, {
      parse: (value) => parseDbText(value, GAIN),
      current: () => lookup(id).gain_db,
      text: (value) => String(Math.round(value * 10) / 10),
      format: formatDb,
      write: (value) => send("gain_db", value, undefined, coalesceKey("track", "gain", id)),
    });
    toggleable(gain, {
      key: coalesceKey("track", "gain", id),
      fallback: 0,
      read: () => lookup(id).gain_db,
      write: (value) => send("gain_db", value, undefined, coalesceKey("track", "gain", id)),
      format: formatDb,
    });
    pan.input.addEventListener("input", () => {
      const value = Number(pan.input.value) / 100;
      pan.output.textContent = panText(value);
      send("pan", value, undefined, coalesceKey("track", "pan", id));
    });
    editableReadout(pan, {
      parse: parsePanText,
      current: () => lookup(id).pan,
      text: panText,
      format: panText,
      write: (value) => send("pan", value, undefined, coalesceKey("track", "pan", id)),
      scale: 100,
    });
    toggleable(pan, {
      key: coalesceKey("track", "pan", id),
      fallback: 0,
      read: () => lookup(id).pan,
      write: (value) => send("pan", value, undefined, coalesceKey("track", "pan", id)),
      format: panText,
      scale: 100,
    });
    return {
      node,
      name,
      tag,
      roleBadge,
      channelTag,
      loudness,
      mute,
      solo,
      bus,
      gain,
      pan,
      kind: "track",
    };
  }

  function buildBus(bus, index) {
    const node = el("section", "track-header bus-header");
    // A group header, like a folder: badge, name and mute on top, levels below.
    const top = el("div", "th-top");
    // The disclosure chevron folds the bus to its header row (a double-click on the
    // header does the same); its name and state are set in update().
    const chevron = el("button", "bus-chevron", { type: "button" });
    const badge = el("span", "bus-badge", { "aria-hidden": "true" });
    badge.textContent = busLetter(index);
    const name = el("span", "bus-name");
    // Two lines (owner, 2026-10-18: the levels were too small to use on one line):
    // badge, name and M on top, the bus level and pan below, always shown.
    const mute = toggle(t("ui.bus.mute"), t("ui.track.mute.short"), "mute");
    const buttons = el("span", "ms");
    buttons.append(mute);
    const controls = el("div", "th-controls");
    const gain = slider(t("ui.bus.gain"), GAIN);
    const pan = slider(t("ui.bus.pan"), PAN);
    pan.wrap.classList.add("pan");
    const faderLabel = el("span", "fader-label", { "aria-hidden": "true" });
    faderLabel.textContent = t("ui.bus.fader");
    controls.append(faderLabel, gain.wrap, pan.wrap);
    // The bus's role; with an asterisk and a Reapply button while some track differs.
    const roleLabel = el("span", "bus-role");
    roleLabel.hidden = true;
    const reapply = el("button", "bus-reapply", { type: "button", tabindex: "-1" });
    reapply.textContent = t("ui.bus.reapply");
    reapply.hidden = true;
    top.append(chevron, badge, name, roleLabel, reapply, buttons);
    node.append(top, controls);
    const id = bus.id;
    node.addEventListener("pointerdown", () => actions.currentBus(id));
    node.addEventListener("focusin", () => actions.currentBus(id));
    chevron.addEventListener("click", () => actions.toggleBus(id));
    reapply.addEventListener("click", () => actions.reapplyRole(id));
    // Double-click the header itself, not its buttons, sliders or the name being edited.
    node.addEventListener("dblclick", (event) => {
      if (!event.target.closest("button, input, select, label, output")) actions.toggleBus(id);
    });
    node.addEventListener("contextmenu", (event) => actions.contextMenu("bus", id, event));
    const send = (field, value, key) =>
      editor.change({
        op: "set_bus",
        args: { bus_id: id, [field]: value },
        coalesce: key,
        provisional: (p) => patchBus(p, id, { [field]: value }),
      });
    mute.addEventListener("click", () => send("mute", !currentBus(id).mute, null));
    gain.input.addEventListener("input", () => {
      const value = Number(gain.input.value);
      gain.output.textContent = formatDb(value);
      send("gain_db", value, coalesceKey("bus", "gain", id));
    });
    pan.input.addEventListener("input", () => {
      const value = Number(pan.input.value) / 100;
      pan.output.textContent = panText(value);
      send("pan", value, coalesceKey("bus", "pan", id));
    });
    editableReadout(gain, {
      parse: (value) => parseDbText(value, GAIN),
      current: () => currentBus(id).gain_db,
      text: (value) => String(Math.round(value * 10) / 10),
      format: formatDb,
      write: (value) => send("gain_db", value, coalesceKey("bus", "gain", id)),
    });
    toggleable(gain, {
      key: coalesceKey("bus", "gain", id),
      fallback: 0,
      read: () => currentBus(id).gain_db,
      write: (value) => send("gain_db", value, coalesceKey("bus", "gain", id)),
      format: formatDb,
    });
    editableReadout(pan, {
      parse: parsePanText,
      current: () => currentBus(id).pan,
      text: panText,
      format: panText,
      write: (value) => send("pan", value, coalesceKey("bus", "pan", id)),
      scale: 100,
    });
    toggleable(pan, {
      key: coalesceKey("bus", "pan", id),
      fallback: 0,
      read: () => currentBus(id).pan,
      write: (value) => send("pan", value, coalesceKey("bus", "pan", id)),
      format: panText,
      scale: 100,
    });
    return { node, name, roleLabel, reapply, mute, gain, pan, chevron, kind: "bus" };
  }

  // The latest project, for handlers that need a value that may have changed.
  let latest = null;
  const latestProject = () => latest.project;
  const lookup = (id) => latest.project.tracks.find((track) => track.id === id);
  const currentBus = (id) => latest.project.buses.find((bus) => bus.id === id);

  function rename(button, id) {
    const input = el("input", "track-rename", { type: "text", "aria-label": t("ui.track.name") });
    input.value = lookup(id).name;
    button.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const finish = (commit) => {
      if (done) return;
      done = true;
      const value = input.value.trim();
      input.replaceWith(button);
      if (commit && value && value !== lookup(id).name) {
        editor.change({
          op: "set_track",
          args: { track_id: id, name: value },
          provisional: (p) => patchTrack(p, id, { name: value }),
        });
      }
    };
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") finish(true);
      else if (event.key === "Escape") {
        event.stopPropagation();
        finish(false);
      }
    });
    input.addEventListener("blur", () => finish(true));
  }

  function setSlider(control, value, text) {
    if (document.activeElement !== control.input && control.input.value !== String(value)) {
      control.input.value = value;
    }
    control.output.textContent = text;
  }

  function update(state) {
    latest = state;
    if (!state.project) {
      root.replaceChildren();
      signature = "";
      return;
    }
    const next = JSON.stringify([
      state.project.tracks.map((track) => [track.id, track.kind, track.bus ?? ""]),
      state.project.buses.map((bus) => [bus.id, bus.name]),
      [...(state.collapsedBuses ?? [])],
      document.documentElement.lang,
    ]);
    if (next !== signature) {
      signature = next;
      build(state);
    }
    const layout = layoutFor(state);
    const hues = trackHues(state.project);
    const busHue = busHues(state.project);
    const dimmed = inactiveTracks(state);
    for (const row of layout.rows) {
      const parts = rows.get(row.id);
      if (!parts) continue;
      parts.node.style.height = `${row.height}px`;
      if (parts.kind === "gap") continue;
      parts.node.classList.toggle("group-end", Boolean(row.last));
      // The bus spine runs from the bus header down through its members.
      const group = row.bus ? busHue.get(row.bus) : null;
      parts.node.toggleAttribute("data-bus", Boolean(group));
      if (group) {
        parts.node.style.setProperty("--bus-spine", `var(--bus-${group}-spine)`);
        parts.node.style.setProperty("--bus-band", `var(--bus-${group}-band)`);
        parts.node.style.setProperty("--bus-text", `var(--bus-${group}-text)`);
      }
      parts.node.classList.toggle("compact", row.height < COMPACT_BELOW_PX && row.kind === "track");
      parts.node.classList.toggle("strip", row.height < STRIP_BELOW_PX && row.kind === "track");
      if (parts.kind === "track") {
        const track = state.project.tracks[row.index];
        parts.node.classList.toggle("current", state.focusTrack === track.id);
        parts.node.classList.toggle("scope-dim", dimmed.has(track.id));
        const hue = hues.get(track.id);
        parts.node.style.setProperty(
          "--track-colour",
          `var(--track-${hue === MUSIC_HUE ? "music" : hue}-edge)`,
        );
        if (parts.name.isConnected) fitName(parts.name, track.name);
        if (!parts.tag.classList.contains(`kind-${track.kind}`)) paintTag(parts.tag, track.kind);
        const differs = roleDiffers(state.project, track);
        parts.roleBadge.hidden = !differs;
        if (differs) {
          const role = kindLabel(state.project.buses.find((item) => item.id === track.bus).kind);
          const text = t("ui.track.role_differs", { role });
          parts.roleBadge.title = text;
          parts.roleBadge.setAttribute("aria-label", text);
        }
        const channels = monoTag(track, state.project);
        parts.channelTag.hidden = channels === null;
        parts.channelTag.textContent = channels ? t(`ui.track.tag.${channels}`) : "";
        paintLoudness(parts.loudness, trackReadout(state.loudness, track.id));
        parts.mute.setAttribute("aria-pressed", String(track.mute));
        parts.solo.setAttribute("aria-pressed", String(track.solo));
        if (document.activeElement !== parts.bus) parts.bus.value = track.bus ?? "";
        setSlider(parts.gain, track.gain_db, formatDb(track.gain_db));
        setSlider(parts.pan, Math.round(track.pan * 100), panText(track.pan));
        if (parts.busFader) {
          const bus = state.project.buses.find((item) => item.id === parts.busFader.id);
          if (bus) setSlider(parts.busFader.control, bus.gain_db, formatDb(bus.gain_db));
        }
      } else {
        const bus = state.project.buses.find((item) => item.id === row.id);
        parts.name.textContent = bus.name;
        parts.node.title = t("ui.bus.name", { name: bus.name });
        parts.node.classList.toggle("no-members", row.members === 0);
        parts.node.classList.toggle("collapsed", Boolean(row.collapsed));
        // A bus with fewer than two tracks has nothing to fold (a single track merges
        // into its own header).
        parts.chevron.hidden = row.members < 2;
        parts.chevron.setAttribute("aria-expanded", String(!row.collapsed));
        const verb = t(row.collapsed ? "cmd.bus.expand" : "cmd.bus.collapse");
        parts.chevron.setAttribute("aria-label", verb);
        parts.chevron.title = verb;
        parts.chevron.textContent = row.collapsed ? "\u25B8" : "\u25BE";
        const status = busRoleStatus(state.project, bus.id);
        parts.roleLabel.hidden = status.role === null;
        parts.reapply.hidden = status.differ === 0;
        if (status.role !== null) {
          const mark = status.differ > 0 ? " *" : "";
          parts.roleLabel.textContent = `${kindLabel(status.role)}${mark}`;
          parts.roleLabel.title =
            status.differ > 0
              ? t("ui.bus.role_partial", { differ: status.differ, total: status.total })
              : t("ui.bus.role", { role: kindLabel(status.role) });
        }
        parts.mute.setAttribute("aria-pressed", String(bus.mute));
        setSlider(parts.gain, bus.gain_db, formatDb(bus.gain_db));
        setSlider(parts.pan, Math.round(bus.pan * 100), panText(bus.pan));
      }
    }
  }

  return { update };
}
