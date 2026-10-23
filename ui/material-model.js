// The Material tab's decisions (docs/design/MATERIAL.md), pure: which rows a filter shows, the
// shares of the played bar, and the texts' keys. The server's rows are src/kuulas/material.py.

export const FILTERS = ["all", "timeline", "unused", "takes"];

/** The rows a filter and a text show: on the timeline (played or only cut), not on it, takes. */
export function filterRows(rows, filter, text) {
  const wanted = String(text ?? "")
    .trim()
    .toLowerCase();
  return (rows ?? []).filter((row) => {
    if (filter === "timeline" && row.state === "unused") return false;
    if (filter === "unused" && row.state !== "unused") return false;
    if (filter === "takes" && !row.recorded) return false;
    return (
      wanted === "" ||
      String(row.name ?? "")
        .toLowerCase()
        .includes(wanted)
    );
  });
}

/** The shares of the recording that are played, only cut, and not on the timeline (sum 1). */
export function barShares(row) {
  const total = (row.used_s ?? 0) + (row.cut_s ?? 0) + (row.unused_s ?? 0);
  if (!(total > 0)) return { used: 0, cut: 0, unused: 1 };
  return { used: row.used_s / total, cut: row.cut_s / total, unused: row.unused_s / total };
}

/** A length in seconds as m:ss, or h:mm:ss from an hour. */
export function lengthText(seconds) {
  const whole = Math.max(0, Math.floor(seconds ?? 0));
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  const s = String(whole % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/** The message key that says what became of the recording. */
export function stateKey(row) {
  return `ui.material.state.${row.missing ? "missing" : row.state}`;
}
