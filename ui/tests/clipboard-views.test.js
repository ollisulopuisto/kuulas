import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  agoText,
  CLIPBOARD_VIEWS,
  clipboardView,
  entryMeta,
  filterEntries,
  foreignState,
  projectLabel,
} from "../clipboard.js";

const S = 48000;
const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;
const entry = (extra = {}) => ({
  id: "e1",
  name: "",
  length: 12 * S,
  clips: 2,
  slots: 2,
  missing_here: 0,
  created_utc: 1000,
  ...extra,
});

describe("the three views", () => {
  test("this project, shared, other projects; this project unless told otherwise", () => {
    assert.deepEqual(CLIPBOARD_VIEWS, ["project", "shared", "others"]);
    assert.equal(clipboardView({}), "project");
    assert.equal(clipboardView(undefined), "project");
    assert.equal(clipboardView({ clipboardView: "shared" }), "shared");
    assert.equal(clipboardView({ clipboardView: "others" }), "others");
    assert.equal(clipboardView({ clipboardView: "nonsense" }), "project");
  });
});

describe("how long ago", () => {
  const ago = (seconds) => agoText(1000, 1000 + seconds, t);
  test("now, minutes, hours, days", () => {
    assert.equal(ago(10), "ui.clipboard.ago_now{}");
    assert.equal(ago(5 * 60), 'ui.clipboard.ago_minutes{"count":5}');
    assert.equal(ago(3 * 3600 + 120), 'ui.clipboard.ago_hours{"count":3}');
    assert.equal(ago(2 * 86400 + 5), 'ui.clipboard.ago_days{"count":2}');
  });
  test("a time that is not known, or in the future, says nothing or now", () => {
    assert.equal(agoText(0, 5000, t), "");
    assert.equal(agoText(undefined, 5000, t), "");
    assert.equal(agoText(9000, 1000, t), "ui.clipboard.ago_now{}");
  });
});

describe("the metadata line", () => {
  test("source project, tracks, length and time ago, in that order", () => {
    const line = entryMeta(
      entry({ source_name: "Episode 4", tracks: ["Olli", "Anna"], created_utc: 1000 }),
      S,
      1000 + 300,
      t,
    );
    assert.equal(line, 'Episode 4 · Olli, Anna · 0:12 · ui.clipboard.ago_minutes{"count":5}');
  });
  test("leaves out what an old entry does not have", () => {
    assert.equal(entryMeta(entry({ created_utc: 0 }), S, 5000, t), "0:12");
  });
});

describe("the filter also searches what was said", () => {
  const list = [
    entry({ id: "1", name: "Intro", text: "Welcome to the show\nHello" }),
    entry({ id: "2", name: "Outro", text: "Thanks for listening" }),
    entry({ id: "3", name: "Jingle" }),
  ];
  const ids = (found) => found.map((item) => item.id);
  test("a word of the transcript text finds the entry, any case", () => {
    assert.deepEqual(ids(filterEntries(list, "WELCOME", S, t)), ["1"]);
    assert.deepEqual(ids(filterEntries(list, "listening thanks", S, t)), ["2"]);
    assert.deepEqual(ids(filterEntries(list, "intro welcome", S, t)), ["1"]);
    assert.deepEqual(ids(filterEntries(list, "welcome thanks", S, t)), []);
  });
  test("the project's name and track names still count", () => {
    const found = filterEntries(
      [entry({ id: "9", source_name: "Pilot", tracks: ["Anna"] })],
      "pilot anna",
      S,
      t,
    );
    assert.deepEqual(ids(found), ["9"]);
  });
});

describe("foreign entries and the other projects list", () => {
  test("a project's state is unknown until it is asked for", () => {
    assert.deepEqual(foreignState({}, "/a/One.kuulas"), { status: "idle", entries: [] });
    const state = {
      clipboardForeign: { "/a/One.kuulas": { status: "ok", entries: [entry()] } },
    };
    assert.equal(foreignState(state, "/a/One.kuulas").status, "ok");
  });
  test("a project is labelled with its name and how many entries it has", () => {
    assert.equal(
      projectLabel({ name: "One", entries: 3 }, t),
      'One · ui.clipboard.project_entries{"count":3}',
    );
  });
});
