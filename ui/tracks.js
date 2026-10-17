// Track and bus headers beside the timeline: name, kind, M, S, bus, gain, pan.
// Rows are built once and updated in place, never rebuilt while a slider is
// dragged (rebuilding would drop the pointer capture). Slider drags go through
// the editor: the value shows at once, the edit carries a coalesce key and the
// whole drag is one undo step.
import { formatDb, formatNumber, t } from "./i18n.js";
import { BUS_HEIGHT, layoutRows } from "./lanes.js";
import { MUSIC_HUE, trackHues } from "./paint.js";
import { coalesceKey, patchBus, patchSolo, patchTrack } from "./provisional.js";

const GAIN = { min: -60, max: 12, step: 0.1 };
const PAN = { min: -100, max: 100, step: 1 };
const COMPACT_BELOW_PX = 40;

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

export function createTrackHeaders({ root, editor, actions }) {
  let signature = "";
  let rows = new Map();

  function build(state) {
    root.replaceChildren();
    rows = new Map();
    for (const track of state.project.tracks) rows.set(track.id, buildTrack(track, state.project));
    for (const bus of state.project.buses) rows.set(bus.id, buildBus(bus));
    for (const { node } of rows.values()) root.append(node);
  }

  function buildTrack(track, project) {
    const node = el("section", "track-header");
    node.dataset.track = track.id;
    const top = el("div", "th-top");
    const name = el("button", "track-name", { type: "button", title: t("ui.track.rename") });
    const tag = el("span", `tag kind-${track.kind}`);
    tag.textContent = kindLabel(track.kind);
    tag.title = kindLabel(track.kind);
    const mute = toggle(t("ui.track.mute"), t("ui.track.mute.short"), "mute");
    const solo = toggle(t("ui.track.solo"), t("ui.track.solo.short"), "solo");
    const buttons = el("span", "ms");
    buttons.append(mute, solo);
    top.append(name, tag, buttons);
    const controls = el("div", "th-controls");
    const bus = el("select", "bus-select", { "aria-label": t("ui.track.bus") });
    const none = el("option");
    none.value = "";
    none.textContent = t("ui.track.no_bus");
    bus.append(none);
    for (const item of project.buses) {
      const option = el("option");
      option.value = item.id;
      option.textContent = item.name;
      bus.append(option);
    }
    const gain = slider(t("ui.track.gain"), GAIN);
    const pan = slider(t("ui.track.pan"), PAN);
    controls.append(bus, gain.wrap, pan.wrap);
    node.append(top, controls);
    const id = track.id;
    const send = (field, value, patch, key) =>
      editor.change({
        op: "set_track",
        args: { track_id: id, [field]: value },
        coalesce: key ?? null,
        provisional: (p) => patchTrack(p, id, patch ?? { [field]: value }),
      });

    node.addEventListener("pointerdown", () => actions.currentTrack(id));
    name.addEventListener("dblclick", () => rename(name, id));
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
    bus.addEventListener("change", () => send("bus", bus.value || null));
    gain.input.addEventListener("input", () => {
      const value = Number(gain.input.value);
      gain.output.textContent = formatDb(value);
      send("gain_db", value, undefined, coalesceKey("track", "gain", id));
    });
    gain.input.addEventListener("dblclick", () => send("gain_db", 0, undefined, null));
    pan.input.addEventListener("input", () => {
      const value = Number(pan.input.value) / 100;
      pan.output.textContent = panText(value);
      send("pan", value, undefined, coalesceKey("track", "pan", id));
    });
    pan.input.addEventListener("dblclick", () => send("pan", 0, undefined, null));
    return { node, name, mute, solo, bus, gain, pan, kind: "track" };
  }

  function buildBus(bus) {
    const node = el("section", "track-header bus-header");
    const name = el("span", "bus-name");
    const mute = toggle(t("ui.bus.mute"), t("ui.track.mute.short"), "mute");
    const gain = slider(t("ui.bus.gain"), GAIN);
    const pan = slider(t("ui.bus.pan"), PAN);
    node.append(name, mute, gain.wrap, pan.wrap);
    const id = bus.id;
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
    return { node, name, mute, gain, pan, kind: "bus" };
  }

  // The latest project, for handlers that need a value that may have changed.
  let latest = null;
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
      state.project.tracks.map((track) => [track.id, track.kind]),
      state.project.buses.map((bus) => [bus.id, bus.name]),
      document.documentElement.lang,
    ]);
    if (next !== signature) {
      signature = next;
      build(state);
    }
    const layout = layoutRows(state.project, state.laneHeight);
    const hues = trackHues(state.project);
    for (const row of layout.rows) {
      const parts = rows.get(row.id);
      if (!parts) continue;
      parts.node.style.height = `${row.height}px`;
      parts.node.classList.toggle("compact", row.height < COMPACT_BELOW_PX && row.kind === "track");
      if (parts.kind === "track") {
        const track = state.project.tracks[row.index];
        parts.node.classList.toggle("current", state.focusTrack === track.id);
        const hue = hues.get(track.id);
        parts.node.style.setProperty(
          "--track-colour",
          `var(--track-${hue === MUSIC_HUE ? "music" : hue}-edge)`,
        );
        if (parts.name.isConnected) parts.name.textContent = track.name;
        parts.mute.setAttribute("aria-pressed", String(track.mute));
        parts.solo.setAttribute("aria-pressed", String(track.solo));
        if (document.activeElement !== parts.bus) parts.bus.value = track.bus ?? "";
        setSlider(parts.gain, track.gain_db, formatDb(track.gain_db));
        setSlider(parts.pan, Math.round(track.pan * 100), panText(track.pan));
      } else {
        const bus = state.project.buses.find((item) => item.id === row.id);
        parts.name.textContent = t("ui.bus.name", { name: bus.name });
        parts.mute.setAttribute("aria-pressed", String(bus.mute));
        setSlider(parts.gain, bus.gain_db, formatDb(bus.gain_db));
        setSlider(parts.pan, Math.round(bus.pan * 100), panText(bus.pan));
      }
    }
    root.style.setProperty("--bus-height", `${BUS_HEIGHT}px`);
  }

  return { update };
}
