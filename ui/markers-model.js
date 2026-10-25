// Markers, regions and chapters (WP19h): the pure parts. A marker is a named point on the
// timeline, a chapter a point that goes in the chapter list, a region a named range. They
// live in the edit state (`project.markers`, frames); the server moves them with ripple
// edits. This file lists them, finds the next one, lays their flags out on the ruler without
// overlap and works out what "region from selection" would make. No DOM, so node --test
// covers it.

export const NOTCH_PX = 8;
const LABEL_PAD_PX = 3;
const LABEL_GAP_PX = 6;
const BAR_PAD_PX = 3;

const byStart = (a, b) => a.start - b.start || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);

/** The markers in listing order: by start, ties by id. */
export function sortedMarkers(markers) {
  return [...(markers ?? [])].sort(byStart);
}

/** Rows for the Markers tab: { id, name, kind, start, end, seconds, length (regions) }. */
export function markerRows(markers, rate) {
  return sortedMarkers(markers).map((marker) => ({
    id: marker.id,
    name: marker.name,
    kind: marker.kind,
    start: marker.start,
    end: marker.end ?? null,
    seconds: marker.start / rate,
    length: marker.end == null ? null : (marker.end - marker.start) / rate,
  }));
}

/**
 * The next (direction 1) or previous (-1) marker, by start, strictly after or before `frame`.
 * No wrapping: past the last one there is none.
 */
export function adjacentMarker(markers, frame, direction) {
  const list = sortedMarkers(markers);
  if (direction > 0) return list.find((marker) => marker.start > frame) ?? null;
  return list.findLast((marker) => marker.start < frame) ?? null;
}

/**
 * The id of the marker under a pointer on the ruler (x in px), or null: a flag from its pole
 * across its notch (a little slack either side), a region along its bar. Nearest start wins.
 */
export function markerIdAtX(markers, { scroll, zoom, width = Number.POSITIVE_INFINITY }, x) {
  const { flags, bars } = flagLayout(markers, { scroll, zoom, width, measure: () => 0 });
  const slack = 3;
  const hits = [
    ...flags
      .filter((flag) => x >= flag.x - slack && x <= flag.x + NOTCH_PX + slack)
      .map((flag) => ({ id: flag.id, at: flag.x })),
    ...bars.filter((bar) => x >= bar.x0 && x <= bar.x1).map((bar) => ({ id: bar.id, at: bar.x0 })),
  ];
  hits.sort((a, b) => Math.abs(a.at - x) - Math.abs(b.at - x));
  return hits[0]?.id ?? null;
}

/** The marker that starts exactly at `frame` (where Next/Previous leaves the playhead). */
export function markerAt(markers, frame) {
  return (markers ?? []).find((marker) => marker.start === frame) ?? null;
}

/** The in-out range as a region { start, end }, or null without both points or a length. */
export function regionFromRange(inPoint, outPoint) {
  if (inPoint == null || outPoint == null || inPoint === outPoint) return null;
  return { start: Math.min(inPoint, outPoint), end: Math.max(inPoint, outPoint) };
}

/** "Marker 3": the lowest number not already used as `${label} ${n}`. */
export function nextMarkerName(markers, label) {
  const taken = new Set((markers ?? []).map((marker) => marker.name));
  let n = 1;
  while (taken.has(`${label} ${n}`)) n += 1;
  return `${label} ${n}`;
}

const countKind = (markers, kind) =>
  (markers ?? []).filter((marker) => marker.kind === kind).length;
export const chapterCount = (markers) => countKind(markers, "chapter");
export const regionCount = (markers) => countKind(markers, "region");

/**
 * The ruler's flags for the visible range. `measure(text)` is the label's width in px.
 * -> { flags: [{ id, kind, x, label, labelX }], bars: [{ id, x0, x1, startsInView, label, labelX }] }
 * A flag's name is kept only when it fits before the next flag or region start, so labels
 * never overlap; otherwise the flag shows alone (the Markers tab has the names).
 */
export function flagLayout(markers, { scroll, zoom, width, measure }) {
  const list = sortedMarkers(markers);
  const xOf = (frame) => (frame - scroll) / zoom;
  const points = [];
  const bars = [];
  for (const marker of list) {
    const x = xOf(marker.start);
    if (marker.kind === "region" && marker.end != null) {
      const xEnd = xOf(marker.end);
      if (xEnd < 0 || x > width) continue;
      const x0 = Math.max(0, x);
      const x1 = Math.min(width, xEnd);
      const fits = x1 - x0 >= measure(marker.name) + 2 * BAR_PAD_PX;
      bars.push({
        id: marker.id,
        x0,
        x1,
        startsInView: x >= 0,
        label: fits ? marker.name : null,
        labelX: x0 + BAR_PAD_PX,
        start: x,
      });
    } else if (x >= -NOTCH_PX && x <= width) {
      points.push({ id: marker.id, kind: marker.kind, x, name: marker.name });
    }
  }
  const starts = [
    ...points.map((p) => p.x),
    ...bars.filter((b) => b.startsInView).map((b) => b.x0),
  ];
  const flags = points.map((point) => {
    const labelX = point.x + NOTCH_PX + LABEL_PAD_PX;
    const limit = Math.min(width, ...starts.filter((s) => s > point.x));
    const fits = point.name !== "" && labelX + measure(point.name) + LABEL_GAP_PX <= limit;
    return {
      id: point.id,
      kind: point.kind,
      x: point.x,
      label: fits ? point.name : null,
      labelX,
    };
  });
  return {
    flags,
    bars: bars.map(({ start: _start, ...bar }) => bar),
  };
}
