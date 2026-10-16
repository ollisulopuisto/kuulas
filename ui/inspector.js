import { edit } from "./api.js";
import { formatDb } from "./i18n.js";
import { t } from "./i18n.js";

function field(labelText, control) {
  const label = document.createElement("label");
  label.className = "inspector-field";
  const name = document.createElement("span"); name.textContent = labelText;
  label.append(name, control);
  return label;
}

export function renderInspector(root, state, onState) {
  root.replaceChildren();
  const title = document.createElement("h2"); title.textContent = t("ui.inspector.title"); root.append(title);
  const project = state.project;
  if (!project || state.selection.size !== 1) {
    const empty = document.createElement("p"); empty.textContent = t("ui.inspector.empty"); root.append(empty); return;
  }
  const id = state.selection.values().next().value;
  let selected;
  for (const track of project.tracks) {
    selected = track.clips.find((clip) => clip.id === id);
    if (selected) break;
  }
  if (!selected) return;
  const label = document.createElement("p");
  const media = project.media.find((item) => item.id === selected.media);
  label.textContent = media?.name ?? selected.id; root.append(label);
  const number = (name, value, min, max, step, convert = Number) => {
    const input = document.createElement("input"); input.type = "number"; input.min = min; input.max = max; input.step = step; input.value = value;
    input.setAttribute("aria-label", t(`ui.clip.${name}`));
    input.addEventListener("change", () => void edit("set_clip", { clip_id: id, [name]: convert(input.value) }).then(onState));
    root.append(field(t(`ui.clip.${name}`), input));
  };
  number("gain_db", selected.gain_db, -60, 12, 0.1);
  number("pan", selected.pan, -1, 1, 0.01);
  number("fade_in", selected.fade_in * 1000 / project.rate, 0, 30000, 1, (value) => Math.round(Number(value) * project.rate / 1000));
  number("fade_out", selected.fade_out * 1000 / project.rate, 0, 30000, 1, (value) => Math.round(Number(value) * project.rate / 1000));
  const muted = document.createElement("input"); muted.type = "checkbox"; muted.checked = selected.muted;
  muted.setAttribute("aria-label", t("ui.clip.muted"));
  muted.addEventListener("change", () => void edit("set_clip", { clip_id: id, muted: muted.checked }).then(onState));
  root.append(field(t("ui.clip.muted"), muted));
  const db = document.createElement("p"); db.textContent = formatDb(selected.gain_db); root.append(db);
}
