// The overview strip above the timeline: the whole edit in miniature, with a
// box for the visible part. Click or drag to move the box.

import { backingSize } from "./canvas-size.js";
import { formatClock } from "./i18n.js";
import { siblingsOf } from "./labels.js";
import { projectEnd } from "./lanes.js";
import { audibleSegments, overviewMarks, overviewRuns } from "./overview-segments.js";
import { trackHues } from "./paint.js";
import { readTheme } from "./theme.js";
import { overviewScroll, overviewWindow } from "./view.js";

// The strip is a map, not a waveform: blocks at reduced strength so the
// visible-part box (accent) is the strongest thing in it. A track's bar is drawn only
// where that track sounds; every silent stretch is a gap, whatever the reason.
const OVERVIEW_ALPHA = 0.6;
const OVERVIEW_LABEL_PX = 10;

export function createOverview({
  canvas,
  getState,
  getTimelineWidth,
  getLiveEnd = () => 0,
  actions,
}) {
  const context = canvas.getContext("2d");
  let queued = false;
  let theme = readTheme();
  let dragging = false;

  const observer = new ResizeObserver(() => {
    const rect = canvas.getBoundingClientRect();
    const backing = backingSize(rect.width, rect.height, devicePixelRatio || 1);
    canvas.width = backing.width;
    canvas.height = backing.height;
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
    const liveEnd = getLiveEnd();
    const total = Math.max(
      projectEnd(state.project),
      Number.isFinite(liveEnd) ? Math.max(0, liveEnd) : 0,
    );
    if (total === 0) return;
    const tracks = state.project.tracks;
    const plotTop = OVERVIEW_LABEL_PX + 6;
    const rowHeight = Math.max(1, (height - plotTop - 2) / Math.max(1, tracks.length));
    const hues = trackHues(state.project);
    tracks.forEach((track, index) => {
      const colours = theme.palette[(hues.get(track.id) ?? 0) % theme.palette.length];
      context.fillStyle = colours.wave;
      context.globalAlpha = OVERVIEW_ALPHA;
      const runs = overviewRuns(
        audibleSegments(track, state.silencePreview?.get?.(track.id)),
        total,
        width,
      );
      for (let i = 0; i < runs.length; i += 2) {
        context.fillRect(
          runs[i],
          plotTop + index * rowHeight,
          runs[i + 1] - runs[i],
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
          if (siblings.has(clip.id)) context.fillRect((clip.start / total) * width, plotTop, 2, 4);
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
    // Keep overview times above the map, clear of the timeline ruler below.
    context.fillStyle = theme.rulerText;
    context.font = `${OVERVIEW_LABEL_PX}px system-ui, sans-serif`;
    context.textBaseline = "top";
    for (const mark of overviewMarks(total, width, state.project.rate, formatClock)) {
      context.fillRect(mark.x, 2, 1, 4);
      const labelX = Math.min(mark.x + 3, width - context.measureText(mark.label).width - 3);
      context.fillText(mark.label, Math.max(3, labelX), 2);
    }
    context.fillStyle = theme.playhead;
    context.fillRect(Math.round((state.playhead / total) * width), 0, 1, height);
  }

  function moveTo(event) {
    const state = getState();
    if (!state.project) return;
    const rect = canvas.getBoundingClientRect();
    const liveEnd = getLiveEnd();
    const scroll = overviewScroll({
      total: Math.max(
        projectEnd(state.project),
        Number.isFinite(liveEnd) ? Math.max(0, liveEnd) : 0,
      ),
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
