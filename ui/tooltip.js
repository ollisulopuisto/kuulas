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

/** One tip box for the whole page, shown while the pointer is over an element with data-tip. */
export function installTooltips(doc = document) {
  const box = doc.createElement("div");
  box.className = "hover-tip";
  box.setAttribute("role", "tooltip");
  box.hidden = true;
  doc.body.append(box);
  doc.addEventListener(
    "pointermove",
    (event) => {
      const text = event.target.closest?.("[data-tip]")?.dataset.tip ?? "";
      if (!text) {
        box.hidden = true;
        return;
      }
      if (box.textContent !== text) box.textContent = text;
      box.hidden = false;
      const at = tipPlacement(
        { x: event.clientX, y: event.clientY },
        { width: box.offsetWidth, height: box.offsetHeight },
        { width: window.innerWidth, height: window.innerHeight },
      );
      box.style.left = `${at.left}px`;
      box.style.top = `${at.top}px`;
    },
    { capture: true },
  ); // first, so a handler that stops the event below cannot hide the tip
  doc.documentElement.addEventListener("pointerleave", () => {
    box.hidden = true;
  });
}
