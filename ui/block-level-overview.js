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

// Deviations already use each speaker's own reference. Adding the checked gain is
// an estimate only: no audio is rendered, and final clip gain limits can differ.
export function speakerSummary(speaker, ticked, limits) {
  const rows = speaker.blocks ?? [];
  const valid = rows.filter((row) => Number.isFinite(row.deviation_db));
  const changed = rows.filter((row) => row.gain_db !== 0 && ticked.has(row.id));
  const spread = (values) => (values.length ? [Math.min(...values), Math.max(...values)] : null);
  return {
    before: spread(valid.map((row) => row.deviation_db)),
    after: spread(valid.map((row) => row.deviation_db + (ticked.has(row.id) ? row.gain_db : 0))),
    blocks: changed.length,
    lift: Math.max(0, ...changed.map((row) => row.gain_db)),
    cut: Math.max(0, ...changed.map((row) => -row.gain_db)),
    limited: changed.filter(
      (row) => row.gain_db >= limits.max_boost_db || -row.gain_db >= limits.max_cut_db,
    ).length,
    leftOut: rows.length - changed.length,
  };
}
