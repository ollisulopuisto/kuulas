// Listening to the rendered mix: the Edit | Rendered mix switch, the banner, the automatic
// return to the edit, and the automix dialog's "Only the In/Out range" box.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { DEFAULT_AUTOMIX, migrateForm } from "../automix-model.js";
import {
  leftStaleRender,
  rangeChoice,
  renderBanner,
  renderSwitch,
  renderWhen,
  spanText,
  withRange,
} from "../render-listen-model.js";

const RATE = 48000;
const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;
const when = (iso) => `when(${iso})`;

const render = (over = {}) => ({
  available: true,
  current: true,
  missing: false,
  listening: false,
  name: "Episode automixer 2026-10-21 12-00-00.wav",
  range: null,
  set_at: "2026-10-21T12:00:00+03:00",
  reason: null,
  ...over,
});

describe("renderSwitch", () => {
  test("no render: no switch", () => {
    assert.equal(renderSwitch(null, t).visible, false);
    assert.equal(renderSwitch(render({ available: false }), t).visible, false);
  });

  test("a current render: both sides enabled, Edit pressed while not listening", () => {
    const s = renderSwitch(render(), t);
    assert.equal(s.visible, true);
    assert.equal(s.mixDisabled, false);
    assert.equal(s.editPressed, true);
    assert.equal(s.mixPressed, false);
    assert.match(s.mixTitle, /ui\.render\.mix_title/);
  });

  test("listening: Rendered mix pressed", () => {
    const s = renderSwitch(render({ listening: true }), t);
    assert.equal(s.mixPressed, true);
    assert.equal(s.editPressed, false);
  });

  test("stale: the mix side is disabled and says why", () => {
    const s = renderSwitch(render({ current: false, reason: "edited" }), t);
    assert.equal(s.visible, true);
    assert.equal(s.mixDisabled, true);
    assert.equal(s.mixTitle, t("ui.render.stale_title"));
  });

  test("missing or changed file: disabled with the file named", () => {
    for (const reason of ["missing", "changed"]) {
      const s = renderSwitch(render({ current: false, missing: reason === "missing", reason }), t);
      assert.equal(s.mixDisabled, true);
      assert.equal(s.mixTitle, t("ui.render.missing_title", { name: render().name }));
    }
  });
});

describe("renderBanner", () => {
  test("hidden while not listening", () => {
    assert.equal(renderBanner(render(), RATE, t, when).visible, false);
    assert.equal(renderBanner(null, RATE, t, when).visible, false);
  });

  test("a whole render: the name and when it was rendered, the level note as title", () => {
    const b = renderBanner(render({ listening: true }), RATE, t, when);
    assert.equal(b.visible, true);
    assert.equal(
      b.text,
      t("ui.render.banner", { name: render().name, when: when(render().set_at) }),
    );
    assert.equal(b.title, t("ui.render.banner_title"));
  });

  test("a range render also names the range and says the levels are the excerpt's", () => {
    const b = renderBanner(
      render({ listening: true, range: [RATE * 61, RATE * 125] }),
      RATE,
      t,
      when,
    );
    assert.match(b.text, /ui\.render\.banner_range/);
    assert.ok(b.text.includes(JSON.stringify({ span: "01:01-02:05" }).slice(1, -1)));
  });
});

describe("leftStaleRender", () => {
  test("listening, then an edit made it stale: true (the notice)", () => {
    const before = render({ listening: true });
    const after = render({ listening: false, current: false, reason: "edited" });
    assert.equal(leftStaleRender(before, after), true);
  });

  test("Back to the edit (still current) is no notice", () => {
    assert.equal(leftStaleRender(render({ listening: true }), render()), false);
  });

  test("not listening before: no notice", () => {
    assert.equal(leftStaleRender(render(), render({ current: false })), false);
    assert.equal(leftStaleRender(null, render({ current: false })), false);
  });

  test("an undo that removed the record ends listening with the notice too", () => {
    const after = { available: false, current: false, listening: false };
    assert.equal(leftStaleRender(render({ listening: true }), after), true);
  });
});

describe("rangeChoice", () => {
  const length = RATE * 60;

  test("both marks, longer than 1 s and shorter than the project: enabled", () => {
    assert.deepEqual(rangeChoice({ inPoint: RATE, outPoint: RATE * 3, length, rate: RATE }), {
      enabled: true,
      range: [RATE, RATE * 3],
    });
  });

  test("marks in either order are a range", () => {
    assert.deepEqual(rangeChoice({ inPoint: RATE * 3, outPoint: RATE, length, rate: RATE }).range, [
      RATE,
      RATE * 3,
    ]);
  });

  test("a missing mark, 1 s or less, or the whole project: disabled", () => {
    const off = { enabled: false, range: null };
    assert.deepEqual(rangeChoice({ inPoint: null, outPoint: RATE, length, rate: RATE }), off);
    assert.deepEqual(rangeChoice({ inPoint: RATE, outPoint: undefined, length, rate: RATE }), off);
    assert.deepEqual(rangeChoice({ inPoint: RATE, outPoint: RATE * 2, length, rate: RATE }), off);
    assert.deepEqual(rangeChoice({ inPoint: 0, outPoint: length, length, rate: RATE }), off);
    assert.deepEqual(rangeChoice({ inPoint: 0, outPoint: length + 9, length, rate: RATE }), off);
  });

  test("withRange adds the range only while the box is on and the range is allowed", () => {
    const body = { target_lufs: -16 };
    const choice = { enabled: true, range: [RATE, RATE * 3] };
    assert.deepEqual(withRange(body, "1", choice), { ...body, range: [RATE, RATE * 3] });
    assert.deepEqual(withRange(body, "", choice), body);
    assert.deepEqual(withRange(body, "1", { enabled: false, range: null }), body);
  });
});

describe("the remembered dialog form", () => {
  test("the range box is part of the form values, off by default and remembered", () => {
    assert.equal(DEFAULT_AUTOMIX.onlyRange, "");
    assert.equal(migrateForm({ onlyRange: "1" }).onlyRange, "1");
    assert.equal(migrateForm({ targetLufs: "-14" }).onlyRange, "");
  });
});

describe("renderWhen", () => {
  test("the Helsinki date, whatever the zone of the stored time", () => {
    // 23:30 UTC on 20.10. is 02:30 on 21.10. in Helsinki (UTC+3 in October).
    assert.equal(
      renderWhen("2026-10-20T23:30:00+00:00", "2:30 am Helsinki"),
      "21.10. 2:30 am Helsinki",
    );
  });
});

describe("spanText", () => {
  test("mm:ss-mm:ss of a range, minutes past an hour not wrapped", () => {
    assert.equal(spanText([RATE * 61, RATE * 125], RATE), "01:01-02:05");
    assert.equal(spanText([0, RATE * 3700], RATE), "00:00-61:40");
  });
});
