import { peakTile } from "./api.js";
import { frameToTime, frameToX, hitTestClip, hitTestLane, timeToFrame, waveformColumns } from "./format.js";
import { t } from "./i18n.js";

const LEVELS = [256, 1024, 4096, 16384, 65536];
const tileCache = new Map();
const colours = ["#7cc6bd", "#e1a56e", "#a8a3e8", "#e18191"];

export function createTimeline(canvas, getState, onChange) {
  const context = canvas.getContext("2d");
  let frame = 0;
  let resizeObserver;
  const resize = () => {
    const ratio = devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.round(rect.width * ratio);
    canvas.height = Math.round(rect.height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    draw();
  };

  async function peaks(media, level, tile) {
    const key = `${media}/${level}/${tile}`;
    if (tileCache.has(key)) return tileCache.get(key);
    const promise = peakTile(media, level, tile).then((buffer) => {
      const data = new Float32Array(buffer);
      const values = [];
      for (let i = 0; i + 1 < data.length; i += 2) values.push([data[i], data[i + 1]]);
      return values;
    }).catch(() => []);
    tileCache.set(key, promise);
    return promise;
  }

  function draw() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const state = getState();
      const { width, height } = canvas.getBoundingClientRect();
      context.clearRect(0, 0, width, height);
      context.fillStyle = "#171a1d";
      context.fillRect(0, 0, width, height);
      if (!state.project) return;
      const tracks = state.project.tracks;
      const laneHeight = state.laneHeight;
      const rate = state.project.rate;
      const tickFrames = Math.max(1, state.zoom * 100);
      const firstTick = Math.floor(state.scroll / tickFrames) * tickFrames;
      context.font = "11px system-ui";
      context.textBaseline = "top";
      for (let tick = firstTick; frameToX(tick, state.scroll, state.zoom) < width; tick += tickFrames) {
        const x = frameToX(tick, state.scroll, state.zoom);
        context.strokeStyle = "#343a40";
        context.beginPath(); context.moveTo(x, 22); context.lineTo(x, height); context.stroke();
        context.fillStyle = "#aab2b9";
        context.fillText(frameToTime(tick, state.language), x + 3, 4);
      }
      for (const [index, track] of tracks.entries()) {
        const top = 24 + index * laneHeight;
        context.strokeStyle = "#394047";
        context.beginPath(); context.moveTo(0, top + laneHeight); context.lineTo(width, top + laneHeight); context.stroke();
        for (const [clipIndex, clip] of track.clips.entries()) {
          const x = frameToX(clip.start, state.scroll, state.zoom);
          const clipWidth = clip.length / state.zoom;
          if (x > width || x + clipWidth < 0) continue;
          const media = state.project.media.find((item) => item.id === clip.media);
          if (!media) continue;
          const y = top + 5;
          const h = laneHeight - 10;
          context.globalAlpha = clip.muted ? 0.35 : 1;
          context.fillStyle = colours[index % colours.length];
          context.fillRect(x, y, Math.max(1, clipWidth), h);
          context.fillStyle = "#131719";
          context.fillText(media.name, x + 5, y + 3, Math.max(0, clipWidth - 10));
          const level = LEVELS.reduce((best, current) => Math.abs(current - state.zoom * rate) < Math.abs(best - state.zoom * rate) ? current : best, LEVELS[0]);
          const tile = Math.max(0, Math.floor((clip.offset * level / 256) / (1024 * level / 256)));
          void peaks(media.id, level, tile).then((values) => {
            if (!values.length) return;
            const columns = waveformColumns(values.slice(0, Math.max(1, Math.floor(clipWidth))), state.waveformMode, state.waveformScale, h - 12);
            context.save();
            context.beginPath(); context.rect(x, y, Math.max(0, clipWidth), h); context.clip();
            context.strokeStyle = "rgba(13, 29, 31, .78)";
            for (const [column, peak] of columns.entries()) {
              const xx = x + column;
              if (state.waveformMode === "classic") {
                const mid = y + h / 2;
                context.beginPath(); context.moveTo(xx, mid - Math.abs(peak.maximum) * h / 2); context.lineTo(xx, mid + Math.abs(peak.minimum) * h / 2); context.stroke();
              } else {
                context.beginPath(); context.moveTo(xx, y + h - peak.height - 4); context.lineTo(xx, y + h - 4); context.stroke();
              }
            }
            context.restore();
          });
          context.globalAlpha = 1;
          if (state.selection.has(clip.id)) {
            context.strokeStyle = "#fff2a6"; context.lineWidth = 2; context.strokeRect(x + 1, y + 1, Math.max(0, clipWidth - 2), h - 2); context.lineWidth = 1;
          }
          if (clipIndex && track.clips[clipIndex - 1].end === clip.start) {
            context.fillStyle = "rgba(0,0,0,.22)"; context.fillRect(x - 3, y, 6, h);
          }
        }
      }
      if (state.inPoint !== null && state.outPoint !== null) {
        const x1 = frameToX(state.inPoint, state.scroll, state.zoom);
        const x2 = frameToX(state.outPoint, state.scroll, state.zoom);
        context.fillStyle = "rgba(124,198,189,.12)"; context.fillRect(x1, 0, x2 - x1, height);
      }
      const playX = frameToX(state.playhead, state.scroll, state.zoom);
      context.strokeStyle = "#ffcb66"; context.lineWidth = 1.5;
      context.beginPath(); context.moveTo(playX, 0); context.lineTo(playX, height); context.stroke();
    });
  }

  canvas.addEventListener("pointerdown", (event) => {
    canvas.focus();
    const rect = canvas.getBoundingClientRect();
    const state = getState();
    const y = event.clientY - rect.top - 24;
    const track = hitTestLane(y, 0, state.project?.tracks ?? [], state.laneHeight);
    const targetTrack = state.project?.tracks.find((item) => item.id === track);
    const at = timeToFrame(event.clientX - rect.left, state.scroll, state.zoom);
    const clip = targetTrack && hitTestClip(at, track, targetTrack.clips.map((item) => ({ ...item, track })));
    onChange({ playhead: at, focusTrack: track, selection: clip ? new Set([clip]) : new Set() });
  });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const state = getState();
    const overLane = event.clientY - canvas.getBoundingClientRect().top > 24;
    if (event.shiftKey || !overLane) onChange({ scroll: Math.max(0, state.scroll + event.deltaY * state.zoom) });
    else onChange({ scrollY: Math.max(0, (state.scrollY ?? 0) + event.deltaY) });
  }, { passive: false });
  resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(canvas);
  resize();
  return { draw, destroy() { cancelAnimationFrame(frame); resizeObserver.disconnect(); } };
}
