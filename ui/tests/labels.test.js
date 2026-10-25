// Informative clip names and recording relations (owner, 2026-10-18).
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  clipLabel,
  DEFAULT_TEMPLATES,
  labelFacts,
  recordingParts,
  siblingsOf,
  truncateMiddle,
} from "../labels.js";

const rate = 48_000;
const project = {
  rate,
  media: [
    { id: "m1", name: "olli3.wav", person: "p-olli" },
    { id: "m2", name: "haastattelu_ville_12.wav", person: "" },
  ],
  people: [{ id: "p-olli", name: "Olli" }],
  tracks: [
    {
      id: "t1",
      clips: [
        { id: "a", media: "m1", start: 0, offset: 80 * rate, length: 120 * rate },
        { id: "b", media: "m1", start: 120 * rate, offset: 300 * rate, length: 10 * rate },
        { id: "c", media: "m2", start: 130 * rate, offset: 0, length: 5 * rate },
      ],
    },
    { id: "t2", clips: [{ id: "d", media: "m1", start: 0, offset: 0, length: 60 * rate }] },
  ],
};
// One character is 7 px in these tests.
const measure = (text) => text.length * 7;

describe("facts for a label", () => {
  test("person from the media, take from the file name, the source range", () => {
    const facts = labelFacts(project, project.tracks[0].clips[0], []);
    assert.equal(facts.person, "Olli");
    assert.equal(facts.take, "3");
    assert.equal(facts.in, "1:20");
    assert.equal(facts.out, "3:20");
    assert.equal(facts.file, "olli3");
  });

  test("no person: track name stands in when set, otherwise file name", () => {
    const facts = labelFacts(project, project.tracks[0].clips[2], []);
    assert.equal(facts.person, "haastattelu_ville_12");
    assert.equal(facts.take, "12");

    const trackProject = {
      ...project,
      tracks: [
        {
          id: "t-named",
          name: "Ville",
          clips: [{ id: "c-named", media: "m2", start: 0, offset: 0, length: 5 * rate }],
        },
      ],
    };
    const namedFacts = labelFacts(trackProject, trackProject.tracks[0].clips[0], []);
    assert.equal(namedFacts.person, "Ville");
    assert.equal(namedFacts.take, "12");
  });

  test("auto take names (Take 1, Otto 2) do not override manual name, populate take", () => {
    const takeClip = {
      id: "c-take",
      media: "m1",
      start: 0,
      offset: 0,
      length: 5 * rate,
      name: "Take 1",
    };
    const p = {
      ...project,
      tracks: [{ id: "t1", name: "Olli", clips: [takeClip] }],
    };
    const words = [{ start: 1 * rate, end: 2 * rate, text: "Terve" }];
    const facts = labelFacts(p, takeClip, words);
    assert.equal(facts.name, "");
    assert.equal(facts.take, "1");
    assert.equal(facts.person, "Olli");
    assert.equal(clipLabel(facts, 600, { measure }), "Olli 1 · 0:00–0:05 · “Terve”");
  });

  test("interrupted take name is also recognized as auto take name", () => {
    const takeClip = {
      id: "c-take-int",
      media: "m1",
      start: 0,
      offset: 0,
      length: 5 * rate,
      name: "Take 2 (interrupted)",
    };
    const p = {
      ...project,
      tracks: [{ id: "t1", name: "Olli", clips: [takeClip] }],
    };
    const facts = labelFacts(p, takeClip, []);
    assert.equal(facts.name, "");
    assert.equal(facts.take, "2");
  });

  test("the first words under the clip, from the timeline words", () => {
    const words = [
      { start: 1 * rate, end: 2 * rate, text: "Mitä" },
      { start: 2 * rate, end: 3 * rate, text: "sä" },
      { start: 200 * rate, end: 201 * rate, text: "outside" },
    ];
    assert.equal(labelFacts(project, project.tracks[0].clips[0], words).words, "Mitä sä");
  });
});

describe("the label for the width there is", () => {
  const facts = labelFacts(project, project.tracks[0].clips[0], [
    { start: 1 * rate, end: 2 * rate, text: "Mitä" },
    { start: 2 * rate, end: 3 * rate, text: "ajattelit" },
  ]);

  test("very narrow: nothing; narrow: the person; medium: person and take", () => {
    assert.equal(clipLabel(facts, 30, { measure }), "");
    assert.equal(clipLabel(facts, 60, { measure }), "Olli");
    assert.equal(clipLabel(facts, 120, { measure }), "Olli 3");
  });

  test("wide: plus the source range; very wide: plus the first words", () => {
    assert.equal(clipLabel(facts, 200, { measure }), "Olli 3 · 1:20–3:20");
    assert.equal(clipLabel(facts, 600, { measure }), "Olli 3 · 1:20–3:20 · “Mitä ajattelit”");
  });

  test("a manual name wins at every width that fits it", () => {
    assert.equal(clipLabel({ ...facts, name: "Intro" }, 120, { measure }), "Intro");
  });

  test("templates are the user's to change; unknown tokens stay empty", () => {
    const templates = { ...DEFAULT_TEMPLATES, m: "{file} {nope}" };
    assert.equal(clipLabel(facts, 120, { measure, templates }), "olli3");
  });

  test("a label that does not fit steps down a tier, never overflows", () => {
    const long = { ...facts, person: "Ville-Veikko Pöyhönen-Laaksonen" };
    const label = clipLabel(long, 120, { measure });
    assert.ok(measure(label) <= 120 - 8, label);
  });
});

describe("truncating file names", () => {
  test("in the middle, keeping the number at the end whole", () => {
    assert.equal(truncateMiddle("haastattelu_ville_12", 12), "haast…lle_12");
    assert.equal(truncateMiddle("short", 12), "short");
    assert.ok(truncateMiddle("haastattelu_ville_12", 12).endsWith("12"));
  });
});

describe("clips of one recording", () => {
  test("parts are numbered by their position in the source", () => {
    const parts = recordingParts(project, "m1");
    assert.deepEqual(parts.get("d"), { n: 1, of: 3 });
    assert.deepEqual(parts.get("a"), { n: 2, of: 3 });
    assert.deepEqual(parts.get("b"), { n: 3, of: 3 });
  });

  test("siblings: the other clips of the same recording, on any track", () => {
    assert.deepEqual([...siblingsOf(project, new Set(["a"]))].sort(), ["b", "d"]);
    assert.equal(siblingsOf(project, new Set()).size, 0);
  });
});
