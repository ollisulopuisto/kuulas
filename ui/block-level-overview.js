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
  let before = null;
  let after = null;
  let blocks = 0;
  let lift = 0;
  let cut = 0;
  let limited = 0;
  const rows = speaker.blocks ?? [];
  for (const row of rows) {
    const included = row.gain_db !== 0 && ticked.has(row.id);
    if (Number.isFinite(row.deviation_db)) {
      const estimated = row.deviation_db + (included ? row.gain_db : 0);
      before = before
        ? [Math.min(before[0], row.deviation_db), Math.max(before[1], row.deviation_db)]
        : [row.deviation_db, row.deviation_db];
      after = after
        ? [Math.min(after[0], estimated), Math.max(after[1], estimated)]
        : [estimated, estimated];
    }
    if (!included) continue;
    blocks += 1;
    lift = Math.max(lift, row.gain_db);
    cut = Math.max(cut, -row.gain_db);
    if (row.gain_db >= limits.max_boost_db || -row.gain_db >= limits.max_cut_db) limited += 1;
  }
  return { before, after, blocks, lift, cut, limited, leftOut: rows.length - blocks };
}

// The "Muualle muutoksia:" links: the other speakers that still have ticked changes.
export function othersChanging(speakers, active, ticked, limits) {
  return speakers
    .filter((speaker) => speaker !== active)
    .map((speaker) => ({ speaker, blocks: speakerSummary(speaker, ticked, limits).blocks }))
    .filter((entry) => entry.blocks > 0);
}

// Every measured block, changed or not (the "Kaikki N lohkoa" count).
export function totalBlocks(measured) {
  return (measured.speakers ?? []).reduce(
    (total, speaker) => total + (speaker.blocks ?? []).length,
    0,
  );
}

// The measured level spread across every speaker, for "all blocks are already within".
export function overallSpan(measured) {
  let span = null;
  for (const speaker of measured.speakers ?? [])
    for (const row of speaker.blocks ?? [])
      if (Number.isFinite(row.deviation_db))
        span = span
          ? [Math.min(span[0], row.deviation_db), Math.max(span[1], row.deviation_db)]
          : [row.deviation_db, row.deviation_db];
  return span;
}

export function spansEqual(a, b) {
  return a !== null && b !== null && a[0] === b[0] && a[1] === b[1];
}
