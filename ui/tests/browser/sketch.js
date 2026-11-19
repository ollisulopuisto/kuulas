// Sketch harness: real tracks.js + real style.css. Two headers: t1 expanded
// into a multi-row card per ?v=a|b|c, t2 collapsed with the new read-only
// state column. Design sketch only, no behaviour changes.
import { createTrackHeaders } from "../../tracks.js";
import { initI18n } from "../../i18n.js";

await initI18n({ language: "fi" });

const variant = new URLSearchParams(location.search).get("v") ?? "a";

const LONG = "vst s13e03 – 20…roitu_processed";
const project = {
  tracks: [
    { id: "t1", name: LONG, kind: "speech", bus: null, gain_db: 0, pan: 0, mute: false, solo: false, channels: 1 },
    { id: "t2", name: LONG, kind: "speech", bus: null, gain_db: 0, pan: 0, mute: false, solo: false, channels: 1 },
  ],
  buses: [],
};
const actions = new Proxy({}, { get: () => () => {} });
const root = document.getElementById("track-headers");
const headers = createTrackHeaders({
  root,
  editor: { apply() {}, current: () => project, change: () => {} },
  actions,
});
const L1 = 190; // expanded lane
const L2 = 110; // collapsed lane
headers.update({
  project,
  laneHeight: L1,
  laneHeights: { t2: L2 },
  collapsedBuses: new Set(),
  focusTrack: null,
});

// Lanes + fake waveforms behind the headers.
const stage = document.querySelector(".stage");
let seed = 7;
const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const addLane = (top, height) => {
  const lane = document.createElement("div");
  lane.className = "lane";
  lane.style.top = `${top}px`;
  lane.style.height = `${height}px`;
  const bars = [];
  for (let x = 44; x < 516; x += 4) {
    const h = 6 + rand() * (height * 0.4);
    bars.push(
      `<rect x="${x}" y="${height / 2 - h / 2}" width="2" height="${h}" rx="1" fill="rgba(230,150,180,0.55)"/>`,
    );
  }
  lane.innerHTML = `<div class="clip"></div><svg viewBox="0 0 640 ${height}" preserveAspectRatio="none">${bars.join("")}</svg>`;
  document.querySelector(".tl-column").prepend(lane);
};
addLane(0, L1);
addLane(L1, L2);

const nodes = [...root.querySelectorAll(".track-header[data-track]")];
const [expanded, collapsed] = nodes;

// --- collapsed: second read-only state column next to M/S (his idea) ---
{
  const strip = collapsed.querySelector(".th-strip");
  const ms = strip.querySelector(".ms");
  const pair = document.createElement("div");
  pair.className = "th-strip-pair";
  const state = document.createElement("div");
  state.className = "th-state";
  const gain = document.createElement("span");
  gain.textContent = "0,0";
  gain.title = "Taso";
  const pan = document.createElement("span");
  pan.textContent = "K";
  pan.title = "Panorointi";
  state.append(gain, pan);
  ms.replaceWith(pair);
  pair.append(ms, state);
}

// --- expanded: multi-row variant ---
expanded.classList.add("hover-open");
const row1 = expanded.querySelector(".th-row1");
const card = expanded.querySelector(".th-card");
const strip = expanded.querySelector(".th-strip");
const name = row1.querySelector(".track-name");
const ms = strip.querySelector(".ms");
const disclosure = row1.querySelector(".th-disclosure");
const summary = row1.querySelector(".track-compact-summary");
const controls = card.querySelector(".th-controls");

const css = document.getElementById("variant-css");
document.getElementById("vtag").textContent = variant.toUpperCase();

const row = (...kids) => {
  const r = document.createElement("div");
  r.className = "mr-row";
  r.append(...kids);
  return r;
};

if (variant === "a") {
  // A: name row / M S ... + summary row / level + pan row (his example)
  card.insertBefore(row(name), controls);
  card.insertBefore(row(ms, disclosure, summary), controls);
  row1.style.display = "none";
} else if (variant === "b") {
  // B: name + ... row / M S + summary row / level + pan row
  card.insertBefore(row(name, disclosure), controls);
  card.insertBefore(row(ms, summary), controls);
  row1.style.display = "none";
} else {
  // C: vertical strip (handle, M, S) kept at the left; rows beside it:
  // name row / summary + ... row / level + pan row
  css.textContent = `
    .track-header.hover-open .th-card { flex-direction: row; align-items: stretch; gap: 10px; }
    .track-header.hover-open .th-strip {
      display: flex !important; flex-direction: column; align-items: center; gap: 3px;
      width: 26px; padding: 4px 2px; border-radius: 8px;
      background: rgba(255,255,255,0.04);
      border: 1px solid #3a3e4c;
    }
    .track-header.hover-open .th-strip .ms { display: flex; flex-direction: column; gap: 3px; }
    .track-header.hover-open .th-strip .ms-button { width: 20px; height: 18px; font-size: 10px; }
    .track-header.hover-open .th-strip .track-handle { opacity: 0.8; }
    .track-header.hover-open .mr-col { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
    .track-header.hover-open .mr-row .track-compact-summary { margin-left: 0; }
  `;
  const col = document.createElement("div");
  col.className = "mr-col";
  col.append(row(name), row(disclosure, summary), controls);
  card.append(col);
  card.insertBefore(strip, col);
  row1.style.display = "none";
}
