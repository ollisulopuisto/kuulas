import { createTimeline } from "../../timeline.js";

const clip = {
  id: "c",
  start: 5000,
  length: 30000,
  offset: 0,
  media: "m",
  gain_db: 0,
  fade_in: 0,
  fade_out: 0,
};
const state = {
  project: {
    rate: 48000,
    tracks: [{ id: "t", name: "Fade hover", kind: "speech", clips: [clip] }],
    buses: [],
    media: [],
  },
  selection: new Set(["c"]),
  scroll: 0,
  scrollY: 0,
  zoom: 50,
  playhead: 0,
  laneHeight: 100,
};
const canvas = document.getElementById("timeline");
const pills = [];
const ctx = canvas.getContext("2d");
const round = ctx.roundRect.bind(ctx);
ctx.roundRect = (...args) => {
  pills.push(args);
  return round(...args);
};
window.probe = {
  pills,
  clear: () => {
    pills.length = 0;
  },
};
createTimeline({
  stack: document.getElementById("timeline-stack"),
  waveCanvas: document.getElementById("wave"),
  overlayCanvas: canvas,
  playheadCanvas: document.getElementById("playhead"),
  getState: () => state,
  actions: new Proxy({}, { get: () => () => {} }),
});

await new Promise((resolve) => setTimeout(resolve, 100));
const samples = {};
window.requestAnimationFrame = (fn) => setTimeout(fn, 0);
const box = canvas.getBoundingClientRect();
for (const [name, x, y] of [
  ["body", 400, 65],
  ["left", 110, 31],
  ["right", 690, 31],
  ["away", 400, 65],
]) {
  pills.length = 0;
  canvas.dispatchEvent(
    new PointerEvent("pointermove", { clientX: box.left + x, clientY: box.top + y }),
  );
  await new Promise((resolve) => setTimeout(resolve, 60));
  samples[name] = pills.map((p) => p.slice(0, 4));
}
document.getElementById("result").textContent = JSON.stringify(samples);
