import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  clockText,
  createDebouncer,
  createLatest,
  createSeq,
  DEBOUNCE_MS,
  jobProgress,
  overlayFrom,
  panelControls,
  summaryLines,
} from "../silence-panel-model.js";

const t = (key, params = {}) => `${key} ${JSON.stringify(params)}`;

function fakeTimers() {
  const pending = new Map();
  let id = 0;
  return {
    setTimeout(fn, ms) {
      id += 1;
      pending.set(id, { fn, ms });
      return id;
    },
    clearTimeout(handle) {
      pending.delete(handle);
    },
    run() {
      const due = [...pending.values()];
      pending.clear();
      for (const { fn } of due) fn();
    },
    pending,
  };
}

describe("Auto-Silence panel: requests", () => {
  test("the debounce is about 80 ms", () => {
    assert.ok(DEBOUNCE_MS >= 50 && DEBOUNCE_MS <= 120);
  });

  test("a burst of changes asks once, with the last values", () => {
    const timers = fakeTimers();
    const calls = [];
    const debounced = createDebouncer((v) => calls.push(v), 80, timers);
    debounced.call(1);
    debounced.call(2);
    debounced.call(3);
    assert.equal(timers.pending.size, 1);
    assert.deepEqual([...timers.pending.values()][0].ms, 80);
    timers.run();
    assert.deepEqual(calls, [3]);
  });

  test("cancel drops the waiting call; flush runs it now", () => {
    const timers = fakeTimers();
    const calls = [];
    const debounced = createDebouncer((v) => calls.push(v), 80, timers);
    debounced.call("a");
    debounced.cancel();
    timers.run();
    assert.deepEqual(calls, []);
    debounced.call("b");
    debounced.flush();
    assert.deepEqual(calls, ["b"]);
    timers.run();
    assert.deepEqual(calls, ["b"]);
  });

  test("only the newest answer counts", () => {
    const latest = createLatest();
    const first = latest.begin();
    const second = latest.begin();
    assert.equal(latest.isLatest(first), false);
    assert.equal(latest.isLatest(second), true);
    latest.drop();
    assert.equal(latest.isLatest(second), false);
  });

  test("the sequence only rises, also past a reload (it starts from the clock)", () => {
    let now = 1000;
    const seq = createSeq(() => now);
    const a = seq.next();
    const b = seq.next();
    assert.ok(b > a);
    now = 5;
    assert.ok(seq.next() > b);
    const later = createSeq(() => 2000);
    assert.ok(later.next() >= 2000);
  });
});

describe("Auto-Silence panel: what it says", () => {
  test("clock text", () => {
    assert.equal(clockText(0), "0:00");
    assert.equal(clockText(754.4), "12:34");
    assert.equal(clockText(3723), "1:02:03");
    assert.equal(clockText(-3), "0:00");
  });

  test("one line per track: closed of total, percent, stretches; now only when gated", () => {
    const rows = [
      { track_id: "a", name: "Aame", close_s: 754, total_s: 2710, stretches: 41, now_s: 190 },
      { track_id: "b", name: "Bea", close_s: 0, total_s: 2710, stretches: 0, now_s: 0 },
    ];
    const lines = summaryLines(rows, t);
    assert.equal(lines.length, 2);
    assert.equal(lines[0].trackId, "a");
    assert.equal(
      lines[0].text,
      t("ui.silence.panel_row", {
        name: "Aame",
        closed: "12:34",
        total: "45:10",
        percent: 28,
        stretches: 41,
      }),
    );
    assert.equal(lines[0].now, t("ui.silence.panel_now", { now: "3:10" }));
    assert.equal(lines[1].now, "");
    assert.match(lines[1].text, /"percent":0/);
  });

  test("a zero-length project does not divide by zero", () => {
    const [line] = summaryLines(
      [{ track_id: "a", name: "A", close_s: 0, total_s: 0, stretches: 0, now_s: 0 }],
      t,
    );
    assert.match(line.text, /"percent":0/);
  });

  test("the overlay the timeline draws: ranges by track", () => {
    const got = overlayFrom([
      { track_id: "a", ranges: [[0, 10]] },
      { track_id: "b", ranges: [] },
    ]);
    assert.deepEqual(
      [...got.entries()],
      [
        ["a", [[0, 10]]],
        ["b", []],
      ],
    );
    assert.equal(overlayFrom(null).size, 0);
  });

  test("measuring progress from the job", () => {
    assert.deepEqual(jobProgress({ state: "running", progress: 0.5, message: "Aame (1 of 2)" }), {
      fraction: 0.5,
      message: "Aame (1 of 2)",
      done: false,
      failed: false,
      cancelled: false,
    });
    assert.equal(jobProgress({ state: "completed", progress: 1 }).done, true);
    assert.equal(jobProgress({ state: "failed" }).failed, true);
    assert.equal(jobProgress({ state: "cancelled" }).cancelled, true);
    assert.equal(jobProgress(undefined).failed, true);
  });
});

describe("Auto-Silence panel: what can be pressed", () => {
  test("while measuring only Cancel works and the progress shows", () => {
    const got = panelControls({ phase: "measuring", valid: true, playing: false });
    assert.deepEqual(got, {
      controls: false,
      listen: false,
      accept: false,
      reset: false,
      progress: true,
      listenKey: "ui.silence.listen",
    });
  });

  test("ready: everything; Accept needs valid values", () => {
    assert.equal(panelControls({ phase: "ready", valid: true, playing: false }).accept, true);
    const bad = panelControls({ phase: "ready", valid: false, playing: false });
    assert.equal(bad.accept, false);
    assert.equal(bad.controls, true);
    assert.equal(bad.listen, true);
  });

  test("while a new answer is coming the controls stay live, Accept waits", () => {
    const got = panelControls({ phase: "updating", valid: true, playing: true });
    assert.equal(got.controls, true);
    assert.equal(got.accept, false);
    assert.equal(got.listenKey, "ui.silence.listen_stop");
  });

  test("after an error the values can be changed and tried again", () => {
    const got = panelControls({ phase: "error", valid: true, playing: false });
    assert.equal(got.controls, true);
    assert.equal(got.accept, false);
    assert.equal(got.progress, false);
  });
});
