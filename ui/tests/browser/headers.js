// Browser harness for the track headers: the real tracks.js and style.css, driven by the query
// string (density, lane, open), reporting measurements into #result for header-browser.test.js.
import { createTrackHeaders } from "../../tracks.js";

const query = new URLSearchParams(location.search);
const density = query.get("density") ?? "comfortable";
const laneHeight = Number(query.get("lane") ?? 80);
document.documentElement.dataset.density = density;

const track = (id, name, bus) => ({
  id,
  name,
  kind: "speech",
  bus,
  gain_db: 0,
  pan: 0,
  mute: false,
  solo: false,
});
const project = {
  tracks: [
    track("t1", "Alice", "b1"),
    track("t2", "Bob", "b1"),
    track("t3", "Solo track", null),
    track("t4", "Last", null),
  ],
  buses: [{ id: "b1", name: "Hosts", kind: "speech", gain_db: 0, pan: 0, mute: false }],
};
const calls = [];
const actions = new Proxy(
  { setLaneHeight: (id, height) => calls.push(["setLaneHeight", id, height]) },
  { get: (target, key) => target[key] ?? (() => {}) },
);
const root = document.getElementById("track-headers");
const headers = createTrackHeaders({
  root,
  editor: { apply() {}, current: () => project },
  actions,
});
headers.update({
  project,
  laneHeight,
  laneHeights: {},
  collapsedBuses: new Set(),
  focusTrack: null,
});

const rect = (node) => {
  const box = node.getBoundingClientRect();
  return { left: box.left, top: box.top, width: box.width, height: box.height };
};
const out = { names: {}, calls, error: null };
for (const node of root.querySelectorAll(".track-header[data-track]")) {
  const name = node.querySelector(".track-name");
  out.names[name.textContent] = {
    grouped: node.hasAttribute("data-bus"),
    untruncated: name.clientWidth >= name.scrollWidth - 1,
    headerTransparent: getComputedStyle(node).backgroundColor === "rgba(0, 0, 0, 0)",
    strip: rect(node.querySelector(".th-strip")),
    ...rect(name),
    header: rect(node),
  };
}
const bus = root.querySelector(".bus-header");
if (bus) {
  out.bus = {
    header: rect(bus),
    name: rect(bus.querySelector(".bus-name")),
    badge: Boolean(bus.querySelector(".th-strip .bus-badge")),
    controlsDisplay: getComputedStyle(bus.querySelector(".th-controls")).display,
    summaryDisplay: getComputedStyle(bus.querySelector(".bus-compact-summary")).display,
  };
}
const finish = () => {
  document.getElementById("result").textContent = JSON.stringify(out);
};
addEventListener("error", (event) => {
  document.getElementById("result").textContent = JSON.stringify({ harnessError: String(event.error && event.error.stack || event.message) });
});
const open = query.get("open");
if (!open) finish();
else {
  // Pin the track's ".." popover (collapsed, the disclosure is hover-only, so
  // click it programmatically), then look at what sits over the grip.
  const node = [...root.querySelectorAll(".track-header[data-track]")].find(
    (header) =>
      header.querySelector(".track-name").title === open ||
      header.querySelector(".track-name").getAttribute("aria-label") === open,
  );
  node.querySelector(".th-disclosure").click();
  setTimeout(() => {
    const flyout = document.querySelector(
      ".track-flyout-layer .track-controls-flyout:not([hidden])",
    );
    const grip = node.querySelector(".lane-grip");
    const box = grip.getBoundingClientRect();
    const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    out.flyout = flyout ? rect(flyout) : null;
    out.controlsOpen = node.classList.contains("controls-open");
    out.header = rect(node);
    out.grip = rect(grip);
    out.gripHit = hit === grip;
    const next = node.nextElementSibling;
    out.next = next ? rect(next) : null;
    hit.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    const nameBox = node.querySelector(".track-name").getBoundingClientRect();
    const nameHit = document.elementFromPoint(
      nameBox.left + nameBox.width / 2,
      nameBox.top + nameBox.height / 2,
    );
    out.nameHit = nameHit?.className ?? null;
    nameHit?.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    out.renameField = Boolean(node.querySelector("input"));
    out.calls = calls;
    finish();
  }, 50);
}
