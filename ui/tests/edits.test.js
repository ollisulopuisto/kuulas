import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createEditor } from "../edits.js";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
}

function harness() {
  let project = { gain: 0, pan: 0 };
  const sent = [];
  const waiting = [];
  const errors = [];
  const accepted = [];
  const editor = createEditor({
    send: (request) => {
      sent.push(request);
      const d = deferred();
      waiting.push(d);
      return d.promise;
    },
    getProject: () => project,
    setProject: (p) => {
      project = p;
    },
    acceptServer: (response) => {
      accepted.push(response);
      project = response.project;
    },
    onError: (e) => errors.push(e),
  });
  const reply = async (index, value) => {
    waiting[index].resolve({ project: value });
    await new Promise((r) => setImmediate(r));
  };
  return { editor, sent, errors, accepted, reply, project: () => project, waiting };
}

const change = (gain, key = "track-gain-t1") => ({
  op: "set_track",
  args: { track_id: "t1", gain_db: gain },
  coalesce: key,
  provisional: (p) => ({ ...p, gain }),
});

describe("provisional edits with coalesce keys", () => {
  test("the screen changes at once and the request carries the key", () => {
    const h = harness();
    h.editor.change(change(-6));
    assert.equal(h.project().gain, -6);
    assert.deepEqual(h.sent, [
      {
        op: "set_track",
        args: { track_id: "t1", gain_db: -6 },
        label: null,
        coalesce: "track-gain-t1",
      },
    ]);
  });

  test("a drag sends the first value and then only the latest one", async () => {
    const h = harness();
    h.editor.change(change(-1));
    for (const v of [-2, -3, -4, -5]) h.editor.change(change(v));
    assert.equal(h.sent.length, 1, "one request in flight at a time");
    assert.equal(h.project().gain, -5, "the display follows the pointer");
    await h.reply(0, { gain: -1 });
    assert.equal(h.sent.length, 2);
    assert.equal(h.sent[1].args.gain_db, -5, "-2..-4 were superseded");
    assert.equal(h.accepted.length, 0, "an answer that is already out of date is not shown");
    assert.equal(h.project().gain, -5, "the slider did not jump back");
    await h.reply(1, { gain: -5 });
    assert.equal(h.accepted.length, 1);
    assert.deepEqual(h.project(), { gain: -5 });
  });

  test("different keys are not merged and keep their order", async () => {
    const h = harness();
    h.editor.change(change(-1, "a"));
    h.editor.change(change(-2, "b"));
    h.editor.change(change(-3, "a"));
    await h.reply(0, { gain: -1 });
    assert.equal(h.sent[1].coalesce, "b");
    await h.reply(1, { gain: -2 });
    assert.equal(h.sent[2].coalesce, "a");
    assert.equal(h.sent[2].args.gain_db, -3);
  });

  test("an edit without a key is never merged", async () => {
    const h = harness();
    h.editor.change({ ...change(1, null), coalesce: null });
    h.editor.change({ ...change(2, null), coalesce: null });
    h.editor.change({ ...change(3, null), coalesce: null });
    await h.reply(0, {});
    await h.reply(1, {});
    assert.deepEqual(
      h.sent.map((r) => r.args.gain_db),
      [1, 2, 3],
    );
  });

  test("a failed edit is reported and the queue is dropped", async () => {
    const h = harness();
    h.editor.change(change(-6));
    h.waiting[0].reject(new Error("no such track"));
    await new Promise((r) => setImmediate(r));
    assert.equal(h.errors.length, 1);
    assert.equal(h.errors[0].message, "no such track");
    assert.equal(h.sent.length, 1);
    assert.equal(h.accepted.length, 0);
  });

  test("idle again after the queue drains: the next edit goes out at once", async () => {
    const h = harness();
    h.editor.change(change(-1));
    await h.reply(0, { gain: -1 });
    h.editor.change(change(-2));
    assert.equal(h.sent.length, 2);
  });
});

describe("relative edits and completion", () => {
  const nudge = (db) => ({
    op: "adjust_clip_gain",
    args: { clip_ids: ["c1"], delta_db: db },
    coalesce: "gain:1",
    combine: (older, newer) => ({ ...newer, delta_db: older.delta_db + newer.delta_db }),
  });

  test("queued edits with the same key add up when they carry a combine function", async () => {
    const h = harness();
    h.editor.change(nudge(0.5));
    h.editor.change(nudge(0.5));
    h.editor.change(nudge(0.5));
    h.editor.change(nudge(0.5));
    await h.reply(0, {});
    assert.equal(h.sent.length, 2);
    assert.equal(h.sent[0].args.delta_db, 0.5);
    assert.equal(h.sent[1].args.delta_db, 1.5, "no key press is lost");
  });

  test("the combine function is not sent to the server", () => {
    const h = harness();
    h.editor.change(nudge(0.5));
    assert.deepEqual(Object.keys(h.sent[0]).sort(), ["args", "coalesce", "label", "op"]);
  });

  test("done gets the server's answer when that request succeeds", async () => {
    const h = harness();
    const seen = [];
    h.editor.change({ ...change(-1), done: (response) => seen.push(response) });
    await h.reply(0, { gain: -1 });
    assert.deepEqual(seen, [{ project: { gain: -1 } }]);
  });

  test("done is not called when the request fails", async () => {
    const h = harness();
    const seen = [];
    h.editor.change({ ...change(-1), done: (response) => seen.push(response) });
    h.waiting[0].reject(new Error("no"));
    await new Promise((r) => setImmediate(r));
    assert.deepEqual(seen, []);
  });
});
