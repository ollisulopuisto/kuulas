import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { chosenWords, registerTranscriptCommands } from "../transcript-commands.js";
import { extendTo, placeCursor, selectWord } from "../transcript-model.js";

const word = (w, s, e, track = "a") => ({ w, s, e, track, clip: "c", index: 0 });
const words = [word("a", 0, 50), word("b", 60, 120), word("c", 300, 350, "b")];
const project = {
  rate: 100,
  tracks: [
    { id: "a", name: "Anna.wav", speaker: "Anna", clips: [{ start: 0, length: 400 }] },
    { id: "b", name: "Ville.wav", speaker: "", clips: [{ start: 0, length: 400 }] },
  ],
};
const stateWith = (transcriptSelection, extra = {}) => ({
  project,
  words,
  head: 4,
  wordsHead: 4,
  transcriptSelection,
  ...extra,
});

function setup(state, { copyOk = true } = {}) {
  const calls = { edits: [], cuts: [], toasts: [], copies: [], order: [], corrects: 0, seeks: [] };
  const registry = createRegistry();
  registerTranscriptCommands(registry, {
    t: (key, values) => `${key} ${JSON.stringify(values ?? {})}`,
    app: {
      getState: () => state,
      edit: (change) => {
        calls.edits.push(change);
        change.done?.({});
      },
      toast: (text) => calls.toasts.push(text),
      copy: async (body) => {
        calls.order.push("copy");
        calls.copies.push(body);
        return copyOk;
      },
      cutWords: async (indices) => {
        calls.order.push("cut");
        calls.cuts.push(indices);
        return true;
      },
      seek: (frame) => calls.seeks.push(frame),
      correct: () => {
        calls.corrects++;
      },
      openFind: () => {
        calls.finds = (calls.finds ?? 0) + 1;
      },
    },
  });
  return { registry, calls };
}

describe("transcript commands", () => {
  test("they only apply to a selection of words the server has now", () => {
    const sel = extendTo(placeCursor(0), 1);
    const { registry } = setup(stateWith(sel));
    assert.equal(registry.can("transcript.delete_words", stateWith(sel)), true);
    assert.equal(registry.can("transcript.cut_words", stateWith(sel)), true);
    assert.equal(registry.can("transcript.delete_words", stateWith(placeCursor(0))), false);
    assert.equal(registry.can("transcript.cut_words", stateWith(placeCursor(0))), false);
    // The edit changed the words and the new ones are not here yet: refuse.
    assert.equal(registry.can("transcript.cut_words", stateWith(sel, { wordsHead: 3 })), false);
    assert.deepEqual(chosenWords(stateWith(sel, { wordsHead: 3 })), []);
  });

  test("Backspace sends one mute_range on the speaker's own track", () => {
    const state = stateWith(extendTo(placeCursor(0), 1));
    const { registry, calls } = setup(state);
    assert.equal(registry.run("transcript.delete_words", null, state), true);
    assert.equal(calls.edits.length, 1);
    assert.equal(calls.edits[0].op, "mute_range");
    assert.deepEqual(calls.edits[0].args.track_ids, ["a"]);
    assert.equal(calls.edits[0].args.group_editing, false);
    assert.equal(calls.cuts.length, 0);
    assert.match(calls.toasts[0], /"count":2,"name":"Anna"/);
  });

  test("Mod+X sends cut_words with the indices, to every track", async () => {
    const state = stateWith(extendTo(placeCursor(1), 2));
    const { registry, calls } = setup(state);
    registry.run("transcript.cut_words", null, state);
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(calls.cuts, [[1, 2]]);
    assert.equal(calls.edits.length, 0);
  });

  test("X deletes the words' stretch on every track and leaves the clipboard alone", async () => {
    const state = stateWith(extendTo(placeCursor(1), 2));
    const { registry, calls } = setup(state);
    registry.run("transcript.remove_words", null, state);
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(calls.cuts, [[1, 2]]);
    assert.deepEqual(calls.copies, []);
    assert.match(calls.toasts[0], /ui\.transcript\.toast\.remove/);
    assert.equal(registry.can("transcript.remove_words", stateWith(placeCursor(-1))), false);
  });

  test("after X or Mod+X the cursor goes to the splice, so P plays the join", async () => {
    for (const id of ["transcript.remove_words", "transcript.cut_words"]) {
      const state = stateWith(extendTo(placeCursor(1), 2));
      const { registry, calls } = setup(state);
      registry.run(id, null, state);
      await new Promise((resolve) => setTimeout(resolve, 0));
      // The middle of the pause before the first selected word: (50+60)/2 = 55.
      assert.deepEqual(calls.seeks, [55], id);
    }
  });

  test("Mod+X copies the stretch to the clipboard first, then cuts", async () => {
    const state = stateWith(extendTo(placeCursor(1), 2));
    const { registry, calls } = setup(state);
    registry.run("transcript.cut_words", null, state);
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(calls.order, ["copy", "cut"]);
    // The middle of the pauses: (50+60)/2 = 55 to 350 (the end of the programme).
    assert.equal(calls.copies[0].start, 55);
    assert.equal(calls.copies[0].end, 350);
    assert.deepEqual(calls.copies[0].track_ids, ["a", "b"]);
    assert.equal(calls.copies[0].group_editing, false);
    assert.match(calls.copies[0].name, /Anna/);
    assert.match(calls.toasts[0], /ui\.transcript\.toast\.cut /);
  });

  test("Mod+X: a failed copy still cuts, and the toast says it was not copied", async () => {
    const state = stateWith(extendTo(placeCursor(1), 2));
    const { registry, calls } = setup(state, { copyOk: false });
    registry.run("transcript.cut_words", null, state);
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(calls.cuts, [[1, 2]]);
    assert.match(calls.toasts[0], /cut_uncopied/);
  });

  test("Enter corrects one selected word, or the word under the cursor", () => {
    const { registry, calls } = setup(stateWith(selectWord(1)));
    assert.equal(registry.can("transcript.correct", stateWith(selectWord(1))), true);
    assert.equal(registry.can("transcript.correct", stateWith(placeCursor(2))), true);
    assert.equal(registry.can("transcript.correct", stateWith(extendTo(placeCursor(0), 2))), false);
    assert.equal(registry.can("transcript.correct", stateWith(placeCursor(-1))), false);
    registry.run("transcript.correct", null, stateWith(selectWord(1)));
    assert.equal(calls.corrects, 1);
  });
});

describe("transcript.find (Mod+F)", () => {
  test("opens the find bar when there are words, and is disabled without", () => {
    const { registry, calls } = setup(stateWith(placeCursor(0)));
    assert.equal(registry.status("transcript.find"), "ready");
    assert.equal(registry.can("transcript.find", stateWith(placeCursor(0))), true);
    assert.equal(registry.can("transcript.find", stateWith(placeCursor(0), { words: [] })), false);
    assert.equal(registry.run("transcript.find", null, stateWith(placeCursor(0))), true);
    assert.equal(calls.finds, 1);
  });
});
