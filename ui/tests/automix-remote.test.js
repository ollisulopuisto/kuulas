// "Run on another Mac": the settings body, the test result rows and the one-line note.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { advancedBody, remoteBody, remoteNote, remoteRows } from "../automix-model.js";

const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;

describe("remoteBody", () => {
  test("trims the fields and leaves empty ones out", () => {
    assert.deepEqual(
      remoteBody({ enabled: true, host: " studio ", cwd: "~/podcast ", workDir: "" }),
      { enabled: true, host: "studio", cwd: "~/podcast" },
    );
  });

  test("off by default", () => {
    assert.deepEqual(remoteBody({ enabled: false, host: "", cwd: "", workDir: "" }), {
      enabled: false,
    });
  });

  test("advancedBody carries it only when given", () => {
    const base = { command: "", cwd: "", tempDir: "", outputDir: "", extra: "" };
    assert.equal("remote" in advancedBody(base), false);
    const remote = { enabled: true, host: "studio", cwd: "", workDir: "" };
    assert.deepEqual(advancedBody({ ...base, remote }).remote, {
      enabled: true,
      host: "studio",
    });
  });
});

describe("remoteNote", () => {
  test("names the host only when it is on", () => {
    assert.equal(
      remoteNote({ enabled: true, host: "studio" }, t),
      'ui.automix.remote_runs_on{"host":"studio"}',
    );
    assert.equal(remoteNote({ enabled: false, host: "studio" }, t), "");
    assert.equal(remoteNote(undefined, t), "");
  });
});

describe("remoteRows", () => {
  const result = {
    ok: false,
    checks: [
      { id: "ssh", ok: true, warn: false, detail: "" },
      { id: "disk", ok: true, warn: true, detail: "12 GB" },
      { id: "cwd", ok: false, warn: false, detail: "/nope" },
      { id: "flags", ok: false, warn: false, detail: "", missing: ["--bed-under-speech-db"] },
    ],
  };

  test("each check is its own row with a status and a reason", () => {
    const rows = remoteRows(result, t);
    assert.deepEqual(
      rows.map((r) => [r.id, r.status]),
      [
        ["ssh", "ok"],
        ["disk", "warn"],
        ["cwd", "failed"],
        ["flags", "failed"],
      ],
    );
    assert.equal(rows[0].label, "ui.automix.remote_check.ssh{}");
    assert.equal(rows[0].statusText, "ui.automix.remote_ok{}");
    assert.equal(rows[1].detail, 'ui.automix.remote_low_disk{"free":"12 GB"}');
    assert.equal(rows[2].detail, "/nope");
    assert.equal(rows[3].detail, 'ui.automix.remote_missing{"flags":"--bed-under-speech-db"}');
  });

  test("a damaged answer gives no rows", () => {
    assert.deepEqual(remoteRows(null, t), []);
    assert.deepEqual(remoteRows({ checks: "x" }, t), []);
  });
});
