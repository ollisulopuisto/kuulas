import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { describeMoves, formatShift, SHOWN } from "../sync-confirm.js";

const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;
const format = (value) => value.toFixed(2);
const move = (track, shift, extra = {}) => ({
  clip_id: track,
  track,
  name: "",
  shift,
  to_track: null,
  ...extra,
});

describe("formatShift", () => {
  test("seconds with a sign and two decimals", () => {
    assert.equal(formatShift(59520, 48000, format), "+1.24 s");
    assert.equal(formatShift(-14880, 48000, format), "−0.31 s");
  });
});

describe("describeMoves", () => {
  test("a short list names every clip with its shift", () => {
    const preview = {
      command: "resync",
      rate: 48000,
      anchor: "Zoom",
      count: 2,
      moves: [move("Olli 2", 59520), move("Kari", -14880)],
    };
    const d = describeMoves(preview, { t, format });
    assert.match(d.title, /^ui\.sync\.confirm\.title.*"count":2.*Zoom/);
    assert.equal(d.lines.length, 2);
    assert.match(d.lines[0], /Olli 2.*\+1\.24 s/);
    assert.match(d.lines[1], /Kari.*−0\.31 s/);
    assert.equal(d.more, "");
  });

  test("a long list shows a few and says how many more", () => {
    const moves = Array.from({ length: SHOWN + 5 }, (_, i) => move(`T${i}`, 480));
    const d = describeMoves(
      { command: "resync", rate: 48000, anchor: "Zoom", count: moves.length, moves },
      { t, format },
    );
    assert.equal(d.lines.length, SHOWN);
    assert.match(d.more, /ui\.sync\.confirm\.more.*"count":5/);
  });

  test("the clip name follows the track name when the clip has one", () => {
    const d = describeMoves(
      {
        command: "resync",
        rate: 48000,
        anchor: "",
        count: 1,
        moves: [move("Kari", 480, { name: "intro" })],
      },
      { t, format },
    );
    assert.match(d.lines[0], /Kari · intro/);
  });

  test("send home names the track each clip goes back to", () => {
    const d = describeMoves(
      {
        command: "send_home",
        rate: 48000,
        anchor: "",
        count: 1,
        moves: [move("Ville", 0, { to_track: "Anna" })],
      },
      { t, format },
    );
    assert.match(d.title, /^ui\.sync\.confirm\.title_home/);
    assert.match(d.lines[0], /ui\.sync\.confirm\.line_home.*Ville.*Anna/);
  });
});
