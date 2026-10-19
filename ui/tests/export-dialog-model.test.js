// The "(options)…" export dialog: which formats it lists and what it asks the export for.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { dialogFormats, exportDialogRequest, pickFormat } from "../export-dialog-model.js";

const ALL = [
  { id: "wav", label: "WAV" },
  { id: "flac", label: "FLAC" },
  { id: "mp3", label: "MP3" },
];

describe("dialogFormats", () => {
  test("lists the server's formats in its order", () => {
    assert.deepEqual(
      dialogFormats(ALL).map((f) => f.id),
      ["wav", "flac", "mp3"],
    );
  });
  test("before the server has answered, WAV and FLAC (no codec needed)", () => {
    assert.deepEqual(
      dialogFormats(null).map((f) => f.id),
      ["wav", "flac"],
    );
  });
});

describe("pickFormat", () => {
  test("the remembered format when it is offered, else the first", () => {
    assert.equal(pickFormat(ALL, "mp3"), "mp3");
    assert.equal(pickFormat(ALL, "ogg"), "wav");
    assert.equal(pickFormat(ALL, undefined), "wav");
    assert.equal(pickFormat([], "mp3"), "wav");
  });
});

describe("exportDialogRequest", () => {
  test("the mix and the tracks, with the format and whether to ask for the folder", () => {
    assert.deepEqual(exportDialogRequest("mix", { format: "flac", ask: true }), {
      what: "mix",
      format: "flac",
      ask: true,
    });
    assert.deepEqual(exportDialogRequest("tracks", { format: "wav", ask: false }), {
      what: "tracks",
      format: "wav",
      ask: false,
    });
  });
  test("an unknown kind is refused", () => {
    assert.throws(() => exportDialogRequest("stems", { format: "wav", ask: true }));
  });
});
