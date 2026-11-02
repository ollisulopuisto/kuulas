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
      media: clip.media ?? null,
      name: clip.name || project.media.find((item) => item.id === clip.media)?.name || clip.id,
    }));
}

/**
 * One row per distinct source file on the track, in the timeline order of each
 * file's first clip. Files share a name, not an identity: two media with the
 * same file name stay separate rows. A clip without media is its own file.
 */
export function trackFileRows(project, trackId) {
  const files = new Map();
  for (const row of trackClipRows(project, trackId)) {
    const key = row.media ?? row.id;
    if (!files.has(key)) {
      const media = project?.media.find((item) => item.id === row.media);
      files.set(key, { key, name: media?.name ?? row.name, clips: [] });
    }
    files.get(key).clips.push(row);
  }
  return [...files.values()];
}

export function createTrackClips({ details, trackId, jump }) {
  const list = document.createElement("ul");
  list.className = "source-list inspector-track-clips";
  details.append(list);
  let signature = "";
  // File-first: one expandable row per source file, clips underneath. Open
  // state survives rebuilds per file; a file holding the selection opens.
  const openFiles = new Map();
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
        return;
      }
      for (const file of trackFileRows(state.project, trackId)) {
        const item = document.createElement("li");
        const group = document.createElement("details");
        group.className = "inspector-clip-file";
        group.open = openFiles.get(file.key) ?? file.clips.some((row) => selected.includes(row.id));
        group.addEventListener("toggle", () => openFiles.set(file.key, group.open));
        const summary = document.createElement("summary");
        summary.textContent = `${file.name} · ${t("ui.inspector.clips.count", { count: file.clips.length })}`;
        group.append(summary);
        const clips = document.createElement("ul");
        clips.className = "source-list inspector-clip-file-clips";
        for (const row of file.clips) {
          const clipItem = document.createElement("li");
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
          clipItem.append(button);
          clips.append(clipItem);
        }
        group.append(clips);
        item.append(group);
        list.append(item);
      }
    },
  };
}
