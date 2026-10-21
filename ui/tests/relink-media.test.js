// Locate / Relink media on a clip (owner, 2026-10-21): what the confirmation says, from the
// server's check (session.check_replace_media). Pure: relink-media.js relinkPlan.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { relinkPlan } from "../relink-media.js";

const t = (key, params = {}) => `${key}${JSON.stringify(params)}`;
const seconds = (frames) => `${frames / 48000} s`;
const report = (over = {}) => ({
  same_file: false,
  new_media_id: "m2",
  name: "a (cleaned).wav",
  old_frames: 480000,
  new_frames: 480000,
  same_length: true,
  clips: 2,
  ...over,
});

describe("relinkPlan", () => {
  test("the same file found elsewhere: relinked, nothing to confirm", () => {
    const plan = relinkPlan(report({ same_file: true, new_media_id: "m1" }), { t, seconds });
    assert.equal(plan.confirm, false);
    assert.match(plan.notice, /ui\.relink\.same_file/);
  });

  test("an edited copy of the same length: confirm, no warning", () => {
    const plan = relinkPlan(report(), { t, seconds });
    assert.equal(plan.confirm, true);
    assert.equal(plan.warn, false);
    assert.match(plan.title, /ui\.relink\.title/);
    assert.ok(
      plan.lines.some((line) => /ui\.relink\.replace/.test(line) && /"clips":2/.test(line)),
    );
    assert.ok(plan.lines.some((line) => /ui\.relink\.keeps_original/.test(line)));
  });

  test("a different length: confirm with a warning naming both lengths", () => {
    const plan = relinkPlan(report({ new_frames: 432000, same_length: false }), { t, seconds });
    assert.equal(plan.confirm, true);
    assert.equal(plan.warn, true);
    const warning = plan.lines.find((line) => /ui\.relink\.length_differs/.test(line));
    assert.ok(warning);
    assert.match(warning, /10 s/);
    assert.match(warning, /9 s/);
  });

  test("the edit it sends: replace_clip_media from the old to the new media, one step", () => {
    const plan = relinkPlan(report(), { t, seconds, mediaId: "m1" });
    assert.deepEqual(plan.edit, {
      op: "replace_clip_media",
      args: { media_id: "m1", new_media_id: "m2" },
    });
  });
});
