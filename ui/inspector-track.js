// The inspector's Track and Bus sections. Same fields and edits as the track
// headers (set_track / set_bus / solo, the same coalesce keys, so a drag in the
// header and a type in the inspector are one undo step each), plus the things
// the resting header hides: pan, the bus picker, the role. Pure decisions are
// in track-target.js.

import { bindToggle } from "./ab-value.js";
import { t } from "./i18n.js";
import { coalesceKey, patchBus, patchSolo, patchTrack } from "./provisional.js";
import { busMembers, busOptions, roleKey } from "./track-target.js";

// The Bus select's last option: not a bus id, it asks for a new bus.
const NEW_BUS = "__new__";
const GAIN = { min: -60, max: 12, step: 0.1 };
const PAN = { min: -100, max: 100, step: 1 };

/** A label wrapping its control, one grid row of the inspector. */
export function field(labelText, control) {
  const label = document.createElement("label");
  label.className = "inspector-field";
  const name = document.createElement("span");
  name.textContent = labelText;
  label.append(name, control);
  return label;
}

const round1 = (v) => Math.round(v * 10) / 10;
const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

function setIfIdle(input, value) {
  if (document.activeElement !== input && input.value !== String(value)) input.value = value;
}

function readonly(text) {
  const out = document.createElement("output");
  out.className = "inspector-readonly";
  out.textContent = text;
  return out;
}

function checkbox(label, onChange) {
  const box = document.createElement("input");
  box.type = "checkbox";
  box.setAttribute("aria-label", label);
  box.addEventListener("change", (event) => onChange(box.checked, event));
  return box;
}

/**
 * A text field that commits on Enter or blur and cancels on Esc (the value
 * snaps back; Esc itself goes on to take the focus home).
 */
function nameInput(label, read, commit) {
  const input = document.createElement("input");
  input.type = "text";
  input.className = "inspector-name";
  input.setAttribute("aria-label", label);
  input.autocomplete = "off";
  const finish = () => {
    const value = input.value.trim();
    if (value && value !== read()) commit(value);
    else input.value = read();
  };
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      finish();
    } else if (event.key === "Escape") input.value = read();
  });
  input.addEventListener("blur", finish);
  return input;
}

/**
 * Build the sections for the current track and/or bus into `place(name)`
 * (which returns a <details>). `latest()` gives the newest client state.
 * Returns { update(state), focusName() }.
 */
export function buildTrackSections({ target, editor, place, latest, onBusCreated = () => {} }) {
  const parts = [];
  let nameNode = null;

  // A numeric field with the default/custom toggle (ab-value.js).
  function numeric(into, { label, range, toInput, fromInput, key, read, send }) {
    const input = document.createElement("input");
    input.type = "number";
    input.min = range.min;
    input.max = range.max;
    input.step = range.step;
    input.setAttribute("aria-label", label);
    input.addEventListener("input", () => {
      if (input.value === "" || Number.isNaN(Number(input.value))) return;
      send(fromInput(Number(input.value)), key);
    });
    bindToggle(input, {
      key,
      fallback: 0,
      read,
      write(value) {
        input.value = String(toInput(value));
        send(value, key);
      },
      marker(stored) {
        input.classList.toggle("has-ab", stored !== null);
        input.title = stored === null ? "" : t("ui.ab.was", { value: String(toInput(stored)) });
      },
    });
    into.append(field(label, input));
    return input;
  }

  function levels(into, { gainLabel, panLabel, kind, id, lookup, send }) {
    const gain = numeric(into, {
      label: gainLabel,
      range: GAIN,
      toInput: round1,
      fromInput: (v) => clamp(v, GAIN.min, GAIN.max),
      key: coalesceKey(kind, "gain", id),
      read: () => lookup().gain_db,
      send: (value, key) => send("gain_db", value, key),
    });
    const pan = numeric(into, {
      label: panLabel,
      range: PAN,
      toInput: (v) => Math.round(v * 100),
      fromInput: (v) => clamp(v, PAN.min, PAN.max) / 100,
      key: coalesceKey(kind, "pan", id),
      read: () => lookup().pan,
      send: (value, key) => send("pan", value, key),
    });
    return { gain, pan };
  }

  function trackSection(track) {
    const id = track.id;
    const into = place("track");
    const lookup = () => latest().project.tracks.find((item) => item.id === id) ?? track;
    const send = (name, value, key = null) =>
      editor.change({
        op: "set_track",
        args: { track_id: id, [name]: value },
        coalesce: key,
        provisional: (p) => patchTrack(p, id, { [name]: value }),
      });
    const name = nameInput(
      t("ui.track.name"),
      () => lookup().name,
      (value) => send("name", value),
    );
    nameNode = name;
    into.append(field(t("ui.track.name"), name));
    const role = readonly("");
    into.append(field(t("ui.track.role"), role));
    const { gain, pan } = levels(into, {
      gainLabel: t("ui.track.gain"),
      panLabel: t("ui.track.pan"),
      kind: "track",
      id,
      lookup,
      send,
    });
    const bus = document.createElement("select");
    bus.className = "inspector-select";
    bus.setAttribute("aria-label", t("ui.track.bus"));
    for (const option of busOptions(latest().project)) {
      const node = document.createElement("option");
      node.value = option.value;
      bus.append(node);
    }
    const newBus = document.createElement("option");
    newBus.value = NEW_BUS;
    bus.append(newBus);
    bus.addEventListener("change", () => {
      if (bus.value !== NEW_BUS) return send("bus", bus.value || null);
      // Create the bus and route this track to it in one step, then name it.
      bus.value = lookup().bus ?? "";
      editor.change({
        op: "add_bus",
        args: { track_ids: [id] },
        label: t("ui.edit.label.group_bus"),
        done: (response) => {
          const created = response?.project?.buses?.at(-1);
          if (created) onBusCreated(created.id);
        },
      });
    });
    into.append(field(t("ui.track.bus"), bus));
    into.append(field(t("ui.track.voice"), readonly(t("ui.track.voice.none"))));
    const mute = checkbox(t("ui.track.mute"), (checked) => send("mute", checked));
    into.append(field(t("ui.track.mute"), mute));
    const solo = checkbox(t("ui.track.solo"), (_checked, event) => {
      // Like the header: exclusive, Shift adds to the set.
      const exclusive = !event.shiftKey;
      editor.change({
        op: "solo",
        args: { track_id: id, exclusive },
        provisional: (p) => patchSolo(p, id, exclusive),
      });
    });
    into.append(field(t("ui.track.solo"), solo));
    parts.push((state) => {
      const current = state.project.tracks.find((item) => item.id === id);
      if (!current) return;
      setIfIdle(name, current.name);
      role.textContent = t(roleKey(current.kind));
      setIfIdle(gain, round1(current.gain_db));
      setIfIdle(pan, Math.round(current.pan * 100));
      state.project.buses.forEach((item, i) => {
        const text = busOptions(state.project)[i + 1];
        const option = bus.options[i + 1];
        if (!option || option.value === NEW_BUS) return;
        option.textContent = t("ui.bus.option", { letter: text.letter, name: item.name });
      });
      bus.options[0].textContent = t("ui.bus.option_none");
      newBus.textContent = t("ui.bus.option_new");
      if (document.activeElement !== bus) bus.value = current.bus ?? "";
      mute.checked = Boolean(current.mute);
      solo.checked = Boolean(current.solo);
    });
  }

  function busSection(info) {
    const id = info.bus.id;
    const into = place("bus");
    const lookup = () => latest().project.buses.find((item) => item.id === id) ?? info.bus;
    const send = (name, value, key = null) =>
      editor.change({
        op: "set_bus",
        args: { bus_id: id, [name]: value },
        coalesce: key,
        provisional: (p) => patchBus(p, id, { [name]: value }),
      });
    const name = nameInput(
      t("ui.bus.name_field"),
      () => lookup().name,
      (value) => send("name", value),
    );
    if (!nameNode) nameNode = name;
    into.append(field(t("ui.bus.name_field"), name));
    const { gain, pan } = levels(into, {
      gainLabel: t("ui.bus.gain"),
      panLabel: t("ui.bus.pan"),
      kind: "bus",
      id,
      lookup,
      send,
    });
    const mute = checkbox(t("ui.bus.mute"), (checked) => send("mute", checked));
    into.append(field(t("ui.bus.mute"), mute));
    // The model has no nested buses (GUI-DESIGN section 25) and no bus solo yet.
    into.append(field(t("ui.bus.parent"), readonly(t("ui.bus.parent.none"))));
    const members = readonly("");
    into.append(field(t("ui.bus.members"), members));
    parts.push((state) => {
      const current = state.project.buses.find((item) => item.id === id);
      if (!current) return;
      setIfIdle(name, current.name);
      setIfIdle(gain, round1(current.gain_db));
      setIfIdle(pan, Math.round(current.pan * 100));
      mute.checked = Boolean(current.mute);
      members.textContent = String(busMembers(state.project, id));
    });
  }

  if (target.track) trackSection(target.track);
  const busInfo = target.bus ?? (target.merged ? target.trackBus : null);
  if (busInfo) busSection(busInfo);

  return {
    update(state) {
      for (const run of parts) run(state);
    },
    focusName() {
      if (!nameNode) return;
      const details = nameNode.closest("details");
      if (details) details.open = true;
      nameNode.focus();
      nameNode.select();
    },
  };
}
