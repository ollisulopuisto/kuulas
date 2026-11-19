import { createTimeline } from "../../timeline.js";

// The permanent gutter left of the wave area (owner, 2026-11-19): the timeline
// canvases start at its right edge, and the painter measures the canvas, never
// the whole stack, so frame 0 maps to the gutter's right edge.
const stack = document.getElementById("timeline-stack");
const timeline = createTimeline({
  stack,
  waveCanvas: document.getElementById("wave"),
  overlayCanvas: document.getElementById("timeline"),
  playheadCanvas: document.getElementById("playhead"),
  getState: () => ({ project: null }),
  actions: new Proxy({}, { get: () => () => {} }),
});
const out = {};
// The ResizeObserver-driven measure is async: poll until it has run (or give up
// and report what we have) so a loaded machine does not flake the read.
const started = Date.now();
const probe = () => {
  try {
    const stackRect = stack.getBoundingClientRect();
    const canvasRect = document.getElementById("timeline").getBoundingClientRect();
    out.gutter =
      parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--track-gutter-w")) ||
      0;
    out.canvasLeft = Math.round(canvasRect.left - stackRect.left);
    out.canvasWidth = Math.round(canvasRect.width);
    out.stackWidth = Math.round(stackRect.width);
    out.sizeWidth = timeline.size().width;
  } catch (e) {
    out.error = String(e);
  }
  if ((out.sizeWidth > 0 && out.canvasWidth > 0) || Date.now() - started > 2500) {
    document.getElementById("result").textContent = JSON.stringify(out);
    return;
  }
  setTimeout(probe, 50);
};
probe();
