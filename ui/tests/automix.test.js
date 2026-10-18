// Mix with the automixer (WP68): the form model, the notice and the command.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  automixNotice,
  automixRequest,
  DEFAULT_AUTOMIX,
  formatWords,
  parseWords,
} from "../automix-model.js";
import { createRegistry } from "../commands.js";
import { registerExportCommands } from "../export-commands.js";

const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;

describe("automixRequest", () => {
  test("defaults send only the loudness", () => {
    assert.deepEqual(automixRequest(DEFAULT_AUTOMIX), { ok: true, body: { target_lufs: -16 } });
  });

  test("an ad spot brings its duration along", () => {
    const form = { targetLufs: "-14.5", adSpot: "1200", adDuration: "45" };
    assert.deepEqual(automixRequest(form), {
      ok: true,
      body: { target_lufs: -14.5, ad_spot: 1200, ad_duration: 45 },
    });
  });

  test("a duration without a spot is ignored", () => {
    const form = { targetLufs: "-16", adSpot: "", adDuration: "45" };
    assert.deepEqual(automixRequest(form).body, { target_lufs: -16 });
  });

  test("bad numbers name the field", () => {
    assert.deepEqual(automixRequest({ ...DEFAULT_AUTOMIX, targetLufs: "loud" }), {
      ok: false,
      field: "targetLufs",
      key: "ui.automix.bad_target_lufs",
    });
    assert.equal(automixRequest({ ...DEFAULT_AUTOMIX, targetLufs: "-90" }).ok, false);
    assert.equal(automixRequest({ ...DEFAULT_AUTOMIX, adSpot: "-3" }).field, "adSpot");
    assert.equal(
      automixRequest({ ...DEFAULT_AUTOMIX, adSpot: "10", adDuration: "0" }).field,
      "adDuration",
    );
  });
});

describe("command words", () => {
  test("split on spaces, quotes keep a word together", () => {
    assert.deepEqual(parseWords('uv run "my tool" --x'), ["uv", "run", "my tool", "--x"]);
    assert.deepEqual(parseWords("  "), []);
  });

  test("formatWords quotes what needs it, and parseWords undoes it", () => {
    const words = ["uv", "run", "my tool", "--speech-plugins", "dxRevive"];
    assert.equal(formatWords(words), 'uv run "my tool" --speech-plugins dxRevive');
    assert.deepEqual(parseWords(formatWords(words)), words);
  });
});

describe("automixNotice", () => {
  test("running with no line yet says so, with Cancel", () => {
    const n = automixNotice({ state: "running", message: "", indeterminate: true }, t);
    assert.equal(n.cancel, true);
    assert.equal(n.sticky, true);
    assert.match(n.text, /ui\.automix\.running/);
  });

  test("before the first PROGRESS line the last log line shows, with no percent", () => {
    const n = automixNotice({ state: "running", message: "Mixing Olli", indeterminate: true }, t);
    assert.match(n.text, /Mixing Olli/);
    assert.doesNotMatch(n.text, /%/);
  });

  test("the stems part shows a percent of the stems", () => {
    const n = automixNotice({ state: "running", message: "", progress: 0.2 }, t);
    assert.match(n.text, /ui\.automix\.preparing.*"percent":50/);
  });

  test("the mix part shows the real percent and the tool's message", () => {
    const n = automixNotice({ state: "running", message: "Engine: music", progress: 0.7 }, t);
    assert.match(n.text, /ui\.automix\.running_percent/);
    assert.match(n.text, /"percent":70/);
    assert.match(n.text, /Engine: music/);
  });

  test("done offers Show in Finder; failed shows the server text; cancelled says so", () => {
    const done = automixNotice({ state: "completed", result: { path: "/p/mix.wav" } }, t);
    assert.deepEqual([done.kind, done.reveal, done.sticky], ["ok", true, true]);
    assert.match(done.text, /\/p\/mix\.wav/);
    const failed = automixNotice({ state: "failed", error: { text: "boom" } }, t);
    assert.deepEqual([failed.kind, failed.text], ["error", "boom"]);
    assert.equal(automixNotice({ state: "cancelled" }, t).kind, "ok");
  });
});

describe("export.automix command", () => {
  const withTracks = { project: { tracks: [{ id: "a" }], markers: [] } };
  const setup = () => {
    const registry = createRegistry();
    const opened = [];
    registerExportCommands(registry, {
      t,
      app: { getState: () => withTracks, toast: () => {}, automix: () => opened.push(1) },
    });
    return { registry, opened };
  };

  test("needs tracks, has a hint, opens the dialog", () => {
    const { registry, opened } = setup();
    assert.equal(registry.status("export.automix"), "ready");
    assert.equal(registry.hintKey("export.automix"), "cmd.export.automix.hint");
    assert.equal(registry.can("export.automix", { project: { tracks: [] } }), false);
    assert.equal(registry.run("export.automix", null, withTracks), true);
    assert.deepEqual(opened, [1]);
  });
});
