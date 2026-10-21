// The button icon set: 16 px stroke icons (24 px grid), one source for every button.
// A button asks for one with `data-icon="name"` (see setIcon); installIcons() writes one
// stylesheet that draws it as a CSS mask in front of the label, so it takes the text colour
// (currentColor), is never read by a screen reader (a pseudo-element), and survives the
// label being re-set with textContent. No emoji, no external files.

const s = (d) => d;
export const ICONS = {
  undo: s("M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11"),
  redo: s("m15 14 5-5-5-5M20 9H9.5a5.5 5.5 0 0 0 0 11H13"),
  bookmark: s("M6 3h12v18l-6-4.5L6 21Z"),
  restore: s("M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2"),
  search: s("m21 21-4.3-4.3M11 18a7 7 0 1 1 0-14 7 7 0 0 1 0 14Z"),
  play: s("M7 4.5v15l12-7.5Z"),
  stop: s("M6 6h12v12H6Z"),
  paste: s("M9 3h6v4H9ZM9 5H5v16h14V5h-4"),
  copy: s("M9 9h11v11H9ZM15 9V4H4v11h5"),
  rename: s("M4 20h4L19 9l-4-4L4 16ZM13 7l4 4"),
  trash: s("M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"),
  cut: s(
    "M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM8.1 7.9 20 20M8.1 16.1 20 4",
  ),
  check: s("m4 12.5 5 5L20 6.5"),
  close: s("M6 6l12 12M18 6 6 18"),
  fit: s("M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"),
  help: s(
    "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01",
  ),
  menu: s("M4 6h16M4 12h16M4 18h16"),
  follow: s("M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 8v8M8 12h8"),
  theme: s("M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 3v18M12 3a9 9 0 0 1 0 18"),
  older: s("m6 9 6 6 6-6"),
  import: s("M12 4v11M7 10l5 5 5-5M5 20h14"),
  export: s("M12 15V4M7 9l5-5 5 5M5 20h14"),
  reset: s("M4 4v6h6M4.5 15a8 8 0 1 0 1.2-8L4 10"),
  save: s("M5 4h11l3 3v13H5ZM8 4v5h7V4M8 20v-6h8v6"),
  folder: s("M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"),
  plus: s("M12 5v14M5 12h14"),
  layers: s("m12 3 9 5-9 5-9-5ZM3 13l9 5 9-5"),
  // The silent-state pair (docs/design/SILENCE-VISUALS.md): closed by Auto-Silence / mic kept
  // open. Also drawn on the timeline canvas (timeline.js drawIcon) from these same paths.
  lock: s("M6 11h12v9H6ZM8.5 11V8a3.5 3.5 0 0 1 7 0v3"),
  unlock: s("M6 11h12v9H6ZM8.5 11V8a3.5 3.5 0 0 1 6.8-1.2"),
  // Missing media: a plain warning triangle.
  alert: s("M12 3.5 2.5 20h19ZM12 10v4.5M12 17.5h.01"),
};

/** The stylesheet text: one `[data-icon]` rule per icon, inside the shared `.button` rule. */
export function iconCss() {
  const rules = Object.entries(ICONS).map(([name, d]) => {
    const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='${d}'/></svg>`;
    const url = `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
    return `.button[data-icon="${name}"]::before{-webkit-mask-image:${url};mask-image:${url}}`;
  });
  const base =
    '.button[data-icon]::before{content:"";flex:none;width:16px;height:16px;background:currentColor;-webkit-mask:center/contain no-repeat;mask:center/contain no-repeat}';
  // the shorthand above resets the image, so the per-icon rules come after it
  return [base, ...rules].join("\n");
}

export function installIcons(doc = document) {
  if (doc.getElementById("icon-styles")) return;
  const style = doc.createElement("style");
  style.id = "icon-styles";
  style.textContent = iconCss();
  doc.head.append(style);
}

/** Give a button its icon (an unknown name is a programming error and throws). */
export function setIcon(button, name) {
  if (!(name in ICONS)) throw new Error(`no icon "${name}"`);
  button.dataset.icon = name;
  return button;
}
