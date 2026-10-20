// Track > Auto > Set music level…: the offset field, the measured numbers and what Apply
// would set, pure (the dialog is music-level-dialog.js; the rule is src/kuulas/music_level.py).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  against,
  DEFAULT_MUSIC_UNDER_DB,
  MAX_MUSIC_UNDER_DB,
  MIN_MUSIC_UNDER_DB,
  measureError,
  normaliseMusicUnder,
  proposedGain,
  summaryLines,
  validateMusicUnder,
} from "../music-level-model.js";

const t = (key, params = {}) => `${key}${JSON.stringify(params)}`;
const fmt = (value) => value.toFixed(1);

const result = (over = {}) => ({
  speech_lufs: -18,
  bed_lufs: -12,
  was_db: 6,
  reason: null,
  mode: "common",
  balance: { m1: 0 },
  music_tracks: ["m1"],
  ...over,
});

describe("the offset", () => {
  test("defaults to -10 dB within -30..0", () => {
    assert.equal(DEFAULT_MUSIC_UNDER_DB, -10);
    assert.deepEqual([MIN_MUSIC_UNDER_DB, MAX_MUSIC_UNDER_DB], [-30, 0]);
    assert.equal(normaliseMusicUnder(null), -10);
    assert.equal(normaliseMusicUnder("junk"), -10);
    assert.equal(normaliseMusicUnder("-12"), -12);
    assert.equal(normaliseMusicUnder(-45), -30);
    assert.equal(normaliseMusicUnder(3), 0);
  });

  test("the field takes a comma decimal and refuses what is out of range, never clamping", () => {
    assert.deepEqual(validateMusicUnder("-7,5"), { ok: true, error: null, value: -7.5 });
    assert.equal(validateMusicUnder("x").error, "ui.music_level.error_number");
    assert.equal(validateMusicUnder("").error, "ui.music_level.error_number");
    assert.equal(validateMusicUnder("-31").error, "ui.music_level.error_range");
    assert.equal(validateMusicUnder("2").error, "ui.music_level.error_range");
  });
});

describe("the measurement", () => {
  test("no music and no speech are said, not shown as numbers", () => {
    assert.equal(measureError(result({ reason: "no_music" })), "error.music_level.no_music");
    assert.equal(measureError(result({ reason: "no_speech" })), "error.music_level.no_speech");
    assert.equal(measureError(result()), null);
    assert.equal(proposedGain(result({ reason: "no_music" }), -10), null);
  });

  test("Apply would set the loudest track to speech + offset - bed", () => {
    assert.equal(proposedGain(result(), -10), -16);
    assert.equal(proposedGain(result(), 0), -6);
  });

  test("where the music sits, in words", () => {
    assert.equal(against(-10, t, fmt), 'music_level.under{"db":"10.0"}');
    assert.equal(against(2.25, t, fmt), 'music_level.above{"db":"2.3"}');
  });

  test("the lines: speech, bed, where it is now, what Apply sets", () => {
    const lines = summaryLines(result(), -10, t, fmt);
    assert.deepEqual(lines, [
      'ui.music_level.speech{"lufs":"-18.0"}',
      'ui.music_level.bed{"lufs":"-12.0"}',
      `ui.music_level.now{"where":"music_level.above{\\"db\\":\\"6.0\\"}"}`,
      'ui.music_level.result_one{"gain":"-16.0"}',
    ]);
    const many = summaryLines(result({ music_tracks: ["m1", "m2"] }), -10, t, fmt);
    assert.equal(many[3], 'ui.music_level.result_many{"gain":"-16.0"}');
    assert.deepEqual(summaryLines(result({ reason: "no_music" }), -10, t, fmt), []);
  });
});

test("every text the model and the dialog use exists in both catalogs", () => {
  const keys = [
    "cmd.app.music_level",
    "cmd.app.music_level.hint",
    "ui.music_level.title",
    "ui.music_level.offset",
    "ui.music_level.offset_hint",
    "ui.music_level.error_number",
    "ui.music_level.error_range",
    "ui.music_level.measuring",
    "ui.music_level.speech",
    "ui.music_level.bed",
    "ui.music_level.now",
    "ui.music_level.result_one",
    "ui.music_level.result_many",
    "ui.music_level.failed",
    "ui.music_level.cancel",
    "ui.music_level.apply",
    "ui.music_level.clamped",
    "ui.prefs.music_under_speech",
    "music_level.under",
    "music_level.above",
    "error.music_level.no_music",
    "error.music_level.no_speech",
  ];
  for (const lang of ["en", "fi"]) {
    const words = JSON.parse(
      readFileSync(
        fileURLToPath(new URL(`../../src/kuulas/locales/${lang}.json`, import.meta.url)),
        "utf8",
      ),
    );
    for (const key of keys) assert.ok(words[key], `${lang}: ${key}`);
  }
});
