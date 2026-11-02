export function initialTrackControlsState() {
  return { openTrackId: null, pinnedTrackId: null };
}

export function transitionTrackControls(state, action) {
  switch (action.type) {
    case "open":
      if (state.pinnedTrackId && state.pinnedTrackId !== action.trackId) return state;
      return { ...state, openTrackId: action.trackId };
    case "toggle":
      if (state.openTrackId === action.trackId) return initialTrackControlsState();
      return { openTrackId: action.trackId, pinnedTrackId: null };
    case "pin":
      return state.openTrackId === action.trackId
        ? { openTrackId: action.trackId, pinnedTrackId: action.trackId }
        : state;
    case "unpin":
      return state.pinnedTrackId === action.trackId
        ? { openTrackId: action.trackId, pinnedTrackId: null }
        : state;
    case "leave":
      if (
        state.openTrackId !== action.trackId ||
        state.pinnedTrackId === action.trackId ||
        action.pointerInside ||
        action.focusInside
      ) {
        return state;
      }
      return initialTrackControlsState();
    case "outside":
      return state.pinnedTrackId ? state : initialTrackControlsState();
    case "escape":
      return initialTrackControlsState();
    default:
      return state;
  }
}
