// What a mouse drag on the timeline does (owner, 2026-10-18): a PREFERENCE with two modes.
//   "range" (default): dragging paints a range, ready to delete or mute; a clip is moved by
//     dragging its label strip, or with Cmd (Ctrl) held, or by dragging any of two or more
//     selected clips.
//   "move": dragging a clip moves it (Hindenburg's way); Shift or Alt paint a range.
// Empty lane space always paints a range. Edges (trim), envelope points, gain line and fade
// handles keep their own behaviour in both modes. Pure; timeline.js asks per press.
import { MOVE_STRIP_PX } from "./clip-drag.js";

export const DRAG_MODES = ["range", "move"];
export const DEFAULT_DRAG_MODE = "range";

export const dragModeChoice = (stored) =>
  DRAG_MODES.includes(stored) ? stored : DEFAULT_DRAG_MODE;
export const nextDragMode = (mode) => (mode === "range" ? "move" : "range");

/**
 * "move", "range" or null (a press that starts neither). `rowY` is px from the lane's top;
 * `hit` is lanes.js hitTest's answer.
 */
export function dragIntent({
  mode,
  hit,
  rowY,
  shift = false,
  alt = false,
  mod = false,
  inSelection = false,
  selectionSize = 0,
}) {
  if (!hit || hit.area !== "lane" || hit.row?.kind !== "track") return null;
  if (hit.edge != null || hit.point != null) return null;
  if (hit.clip == null) return "range";
  // Alt+Cmd (Ctrl) on a clip moves it alone, out of its sync group (R51); Alt alone paints a range.
  if (alt && mod) return "move";
  if (shift || alt) return "range";
  if (mod) return "move";
  if (mode === "move") return "move";
  // A selection of several clips (after Select forward, say) is dragged as it is; one clip that
  // was just clicked still paints, or nothing could be painted on a clip you have clicked.
  if (inSelection && selectionSize >= 2) return "move";
  return rowY >= 0 && rowY < MOVE_STRIP_PX ? "move" : "range";
}
