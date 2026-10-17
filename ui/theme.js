// Colours for the canvases come from the CSS custom properties in style.css,
// so light and dark mode (and any later theme) are changed in one place.
const CLIP_COLOURS = 4;

export function readTheme(element = document.documentElement) {
  const style = getComputedStyle(element);
  const get = (name) => style.getPropertyValue(name).trim();
  const palette = [];
  for (let i = 0; i < CLIP_COLOURS; i += 1) {
    palette.push({
      fill: get(`--clip-${i}-bg`),
      ink: get(`--clip-${i}-ink`),
      wave: get(`--clip-${i}-ink`),
    });
  }
  return {
    palette,
    ink: get("--ink"),
    muted: get("--muted"),
    rule: get("--rule"),
    panel: get("--panel"),
    accent: get("--accent"),
    playhead: get("--playhead"),
    font: get("--font-ui") || "system-ui, sans-serif",
    mono: get("--font-mono") || "ui-monospace, monospace",
  };
}
