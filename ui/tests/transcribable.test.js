// The "music is not transcribed" rule: skipped only when every clip is on a music track.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { isTranscribable, musicNote, musicOnlyIds, withoutMusic } from "../transcribable.js";

const track = (id, kind, media) => ({
  id,
  kind,
  clips: media.map((m) => ({ id: `${id}${m}`, media: m })),
});

describe("transcribable", () => {
  test("a recording only on music tracks is skipped", () => {
    const project = { tracks: [track("S", "speech", ["a"]), track("M", "music", ["b"])] };
    assert.deepEqual([...musicOnlyIds(project)], ["b"]);
    assert.equal(isTranscribable(project, "a"), true);
    assert.equal(isTranscribable(project, "b"), false);
  });

  test("a recording on a speech and a music track is still transcribed", () => {
    const project = { tracks: [track("S", "speech", ["a"]), track("M", "music", ["a"])] };
    assert.equal(isTranscribable(project, "a"), true);
  });

  test("a recording used nowhere is transcribed", () => {
    const project = { tracks: [track("M", "music", ["a"])] };
    assert.equal(isTranscribable(project, "unused"), true);
  });

  test("withoutMusic filters ids and survives no project", () => {
    const project = { tracks: [track("M", "music", ["b"])] };
    assert.deepEqual(withoutMusic(project, ["a", "b"]), ["a"]);
    assert.deepEqual(withoutMusic(null, ["a"]), ["a"]);
  });

  test("the panel note shows for a selected music-only clip without words", () => {
    const project = {
      media: [{ id: "b", name: "Airhorn.wav" }],
      tracks: [track("M", "music", ["b"])],
    };
    const selection = new Set(["Mb"]);
    assert.deepEqual(musicNote({ project, selection, transcribed: [] }), {
      id: "b",
      name: "Airhorn.wav",
    });
    assert.equal(musicNote({ project, selection, transcribed: ["b"] }), null);
    assert.equal(musicNote({ project, selection: new Set(), transcribed: [] }), null);
  });
});
