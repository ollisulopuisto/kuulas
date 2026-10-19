// Mix with the automixer (WP68): the form model, the notice and the command.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  advancedBody,
  automixNotice,
  automixRequest,
  DEFAULT_AUTOMIX,
  fileNamePreview,
  formatTimestamp,
  formatWords,
  LUFS_PRESETS,
  migrateForm,
  parseTimestamp,
  parseWords,
  validateAutomix,
} from "../automix-model.js";
import { createRegistry } from "../commands.js";
import { registerExportCommands } from "../export-commands.js";

const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;

describe("automixRequest", () => {
  test("defaults send only the loudness", () => {
    assert.deepEqual(automixRequest(DEFAULT_AUTOMIX), { ok: true, body: { target_lufs: -16 } });
  });

  test("an ad spot brings its duration along", () => {
    const form = { targetLufs: "-14.5", adBreak: "1", adSpot: "1200", adDuration: "45" };
    assert.deepEqual(automixRequest(form), {
      ok: true,
      body: { target_lufs: -14.5, ad_spot: 1200, ad_duration: 45 },
    });
  });

  test("a duration without a spot is ignored", () => {
    const form = { targetLufs: "-16", adBreak: "", adSpot: "1200", adDuration: "45" };
    assert.deepEqual(automixRequest(form).body, { target_lufs: -16 });
  });

  test("bad numbers name the field", () => {
    assert.deepEqual(automixRequest({ ...DEFAULT_AUTOMIX, targetLufs: "loud" }), {
      ok: false,
      field: "targetLufs",
      key: "ui.automix.bad_target_lufs",
    });
    assert.equal(automixRequest({ ...DEFAULT_AUTOMIX, targetLufs: "-90" }).ok, false);
    assert.equal(
      automixRequest({ ...DEFAULT_AUTOMIX, adBreak: "1", adSpot: "-3" }).field,
      "adSpot",
    );
    assert.equal(
      automixRequest({ ...DEFAULT_AUTOMIX, adBreak: "1", adSpot: "10", adDuration: "0" }).field,
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

describe("presets", () => {
  test("podcast, louder, broadcast", () => {
    assert.deepEqual(
      LUFS_PRESETS.map((p) => p.lufs),
      ["-16", "-14", "-23"],
    );
    assert.equal(DEFAULT_AUTOMIX.targetLufs, LUFS_PRESETS[0].lufs);
  });
});

describe("timestamps", () => {
  test("seconds, m:ss and h:mm:ss", () => {
    assert.equal(parseTimestamp("1200"), 1200);
    assert.equal(parseTimestamp("20:00"), 1200);
    assert.equal(parseTimestamp("1:02:03"), 3723);
    assert.equal(parseTimestamp(" 0:07.5 "), 7.5);
    assert.equal(parseTimestamp("12,5"), 12.5);
  });

  test("anything else is null", () => {
    for (const bad of ["", "abc", "1:2:3:4", "-5", "1:-2", "1::2", "5:75"]) {
      assert.equal(parseTimestamp(bad), null, bad);
    }
  });

  test("formatTimestamp reads back", () => {
    assert.equal(formatTimestamp(1200), "20:00");
    assert.equal(formatTimestamp(3723), "1:02:03");
    assert.equal(formatTimestamp(7.5), "0:07.5");
  });
});

describe("validateAutomix", () => {
  test("a clean default form is valid and sends only the loudness", () => {
    const result = validateAutomix(DEFAULT_AUTOMIX);
    assert.equal(result.ok, true);
    assert.deepEqual(result.errors, {});
    assert.deepEqual(result.body, { target_lufs: -16 });
  });

  test("every bad field is reported at once, with its message key", () => {
    const result = validateAutomix({
      targetLufs: "x",
      adBreak: "1",
      adSpot: "",
      adDuration: "-1",
    });
    assert.equal(result.ok, false);
    assert.deepEqual(result.errors, {
      targetLufs: "ui.automix.bad_target_lufs",
      adSpot: "ui.automix.bad_ad_spot",
      adDuration: "ui.automix.bad_ad_duration",
    });
  });

  test("an ad break takes a timestamp; the body is in seconds", () => {
    const result = validateAutomix({
      targetLufs: "-14",
      adBreak: "1",
      adSpot: "20:00",
      adDuration: "",
    });
    assert.deepEqual(result.body, { target_lufs: -14, ad_spot: 1200 });
  });

  test("ad fields are not checked while the box is off", () => {
    const result = validateAutomix({ ...DEFAULT_AUTOMIX, adSpot: "junk", adDuration: "junk" });
    assert.equal(result.ok, true);
  });

  test("automixRequest agrees on the first error", () => {
    assert.equal(automixRequest({ ...DEFAULT_AUTOMIX, targetLufs: "" }).field, "targetLufs");
  });
});

describe("migrateForm", () => {
  test("an old remembered form with a spot turns the break on", () => {
    const form = migrateForm({ targetLufs: "-14", adSpot: "600", adDuration: "" });
    assert.equal(form.adBreak, "1");
    assert.equal(form.targetLufs, "-14");
  });

  test("missing keys fall back to the defaults", () => {
    assert.deepEqual(migrateForm({}), DEFAULT_AUTOMIX);
    assert.deepEqual(migrateForm(null), DEFAULT_AUTOMIX);
  });
});

describe("advancedBody", () => {
  test("empty fields are left out so the defaults apply", () => {
    assert.deepEqual(
      advancedBody({ command: "", cwd: " ", tempDir: "", outputDir: "", extra: "" }),
      {
        command: undefined,
        cwd: undefined,
        temp_dir: undefined,
        output_dir: undefined,
        extra_args: [],
      },
    );
  });

  test("words are split with quotes", () => {
    const body = advancedBody({
      command: 'uv run "my tool"',
      cwd: "/a",
      tempDir: "/t",
      outputDir: "/o",
      extra: "--x 1",
    });
    assert.deepEqual(body.command, ["uv", "run", "my tool"]);
    assert.deepEqual(body.extra_args, ["--x", "1"]);
    assert.equal(body.output_dir, "/o");
  });
});

describe("fileNamePreview", () => {
  test("edit name, automixer, local stamp, .wav", () => {
    const when = new Date(2026, 9, 19, 14, 30, 5);
    assert.equal(fileNamePreview("Episode 12", when), "Episode 12 automixer 2026-10-19 143005.wav");
  });
});
