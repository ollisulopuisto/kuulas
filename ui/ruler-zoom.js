// Zoom to a range dragged on the ruler. Pure: no DOM, no imports.
// x = (frame - scroll) * zoom  =>  frame = x / zoom + scroll
export function rangeFromDrag(x0, x1, { scroll, zoom, minPx = 8 }) {
  if (Math.abs(x1 - x0) < minPx) return null;
  const f0 = Math.round(x0 / zoom + scroll);
  const f1 = Math.round(x1 / zoom + scroll);
  const start = Math.max(0, Math.min(f0, f1));
  const end = Math.max(f0, f1);
  return { start, end };
}

// Zoom the view so [start, end] fills width minus padding on each side.
// When the wanted zoom is above maxZoom, centre the range instead.
export function zoomToRange({ start, end }, { width, padding = 0.02, minZoom, maxZoom }) {
  const padPx = width * padding;
  const span = end - start;
  let zoom = (width - 2 * padPx) / span;
  const centred = zoom > maxZoom;
  zoom = Math.min(Math.max(zoom, minZoom), maxZoom);
  const scroll = centred
    ? Math.max(0, (start + end) / 2 - width / 2 / zoom)
    : Math.max(0, start - padPx / zoom);
  return { scroll, zoom };
}
