// The inspector's Source section: the recording's file name, a mini map of the whole
// recording (used solid, cut hatched, unused outlined; this clip boxed), "Part n of m",
// and the other clips of the recording. Click a row: select that clip and move the play
// cursor there. The numbers come from source-map.js; the colours are design tokens.

import { formatClock, t } from "./i18n.js";
import {
  clipSpan,
  FLICKS_PER_SECOND,
  otherClips,
  partOf,
  segments,
  summaryText,
} from "./source-map.js";

const seconds = (flicks) => flicks / FLICKS_PER_SECOND;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** Build the section's body into `details`; `update(found, map, project)` redraws it. */
export function createSourceSection({ details, jump }) {
  const summary = details.querySelector("summary");
  const note = el("span", "inspector-summary");
  summary.append(note);

  const file = el("p", "inspector-source-file");
  const map = el("div", "source-map");
  map.setAttribute("role", "img");
  map.setAttribute("aria-label", t("ui.inspector.source.map"));
  const legend = el("ul", "source-legend");
  for (const kind of ["used", "cut", "unused", "this"]) {
    const item = el("li");
    item.append(el("i", `source-key source-${kind}`), t(`ui.inspector.source.${kind}`));
    legend.append(item);
  }
  const part = el("p", "hint source-part");
  const heading = el("h3", "source-others");
  const list = el("ul", "source-list");
  details.append(file, map, legend, part, heading, list);

  function update(found, data, project) {
    const { clip, media } = found;
    file.textContent = media?.name ?? clip.id;
    map.replaceChildren();
    list.replaceChildren();
    note.textContent = data ? summaryText(data, t) : "";
    if (!data) {
      part.textContent = t("ui.inspector.source.loading");
      heading.textContent = "";
      return;
    }
    for (const seg of segments(data)) {
      const bar = el("span", `source-seg source-${seg.kind}`);
      bar.style.left = `${seg.left}%`;
      bar.style.width = `${seg.width}%`;
      map.append(bar);
    }
    const span = clipSpan(data, clip.id);
    if (span) {
      const mark = el("span", "source-seg source-this");
      mark.style.left = `${span.left}%`;
      mark.style.width = `${span.width}%`;
      map.append(mark);
    }
    const own = partOf(data, clip.id);
    part.textContent = own ? t("ui.clip.part", own) : "";
    const others = otherClips(data, clip.id);
    heading.textContent = t("ui.inspector.source.others", { count: others.length });
    if (others.length === 0) {
      list.append(el("li", "hint", t("ui.inspector.source.none")));
      return;
    }
    const rate = project.rate;
    for (const row of others) {
      const track = project.tracks.find((item) => item.id === row.track);
      const target = track?.clips.find((item) => item.id === row.clip);
      if (!target) continue;
      const time = formatClock(target.start / rate);
      const button = el("button", "source-row");
      button.type = "button";
      button.title = t("ui.inspector.source.jump", { time });
      button.append(
        el("span", "source-n", `${row.n}/${row.of}`),
        el("span", "source-track", track.speaker || track.name),
        el(
          "span",
          "source-where",
          `${formatClock(seconds(row.from))}–${formatClock(seconds(row.to))} · ${time}`,
        ),
      );
      button.addEventListener("click", () => jump(row.clip, track.id, target.start));
      const item = el("li");
      item.append(button);
      list.append(item);
    }
  }

  return { update };
}
