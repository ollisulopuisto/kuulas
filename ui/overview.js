// The overview strip above the timeline: the whole edit in miniature, with a
// box for the visible part. Click or drag to move the box.

import { siblingsOf } from "./labels.js";
import { projectEnd } from "./lanes.js";
import { trackHues } from "./paint.js";
import { readTheme } from "./theme.js";
import { overviewScroll, overviewWindow } from "./view.js";

// The strip is a map, not a waveform: blocks at reduced strength so the
// visible-part box (accent) is the strongest thing in it.
const OVERVIEW_ALPHA = 0.6;
const OVERVIEW_MUTED_ALPHA = 0.25;

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
    const rowHeight = Math.max(1, (height - 4) / Math.max(1, tracks.length));
    const hues = trackHues(state.project);
    tracks.forEach((track, index) => {
      const colours = theme.palette[(hues.get(track.id) ?? 0) % theme.palette.length];
      context.fillStyle = colours.wave;
      context.globalAlpha = track.mute ? OVERVIEW_MUTED_ALPHA : OVERVIEW_ALPHA;
      for (const clip of track.clips) {
        const x = (clip.start / total) * width;
        context.fillRect(
          x,
          2 + index * rowHeight,
          Math.max(1, (clip.length / total) * width),
          Math.max(1, rowHeight - 1),
        );
      }
    });
    context.globalAlpha = 1;
    // Clips of the selected clip's recording, wherever they are in the edit.
    const siblings = siblingsOf(state.project, state.selection);
    if (siblings.size > 0) {
      context.fillStyle = theme.sibling;
      for (const track of tracks) {
        for (const clip of track.clips) {
          if (siblings.has(clip.id)) context.fillRect((clip.start / total) * width, 0, 2, 4);
        }
      }
    }
    const box = overviewWindow({
      total,
      scroll: state.scroll,
      zoom: state.zoom,
      width: getTimelineWidth(),
      strip: width,
    });
    context.fillStyle = theme.range;
    context.fillRect(box.x, 0, box.w, height);
    context.strokeStyle = theme.accent;
    context.lineWidth = 1.5;
    context.strokeRect(box.x + 0.75, 0.75, Math.max(1, box.w - 1.5), height - 1.5);
    context.fillStyle = theme.playhead;
    context.fillRect(Math.round((state.playhead / total) * width), 0, 1, height);
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
