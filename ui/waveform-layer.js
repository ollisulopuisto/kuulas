// The waveform canvas, drawn in a Web Worker when the browser can
// (OffscreenCanvas), else on the main thread with the same painter.
import { peakTile } from "./api.js";
import { paintWaveforms } from "./paint.js";
import { createTileStore } from "./tiles.js";

export function createWaveformLayer(canvas) {
  const canTransfer =
    typeof Worker !== "undefined" && typeof canvas.transferControlToOffscreen === "function";
  if (canTransfer) {
    try {
      const worker = new Worker(new URL("./waveform.worker.js", import.meta.url), {
        type: "module",
      });
      const offscreen = canvas.transferControlToOffscreen();
      worker.postMessage({ type: "init", canvas: offscreen }, [offscreen]);
      return { mode: "worker", draw: (job) => worker.postMessage({ type: "draw", job }) };
    } catch (error) {
      console.warn("waveform worker unavailable, drawing on the main thread", error);
    }
  }
  const context = canvas.getContext("2d");
  let latest = null;
  let scheduled = false;
  const store = createTileStore({ fetchTile: peakTile, onChange: () => schedule() });
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      if (!latest) return;
      const width = Math.round(latest.width * latest.ratio);
      const height = Math.round(latest.height * latest.ratio);
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      const { missing } = paintWaveforms(context, latest, (m, l, t) => store.lookup(m, l, t));
      store.want(missing);
    });
  }
  return {
    mode: "main",
    draw(job) {
      latest = job;
      schedule();
    },
  };
}
