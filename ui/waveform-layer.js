// The waveform canvas, drawn in a Web Worker when the browser can
// (OffscreenCanvas), else on the main thread with the same painter.
import { peakTile } from "./api.js";
import { backingSize } from "./canvas-size.js";
import { paintWaveforms } from "./paint.js";
import { createTileStore } from "./tiles.js";

export function createWaveformLayer(canvas, { onOvers } = {}) {
  const canTransfer =
    typeof Worker !== "undefined" && typeof canvas.transferControlToOffscreen === "function";
  if (canTransfer) {
    try {
      const worker = new Worker(new URL("./waveform.worker.js", import.meta.url), {
        type: "module",
      });
      const offscreen = canvas.transferControlToOffscreen();
      worker.addEventListener("message", ({ data }) => {
        if (data?.type === "overs") onOvers?.(data.overs);
      });
      worker.postMessage({ type: "init", canvas: offscreen }, [offscreen]);
      return { mode: "worker", draw: (job) => worker.postMessage({ type: "draw", job }) };
    } catch (error) {
      console.warn("waveform worker unavailable, drawing on the main thread", error);
    }
  }
  const context = canvas.getContext("2d");
  let latest = null;
  let scheduled = false;
  let lastOvers = "";
  const store = createTileStore({ fetchTile: peakTile, onChange: () => schedule() });
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      if (!latest) return;
      const { width, height } = backingSize(latest.width, latest.height, latest.ratio);
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      const { missing, overs } = paintWaveforms(context, latest, (m, l, t) =>
        store.lookup(m, l, t),
      );
      store.want(missing);
      const key = JSON.stringify(overs);
      if (key !== lastOvers) {
        lastOvers = key;
        onOvers?.(overs);
      }
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
