// The JKL shuttle ladder: a port of src/kuulas/shuttle.py. Both read
// ui/tests/fixtures/shuttle-cases.json, so they cannot drift apart.

export const LADDER = [1, 1.5, 2, 3, 5];
/** Tap-step length (ms) for held scrubbing. */
export const STEP_MS = 10;

function nextLadder(speed, sign) {
  if (sign * speed <= 0) return sign * LADDER[0];
  const step = LADDER.find((s) => s > Math.abs(speed)) ?? LADDER.at(-1);
  return sign * step;
}

/** The new signed speed after `key` ("j" backward, "k" stop, "l" forward); K is 0. */
export function press(speed, key) {
  if (key === "k") return 0;
  if (key === "l") return nextLadder(speed, 1);
  if (key === "j") return nextLadder(speed, -1);
  throw new Error(`unknown shuttle key: ${key}`);
}

/** "tape" (pitch follows speed) up to 2x either way; above that, "grains". */
export const scrubStyle = (speed) => (Math.abs(speed) <= 2 ? "tape" : "grains");

/** The slow signed speed while K is held with L ("l") or J ("j"). */
export function heldScrubSpeed(direction) {
  if (direction === "l") return 0.25;
  if (direction === "j") return -0.25;
  throw new Error(`unknown shuttle key: ${direction}`);
}
