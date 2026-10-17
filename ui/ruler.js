// Ruler ticks that adapt to zoom: a round step (1-2-5 of a unit, or whole
// minutes and hours) whose labels never come closer than MIN_LABEL_PX.
import { formatClock } from "./i18n.js";

export const MIN_LABEL_PX = 80;
const MIN_MINOR_PX = 6;
const MINORS_PER_STEP = 5;
const STEPS_S = [
  0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900,
  1800, 3600, 7200, 14_400, 43_200,
];

function stepFor(zoom, rate) {
  return STEPS_S.find((seconds) => (seconds * rate) / zoom >= MIN_LABEL_PX) ?? STEPS_S.at(-1);
}

function digitsFor(step) {
  return step >= 1 ? 0 : Math.ceil(-Math.log10(step) - 1e-9);
}

/**
 * Ticks for the visible range: { frame, x, label }. `label` is null for the
 * small ticks between labelled ones.
 */
export function rulerTicks({ scroll, zoom, width, rate }) {
  const step = stepFor(zoom, rate);
  const stepFrames = step * rate;
  const minorFrames = stepFrames / MINORS_PER_STEP;
  const withMinor = minorFrames / zoom >= MIN_MINOR_PX;
  const unit = withMinor ? minorFrames : stepFrames;
  const per = withMinor ? MINORS_PER_STEP : 1;
  const digits = digitsFor(step);
  const ticks = [];
  const last = scroll + width * zoom;
  for (let k = Math.ceil(scroll / unit); k * unit <= last; k += 1) {
    const frame = Math.round(k * unit);
    const major = k % per === 0;
    ticks.push({
      frame,
      x: (frame - scroll) / zoom,
      label: major ? formatClock(frame / rate, digits) : null,
    });
  }
  return ticks;
}
