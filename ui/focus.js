// Keyboard focus: which panel has it. F6 and Shift+F6 cycle, Esc goes home.
// "Keyboard focus" is the panel; "current track" is the up/down cursor; "focus
// mode" is the F key (WP28). The three words are not interchangeable.
export const PANELS = [
  "timeline",
  "transcript",
  "inspector",
  "history",
  "markers",
  "material",
  "candidates",
];
export const HOME = "timeline";

/** The panel after `current` (direction 1) or before it (-1), wrapping around. */
export function nextPanel(current, direction) {
  if (current === "clipboard") current = "material";
  const at = PANELS.includes(current) ? PANELS.indexOf(current) : 0;
  return PANELS[(at + (direction < 0 ? PANELS.length - 1 : 1)) % PANELS.length];
}
