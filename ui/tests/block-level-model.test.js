// Track > Auto > Level blocks…: the rows, the ticks and what Apply sends, pure (the panel is
// block-level-panel.js; the rule is src/kuulas/block_level.py).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  allChangedIds,
  blockText,
  canApply,
  changedBySpeaker,
  leftAloneCount,
  loudBySpeaker,
  loudText,
  measureError,
  phaseAfterEdit,
  ruleText,
  skipIds,
} from "../block-level-model.js";

const t = (key, params = {}) => `${key}${JSON.stringify(params)}`;
const fmt = (value) => value.toFixed(1);
const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
const RATE = 48000;

const block = (id, start, end, deviation, gain) => ({
  id,
  start: start * RATE,
  end: end * RATE,
  own_s: end - start,
  level_db: -20,
  deviation_db: deviation,
  gain_db: gain,
});

const result = (over = {}) => ({
  key: "k",
  reason: null,
  rate: RATE,
  threshold_db: 3,
  max_cut_db: 18,
  max_boost_db: 6,
  speakers: [
    {
      name: "anna",
      track_ids: ["t1"],
      blocks: [block("anna#0", 1, 9, 0.2, 0), block("anna#1", 21, 29, 12, -12)],
      loud: [{ start: 3 * RATE, end: 4 * RATE, excess_db: 8 }],
    },
    { name: "ville", track_ids: ["t2"], blocks: [block("ville#0", 5, 15, -6, 6)], loud: [] },
  ],
  ...over,
});

describe("the measurement", () => {
  test("no speech and a malformed answer are said, not listed", () => {
    assert.equal(measureError(result({ reason: "no_speech" })), "error.block_level.no_speech");
    assert.equal(measureError(result({ speakers: undefined })), "ui.block_level.failed");
    assert.equal(measureError(result({ key: undefined })), "ui.block_level.failed");
    assert.equal(measureError(result()), null);
    assert.deepEqual(changedBySpeaker(result({ reason: "no_speech" })), []);
    assert.equal(leftAloneCount(undefined), 0);
  });

  test("only blocks with a gain are rows; the others are counted", () => {
    const rows = changedBySpeaker(result());
    assert.deepEqual(
      rows.map((r) => [r.name, r.rows.map((b) => b.id)]),
      [
        ["anna", ["anna#1"]],
        ["ville", ["ville#0"]],
      ],
    );
    assert.equal(leftAloneCount(result()), 1);
  });

  test("loud spots are listed apart from the rows", () => {
    const loud = loudBySpeaker(result());
    assert.deepEqual(
      loud.map((l) => [l.name, l.spots.length]),
      [["anna", 1]],
    );
  });
});

describe("the ticks", () => {
  test("all changed blocks start ticked and nothing is skipped", () => {
    const ticked = allChangedIds(result());
    assert.deepEqual([...ticked].sort(), ["anna#1", "ville#0"]);
    assert.deepEqual(skipIds(result(), ticked), []);
  });

  test("an unticked row is sent as skip", () => {
    const ticked = allChangedIds(result());
    ticked.delete("anna#1");
    assert.deepEqual(skipIds(result(), ticked), ["anna#1"]);
  });
});

describe("the text", () => {
  test("a row says where, how far off and the gain, signed", () => {
    const row = blockText(block("a", 21, 29, 12, -12), RATE, t, fmt, clock);
    assert.equal(
      row,
      'ui.block_level.row{"start":"0:21","end":"0:29","deviation":"+12.0","gain":"-12.0"}',
    );
  });

  test("a loud spot says where and how far over", () => {
    assert.equal(
      loudText({ start: 3 * RATE, end: 4 * RATE, excess_db: 8 }, RATE, t, fmt, clock),
      'ui.block_level.loud_row{"start":"0:03","end":"0:04","excess":"8.0"}',
    );
  });

  test("the rule line shows the threshold and the limits", () => {
    assert.equal(
      ruleText(result(), t, fmt),
      'ui.block_level.rule{"threshold":"3.0","cut":"18.0","boost":"6.0"}',
    );
  });
});

test("every text the model and the dialog use exists in both catalogs", () => {
  const keys = [
    "cmd.app.block_level",
    "cmd.app.block_level.hint",
    "ui.block_level.title",
    "ui.block_level.measuring",
    "ui.block_level.rule",
    "ui.block_level.blocks",
    "ui.block_level.row",
    "ui.block_level.none",
    "ui.block_level.left",
    "ui.block_level.loud",
    "ui.block_level.loud_row",
    "ui.block_level.markers",
    "ui.block_level.failed",
    "ui.block_level.close",
    "ui.block_level.measure_again",
    "ui.block_level.stale",
    "ui.block_level.apply",
    "ui.block_level.done",
    "ui.block_level.clamped",
    "ui.block_level.left_out",
    "ui.automix.done_text_block",
    "ui.automix.done_stale_block",
    "ui.automix.done_again_block",
    "error.block_level.no_speech",
    "error.block_level.stale",
  ];
  for (const lang of ["en", "fi"]) {
    const path = fileURLToPath(new URL(`../../src/kuulas/locales/${lang}.json`, import.meta.url));
    const catalog = JSON.parse(readFileSync(path, "utf8"));
    for (const key of keys) assert.ok(catalog[key], `${lang} lacks ${key}`);
  }
});

describe("the panel's phases while you edit", () => {
  test("an edit makes a measuring or ready panel stale, the others stay", () => {
    assert.equal(phaseAfterEdit("measuring"), "stale");
    assert.equal(phaseAfterEdit("ready"), "stale");
    assert.equal(phaseAfterEdit("idle"), "idle");
    assert.equal(phaseAfterEdit("failed"), "failed");
    assert.equal(phaseAfterEdit("stale"), "stale");
  });
  test("only a ready result can be applied", () => {
    assert.deepEqual(["idle", "measuring", "ready", "stale", "failed"].map(canApply), [
      false,
      false,
      true,
      false,
      false,
    ]);
  });
});
