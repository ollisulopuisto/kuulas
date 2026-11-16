// The hover tip: an element with a data-tip attribute shows its text in a box the app draws.
// The native title tip is drawn by the operating system in its own light or dark style, and
// it can be hard to see on the app's dark surfaces, so the app draws its own on the raised
// surface colour with a border.

const GAP_X = 14; // the tip's offset from the pointer, to the right
const GAP_Y = 18; // and below it
const EDGE = 8; // the smallest distance kept from the window's edges

/**
 * Where a tip of `size` goes for a pointer at `pointer` in a window of `view`: below and right of
 * the pointer, turned to the other side where it would leave the window, never past the edges.
 */
export function tipPlacement(pointer, size, view) {
  let left = pointer.x + GAP_X;
  if (left + size.width > view.width - EDGE) left = pointer.x - size.width - GAP_X;
  let top = pointer.y + GAP_Y;
  if (top + size.height > view.height - EDGE) top = pointer.y - size.height - 10;
  return { left: Math.max(EDGE, left), top: Math.max(EDGE, top) };
}

export const REST_MS = 600; // how long the pointer must rest before a hint appears
const REST_SLOP = 4; // px of movement that still counts as resting

/**
 * Calls `onRest` once the pointer has stayed within a few pixels of one spot, over the same `key`
 * (the text it would show), for REST_MS. Any larger move, or a new key, calls `onMove` and starts
 * the wait again; `cancel` stops it.
 */
export function createRestDelay({ onRest, onMove, timers = globalThis }) {
  let origin = null;
  let key = null;
  let timer = null;
  function cancel() {
    timers.clearTimeout(timer);
    timer = null;
    origin = null;
    key = null;
    onMove();
  }
  function move(x, y, next) {
    if (origin && next === key && Math.hypot(x - origin.x, y - origin.y) <= REST_SLOP) return;
    timers.clearTimeout(timer);
    origin = { x, y };
    key = next;
    onMove();
    timer = timers.setTimeout(onRest, REST_MS);
  }
  return { move, cancel };
}

/** One tip box for the whole page, shown once the pointer rests on an element with data-tip. */
export function installTooltips(doc = document) {
  const box = doc.createElement("div");
  box.className = "hover-tip";
  box.setAttribute("role", "tooltip");
  box.hidden = true;
  doc.body.append(box);
  let last = null;
  const rest = createRestDelay({
    onMove() {
      box.hidden = true;
    },
    onRest() {
      box.textContent = last.text;
      box.hidden = false;
      const at = tipPlacement(
        { x: last.x, y: last.y },
        { width: box.offsetWidth, height: box.offsetHeight },
        { width: window.innerWidth, height: window.innerHeight },
      );
      box.style.left = `${at.left}px`;
      box.style.top = `${at.top}px`;
    },
  });
  doc.addEventListener(
    "pointermove",
    (event) => {
      const text = event.target.closest?.("[data-tip]")?.dataset.tip ?? "";
      if (!text) {
        rest.cancel();
        return;
      }
      last = { text, x: event.clientX, y: event.clientY };
      rest.move(event.clientX, event.clientY, text);
    },
    { capture: true },
  ); // first, so a handler that stops the event below cannot hide the tip
  for (const type of ["pointerdown", "keydown", "wheel"]) {
    doc.addEventListener(type, rest.cancel, { capture: true, passive: true });
  }
  doc.documentElement.addEventListener("pointerleave", rest.cancel);
}
