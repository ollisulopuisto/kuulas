// The silent-state visual language (docs/design/SILENCE-VISUALS.md): which columns lose their
// fill, the outline geometry, where the lock icons go, the draw order, and the inactive style.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  columnRuns,
  DEFAULT_INACTIVE_STYLE,
  desaturateColour,
  desaturatePalette,
  envelopeOutline,
  INACTIVE_STYLES,
  inactiveLook,
  inactiveStyleChoice,
  lockSpots,
  openLockSpot,
  SILENCE_LEGEND,
  SILENCE_LEGEND_TITLE,
  SILENT_OVERLAY_LAYERS,
  silentColumns,
  TRACK_LAYERS,
} from "../silence-visuals.js";

describe("silentColumns: which drawn columns are silent (outline, no fill)", () => {
  test("a plain clip sounds everywhere", () => {
    assert.deepEqual([...silentColumns(5, 10, {})], [0, 0, 0, 0, 0]);
  });

  test("a muted clip is silent everywhere", () => {
    assert.deepEqual([...silentColumns(4, 10, { muted: true })], [1, 1, 1, 1]);
  });

  test("a clip half inside a gate: silent only under the gate's pixel run", () => {
    // Columns 10..15 drawn; the gate covers pixels 12..14 and 30..40 (off this clip).
    assert.deepEqual([...silentColumns(6, 10, { gate: [12, 14, 30, 40] })], [0, 0, 1, 1, 0, 0]);
  });

  test("a run reaching past either end is clipped to the drawn columns", () => {
    assert.deepEqual([...silentColumns(4, 10, { gate: [0, 11, 13, 99] })], [1, 0, 0, 1]);
  });

  test("a clip that keeps the mic open (ungated) ignores the gate, but not its own mute", () => {
    assert.deepEqual([...silentColumns(3, 0, { gate: [0, 3], ungated: true })], [0, 0, 0]);
    assert.deepEqual([...silentColumns(2, 0, { muted: true, ungated: true })], [1, 1]);
  });
});

describe("columnRuns", () => {
  test("[start, end) pairs of the marked columns", () => {
    assert.deepEqual(columnRuns(Uint8Array.from([0, 1, 1, 0, 1])), [1, 3, 4, 5]);
    assert.deepEqual(columnRuns(Uint8Array.from([0, 0])), []);
    assert.deepEqual(columnRuns(Uint8Array.from([1, 1])), [0, 2]);
  });
});

describe("envelopeOutline: the min/max envelope as one closed polygon per run", () => {
  // bars: [top, bottom] per column, in px inside a body of height 20.
  const bars = Float32Array.from([5, 15, 2, 18, 8, 12, 10, 10]);

  test("top edge left to right, then the bottom edge back, column centres plus the run ends", () => {
    const points = envelopeOutline(bars, 1, 3, 20);
    assert.deepEqual([...points], [1, 2, 1.5, 2, 2.5, 8, 3, 8, 3, 12, 2.5, 12, 1.5, 18, 1, 18]);
  });

  test("the stroke stays inside the body: y clamped to half a pixel from each side", () => {
    const flat = Float32Array.from([0, 20]);
    assert.deepEqual(
      [...envelopeOutline(flat, 0, 1, 20)],
      [0, 0.5, 0.5, 0.5, 1, 0.5, 1, 19.5, 0.5, 19.5, 0, 19.5],
    );
  });

  test("a silent column with no peak still draws (a flat line at the floor)", () => {
    const silent = Float32Array.from([20, 20, 20, 20]);
    const points = envelopeOutline(silent, 0, 2, 20);
    assert.ok(points.length > 0);
    for (let i = 1; i < points.length; i += 2) assert.equal(points[i], 19.5);
  });
});

describe("lockSpots: one lock per visible closed stretch", () => {
  const opts = { iconPx: 12, pad: 3, blocked: [] };

  test("at the left edge of the visible part of each run", () => {
    assert.deepEqual(lockSpots([0, 100, 200, 260], opts), [3, 203]);
  });

  test("skipped when the run is narrower than the icon plus padding", () => {
    assert.deepEqual(lockSpots([10, 27, 50, 68], opts), [53]);
  });

  test("never over a clip border or handle: moved past a blocked span, or skipped", () => {
    // A clip edge zone at 98..110 inside the run 95..200: the lock goes after it.
    assert.deepEqual(lockSpots([95, 200], { ...opts, blocked: [[98, 110]] }), [111]);
    // Two blocked spans in a row.
    assert.deepEqual(
      lockSpots([95, 200], {
        ...opts,
        blocked: [
          [98, 110],
          [112, 130],
        ],
      }),
      [131],
    );
    // No room left after the blocked span: no lock (the outline still says silent).
    assert.deepEqual(lockSpots([95, 125], { ...opts, blocked: [[98, 112]] }), []);
  });

  test("a blocked span before or after the icon does not move it", () => {
    assert.deepEqual(
      lockSpots([100, 200], {
        ...opts,
        blocked: [
          [0, 50],
          [150, 160],
        ],
      }),
      [103],
    );
  });
});

describe("openLockSpot: the open padlock of a clip that keeps the mic open", () => {
  test("right after the name, when the clip has room", () => {
    assert.equal(openLockSpot({ after: 80, limit: 200, iconPx: 12, gap: 4 }), 84);
  });
  test("no room before the clip's right edge zone: not drawn", () => {
    assert.equal(openLockSpot({ after: 80, limit: 95, iconPx: 12, gap: 4 }), null);
  });
});

describe("draw order: clip chrome is drawn above every silent-state overlay", () => {
  test("the preview and the locks come before the clip borders, handles and selection", () => {
    const at = (name) => TRACK_LAYERS.indexOf(name);
    assert.ok(at("clips") > 0, "clips is a layer");
    for (const layer of SILENT_OVERLAY_LAYERS) {
      assert.ok(at(layer) >= 0, `${layer} is a layer`);
      assert.ok(at(layer) < at("clips"), `${layer} is drawn under the clips`);
    }
  });

  test("timeline.js paints a track by walking TRACK_LAYERS (not its own order)", () => {
    const source = readFileSync(fileURLToPath(new URL("../timeline.js", import.meta.url)), "utf8");
    assert.ok(/for \(const layer of TRACK_LAYERS\)/.test(source), "drawTrack walks TRACK_LAYERS");
    // The hatch of silence is gone: neither a muted clip nor a gate is hatched any more.
    assert.ok(!/drawGateHatch|drawSilenceHatch|theme\.hatch/.test(source), "no silence hatch");
  });
});

describe("inactive style: dim, desaturate or both", () => {
  test("three variants, a default, and an unknown stored value falls back to it", () => {
    assert.deepEqual(INACTIVE_STYLES, ["both", "desaturate", "dim"]);
    assert.equal(DEFAULT_INACTIVE_STYLE, "both");
    assert.equal(inactiveStyleChoice("dim"), "dim");
    assert.equal(inactiveStyleChoice("nonsense"), "both");
    assert.equal(inactiveStyleChoice(null), "both");
  });

  test("dim veils, desaturate does not, both veils lightly", () => {
    assert.deepEqual(inactiveLook("dim"), { veil: 0.72, desaturate: false });
    assert.deepEqual(inactiveLook("desaturate"), { veil: 0, desaturate: true });
    const both = inactiveLook("both");
    assert.equal(both.desaturate, true);
    assert.ok(both.veil > 0 && both.veil < inactiveLook("dim").veil / 2);
  });

  test("a desaturated colour is grey and keeps its luminance (so every contrast ratio holds)", () => {
    const lum = (hex) => {
      const lin = (v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
      const [r, g, b] = [1, 3, 5].map((i) => lin(Number.parseInt(hex.slice(i, i + 2), 16) / 255));
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    for (const hex of ["#1157a4", "#946000", "#ad456b", "#eef6ea", "#000000", "#ffffff"]) {
      const grey = desaturateColour(hex);
      assert.match(grey, /^#([0-9a-f]{2})\1\1$/, `${hex} -> ${grey}`);
      // One 8-bit step of rounding: the contrast against anything moves by under 1.5 %.
      const drift = (lum(grey) + 0.05) / (lum(hex) + 0.05);
      assert.ok(Math.abs(drift - 1) < 0.015, `${hex} -> ${grey}`);
    }
  });

  test("rgb() with alpha keeps the alpha; anything unparsable is left as it is", () => {
    assert.match(desaturateColour("rgb(255 0 0 / 0.5)"), /^rgb\((\d+) \1 \1 \/ 0\.5\)$/);
    assert.match(desaturateColour("rgba(0, 128, 0, 0.25)"), /^rgb\((\d+) \1 \1 \/ 0\.25\)$/);
    assert.equal(desaturateColour("transparent"), "transparent");
    assert.equal(desaturateColour(""), "");
  });

  test("a palette is desaturated entry by entry, once (not per frame)", () => {
    const out = desaturatePalette([{ fill: "#eef6ea", wave: "#4e8626", ink: "#51852f" }]);
    assert.equal(out.length, 1);
    for (const value of Object.values(out[0])) assert.match(value, /^#([0-9a-f]{2})\1\1$/);
  });
});

describe("the legend (Auto-Silence panel)", () => {
  test("one line per state, each in both languages, the silent pair first", () => {
    const read = (lang) =>
      JSON.parse(
        readFileSync(
          fileURLToPath(new URL(`../../src/kuulas/locales/${lang}.json`, import.meta.url)),
          "utf8",
        ),
      );
    const [en, fi] = [read("en"), read("fi")];
    assert.deepEqual(
      SILENCE_LEGEND.map((line) => line.state),
      ["filled", "outline", "lock", "open", "preview", "inactive"],
    );
    for (const key of [SILENCE_LEGEND_TITLE, ...SILENCE_LEGEND.map((line) => line.key)]) {
      assert.ok(en[key], `en ${key}`);
      assert.ok(fi[key], `fi ${key}`);
    }
  });
});
