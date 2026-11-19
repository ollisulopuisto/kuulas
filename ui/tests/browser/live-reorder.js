import { createTrackHeaders } from "../../tracks.js";

const root = document.getElementById("track-headers");
const params = new URLSearchParams(location.search);
const folded = params.has("folded");
const terminal = params.has("terminal");
const track = (id, bus = null) => ({
  id,
  name: id,
  kind: "speech",
  bus,
  gain_db: 0,
  pan: 0,
});
const bus = { id: "v", name: "Voices", gain_db: 0, pan: 0, mute: false };
let project = folded
  ? {
      // h1 and h2 sit in a bus folded to its header row, between a and b.
      tracks: [track("a"), track("h1", "v"), track("h2", "v"), track("b")],
      buses: [bus],
    }
  : terminal
    ? {
        // The folded bus is the last row before the dragged track: nothing visible
        // follows a, so the below-all-rows fallback decides (owner, 2026-11-19).
        tracks: [track("h1", "v"), track("h2", "v"), track("a")],
        buses: [bus],
      }
    : {
        tracks: ["a", "b", "c"].map((id) => track(id)),
        buses: [],
      };
const calls = [];
const state = () => ({
  project,
  laneHeight: 100,
  laneHeights: {},
  collapsedBuses: folded || terminal ? new Set(["v"]) : new Set(),
  focusTrack: null,
});
const headers = createTrackHeaders({
  root,
  actions: new Proxy({}, { get: () => () => {} }),
  editor: {
    current: () => project,
    change(edit) {
      calls.push(edit);
      if (edit.provisional) {
        project = edit.provisional(project);
        headers.update(state());
      }
    },
  },
});
headers.update(state());
const handle = root.querySelector('[data-track="a"] .track-handle');
// Synthetic pointer events have no active native pointer to capture; the
// identity/connected checks below cover the no-detach invariant directly.
handle.setPointerCapture = () => {};
const fire = (type, y) =>
  handle.dispatchEvent(
    new PointerEvent(type, { button: 0, pointerId: 1, clientY: y, bubbles: true }),
  );
const out = {};
const observer = new MutationObserver(() => {});
observer.observe(root, { childList: true });
if (terminal) {
  const rectOf = (sel) => root.querySelector(sel).getBoundingClientRect();
  const mid = (rect) => rect.top + rect.height / 2;
  try {
    const aMid = mid(rectOf('[data-track="a"]'));
    fire("pointerdown", aMid);
    fire("pointerup", aMid);
    out.stationaryCalls = calls.length;
    out.stationaryOrder = project.tracks.map((t) => t.id);
    const busMid = mid(rectOf(".bus-header"));
    fire("pointerdown", aMid);
    fire("pointermove", busMid - 1);
    fire("pointerup", busMid - 1);
    out.aboveBusCalls = calls.length;
    out.aboveBusOrder = project.tracks.map((t) => t.id);
  } catch (e) {
    out.error = String(e);
  }
} else if (folded) {
  // A folded bus between the dragged track and the next visible one: pressing and
  // releasing the handle without moving (or hovering the bus's top half) must not
  // move `a` behind the hidden members (owner, 2026-11-19).
  const rectOf = (sel) => root.querySelector(sel).getBoundingClientRect();
  const mid = (rect) => rect.top + rect.height / 2;
  try {
    const aMid = mid(rectOf('[data-track="a"]'));
    fire("pointerdown", aMid);
    fire("pointerup", aMid);
    out.stationaryCalls = calls.length;
    out.stationaryOrder = project.tracks.map((t) => t.id);
    const busMid = mid(rectOf(".bus-header"));
    const bMid = mid(rectOf('[data-track="b"]'));
    fire("pointerdown", aMid);
    fire("pointermove", busMid - 1);
    fire("pointerup", busMid - 1);
    out.aboveBusCalls = calls.length;
    out.aboveBusOrder = project.tracks.map((t) => t.id);
    fire("pointerdown", aMid);
    fire("pointermove", (busMid + bMid) / 2);
    fire("pointerup", (busMid + bMid) / 2);
    out.belowBusCalls = calls.length;
    out.belowBusOrder = project.tracks.map((t) => t.id);
  } catch (e) {
    out.error = String(e);
  }
} else {
  try {
    fire("pointerdown", 30);
    fire("pointermove", 160);
    out.afterFirstMove = project.tracks.map((t) => t.id);
    let connected = handle.isConnected;
    fire("pointermove", 290);
    out.afterSecondMove = project.tracks.map((t) => t.id);
    connected &&= handle.isConnected;
    fire("pointermove", 10);
    out.afterBackMove = project.tracks.map((t) => t.id);
    connected &&= handle.isConnected;
    out.sameHandle = handle === root.querySelector('[data-track="a"] .track-handle');
    out.connectedThroughout = connected;
    out.callsBeforeUp = calls.length;
    out.uniqueDragKeys = new Set(calls.map((c) => c.coalesce)).size;
    // While the pointer is captured nothing may detach; once it is released the
    // DOM resync is exactly what should happen.
    out.detachedDuringDrag = observer
      .takeRecords()
      .flatMap((record) => [...record.removedNodes]).length;
    fire("pointerup", 10);
    out.callsAfterUp = calls.length;
    fire("pointerdown", 30);
    fire("pointermove", 290);
    fire("pointercancel", 290);
    const atCancel = calls.length;
    fire("pointermove", 10);
    out.stoppedOnCancel = atCancel === calls.length;
    out.separateDragsHaveDifferentKeys = new Set(calls.map((edit) => edit.coalesce)).size === 2;
    // Visual order is CSS `order` during a drag; once it ends the DOM must match,
    // or Tab stops follow the stale pre-drag order (owner, 2026-11-19).
    const domOrder = () =>
      [...root.children].filter((n) => n.dataset?.track).map((n) => n.dataset.track);
    out.domAfterCancel = domOrder();
    // A reorder from elsewhere (keyboard move, undo) must reorder the DOM too.
    project = { ...project, tracks: [...project.tracks].reverse() };
    headers.update(state());
    out.domAfterExternal = domOrder();
    // Routine updates (level paints, focus changes) must not churn the DOM or
    // steal focus, and a reorder landing while a control holds the pointer must
    // wait for release (owner, 2026-11-19).
    observer.takeRecords();
    const mButton = root.querySelector('[data-track="c"] .ms-button');
    mButton.focus();
    out.focusedBefore = document.activeElement === mButton;
    headers.update(state());
    out.noopRemovals = observer.takeRecords().flatMap((record) => [...record.removedNodes]).length;
    out.focusKept = document.activeElement === mButton;
    const pill = root.querySelector('[data-track="c"] .track-name');
    pill.dispatchEvent(new PointerEvent("pointerdown", { button: 0, pointerId: 9, bubbles: true }));
    project = { ...project, tracks: [project.tracks[1], project.tracks[2], project.tracks[0]] };
    headers.update(state());
    out.domWhileHeld = domOrder();
    pill.dispatchEvent(new PointerEvent("pointerup", { button: 0, pointerId: 9, bubbles: true }));
    out.domAfterRelease = domOrder();
    // A press released outside the headers (no pointer capture on a plain click) still
    // counts as released: the next reorder must sync the DOM right away (Devin Review,
    // 2026-11-19). The pill's pointerup listener must not be the only release path.
    pill.dispatchEvent(
      new PointerEvent("pointerdown", { button: 0, pointerId: 11, bubbles: true }),
    );
    document.body.dispatchEvent(
      new PointerEvent("pointerup", { button: 0, pointerId: 11, bubbles: true }),
    );
    project = { ...project, tracks: [...project.tracks].reverse() };
    headers.update(state());
    out.domAfterMissedRelease = domOrder();
    out.expectedAfterMissedRelease = [...project.tracks].map((t) => t.id);
  } catch (e) {
    out.error = String(e);
  }
}
document.getElementById("result").textContent = JSON.stringify(out);
