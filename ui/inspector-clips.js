// Timeline clips are track properties, not the project's whole-recording library.
import { frameToTime } from "./format.js";
import { t } from "./i18n.js";

/** Stable timeline order, including muted clips and repeated uses of one recording. */
export function trackClipRows(project, trackId) {
  const track = project?.tracks.find((item) => item.id === trackId);
  return [...(track?.clips ?? [])]
    .sort((a, b) => a.start - b.start || a.id.localeCompare(b.id))
    .map((clip) => ({
      id: clip.id,
      track: trackId,
      start: clip.start,
      length: clip.length,
      muted: Boolean(clip.muted),
      name: clip.name || project.media.find((item) => item.id === clip.media)?.name || clip.id,
    }));
}

export function createTrackClips({ details, trackId, jump }) {
  const list = document.createElement("ul");
  list.className = "source-list inspector-track-clips";
  details.append(list);
  let signature = "";
  return {
    update(state) {
      const rows = trackClipRows(state.project, trackId);
      const selected = [...(state.selection ?? [])];
      const next = JSON.stringify([rows, selected, state.project.rate]);
      if (next === signature) return;
      signature = next;
      list.replaceChildren();
      if (!rows.length) {
        const empty = document.createElement("li");
        empty.className = "hint";
        empty.textContent = t("ui.inspector.clips.empty");
        list.append(empty);
      }
      for (const row of rows) {
        const item = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.className = "source-row";
        button.dataset.clip = row.id;
        button.setAttribute("aria-pressed", String(selected.includes(row.id)));
        button.title = t("ui.inspector.clips.jump");
        const name = document.createElement("span");
        name.className = "source-track";
        name.textContent = row.name;
        const meta = document.createElement("span");
        meta.className = "source-where";
        const timing = `${frameToTime(row.start, state.project.rate)} · ${frameToTime(row.length, state.project.rate)}`;
        meta.textContent = row.muted ? `${timing} · ${t("ui.clip.muted")}` : timing;
        button.append(name, meta);
        button.addEventListener("click", () => jump(row.id, row.track, row.start));
        item.append(button);
        list.append(item);
      }
    },
  };
}
