// The start page: removing entries from the recent list, and the highlight before a Cmd+digit
// opens a project. Pure logic (launcher-model.js); the DOM is in launcher_page.py.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  createOpener,
  missingPaths,
  PULSE_MS,
  PULSE_REDUCED_MS,
  removeEntry,
  restoreEntry,
  rowActions,
} from "../launcher-model.js";

const rows = [
  { path: "/p/A.kuulas", exists: true },
  { path: "/p/B.kuulas", exists: false },
  { path: "/p/C.kuulas", exists: true },
];

describe("removing entries", () => {
  test("removeEntry returns the shorter list, what went and where; the input is kept", () => {
    const out = removeEntry(rows, "/p/B.kuulas");
    assert.deepEqual(
      out.rows.map((r) => r.path),
      ["/p/A.kuulas", "/p/C.kuulas"],
    );
    assert.deepEqual(out.removed, rows[1]);
    assert.equal(out.index, 1);
    assert.equal(rows.length, 3);
  });

  test("removing an entry that is not there changes nothing", () => {
    const out = removeEntry(rows, "/p/Z.kuulas");
    assert.deepEqual(out.rows, rows);
    assert.equal(out.removed, null);
    assert.equal(out.index, -1);
  });

  test("restoreEntry puts it back at its place, once", () => {
    const { rows: shorter, removed, index } = removeEntry(rows, "/p/B.kuulas");
    assert.deepEqual(restoreEntry(shorter, removed, index), rows);
    assert.deepEqual(restoreEntry(rows, removed, index), rows);
    assert.deepEqual(restoreEntry(shorter, null, 0), shorter);
    assert.equal(restoreEntry(shorter, removed, 99).at(-1).path, "/p/B.kuulas");
  });

  test("missingPaths lists the entries whose folder is gone", () => {
    assert.deepEqual(missingPaths(rows), ["/p/B.kuulas"]);
    assert.deepEqual(missingPaths([{ path: "/x" }]), []);
  });

  test("a missing row offers Locate and Remove; a live row only Remove", () => {
    assert.deepEqual(rowActions({ missing: true }), ["locate", "remove"]);
    assert.deepEqual(rowActions({ missing: false }), ["remove"]);
  });
});

function harness({ reducedMotion = false } = {}) {
  const log = [];
  const timers = [];
  const opener = createOpener({
    reducedMotion,
    schedule: (fn, ms) => {
      timers.push({ fn, ms });
    },
    highlight: (index) => log.push(["highlight", index]),
    unhighlight: (index) => log.push(["unhighlight", index]),
    open: (model) => log.push(["open", model.path]),
    explain: (model) => log.push(["explain", model.path]),
  });
  return { opener, log, timers };
}
const live = { path: "/p/A.kuulas", missing: false };
const gone = { path: "/p/B.kuulas", missing: true };

describe("the key highlight before opening", () => {
  test("a key press highlights first and opens only after the pulse", () => {
    const { opener, log, timers } = harness();
    opener.request(live, 0, "key");
    assert.deepEqual(log, [["highlight", 0]]);
    assert.equal(timers.length, 1);
    assert.equal(timers[0].ms, PULSE_MS);
    assert.ok(PULSE_MS >= 150 && PULSE_MS <= 200);
    timers[0].fn();
    assert.deepEqual(log, [
      ["highlight", 0],
      ["unhighlight", 0],
      ["open", "/p/A.kuulas"],
    ]);
  });

  test("reduced motion: still highlighted, never longer than the animation", () => {
    const { opener, timers } = harness({ reducedMotion: true });
    opener.request(live, 2, "key");
    assert.equal(timers[0].ms, PULSE_REDUCED_MS);
    assert.ok(PULSE_REDUCED_MS <= PULSE_MS);
  });

  test("a click opens at once, with no delay", () => {
    const { opener, log, timers } = harness();
    opener.request(live, 0, "click");
    assert.deepEqual(log, [["open", "/p/A.kuulas"]]);
    assert.equal(timers.length, 0);
  });

  test("a second press while one is pending opens nothing twice", () => {
    const { opener, log, timers } = harness();
    opener.request(live, 0, "key");
    opener.request({ path: "/p/C.kuulas", missing: false }, 2, "key");
    assert.equal(timers.length, 1);
    timers[0].fn();
    assert.equal(log.filter(([what]) => what === "open").length, 1);
    assert.equal(log.at(-1)[1], "/p/A.kuulas");
  });

  test("a missing project explains instead of opening, with no pulse", () => {
    const { opener, log, timers } = harness();
    opener.request(gone, 1, "key");
    opener.request(gone, 1, "click");
    assert.deepEqual(log, [
      ["explain", "/p/B.kuulas"],
      ["explain", "/p/B.kuulas"],
    ]);
    assert.equal(timers.length, 0);
  });
});
