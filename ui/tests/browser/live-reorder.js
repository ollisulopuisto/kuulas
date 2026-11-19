import { createTrackHeaders } from "../../tracks.js";

const root = document.getElementById("track-headers");
let project = {
  tracks: ["a", "b", "c"].map((id) => ({
    id,
    name: id,
    kind: "speech",
    bus: null,
    gain_db: 0,
    pan: 0,
  })),
  buses: [],
};
const calls = [];
const state = () => ({
  project,
  laneHeight: 100,
  laneHeights: {},
  collapsedBuses: new Set(),
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
  fire("pointerup", 10);
  out.callsAfterUp = calls.length;
  out.detachedRows = observer.takeRecords().flatMap((record) => [...record.removedNodes]).length;
  fire("pointerdown", 30);
  fire("pointermove", 290);
  fire("pointercancel", 290);
  const atCancel = calls.length;
  fire("pointermove", 10);
  out.stoppedOnCancel = atCancel === calls.length;
  out.separateDragsHaveDifferentKeys = new Set(calls.map((edit) => edit.coalesce)).size === 2;
} catch (e) {
  out.error = String(e);
}
document.getElementById("result").textContent = JSON.stringify(out);
