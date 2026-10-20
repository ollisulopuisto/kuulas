// Track > Auto > Set music level…: the offset ("Music under speech (dB)"), the measured
// numbers and what Apply would set, pure (the dialog is music-level-dialog.js). The rule and
// the limits mirror src/kuulas/music_level.py; the server checks again.

import { parseNumber } from "./silence-model.js";

/** Remembered in Preferences (prefs.js) under this key. */
export const MUSIC_UNDER_KEY = "musicUnderSpeechDb";
/** Owner, 2026-10-20: clearly under the voice. The automixer's own fixed rule is -1. */
export const DEFAULT_MUSIC_UNDER_DB = -10;
export const MIN_MUSIC_UNDER_DB = -30;
export const MAX_MUSIC_UNDER_DB = 0;
/** The Preferences slider's step; the dialog's field takes any number in range. */
export const MUSIC_UNDER_STEP_DB = 1;

const clamp = (value) => Math.min(MAX_MUSIC_UNDER_DB, Math.max(MIN_MUSIC_UNDER_DB, value));

/** A stored value -> dB within the range, else the default. */
export function normaliseMusicUnder(value) {
  const number = parseNumber(value);
  return number === null ? DEFAULT_MUSIC_UNDER_DB : clamp(number);
}

/** What was typed -> { ok, error (message key or null), value }. Never clamps silently. */
export function validateMusicUnder(text) {
  const number = parseNumber(text);
  if (number === null) return { ok: false, error: "ui.music_level.error_number", value: null };
  if (number < MIN_MUSIC_UNDER_DB || number > MAX_MUSIC_UNDER_DB) {
    return { ok: false, error: "ui.music_level.error_range", value: null };
  }
  return { ok: true, error: null, value: number };
}

/** The message key for a measurement that has nothing to apply, else null. */
export function measureError(result) {
  if (result?.reason === "no_music") return "error.music_level.no_music";
  if (result?.reason === "no_speech") return "error.music_level.no_speech";
  if (result?.speech_lufs == null || result?.bed_lufs == null) return "ui.music_level.failed";
  return null;
}

/**
 * The gain Apply gives the loudest-set music track (the others keep their balance under it):
 * speech + offset - bed. Null when the measurement cannot be applied.
 */
export function proposedGain(result, offset) {
  if (measureError(result)) return null;
  return Math.round((result.speech_lufs + offset - result.bed_lufs) * 100) / 100;
}

/** "10.0 dB under the speech" / "2.3 dB above the speech". `fmt` formats one decimal. */
export function against(db, t, fmt) {
  return db <= 0
    ? t("music_level.under", { db: fmt(-db) })
    : t("music_level.above", { db: fmt(db) });
}

/** The dialog's result lines for a finished measurement, or [] when it has nothing to show. */
export function summaryLines(result, offset, t, fmt) {
  const gain = proposedGain(result, offset);
  if (gain === null) return [];
  const lines = [
    t("ui.music_level.speech", { lufs: fmt(result.speech_lufs) }),
    t("ui.music_level.bed", { lufs: fmt(result.bed_lufs) }),
  ];
  if (result.was_db != null) {
    lines.push(t("ui.music_level.now", { where: against(result.was_db, t, fmt) }));
  }
  const many = (result.music_tracks?.length ?? 1) > 1;
  lines.push(
    t(many ? "ui.music_level.result_many" : "ui.music_level.result_one", { gain: fmt(gain) }),
  );
  return lines;
}
