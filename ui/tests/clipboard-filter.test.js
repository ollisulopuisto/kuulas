import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { entryDetails, filterEntries } from "../clipboard.js";

const S = 48000;
const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;
const entry = (extra = {}) => ({
  id: "e1",
  name: "",
  pinned: false,
  length: 5 * S,
  clips: 2,
  slots: 2,
  missing_here: 0,
  ...extra,
});

describe("the filter box", () => {
  const list = [
    entry({ id: "1", name: "Intro jingle", tracks: ["Music"], source_name: "Episode 4" }),
    entry({ id: "2", name: "", tracks: ["Olli", "Anna"], source_name: "Episode 5" }),
    entry({ id: "3", name: "Outro", tracks: ["Music"], source_name: "Episode 5" }),
  ];
  const ids = (found) => found.map((item) => item.id);

  test("no query keeps everything", () => {
    assert.deepEqual(ids(filterEntries(list, "", S, t)), ["1", "2", "3"]);
    assert.deepEqual(ids(filterEntries(list, "   ", S, t)), ["1", "2", "3"]);
    assert.deepEqual(ids(filterEntries(undefined, "x", S, t)), []);
  });

  test("matches the name, a track name or the source project, ignoring case", () => {
    assert.deepEqual(ids(filterEntries(list, "JINGLE", S, t)), ["1"]);
    assert.deepEqual(ids(filterEntries(list, "anna", S, t)), ["2"]);
    assert.deepEqual(ids(filterEntries(list, "episode 4", S, t)), ["1"]);
  });

  test("every word must match somewhere", () => {
    assert.deepEqual(ids(filterEntries(list, "music episode 5", S, t)), ["3"]);
    assert.deepEqual(ids(filterEntries(list, "music olli", S, t)), []);
  });

  test("an unnamed entry is found by its automatic title", () => {
    assert.deepEqual(ids(filterEntries(list, "untitled", S, t)), ["2"]);
  });
});

describe("the details line", () => {
  test("source project, track names and length", () => {
    assert.equal(
      entryDetails(entry({ tracks: ["Olli", "Anna"], source_name: "Ep 5", length: 75 * S }), S, t),
      'ui.clipboard.details{"source":"Ep 5","tracks":"Olli, Anna","duration":"1:15"}',
    );
  });

  test("an entry from before the names were kept still has a line", () => {
    assert.equal(
      entryDetails(entry({ length: 5 * S }), S, t),
      'ui.clipboard.details_short{"duration":"0:05"}',
    );
  });
});
