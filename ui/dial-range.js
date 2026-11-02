// The same native range is a dial in short headers and a rail in taller ones.
// Native arrows/Home/End remain available; pointer motion is vertical, not angular.
export function bindDialRange(input, isDial) {
  const paint = () => {
    const min = Number(input.min);
    const max = Number(input.max);
    const fraction = Math.max(0, Math.min(1, (Number(input.value) - min) / (max - min)));
    input.parentElement.style.setProperty("--dial-angle", `${-135 + fraction * 270}deg`);
    input.title = `${input.getAttribute("aria-label")}: ${input.getAttribute("aria-valuetext") || input.value}`;
    input.setAttribute("aria-orientation", isDial() ? "vertical" : "horizontal");
  };
  input.addEventListener("input", paint);
  input.addEventListener("pointerdown", (event) => {
    if (!isDial() || event.button !== 0) return;
    event.preventDefault();
    input.focus();
    input.setPointerCapture(event.pointerId);
    const start = Number(input.value);
    const y = event.clientY;
    const min = Number(input.min);
    const max = Number(input.max);
    const step = Number(input.step) || 1;
    const move = (e) => {
      const distance = e.shiftKey ? 600 : 150;
      const value = Math.max(
        min,
        Math.min(max, start + ((y - e.clientY) / distance) * (max - min)),
      );
      input.value = String(Math.round(value / step) * step);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    };
    const done = () => {
      input.removeEventListener("pointermove", move);
      input.removeEventListener("pointerup", done);
      input.removeEventListener("pointercancel", done);
    };
    input.addEventListener("pointermove", move);
    input.addEventListener("pointerup", done);
    input.addEventListener("pointercancel", done);
  });
  return paint;
}

export function controlLines(height) {
  return height < 60 ? 1 : height < 100 ? 2 : 3;
}
