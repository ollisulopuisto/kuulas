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
  editor: {
    apply() {},
    current: () => project,
    change: (edit) =>
      calls.push(["change", edit.op, ...(edit.op === "solo" ? [edit.args.exclusive] : [])]),
  },
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
  document.getElementById("result").textContent = JSON.stringify({
    harnessError: String((event.error && event.error.stack) || event.message),
  });
});
const intent = query.get("intent");
if (intent) {
  // Devin (#233): enter directly over the collapsed Solo and press its
  // original centre at once. The card opens the moment the pointer enters
  // (header redesign, 2026-11-18), so the in-flight press lands on the
  // revealed controls - it must be swallowed and redirected to Solo: only the
  // Solo action may run, never the gain. The next, deliberate click still works.
  const node = [...root.querySelectorAll(".track-header[data-track]")].find(
    (header) => header.querySelector(".track-name").textContent === intent,
  );
  const soloBtn = node.querySelector(".ms-button.solo");
  const box = soloBtn.getBoundingClientRect();
  const cx = box.left + box.width / 2;
  const cy = box.top + box.height / 2;
  const gain = node.querySelector('.th-controls input[type="range"]');
  gain.addEventListener("input", () => calls.push(["input", "gain"]));
  node.dispatchEvent(
    new PointerEvent("pointerenter", { bubbles: false, clientX: cx, clientY: cy }),
  );
  out.intentImmediate = getComputedStyle(node.querySelector(".th-controls")).display;
  const hit = document.elementFromPoint(cx, cy);
  out.hitInControls = Boolean(hit && hit.closest(".th-controls"));
  const down = new PointerEvent("pointerdown", {
    bubbles: true,
    cancelable: true,
    clientX: cx,
    clientY: cy,
  });
  (hit ?? node).dispatchEvent(down);
  out.pressSwallowed = down.defaultPrevented;
  out.calls = calls.slice();
  soloBtn.click();
  out.callsAfter = calls.slice();
  // Fresh entry with Shift held (Devin, #233): the redirected press must keep
  // the modifier - Shift-click on Solo is non-exclusive (exclusive === false).
  calls.length = 0;
  node.classList.remove("hover-open");
  node.dispatchEvent(
    new PointerEvent("pointerenter", { bubbles: false, clientX: cx, clientY: cy }),
  );
  const shiftHit = document.elementFromPoint(cx, cy);
  const shiftDown = new PointerEvent("pointerdown", {
    bubbles: true,
    cancelable: true,
    clientX: cx,
    clientY: cy,
    shiftKey: true,
  });
  (shiftHit ?? node).dispatchEvent(shiftDown);
  out.shiftSwallowed = shiftDown.defaultPrevented;
  out.shiftCalls = calls.slice();
  setTimeout(() => {
    out.intentAfter = getComputedStyle(node.querySelector(".th-controls")).display;
    finish();
  }, 100);
} else if (query.get("pan")) {
  // Devin (#233): in the expanded card the pan dial's hover/focus readout must
  // stay hidden - shown, its stale fixed positioning lands at the viewport top.
  const node = [...root.querySelectorAll(".track-header[data-track]")].find(
    (header) => header.querySelector(".track-name").textContent === query.get("pan"),
  );
  node.classList.add("hover-open");
  const panWrap = node.querySelector(".th-controls .slider-control.pan");
  panWrap.querySelector("input").focus();
  out.panOutputDisplay = getComputedStyle(panWrap.querySelector("output")).display;
  finish();
} else {
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
}
