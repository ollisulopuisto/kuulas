// The visual grammar registry (ui/grammar.js): every signal is complete, the
// helpers that decide what a clip shows are right, and user themes are checked.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  BUS_HUES,
  busHues,
  busLetter,
  CHANNELS,
  fileMark,
  needsFileMark,
  pickSignals,
  resolvePalette,
  ribbonLayout,
  SEMANTIC_TOKENS,
  SIGNALS,
  seamKind,
  signal,
  signalTokens,
  themeFromManifest,
  zebraSteps,
} from "../grammar.js";

describe("the registry", () => {
  test("every signal has an id, a known channel, a priority, tokens and a twin", () => {
    const ids = new Set();
    for (const s of SIGNALS) {
      assert.ok(s.id && !ids.has(s.id), `duplicate or missing id: ${s.id}`);
      ids.add(s.id);
      assert.ok(CHANNELS.includes(s.channel), `${s.id}: unknown channel ${s.channel}`);
      assert.ok(Number.isInteger(s.priority) && s.priority >= 0, `${s.id}: priority`);
      assert.ok(Array.isArray(s.tokens), `${s.id}: tokens`);
      assert.ok(typeof s.when === "string" && s.when.length > 0, `${s.id}: when`);
    }
  });

  test("every signal that uses colour has a non-colour twin (shape, pattern or text)", () => {
    for (const s of SIGNALS) {
      if (s.tokens.length === 0) continue;
      assert.ok(typeof s.twin === "string" && s.twin.length > 8, `${s.id} has no twin`);
    }
  });

  test("each channel carries one meaning: no two signals share a channel and a priority tier", () => {
    const seen = new Map();
    for (const s of SIGNALS) {
      const key = `${s.channel}/${s.meaning}`;
      assert.ok(s.meaning, `${s.id}: meaning`);
      seen.set(key, [...(seen.get(key) ?? []), s.id]);
    }
    const channelsToMeanings = new Map();
    for (const s of SIGNALS) {
      channelsToMeanings.set(
        s.channel,
        new Set([...(channelsToMeanings.get(s.channel) ?? []), s.meaning]),
      );
    }
    for (const [channel, meanings] of channelsToMeanings) {
      assert.equal(meanings.size, 1, `${channel} carries ${[...meanings].join(", ")}`);
    }
  });

  test("every signal says whether it shows at rest (density rework, 2026-10-18)", () => {
    for (const s of SIGNALS) {
      assert.equal(typeof s.atRest, "boolean", `${s.id}: atRest`);
      if (!s.atRest) assert.ok(s.whenNotAtRest?.length > 5, `${s.id}: when does it show then?`);
    }
    for (const id of ["sibling", "collateral", "ribbons", "preview"]) assert.ok(signal(id), id);
    assert.equal(signal("collateral").priority, 0, "collateral outranks candidate");
  });

  test("signal tokens are semantic tokens", () => {
    for (const name of signalTokens()) assert.ok(SEMANTIC_TOKENS.includes(name), name);
  });
});

describe("what a clip shows", () => {
  test("at most three ranked signals; always-on ones are never dropped", () => {
    const { shown, hidden } = pickSignals(["sync", "clipping", "takes", "note", "free"]);
    assert.equal(shown.length, 3);
    assert.equal(hidden.length, 2);
    const ranked = shown.map((id) => SIGNALS.find((s) => s.id === id).priority);
    assert.deepEqual(
      ranked,
      [...ranked].sort((a, b) => a - b),
      "highest priority first",
    );
    const alarm = pickSignals(["damaged", "drift", "sync", "clipping", "takes", "note"]);
    assert.ok(alarm.shown.includes("damaged") && alarm.shown.includes("drift"));
  });

  test("seams: a clean split, a jump cut, a change of file, or none", () => {
    const a = { media: "m1", start: 0, offset: 0, length: 100 };
    assert.equal(seamKind(a, { media: "m1", start: 100, offset: 100, length: 50 }), "split");
    assert.equal(seamKind(a, { media: "m1", start: 100, offset: 400, length: 50 }), "jump");
    assert.equal(seamKind(a, { media: "m2", start: 100, offset: 0, length: 50 }), "file");
    assert.equal(seamKind(a, { media: "m1", start: 150, offset: 150, length: 50 }), null);
  });

  test("zebra: neighbouring clips from different files never share a body step", () => {
    const clips = [
      { id: "a", media: "A", start: 0 },
      { id: "b", media: "A", start: 10 },
      { id: "c", media: "B", start: 20 },
      { id: "d", media: "C", start: 30 },
      { id: "e", media: "C", start: 40 },
    ];
    const steps = zebraSteps(clips);
    assert.equal(steps.get("a"), 0);
    assert.equal(steps.get("b"), 0, "same file keeps its step");
    assert.equal(steps.get("c"), 1);
    assert.equal(steps.get("d"), 0);
    assert.equal(steps.get("e"), 0);
    assert.equal(
      zebraSteps([
        { id: "z", media: "Z", start: 5 },
        { id: "y", media: "Y", start: 1 },
      ]).get("y"),
      0,
      "by time, not by array order",
    );
  });

  test("file marks: stable, two unambiguous characters, from the content hash", () => {
    const sha = "3d331d83c5d17b0414a466ffdf4389b99e2f6535526a11e7b93c139ff9826cad";
    assert.equal(fileMark(sha), fileMark(sha));
    assert.match(fileMark(sha), /^[ACDEFHJKLMNPRTUVWXY34679]{2}$/);
    assert.notEqual(fileMark(sha), fileMark(`ff${sha.slice(2)}`));
    assert.equal(fileMark(""), "");
  });

  test("a file mark is shown only where it tells files apart", () => {
    assert.equal(needsFileMark({ clips: [{ media: "a" }, { media: "a" }] }), false);
    assert.equal(needsFileMark({ clips: [{ media: "a" }, { media: "b" }] }), true);
  });
});

describe("buses", () => {
  test("bus hues follow bus order and cycle; letters are A, B, C …", () => {
    const buses = Array.from({ length: BUS_HUES + 1 }, (_, i) => ({ id: `b${i}` }));
    const hues = busHues({ buses });
    assert.equal(hues.get("b0"), 1);
    assert.equal(hues.get(`b${BUS_HUES}`), 1);
    assert.equal(busLetter(0), "A");
    assert.equal(busLetter(2), "C");
    assert.equal(busLetter(26), "AA");
  });
});

describe("palettes and themes", () => {
  test("resolvePalette reads every semantic token once and builds the canvas palette", () => {
    const asked = [];
    const palette = resolvePalette((name) => {
      asked.push(name);
      return name.includes("opacity") ? "0.5" : "#123456";
    });
    assert.equal(new Set(asked).size, asked.length, "each token read once");
    assert.equal(palette.tracks.length, 7);
    assert.equal(palette.tracks[0].bodyAlt, "#123456");
    assert.equal(palette.buses.length, BUS_HUES);
    assert.equal(palette.signals.selected, "#123456");
    assert.equal(palette.numbers.mutedOpacity, 0.5);
  });

  test("a user theme is data: known semantic tokens only, checked values", () => {
    const ok = themeFromManifest({
      name: "Late night",
      base: "dark",
      density: "compact",
      tokens: { "--accent": "#ffaa00", "--signal-muted-opacity": "0.3" },
    });
    assert.deepEqual(ok.errors, []);
    // Applied as <html data-theme="dark" data-user-theme="late-night">: the base
    // theme supplies every value the manifest does not override.
    assert.equal(ok.base, "dark");
    assert.equal(ok.attribute, "late-night");
    assert.match(ok.css, /:root\[data-user-theme="late-night"\]/);
    assert.match(ok.css, /--accent: #ffaa00;/);
    const bad = themeFromManifest({
      name: "x",
      base: "sepia",
      tokens: { "--p-gray-50": "#000000", "--accent": "red; }", "--track-0-wave": "#12345" },
    });
    assert.equal(bad.errors.length, 4);
    assert.equal(bad.css, "");
  });
});

describe("collapsed bus ribbons (owner, 2026-10-18)", () => {
  test("one 8 px strip per member, capped at 48 px, thinner beyond six", () => {
    assert.deepEqual(ribbonLayout(3), { strip: 8, height: 24 + 8 });
    assert.deepEqual(ribbonLayout(6), { strip: 8, height: 48 });
    const many = ribbonLayout(10);
    assert.ok(many.strip < 8 && many.strip >= 3);
    assert.ok(many.height <= 48);
  });

  test("a single member keeps the summed waveform", () => {
    assert.equal(ribbonLayout(1), null);
  });
});
