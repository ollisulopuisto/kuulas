import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { chosenWords, registerTranscriptCommands } from "../transcript-commands.js";
import { extendTo, placeCursor, selectWord } from "../transcript-model.js";

const word = (w, s, e, track = "a") => ({ w, s, e, track, clip: "c", index: 0 });
const words = [word("a", 0, 50), word("b", 60, 120), word("c", 300, 350, "b")];
const project = {
  tracks: [
    { id: "a", name: "Anna.wav", speaker: "Anna" },
    { id: "b", name: "Ville.wav", speaker: "" },
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

function setup(state) {
  const calls = { edits: [], cuts: [], toasts: [], corrects: 0 };
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
      cutWords: async (indices) => {
        calls.cuts.push(indices);
        return true;
      },
      correct: () => {
        calls.corrects++;
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

  test("X sends cut_words with the indices, to every track", async () => {
    const state = stateWith(extendTo(placeCursor(1), 2));
    const { registry, calls } = setup(state);
    registry.run("transcript.cut_words", null, state);
    await Promise.resolve();
    assert.deepEqual(calls.cuts, [[1, 2]]);
    assert.equal(calls.edits.length, 0);
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
