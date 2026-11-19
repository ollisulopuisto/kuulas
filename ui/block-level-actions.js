// Block inspection actions share the editor's focus rules and always audition the edit.
import { focusTrack } from "./range-scope.js";

export function createBlockLevelActions({ api, getState, setState, transport, jumpTo, onError }) {
  return {
    async onListen(row) {
      try {
        const response = await api.renderListen(false);
        // This endpoint returns the unchanged project too. Publishing it would mark the
        // measurement stale even though only the playback source changed.
        setState({ render: response.render });
        await transport.preview(row.start, row.end);
      } catch (error) {
        onError(error);
      }
    },
    onJump(row) {
      if (row.track_ids?.[0]) setState(focusTrack(getState(), row.track_ids[0]));
      jumpTo(row.start);
    },
  };
}
