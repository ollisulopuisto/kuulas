// The overview strip above the timeline: the whole edit in miniature, with a
// box for the visible part. Click or drag to move the box.
import { projectEnd } from "./lanes.js";
import { readTheme } from "./theme.js";
import { overviewScroll, overviewWindow } from "./view.js";

export function createOverview({ canvas, getState, getTimelineWidth, actions }) {
  const context = canvas.getContext("2d");
  let queued = false;
  let theme = readTheme();
  let dragging = false;

  const observer = new ResizeObserver(() => {
    const ratio = devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.round(rect.width * ratio);
    canvas.height = Math.round(rect.height * ratio);
    theme = readTheme();
    redraw();
  });
  observer.observe(canvas);

  function redraw() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      draw();
    });
  }

  function draw() {
    const state = getState();
    const ratio = canvas.width / Math.max(1, canvas.clientWidth);
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    if (!state.project) return;
    const total = projectEnd(state.project);
    if (total === 0) return;
    const tracks = state.project.tracks;
    const rowHeight = Math.max(1, (height - 2) / Math.max(1, tracks.length));
    tracks.forEach((track, index) => {
      const colours =
        theme.palette[(track.kind === "music" ? 3 : index % 3) % theme.palette.length];
      context.fillStyle = colours.ink;
      context.globalAlpha = 0.6;
      for (const clip of track.clips) {
        const x = (clip.start / total) * width;
        context.fillRect(
          x,
          1 + index * rowHeight,
          Math.max(1, (clip.length / total) * width),
          Math.max(1, rowHeight - 1),
        );
      }
    });
    context.globalAlpha = 1;
    const box = overviewWindow({
      total,
      scroll: state.scroll,
      zoom: state.zoom,
      width: getTimelineWidth(),
      strip: width,
    });
    context.fillStyle = theme.accent;
    context.globalAlpha = 0.2;
    context.fillRect(box.x, 0, box.w, height);
    context.globalAlpha = 1;
    context.strokeStyle = theme.accent;
    context.lineWidth = 1;
    context.strokeRect(box.x + 0.5, 0.5, Math.max(1, box.w - 1), height - 1);
  }

  function moveTo(event) {
    const state = getState();
    if (!state.project) return;
    const rect = canvas.getBoundingClientRect();
    const scroll = overviewScroll({
      total: projectEnd(state.project),
      zoom: state.zoom,
      width: getTimelineWidth(),
      strip: rect.width,
      x: event.clientX - rect.left,
    });
    actions.scrollTo(Math.round(scroll));
  }

  canvas.addEventListener("pointerdown", (event) => {
    dragging = true;
    canvas.setPointerCapture(event.pointerId);
    moveTo(event);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (dragging) moveTo(event);
  });
  const release = () => {
    dragging = false;
  };
  canvas.addEventListener("pointerup", release);
  canvas.addEventListener("pointercancel", release);

  return {
    redraw,
    refreshTheme: () => {
      theme = readTheme();
      redraw();
    },
  };
}
