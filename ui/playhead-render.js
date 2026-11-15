/** Draw only the playhead on its own animation layer. Positions stay subpixel for smooth travel. */
export function drawPlayhead(context, { frame, scroll, zoom, width, height, ratio = 1, color }) {
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  const x = (frame - scroll) / zoom;
  if (!Number.isFinite(x) || x < -5.5 || x > width + 5.5) return false;

  context.strokeStyle = color;
  context.fillStyle = color;
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(x, 0);
  context.lineTo(x, height);
  context.stroke();
  context.beginPath();
  context.moveTo(x - 5.5, 0);
  context.lineTo(x + 5.5, 0);
  context.lineTo(x + 5.5, 6);
  context.lineTo(x, 11);
  context.lineTo(x - 5.5, 6);
  context.closePath();
  context.fill();
  return true;
}
