// Draws every lane's clips and waveforms on an OffscreenCanvas, off the main
// thread (PLAN: no main-thread task over 16 ms). The page posts
//   { type: "init", canvas }   once, with the transferred canvas
//   { type: "draw", job }      whenever the view changes (see paint.js)
// and this fetches the peak tiles it is missing, then paints the newest job again.
import { peakTile } from "./api.js";
import { paintWaveforms } from "./paint.js";
import { createTileStore } from "./tiles.js";

let canvas = null;
let context = null;
let latest = null;
let scheduled = false;

const store = createTileStore({ fetchTile: peakTile, onChange: schedule });

function schedule() {
  if (scheduled) return;
  scheduled = true;
  setTimeout(paint, 0);
}

function paint() {
  scheduled = false;
  if (!context || !latest) return;
  const job = latest;
  const width = Math.round(job.width * job.ratio);
  const height = Math.round(job.height * job.ratio);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const { missing } = paintWaveforms(context, job, (media, level, tile) =>
    store.lookup(media, level, tile),
  );
  store.want(missing);
}

self.addEventListener("message", ({ data }) => {
  if (data.type === "init") {
    canvas = data.canvas;
    context = canvas.getContext("2d");
  } else if (data.type === "draw") {
    latest = data.job;
    schedule();
  }
});
