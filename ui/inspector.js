// The inspector: the selected clip's gain, pan, fades, mute and sync group.
// Edits use `set_clip` with coalesce keys, like the track sliders.

import { bindToggle } from "./ab-value.js";
import { formatDb, formatNumber, t } from "./i18n.js";
import { MUSIC_HUE, trackHues } from "./paint.js";
import { coalesceKey, patchClip } from "./provisional.js";
import { panText } from "./tracks.js";

const GAIN = { min: -60, max: 12, step: 0.1 };
const FADE_MAX_MS = 30_000;

/** The one selected clip and its media, or null (nothing or several selected). */
export function selectedClip(state) {
  if (!state.project || state.selection.size !== 1) return null;
  const [id] = state.selection;
  for (const track of state.project.tracks) {
    const clip = track.clips.find((candidate) => candidate.id === id);
    if (clip)
      return {
        clip,
        track,
        media: state.project.media.find((item) => item.id === clip.media) ?? null,
      };
  }
  return null;
}

/** Which sections start open: Level and Sync; the rest wait to be asked for. */
const SECTION_DEFAULTS = { level: true, fades: false, sync: true, details: false };
const SECTIONS_KEY = "kuulas.inspector.sections";

/** The open state of each section from what the user left (JSON), else the defaults. */
export function openSections(saved) {
  const out = { ...SECTION_DEFAULTS };
  try {
    const parsed = JSON.parse(saved);
    for (const name of Object.keys(out)) {
      if (typeof parsed?.[name] === "boolean") out[name] = parsed[name];
    }
  } catch {
    // Nothing saved, or not ours: the defaults.
  }
  return out;
}

function loadSections() {
  try {
    return openSections(localStorage.getItem(SECTIONS_KEY));
  } catch {
    return openSections(null);
  }
}

function saveSections(state) {
  try {
    localStorage.setItem(SECTIONS_KEY, JSON.stringify(state));
  } catch {
    // Not remembered this time.
  }
}

export function syncGroupOf(project, mediaId) {
  return project.sync_groups?.find((group) => mediaId in group.members) ?? null;
}

function field(labelText, control) {
  const label = document.createElement("label");
  label.className = "inspector-field";
  const name = document.createElement("span");
  name.textContent = labelText;
  label.append(name, control);
  return label;
}

export function createInspector({ root, editor }) {
  let builtFor = "";
  let parts = null;

  function build(state, found) {
    root.replaceChildren();
    const title = document.createElement("h2");
    title.textContent = t("ui.inspector.title");
    root.append(title);
    parts = null;
    if (!found) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = t("ui.inspector.empty");
      root.append(empty);
      return;
    }
    const { clip } = found;
    const id = clip.id;
    const send = (name, value, patch = { [name]: value }) =>
      editor.change({
        op: "set_clip",
        args: { clip_id: id, [name]: value },
        coalesce: coalesceKey("clip", name, id),
        provisional: (p) => patchClip(p, id, patch),
      });
    const rate = state.project.rate;
    const heading = document.createElement("p");
    heading.className = "inspector-media";
    root.append(heading);

    // Sections are native <details>: keyboard and screen readers get them for free.
    const open = loadSections();
    const section = (name) => {
      const details = document.createElement("details");
      details.className = "inspector-section";
      details.open = open[name];
      const summary = document.createElement("summary");
      summary.textContent = t(`ui.inspector.${name}`);
      details.append(summary);
      details.addEventListener("toggle", () => {
        open[name] = details.open;
        saveSections(open);
      });
      root.append(details);
      return details;
    };
    let into = root;
    const number = (name, range, toModel) => {
      const input = document.createElement("input");
      input.type = "number";
      input.min = range.min;
      input.max = range.max;
      input.step = range.step;
      input.setAttribute("aria-label", t(`ui.clip.${name}`));
      input.addEventListener("input", () => {
        if (input.value === "" || Number.isNaN(Number(input.value))) return;
        send(name, toModel(Number(input.value)));
      });
      into.append(field(t(`ui.clip.${name}`), input));
      return input;
    };
    into = section("level");
    const gain = number("gain_db", GAIN, (v) => Math.max(GAIN.min, Math.min(GAIN.max, v)));
    const pan = number(
      "pan",
      { min: -100, max: 100, step: 1 },
      (v) => Math.max(-100, Math.min(100, v)) / 100,
    );
    into = section("fades");
    const fadeIn = number("fade_in", { min: 0, max: FADE_MAX_MS, step: 1 }, (v) =>
      Math.round((v * rate) / 1000),
    );
    const fadeOut = number("fade_out", { min: 0, max: FADE_MAX_MS, step: 1 }, (v) =>
      Math.round((v * rate) / 1000),
    );
    // Default/custom toggle (ab-value.js) on every numeric field.
    const clipNow = () => current?.clip;
    const toggleField = (input, name, toInput, fromModel) =>
      bindToggle(input, {
        key: coalesceKey("clip", name, id),
        fallback: 0,
        read: () => clipNow()?.[name] ?? 0,
        write(value) {
          input.value = String(toInput(value));
          send(name, fromModel(value));
        },
        marker(stored) {
          input.classList.toggle("has-ab", stored !== null);
          input.title = stored === null ? "" : t("ui.ab.was", { value: String(toInput(stored)) });
        },
      });
    toggleField(
      gain,
      "gain_db",
      (v) => Math.round(v * 10) / 10,
      (v) => v,
    );
    toggleField(
      pan,
      "pan",
      (v) => Math.round(v * 100),
      (v) => v,
    );
    toggleField(
      fadeIn,
      "fade_in",
      (v) => Math.round((v * 1000) / rate),
      (v) => v,
    );
    toggleField(
      fadeOut,
      "fade_out",
      (v) => Math.round((v * 1000) / rate),
      (v) => v,
    );
    const muted = document.createElement("input");
    muted.type = "checkbox";
    muted.setAttribute("aria-label", t("ui.clip.muted"));
    muted.addEventListener("change", () => send("muted", muted.checked));
    // Mute belongs with level, the first thing you reach for.
    root.querySelector(".inspector-section").append(field(t("ui.clip.muted"), muted));
    const sync = document.createElement("p");
    sync.className = "hint";
    section("sync").append(sync);
    const readout = document.createElement("p");
    readout.className = "hint";
    section("details").append(readout);
    parts = { heading, gain, pan, fadeIn, fadeOut, muted, sync, readout, rate };
  }

  function setNumber(input, value) {
    if (document.activeElement !== input && input.value !== String(value)) input.value = value;
  }

  let current = null;
  function update(state) {
    const found = selectedClip(state);
    current = found;
    const next = `${found?.clip.id ?? ""}|${document.documentElement.lang}`;
    if (next !== builtFor) {
      builtFor = next;
      build(state, found);
    }
    if (!found || !parts) return;
    const { clip, media } = found;
    const group = syncGroupOf(state.project, clip.media);
    parts.heading.textContent = media?.name ?? clip.id;
    const hue = trackHues(state.project).get(found.track.id);
    parts.heading.style.setProperty(
      "--track-colour",
      `var(--track-${hue === MUSIC_HUE ? "music" : hue}-edge)`,
    );
    setNumber(parts.gain, Math.round(clip.gain_db * 10) / 10);
    setNumber(parts.pan, Math.round(clip.pan * 100));
    setNumber(parts.fadeIn, Math.round((clip.fade_in * 1000) / parts.rate));
    setNumber(parts.fadeOut, Math.round((clip.fade_out * 1000) / parts.rate));
    parts.muted.checked = Boolean(clip.muted);
    const where = group ? t("ui.clip.sync.group", { id: group.id }) : t("ui.clip.sync.none");
    parts.sync.textContent = t("ui.clip.sync", { where });
    const length = t("ui.unit.seconds", {
      value: formatNumber(clip.length / parts.rate, { digits: 1 }),
    });
    parts.readout.textContent = `${formatDb(clip.gain_db)} · ${panText(clip.pan)} · ${length}`;
  }

  return { update };
}
