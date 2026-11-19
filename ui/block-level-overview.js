// Overview and selection are views of the measured proposals, never a second levelling
// algorithm. A marked range includes whole blocks only (owner, 2026-11-19).
export function overviewSpeakers(measured) {
  return (measured.speakers ?? []).map((speaker) => ({
    ...speaker,
    rows: (speaker.blocks ?? []).filter((row) => row.gain_db !== 0),
  }));
}
export function overviewScale(measured) {
  const rows = (measured.speakers ?? []).flatMap((speaker) => speaker.blocks ?? []);
  return {
    end: Math.max(1, ...rows.map((row) => row.end)),
    gain: Math.max(1, ...rows.map((row) => Math.abs(row.gain_db))),
  };
}
export function eligibleBlockIds(
  measured,
  { range = null, threshold = measured.threshold_db } = {},
) {
  if (!Number.isFinite(threshold)) return new Set();
  const floor = Math.max(measured.threshold_db, threshold);
  return new Set(
    overviewSpeakers(measured)
      .flatMap((speaker) => speaker.rows)
      .filter(
        (row) =>
          Math.abs(row.deviation_db) >= floor &&
          (!range || (range.end > range.start && row.start >= range.start && row.end <= range.end)),
      )
      .map((row) => row.id),
  );
}
