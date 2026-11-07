/** Pure interaction state for the track-control overlay. */
export const TRACK_FLYOUT_CLOSE_DELAY_MS = 140;

export const initialTrackFlyoutState = () => ({
  hoveredId: null,
  focusedId: null,
  pinnedId: null,
});

export function trackFlyoutReducer(state, event) {
  switch (event.type) {
    case "hover":
      return { ...state, hoveredId: event.trackId };
    case "leave":
      return state.hoveredId === event.trackId ? { ...state, hoveredId: null } : state;
    case "focus":
      return { ...state, focusedId: event.trackId };
    case "blur":
      return state.focusedId === event.trackId ? { ...state, focusedId: null } : state;
    case "pin":
      return { ...state, pinnedId: state.pinnedId === event.trackId ? null : event.trackId };
    case "escape":
      return { ...state, pinnedId: null, focusedId: null, hoveredId: null };
    case "remove":
      return {
        hoveredId: state.hoveredId === event.trackId ? null : state.hoveredId,
        focusedId: state.focusedId === event.trackId ? null : state.focusedId,
        pinnedId: state.pinnedId === event.trackId ? null : state.pinnedId,
      };
    default:
      return state;
  }
}

export function openTrackFlyoutId(state) {
  return state.pinnedId ?? state.focusedId ?? state.hoveredId;
}
