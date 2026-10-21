// The structured automix toast (docs/design/TOAST.md): job + t -> what the toast draws.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { automixNotice } from "../automix-model.js";
import { automixToast, TRACK_STAGES } from "../automix-toast-model.js";

const t = (key, values = {}) =>
  Object.keys(values).length ? `${key}${JSON.stringify(values)}` : key;

const tracks = {
  phase: 3,
  phases: 4,
  phase_name: "tracks",
  track: { index: 1, total: 4, name: "Olli" },
  stage: { name: "plugin", n: 3, of: 9, state: "working", off: ["duck"] },
};
const running = (detail, extra = {}) => ({
  state: "running",
  progress: 0.49,
  message: "3/4 track 1/4 Olli: plugin (3/9) ...",
  eta: ["minutes", 12],
  detail,
  ...extra,
});

describe("automixToast: the tracks phase", () => {
  const view = automixToast(running(tracks), t);

  test("is the structured layout", () => {
    assert.equal(view.rich, true);
    assert.equal(view.title, "ui.automix.toast.title");
  });

  test("title row: percent and time left", () => {
    assert.equal(view.percent, 49);
    assert.equal(view.percentText, "49 %");
    assert.equal(view.eta, 'ui.eta.minutes{"n":12}');
  });

  test("phase line: name and step n of N", () => {
    assert.equal(view.phase, "ui.automix.toast.phase.tracks");
    assert.equal(view.step, 'ui.automix.toast.step{"n":3,"total":4}');
  });

  test("track line: track i of n, the name, the stage", () => {
    assert.equal(view.track, 'ui.automix.toast.track{"index":1,"total":4}');
    assert.equal(view.trackName, "Olli");
    assert.equal(view.stage, "ui.automix.toast.stage.plugin");
    assert.equal(view.stageCount, "3/9");
    assert.equal(view.note, "");
  });

  test("nine pips: done before, working now, pending after, off is skipped", () => {
    assert.equal(view.pips.length, 9);
    assert.deepEqual(
      view.pips.map((pip) => pip.state),
      ["done", "done", "working", "pending", "pending", "pending", "pending", "skipped", "pending"],
    );
    assert.equal(view.pips[2].label, "ui.automix.toast.stage.plugin");
  });

  test("a done stage reads done; a skipped one reads skipped", () => {
    const done = automixToast(
      running({ ...tracks, stage: { ...tracks.stage, name: "debleed", n: 2, state: "done" } }),
      t,
    );
    assert.equal(
      done.stage,
      'ui.automix.toast.stage_done{"stage":"ui.automix.toast.stage.debleed"}',
    );
    assert.equal(done.pips[1].state, "done");
    assert.equal(done.pips[2].state, "pending");
    const skipped = automixToast(
      running({ ...tracks, stage: { ...tracks.stage, name: "duck", n: 8, state: "skipped" } }),
      t,
    );
    assert.equal(
      skipped.stage,
      'ui.automix.toast.stage_skipped{"stage":"ui.automix.toast.stage.duck"}',
    );
    assert.equal(skipped.pips[7].state, "skipped");
  });

  test("aria: the bar's numbers and a phase-only announcement", () => {
    assert.equal(view.bar.now, 49);
    assert.equal(view.bar.fraction, 0.49);
    assert.equal(view.bar.valuetext, '49 %, ui.eta.minutes{"n":12}');
    assert.equal(
      view.announce,
      'ui.automix.toast.announce{"phase":"ui.automix.toast.phase.tracks","step":"ui.automix.toast.step{\\"n\\":3,\\"total\\":4}"}',
    );
    const nextStage = automixToast(
      running({ ...tracks, stage: { ...tracks.stage, name: "cleanup", n: 4 } }),
      t,
    );
    assert.equal(nextStage.announce, view.announce, "a stage change is not announced");
  });

  test("keeps the notice flags and the old text for the fallback", () => {
    const old = automixNotice(running(tracks), t);
    assert.equal(view.text, old.text);
    assert.equal(view.notice.cancel, true);
    assert.equal(view.notice.sticky, true);
  });
});

describe("automixToast: other phases", () => {
  test("stems: phase 1 of 4, the message without its step prefix as the note", () => {
    const view = automixToast(
      running(
        { phase: 1, phases: 4, phase_name: "stems", track: null, stage: null },
        { progress: 0.2, message: "1/4 Maija 2/2", eta: null },
      ),
      t,
    );
    assert.equal(view.phase, "ui.automix.toast.phase.stems");
    assert.equal(view.step, 'ui.automix.toast.step{"n":1,"total":4}');
    assert.equal(view.note, "Maija 2/2");
    assert.equal(view.track, "");
    assert.deepEqual(view.pips, []);
    assert.equal(view.percent, 20);
    assert.equal(view.eta, "");
  });

  test("analysis before any number: no percent, the bar is indeterminate", () => {
    const view = automixToast(
      running(
        { phase: 2, phases: 4, phase_name: "analysis", track: null, stage: null },
        { progress: 0.4, indeterminate: true, message: "2/4 loading 2 tracks" },
      ),
      t,
    );
    assert.equal(view.indeterminate, true);
    assert.equal(view.percent, null);
    assert.equal(view.percentText, "");
    assert.equal(view.bar.now, null);
    assert.equal(view.eta, "");
    assert.equal(view.note, "loading 2 tracks");
  });

  test("mastering: phase 4 of 4, no track line", () => {
    const view = automixToast(
      running(
        { phase: 4, phases: 4, phase_name: "mastering", track: null, stage: null },
        { progress: 0.93, message: "4/4 Engine: master" },
      ),
      t,
    );
    assert.equal(view.phase, "ui.automix.toast.phase.mastering");
    assert.equal(view.step, 'ui.automix.toast.step{"n":4,"total":4}');
    assert.equal(view.note, "Engine: master");
    assert.deepEqual(view.pips, []);
  });

  test("remote: upload is step 2 of 6, download 6 of 6", () => {
    const up = automixToast(
      running(
        { phase: 2, phases: 6, phase_name: "upload", track: null, stage: null },
        { progress: 0.18, message: "2/6 Olli.wav" },
      ),
      t,
    );
    assert.equal(up.phase, "ui.automix.toast.phase.upload");
    assert.equal(up.step, 'ui.automix.toast.step{"n":2,"total":6}');
    assert.equal(up.note, "Olli.wav");
    const down = automixToast(
      running({ phase: 6, phases: 6, phase_name: "download", track: null, stage: null }),
      t,
    );
    assert.equal(down.phase, "ui.automix.toast.phase.download");
  });

  test("paused: the paused line replaces the time left", () => {
    const view = automixToast(
      running(tracks, { paused: true, message: "Paused while playing" }),
      t,
    );
    assert.equal(view.eta, "Paused while playing");
  });
});

describe("automixToast: percent", () => {
  const at = (progress) => automixToast(running(tracks, { progress }), t).percent;
  test("rounds and clamps", () => {
    assert.equal(at(0.494), 49);
    assert.equal(at(0.495), 50);
    assert.equal(at(-1), 0);
    assert.equal(at(Number.NaN), 0);
  });
  test("never says 100 % while it still runs", () => {
    assert.equal(at(0.999), 99);
    assert.equal(at(1), 99);
  });
});

describe("automixToast: fallback to the old single line", () => {
  test("no detail (older server, events off): the old text, not rich", () => {
    for (const detail of [undefined, null, {}, { phase: "x" }, { phase: 1, phases: 4 }]) {
      const job = running(detail);
      const view = automixToast(job, t);
      assert.equal(view.rich, false, JSON.stringify(detail));
      assert.equal(view.text, automixNotice(job, t).text);
    }
  });

  test("finished, failed and cancelled stay as they are", () => {
    for (const job of [
      { state: "completed", result: { path: "/x.wav", summary: [] }, detail: tracks },
      { state: "failed", error: { text: "boom" }, detail: tracks },
      { state: "cancelled", detail: tracks },
    ]) {
      const view = automixToast(job, t);
      assert.equal(view.rich, false, job.state);
      assert.deepEqual(view.notice, automixNotice(job, t));
    }
  });

  test("an unknown phase name or stage still draws without throwing", () => {
    const view = automixToast(
      running({ ...tracks, phase_name: "future", stage: { name: "warp", n: 12, of: 9 } }),
      t,
    );
    assert.equal(view.rich, true);
    assert.equal(view.phase, "");
    assert.equal(view.pips.length, 9);
    assert.ok(view.pips.every((pip) => pip.state === "done" || pip.state === "skipped"));
  });
});

test("TRACK_STAGES matches the server's order (automix.py)", () => {
  const source = readFileSync(
    fileURLToPath(new URL("../../src/kuulas/automix.py", import.meta.url)),
    "utf8",
  );
  const tuple = source.match(/TRACK_STAGES = \(([^)]*)\)/)[1];
  const names = [...tuple.matchAll(/"([a-z]+)"/g)].map((m) => m[1]);
  assert.deepEqual([...TRACK_STAGES], names);
});
