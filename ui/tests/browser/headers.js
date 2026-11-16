// Browser harness for the track headers: the real tracks.js and style.css, driven by the query
// string (density, rail, grouped), reporting measurements into #result for headers.test.js.
import { createTrackHeaders } from "../../tracks.js";

const query = new URLSearchParams(location.search);
const density = query.get("density") ?? "comfortable";
const rail = query.get("rail") ?? "icons";
const laneHeight = Number(query.get("lane") ?? 80);
document.documentElement.dataset.density = density;
document.querySelector(".editor").dataset.rail = rail;

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
    ...rect(name),
    header: rect(node),
  };
}
const bus = root.querySelector(".bus-header");
if (bus) {
  const parts = {};
  for (const child of bus.querySelector(".th-top").children) parts[child.className] = rect(child);
  out.bus = {
    header: rect(bus),
    name: rect(bus.querySelector(".bus-name")),
    top: rect(bus.querySelector(".th-top")),
    parts,
    controls: rect(bus.querySelector(".th-controls")),
    controlsVisibility: getComputedStyle(bus.querySelector(".th-controls")).visibility,
    summary: rect(bus.querySelector(".bus-compact-summary")),
    columns: getComputedStyle(bus).gridTemplateColumns,
  };
}
const finish = () => {
  document.getElementById("result").textContent = JSON.stringify(out);
};
const open = query.get("open");
if (!open) finish();
else {
  // Approach the lane as a pointer does: enter the header, then look at what sits over its grip.
  const node = [...root.querySelectorAll(".track-header[data-track]")].find(
    (header) =>
      header.querySelector(".track-name").title === open ||
      header.querySelector(".track-name").getAttribute("aria-label") === open,
  );
  node.dispatchEvent(new PointerEvent("pointerenter", { bubbles: false }));
  setTimeout(() => {
    const flyout = document.querySelector(
      ".track-flyout-layer .track-controls-flyout:not([hidden])",
    );
    const grip = node.querySelector(".lane-grip");
    const box = grip.getBoundingClientRect();
    const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    out.flyout = flyout ? rect(flyout) : null;
    out.flyoutScrolls = flyout ? flyout.scrollHeight > flyout.clientHeight : null;
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
