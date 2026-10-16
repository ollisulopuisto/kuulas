import { edit } from "./api.js";
import { formatDb } from "./i18n.js";
import { t } from "./i18n.js";

export function renderTracks(root, project, onState) {
  root.replaceChildren();
  if (!project) return;
  for (const track of project.tracks) {
    const row = document.createElement("section");
    row.className = "track-header";
    row.dataset.track = track.id;
    const title = document.createElement("button");
    title.className = "track-name";
    title.textContent = track.name;
    title.title = t("ui.track.rename");
    title.addEventListener("dblclick", () => {
      const input = document.createElement("input");
      input.value = track.name;
      input.setAttribute("aria-label", t("ui.track.name"));
      title.replaceWith(input); input.focus(); input.select();
      input.addEventListener("change", () => void edit("set_track", { track_id: track.id, name: input.value }).then(onState));
      input.addEventListener("blur", () => input.replaceWith(title), { once: true });
      input.addEventListener("keydown", (event) => { if (event.key === "Enter") input.blur(); if (event.key === "Escape") input.replaceWith(title); });
    });
    row.append(title);
    for (const [key, active] of [["mute", track.mute], ["solo", track.solo]]) {
      const button = document.createElement("button");
      button.className = "small-button";
      button.textContent = t(`ui.track.${key}.short`);
      button.title = t(`ui.track.${key}`);
      button.setAttribute("aria-pressed", String(active));
      button.addEventListener("click", () => void edit("set_track", { track_id: track.id, [key]: !active }).then(onState));
      row.append(button);
    }
    const bus = document.createElement("select");
    bus.setAttribute("aria-label", t("ui.track.bus"));
    const noBus = document.createElement("option"); noBus.value = ""; noBus.textContent = t("ui.track.no_bus"); bus.append(noBus);
    for (const item of project.buses) {
      const option = document.createElement("option"); option.value = item.id; option.textContent = item.name; bus.append(option);
    }
    bus.value = track.bus ?? "";
    bus.addEventListener("change", () => void edit("set_track", { track_id: track.id, bus: bus.value || null }).then(onState));
    row.append(bus);
    for (const [key, min, max, step, value] of [["gain", -60, 12, 0.1, track.gain_db], ["pan", -100, 100, 1, track.pan * 100]]) {
      const label = document.createElement("label"); label.className = "slider-control";
      const range = document.createElement("input"); range.type = "range"; range.min = min; range.max = max; range.step = step; range.value = value;
      range.setAttribute("aria-label", t(`ui.track.${key}`));
      const output = document.createElement("output"); output.textContent = key === "gain" ? formatDb(value) : `${Math.round(value)}`;
      range.addEventListener("input", () => { output.textContent = key === "gain" ? formatDb(Number(range.value)) : String(Math.round(Number(range.value))); });
      range.addEventListener("change", () => void edit("set_track", { track_id: track.id, [key === "pan" ? "pan" : "gain_db"]: key === "pan" ? Number(range.value) / 100 : Number(range.value) }, null, `track-${key}-${track.id}`).then(onState));
      label.append(range, output); row.append(label);
    }
    root.append(row);
  }
  for (const bus of project.buses) {
    const row = document.createElement("section"); row.className = "track-header bus-header";
    const label = document.createElement("span"); label.textContent = t("ui.bus.name", { name: bus.name }); row.append(label);
    root.append(row);
  }
}
