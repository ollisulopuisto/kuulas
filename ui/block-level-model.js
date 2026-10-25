// Track > Auto > Level blocks…: the measured blocks as rows the dialog lists, what is ticked
// and what Apply sends, pure (the dialog is block-level-panel.js; the rule is
// src/kuulas/block_level.py, which takes speechmix.blocks and sets clip gains).

/** The message key for a measurement that has nothing to show or apply, else null. */
export function measureError(result) {
  if (result?.reason === "no_speech") return "error.block_level.no_speech";
  if (!Array.isArray(result?.speakers) || typeof result?.key !== "string") {
    return "ui.block_level.failed";
  }
  return null;
}

/** The blocks Apply would change (a gain other than 0), by speaker: [{ name, rows }]. */
export function changedBySpeaker(result) {
  if (measureError(result)) return [];
  const out = [];
  for (const speaker of result.speakers) {
    const rows = (speaker.blocks ?? []).filter((block) => block.gain_db !== 0);
    if (rows.length > 0) out.push({ name: speaker.name, rows });
  }
  return out;
}

/** How many blocks are within the threshold and stay as they are. */
export function leftAloneCount(result) {
  if (measureError(result)) return 0;
  let count = 0;
  for (const speaker of result.speakers) {
    count += (speaker.blocks ?? []).filter((block) => block.gain_db === 0).length;
  }
  return count;
}

/** The loud spots (listened to, never changed), by speaker: [{ name, spots }]. */
export function loudBySpeaker(result) {
  if (measureError(result)) return [];
  return result.speakers
    .filter((speaker) => (speaker.loud ?? []).length > 0)
    .map((speaker) => ({ name: speaker.name, spots: speaker.loud }));
}

/** The ids of the changed blocks that are not ticked: what Apply sends as `skip`. */
export function skipIds(result, ticked) {
  return changedBySpeaker(result)
    .flatMap((speaker) => speaker.rows)
    .filter((block) => !ticked.has(block.id))
    .map((block) => block.id);
}

/** Every changed block's id: the ticked set when the dialog opens (all of them). */
export function allChangedIds(result) {
  return new Set(
    changedBySpeaker(result)
      .flatMap((speaker) => speaker.rows)
      .map((block) => block.id),
  );
}

const signed = (value, fmt) => (value > 0 ? `+${fmt(value)}` : fmt(value));

/**
 * One row's text: "1:02–1:10: +12.0 dB off its level, gain -12.0 dB". `rate` turns the
 * block's frames into seconds; `clock(seconds)` formats them, `fmt(value)` one decimal.
 */
export function blockText(block, rate, t, fmt, clock) {
  return t("ui.block_level.row", {
    start: clock(block.start / rate),
    end: clock(block.end / rate),
    deviation: signed(block.deviation_db, fmt),
    gain: signed(block.gain_db, fmt),
  });
}

/** One loud spot's text: "0:03–0:04: 8.0 dB over its block". */
export function loudText(spot, rate, t, fmt, clock) {
  return t("ui.block_level.loud_row", {
    start: clock(spot.start / rate),
    end: clock(spot.end / rate),
    excess: fmt(spot.excess_db),
  });
}

/** The rule line with the threshold and limits the measurement reports. */
export function ruleText(result, t, fmt) {
  return t("ui.block_level.rule", {
    threshold: fmt(result.threshold_db),
    cut: fmt(result.max_cut_db),
    boost: fmt(result.max_boost_db),
  });
}

/**
 * The panel stays open while you edit (it is not a modal). Phases: idle, measuring, ready (a
 * result you can Apply), stale (the project changed after the measuring started, so the
 * result no longer fits: Apply stays off until you measure again), failed.
 * An edit makes a measuring or ready panel stale; the rest are unchanged.
 */
export function phaseAfterEdit(phase) {
  return phase === "measuring" || phase === "ready" ? "stale" : phase;
}

/** Apply is on only for a result that still fits the project. */
export const canApply = (phase) => phase === "ready";
