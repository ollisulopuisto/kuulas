// Transcribe on Colab (WP78): the consent rule, the settings form, the notice and the commands.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  CONSENT_KEY,
  colabForm,
  colabNotice,
  colabSettingsBody,
  consentNeeded,
  rememberConsent,
  rememberedConsent,
  resumableJob,
} from "../colab-model.js";
import { createPrefs } from "../prefs.js";

const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;

const memory = () => {
  const data = new Map();
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => void data.set(k, String(v)),
    removeItem: (k) => void data.delete(k),
  };
};

describe("consent to upload", () => {
  test("asked until the user agreed in this session or asked not to be asked again", () => {
    assert.equal(consentNeeded({ remembered: false, session: false }), true);
    assert.equal(consentNeeded({ remembered: false, session: true }), false);
    assert.equal(consentNeeded({ remembered: true, session: false }), false);
  });

  test("the remembered choice is a user preference that survives a new prefs object", () => {
    const storage = memory();
    assert.equal(rememberedConsent(createPrefs(storage)), false);
    assert.equal(rememberConsent(createPrefs(storage)), true);
    assert.equal(storage.getItem(`kuulas.${CONSENT_KEY}`), "always");
    assert.equal(rememberedConsent(createPrefs(storage)), true);
  });

  test("without storage nothing is remembered and nothing throws", () => {
    const prefs = createPrefs(null);
    assert.equal(rememberConsent(prefs), false);
    assert.equal(rememberedConsent(prefs), false);
  });
});

describe("settings form", () => {
  test("texts become the settings body; empty fields are left out", () => {
    const form = {
      command: 'uv run "my tool"',
      cwd: " /p ",
      extra: "--a --b",
      model: "small",
      language: "fi",
      noDrive: true,
      align: false,
    };
    assert.deepEqual(colabSettingsBody(form), {
      command: ["uv", "run", "my tool"],
      cwd: "/p",
      extra_args: ["--a", "--b"],
      no_drive: true,
      align: false,
      model: "small",
      language: "fi",
    });
    assert.deepEqual(
      colabSettingsBody({
        command: "",
        cwd: "",
        extra: "",
        model: "",
        language: "",
        noDrive: false,
      }),
      { extra_args: [], no_drive: false, align: true },
    );
  });

  test("the form shows the resolved settings", () => {
    const form = colabForm({
      command: ["uvx", "a b"],
      cwd: null,
      extra_args: ["--x"],
      no_drive: true,
      align: true,
      model: "turbo",
      language: null,
    });
    assert.deepEqual(form, {
      command: 'uvx "a b"',
      cwd: "",
      extra: "--x",
      model: "turbo",
      language: "",
      noDrive: true,
      align: true,
    });
  });
});

describe("colabNotice", () => {
  const names = "Olli.wav";

  test("running shows the tool's line, with a percent once it has one", () => {
    let n = colabNotice({ state: "running", indeterminate: true, message: "", progress: 0 }, t);
    assert.deepEqual([n.kind, n.sticky, n.cancel], ["ok", true, true]);
    assert.equal(n.text, "ui.colab.running{}");
    n = colabNotice({ state: "running", indeterminate: true, message: "[1/2] up", progress: 0 }, t);
    assert.equal(n.text, 'ui.colab.running_line{"line":"[1/2] up"}');
    n = colabNotice({ state: "running", indeterminate: false, message: "x", progress: 0.456 }, t);
    assert.equal(n.text, 'ui.colab.running_percent{"percent":46,"line":"x"}');
  });

  test("done, failed and cancelled", () => {
    const done = colabNotice({ state: "completed" }, t, names);
    assert.equal(done.text, 'ui.colab.done{"names":"Olli.wav"}');
    assert.deepEqual([done.kind, done.cancel], ["ok", false]);
    const failed = colabNotice({ state: "failed", error: { text: "Boom" } }, t, names);
    assert.deepEqual(
      [failed.kind, failed.text, failed.sticky, failed.cancel],
      ["error", "Boom", false, false],
    );
    const cancelled = colabNotice({ state: "cancelled" }, t, names);
    assert.equal(cancelled.text, "ui.colab.cancelled{}");
    assert.equal(cancelled.cancel, false);
  });
});

describe("background transcription (WP79)", () => {
  test("a local background job has its own words, an interrupted one says how to go on", () => {
    const local = { state: "running", backend: "local", indeterminate: true, message: "" };
    assert.equal(colabNotice(local, t).text, "ui.transcribe.running{}");
    assert.equal(
      colabNotice({ state: "completed", backend: "local" }, t, "A").text,
      'ui.transcribe.done{"names":"A"}',
    );
    const gone = colabNotice({ state: "interrupted", backend: "colab" }, t);
    assert.deepEqual(
      [gone.kind, gone.text, gone.cancel],
      ["error", "ui.colab.interrupted{}", false],
    );
  });

  test("a running background job is picked up again after the window is reopened", () => {
    const jobs = [
      { id: "a", kind: "export", state: "running" },
      { id: "b", kind: "transcribe", background: true, state: "completed" },
      { id: "c", kind: "transcribe", background: true, state: "running" },
    ];
    assert.equal(resumableJob(jobs)?.id, "c");
    assert.equal(resumableJob(jobs.slice(0, 2)), undefined);
  });
});

describe("commands and menus", () => {
  const read = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

  test("the Colab commands are in the keymap, the app commands and a menu", async () => {
    const { DEFAULT_KEYMAP } = await import("../keymap-default.js");
    const { MENU, menuTargets } = await import("../menu-model.js");
    const targets = new Set(menuTargets(MENU));
    for (const id of [
      "app.transcribe",
      "app.transcribe_colab",
      "app.colab_settings",
      "app.transcribe_restart",
    ]) {
      assert.ok(
        DEFAULT_KEYMAP.some((entry) => entry.id === id),
        `${id} has no keymap entry`,
      );
      assert.ok(targets.has(id), `${id} is in no menu`);
    }
  });

  test("the handlers are wired in app-commands.js", () => {
    const source = read("../app-commands.js");
    assert.match(source, /"app\.transcribe_colab"/);
    assert.match(source, /"app\.colab_settings"/);
    assert.match(source, /"app\.transcribe_restart"/);
  });

  test("the strings exist in English and Finnish", () => {
    const en = JSON.parse(read("../../src/kuulas/locales/en.json"));
    const fi = JSON.parse(read("../../src/kuulas/locales/fi.json"));
    for (const key of [
      "cmd.app.transcribe_colab",
      "cmd.app.transcribe_colab.hint",
      "cmd.app.colab_settings",
      "cmd.app.colab_settings.hint",
      "menu.transcribe",
      "cmd.app.transcribe_restart",
      "cmd.app.transcribe_restart.hint",
      "ui.colab.interrupted",
      "ui.transcribe.running",
      "ui.transcribe.done",
    ]) {
      assert.ok(en[key], `en ${key}`);
      assert.ok(fi[key], `fi ${key}`);
    }
  });

  test("the consent text says the audio leaves the computer", () => {
    const en = JSON.parse(read("../../src/kuulas/locales/en.json"));
    assert.match(en["ui.colab.consent_text"], /leaves this computer/);
    assert.match(en["cmd.app.transcribe_colab"], /uploaded to Google/);
  });
});
