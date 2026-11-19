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
  // A full press: down, up, click on whatever the pointer rests on.
  const press = (target, { shift = false } = {}) => {
    const down = new PointerEvent("pointerdown", {
      bubbles: true,
      cancelable: true,
      clientX: cx,
      clientY: cy,
      shiftKey: shift,
    });
    target.dispatchEvent(down);
    target.dispatchEvent(
      new PointerEvent("pointerup", { bubbles: true, clientX: cx, clientY: cy, shiftKey: shift }),
    );
    target.dispatchEvent(
      new MouseEvent("click", { bubbles: true, clientX: cx, clientY: cy, shiftKey: shift }),
    );
    return down;
  };
  // Enter over the collapsed strip's Solo: the card must NOT open at once
  // (owner, 2026-11-19: ~120 ms of intent first), and with the persistent
  // strip nothing shifts, so the press lands on Solo itself.
  node
    .querySelector(".th-strip")
    .dispatchEvent(new PointerEvent("pointerenter", { bubbles: false, clientX: cx, clientY: cy }));
  out.intentImmediate = getComputedStyle(node.querySelector(".th-controls")).display;
  const hit = document.elementFromPoint(cx, cy);
  out.hitInControls = Boolean(hit && hit.closest(".th-controls"));
  const down = press(hit ?? node);
  out.pressSwallowed = down.defaultPrevented;
  out.calls = calls.slice();
  soloBtn.click();
  out.callsAfter = calls.slice();
  // Fresh entry with Shift held: a Shift press is a non-exclusive Solo.
  calls.length = 0;
  node.classList.remove("hover-open");
  node
    .querySelector(".th-strip")
    .dispatchEvent(new PointerEvent("pointerenter", { bubbles: false, clientX: cx, clientY: cy }));
  const shiftHit = document.elementFromPoint(cx, cy);
  const shiftDown = press(shiftHit ?? node, { shift: true });
  out.shiftSwallowed = shiftDown.defaultPrevented;
  out.shiftCalls = calls.slice();
  setTimeout(() => {
    out.intentAfter = getComputedStyle(node.querySelector(".th-controls")).display;
    finish();
  }, 200);
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
} else if (query.get("hover")) {
  // The approved hover rule (owner, 2026-11-19): the card opens only from the
  // collapsed strip or the name pill, after ~120 ms of intent; leaving starts
  // a ~250 ms grace; open while the pointer is inside the card; a name click
  // pins (double-click still renames); no layout shift under the pointer.
  const name = query.get("hover");
  const node = [...root.querySelectorAll(".track-header[data-track]")].find(
    (header) => header.querySelector(".track-name").textContent === name,
  );
  const strip = node.querySelector(".th-strip");
  const nameEl = node.querySelector(".track-name");
  const card = node.querySelector(".th-card");
  const openNow = () => node.classList.contains("hover-open");
  const stripRect = () => JSON.stringify(strip.getBoundingClientRect());
  out.collapsedStrip = stripRect();
  const steps = [];
  const at = (ms, fn) => steps.push([ms, fn]);
  const runSteps = (start) => {
    let t = start;
    for (const [ms, fn] of steps) {
      t += ms;
      setTimeout(fn, t);
    }
    return t;
  };
  // 1. Intent: entering the strip opens after ~120 ms, not at once.
  const sc = strip.getBoundingClientRect();
  strip.dispatchEvent(
    new PointerEvent("pointerenter", { bubbles: false, clientX: sc.left + 4, clientY: sc.top + 4 }),
  );
  at(60, () => {
    out.openAt60 = openNow();
  });
  at(140, () => {
    out.openAt200 = openNow();
    out.openStrip = stripRect();
  });
  // 2. Stay open anywhere inside the card: move to the controls, still open.
  at(20, () => {
    const cc = card.getBoundingClientRect();
    node.dispatchEvent(
      new PointerEvent("pointermove", {
        bubbles: false,
        clientX: cc.right - 8,
        clientY: cc.top + 8,
      }),
    );
    out.openInsideCard = openNow();
  });
  // 3. Grace: leaving the card keeps it open briefly, then closes.
  at(20, () => {
    card.dispatchEvent(
      new PointerEvent("pointerleave", { bubbles: false, relatedTarget: document.body }),
    );
    node.dispatchEvent(
      new PointerEvent("pointerleave", { bubbles: false, relatedTarget: document.body }),
    );
  });
  at(100, () => {
    out.openAfterLeave100 = openNow();
  });
  at(300, () => {
    out.openAfterLeave400 = openNow();
  });
  // 4. The card gaps are not a trigger: entering the node away from the strip
  // and the name never opens (today the whole card is the trigger).
  at(50, () => {
    node.dispatchEvent(
      new PointerEvent("pointerenter", {
        bubbles: false,
        clientX: sc.right + 30,
        clientY: sc.top + 4,
      }),
    );
  });
  at(250, () => {
    out.openFromGap = openNow();
  });
  // 5. A name click pins: the card stays open after leaving, until a click
  // elsewhere; Escape also unpins. Double-click still renames, never pins.
  at(50, () => {
    nameEl.dispatchEvent(
      new PointerEvent("pointerenter", {
        bubbles: false,
        clientX: sc.left + 4,
        clientY: sc.top + 4,
      }),
    );
  });
  at(200, () => {
    out.openFromName = openNow();
    nameEl.click();
  });
  at(300, () => {
    card.dispatchEvent(
      new PointerEvent("pointerleave", { bubbles: false, relatedTarget: document.body }),
    );
  });
  at(400, () => {
    out.pinnedAfterLeave = openNow();
    document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
  });
  at(60, () => {
    out.openAfterOutsideClick = openNow();
    nameEl.click();
  });
  at(300, () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  });
  at(60, () => {
    out.openAfterEsc = openNow();
    nameEl.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
  });
  at(300, () => {
    out.renameStillWorks = Boolean(node.querySelector("input"));
    out.pinnedByDblclick = openNow() && !node.querySelector("input");
    out.noShift = out.collapsedStrip === out.openStrip;
    finish();
  });
  runSteps(0);
} else if (query.get("esc")) {
  // Devin review on #240: a pinned header's Escape must be consumed before the
  // global keyboard dispatcher (a document bubble listener, installed first in
  // the real app) sees it, so one press unpins without also clearing the clip
  // selection and range marks. Escape in a field still belongs to the field.
  const node = root.querySelector(".track-header[data-track]");
  const nameEl = node.querySelector(".track-name");
  let globalSawEsc = 0;
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") globalSawEsc += 1;
  });
  nameEl.dispatchEvent(
    new PointerEvent("pointerenter", { bubbles: false, clientX: 5, clientY: 5 }),
  );
  setTimeout(() => nameEl.click(), 200);
  setTimeout(() => {
    out.pinned = node.classList.contains("pinned");
    node.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    out.globalAfterPinnedEsc = globalSawEsc;
    out.unpinned = !node.classList.contains("pinned");
  }, 600);
  setTimeout(() => {
    node.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    out.globalAfterPlainEsc = globalSawEsc;
    // Devin review on #240, round 2: pin the card again, open its controls
    // flyout, then Escape must dismiss both - the consumed key never reaches
    // the flyout's own Escape handler.
    nameEl.click();
  }, 700);
  setTimeout(() => node.querySelector(".th-disclosure").click(), 1000);
  setTimeout(() => {
    const flyout = () =>
      document.querySelector(".track-flyout-layer .track-controls-flyout:not([hidden])");
    out.flyoutOpen = Boolean(flyout());
    node
      .querySelector(".th-disclosure")
      .dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    out.flyoutAfterEsc = Boolean(flyout());
    out.pinnedAfterFlyoutEsc = node.classList.contains("pinned");
    finish();
  }, 1200);
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
