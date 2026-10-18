import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { monoDecision, monoEdits, monoTag } from "../mono-ask.js";

const stereo = [
  { id: "t1", name: "Olli" },
  { id: "t2", name: "Mari" },
];

describe("what to do about stereo speech after an import", () => {
  test("nothing stereo: nothing to ask or do, whatever the setting", () => {
    for (const choice of ["ask", "mono", "stereo"]) {
      assert.deepEqual(monoDecision(choice, []), { action: "none", tracks: [] });
      assert.deepEqual(monoDecision(choice, undefined), { action: "none", tracks: [] });
    }
  });

  test("ask: the tracks are named in the question", () => {
    assert.deepEqual(monoDecision("ask", stereo), { action: "ask", tracks: stereo });
  });

  test("always mono answers for the user, always stereo keeps them", () => {
    assert.equal(monoDecision("mono", stereo).action, "mono");
    assert.equal(monoDecision("stereo", stereo).action, "none");
  });

  test("a damaged setting asks", () => {
    assert.equal(monoDecision("sideways", stereo).action, "ask");
  });

  test("turning into mono is one set_track per track", () => {
    const edits = monoEdits(stereo);
    assert.equal(edits.length, 2);
    assert.equal(edits[0].op, "set_track");
    assert.deepEqual(edits[0].args, { track_id: "t1", mono: true });
    assert.equal(edits[0].labelKey, "ui.edit.label.mono");
  });
});

describe("the mono or stereo tag in the track header", () => {
  const project = {
    media: [
      { id: "m1", channels: 1 },
      { id: "m2", channels: 2 },
    ],
  };
  const track = (kind, media, mono) => ({ kind, mono, clips: media.map((m) => ({ media: m })) });

  test("a mono track says mono, a stereo source on a speech track says stereo", () => {
    assert.equal(monoTag(track("speech", ["m2"], true), project), "mono");
    assert.equal(monoTag(track("speech", ["m2"], false), project), "stereo");
    assert.equal(monoTag(track("speech", ["m2"], undefined), project), "stereo");
  });

  test("a mono source is mono whatever the flag says", () => {
    assert.equal(monoTag(track("speech", ["m1"], false), project), "mono");
  });

  test("music gets no tag, an empty track is mono", () => {
    assert.equal(monoTag(track("music", ["m2"], false), project), null);
    assert.equal(monoTag(track("speech", [], false), project), "mono");
  });
});
