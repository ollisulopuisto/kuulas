// Transcribe on Colab (WP78): the consent rule, the settings form, the notice and the commands.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  CONSENT_KEY,
  colabForm,
  colabModelSelection,
  colabNotice,
  colabSettingsBody,
  consentNeeded,
  rememberConsent,
  rememberedConsent,
  resumableJob,
  signinPolls,
  signinView,
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
  test("Colab model choices use backend IDs and migrate the former turbo default", () => {
    assert.deepEqual(colabModelSelection(), { model: "whisper", customModel: "" });
    assert.deepEqual(colabModelSelection("turbo"), { model: "whisper", customModel: "" });
    assert.deepEqual(colabModelSelection("whisper"), { model: "whisper", customModel: "" });
    assert.deepEqual(colabModelSelection("parakeet-ultra"), {
      model: "parakeet-ultra",
      customModel: "",
    });
    assert.deepEqual(colabModelSelection("custom-model"), {
      model: "custom",
      customModel: "custom-model",
    });
    assert.deepEqual(colabModelSelection("custom"), {
      model: "custom",
      customModel: "custom",
    });
    assert.deepEqual(colabForm({ model: "turbo" }), {
      command: "",
      cwd: "",
      extra: "",
      model: "whisper",
      customModel: "",
      language: "",
      noDrive: false,
      align: true,
    });
  });

  test("both model choices have translated labels", () => {
    for (const language of ["en", "fi"]) {
      const catalog = JSON.parse(
        readFileSync(new URL(`../../src/kuulas/locales/${language}.json`, import.meta.url), "utf8"),
      );
      assert.ok(catalog["ui.colab.model.whisper"]);
      assert.ok(catalog["ui.colab.model.parakeet_ultra"]);
      assert.ok(catalog["ui.colab.model_hint"]);
      assert.ok(catalog["ui.colab.model.custom"]);
      assert.ok(catalog["ui.colab.model_custom_label"]);
      assert.ok(catalog["ui.colab.model_custom_placeholder"]);
    }
  });

  test("the selected backend model ID is persisted unchanged", () => {
    assert.equal(
      colabSettingsBody({
        command: "",
        cwd: "",
        extra: "",
        model: "parakeet-ultra",
        language: "",
      }).model,
      "parakeet-ultra",
    );
    assert.equal(
      colabSettingsBody({
        command: "",
        cwd: "",
        extra: "",
        model: "whisper",
        language: "",
      }).model,
      "whisper",
    );
  });

  test("a custom backend model ID is preserved", () => {
    const body = colabSettingsBody({
      command: "",
      cwd: "",
      extra: "",
      model: "custom",
      customModel: "  faster-whisper-large-v3-turbo  ",
      language: "",
    });
    assert.equal(body.model, "faster-whisper-large-v3-turbo");
    assert.equal(
      colabSettingsBody({
        command: "",
        cwd: "",
        extra: "",
        model: "custom",
        customModel: "custom",
        language: "",
      }).model,
      "custom",
    );
  });

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
      model: "whisper",
      customModel: "",
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

describe("signing in to Google for Colab", () => {
  const status = (fields) => ({
    signed_in: false,
    state: "idle",
    url: null,
    lines: [],
    error: null,
    ...fields,
  });

  test("not signed in offers the sign-in and nothing else", () => {
    const view = signinView(status({}), t);
    assert.deepEqual(
      [view.phase, view.showStart, view.showCode, view.showCancel, view.ok],
      ["idle", true, false, false, false],
    );
    assert.equal(view.message, "ui.colab.signin_state_no{}");
  });

  test("a started sign-in waits for the address, then asks for the code", () => {
    const starting = signinView(status({ state: "running" }), t);
    assert.deepEqual(
      [starting.phase, starting.showStart, starting.showCode, starting.showCancel],
      ["starting", false, false, true],
    );
    const url = "https://accounts.google.com/o/oauth2/auth?x=1";
    const waiting = signinView(status({ state: "running", url }), t);
    assert.deepEqual(
      [waiting.phase, waiting.showCode, waiting.showCancel, waiting.url],
      ["waiting", true, true, url],
    );
  });

  test("done is ok and lets the transcription go on", () => {
    const view = signinView(status({ state: "done", signed_in: true }), t);
    assert.deepEqual([view.phase, view.ok, view.showStart], ["ok", true, false]);
    assert.equal(signinView(status({ signed_in: true }), t).ok, true);
  });

  test("a failure shows the tool's words and offers to try again", () => {
    const view = signinView(status({ state: "failed", error: { text: "bad code" } }), t);
    assert.deepEqual(
      [view.phase, view.error, view.showStart, view.ok],
      ["failed", "bad code", true, false],
    );
  });

  test("a cancelled sign-in is a fresh start", () => {
    const view = signinView(status({ state: "cancelled" }), t);
    assert.deepEqual([view.phase, view.showStart], ["idle", true]);
  });

  test("only a running sign-in is polled", () => {
    assert.equal(signinPolls(status({ state: "running" })), true);
    for (const state of ["idle", "done", "failed", "cancelled"]) {
      assert.equal(signinPolls(status({ state })), false);
    }
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
      "app.transcribe_all_colab",
      "app.colab_settings",
      "app.colab_signin",
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
    assert.match(source, /"app\.transcribe_all_colab"/);
    assert.match(source, /"app\.colab_settings"/);
    assert.match(source, /"app\.colab_signin"/);
    assert.match(source, /"app\.transcribe_restart"/);
  });

  test("the strings exist in English and Finnish", () => {
    const en = JSON.parse(read("../../src/kuulas/locales/en.json"));
    const fi = JSON.parse(read("../../src/kuulas/locales/fi.json"));
    for (const key of [
      "cmd.app.transcribe_colab",
      "cmd.app.transcribe_colab.hint",
      "cmd.app.transcribe_all_colab",
      "cmd.app.transcribe_all_colab.hint",
      "cmd.app.colab_settings",
      "cmd.app.colab_settings.hint",
      "cmd.app.colab_signin",
      "cmd.app.colab_signin.hint",
      "ui.colab.signin_title",
      "ui.colab.signin_text",
      "menu.transcribe.local",
      "menu.transcribe.colab",
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

  test("the interrupted texts name the command, not a menu path", () => {
    const en = JSON.parse(read("../../src/kuulas/locales/en.json"));
    const fi = JSON.parse(read("../../src/kuulas/locales/fi.json"));
    for (const key of ["ui.colab.interrupted", "error.transcribe.interrupted"]) {
      assert.match(en[key], /command "Restart interrupted transcriptions" in the menus/);
      assert.match(fi[key], /"Käynnistä keskeytyneet litteroinnit uudelleen"/);
      assert.doesNotMatch(en[key], /Transcribe >/);
      assert.doesNotMatch(fi[key], /Litteroi >/);
    }
  });

  test("the consent text says the audio leaves the computer", () => {
    const en = JSON.parse(read("../../src/kuulas/locales/en.json"));
    assert.match(en["ui.colab.consent_text"], /leaves this computer/);
    assert.match(en["cmd.app.transcribe_colab"], /uploaded to Google/);
  });

  test("the model picker is a labeled select with an accessible custom-ID input", () => {
    const source = read("../colab-dialog.js");
    assert.match(source, /select\.name = "model"/);
    assert.match(source, /label\.htmlFor = select\.id/);
    assert.match(
      source,
      /customModel\.setAttribute\("aria-label", t\("ui\.colab\.model_custom_label"\)\)/,
    );
    assert.match(
      source,
      /fields\.model\.addEventListener\("change", updateCustomModelVisibility\)/,
    );
  });
});
