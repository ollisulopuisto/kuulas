// Real-browser timing-review regressions for selection, failures and playback.
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const run = promisify(execFile);
const ui = fileURLToPath(new URL("..", import.meta.url));
const chrome = [
  process.env.CHROME,
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].find((path) => path && existsSync(path));
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" };

let server;
let port;
before(async () => {
  server = createServer((req, res) => {
    if (req.url.startsWith("/api/locales/")) {
      const lang = req.url.endsWith("/fi") ? "fi" : "en";
      res.writeHead(200, { "content-type": "application/json" });
      res.end(readFileSync(join(ui, `../src/kuulas/locales/${lang}.json`)));
      return;
    }
    const path = normalize(join(ui, new URL(req.url, "http://x").pathname));
    if (!path.startsWith(ui) || !existsSync(path)) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { "content-type": types[extname(path)] ?? "application/octet-stream" });
    res.end(readFileSync(path));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  port = server.address().port;
});
after(() => server.close());

test("sync keyboard targets, visible errors and playback seek stay coordinated", async () => {
  assert.ok(chrome, "Chrome required");
  const { stdout } = await run(chrome, [
    "--headless",
    "--no-sandbox",
    "--disable-gpu",
    "--window-size=1400,1000",
    "--virtual-time-budget=2000",
    "--dump-dom",
    `http://127.0.0.1:${port}/tests/browser/sync-review.html`,
  ]);
  const result = JSON.parse(stdout.match(/<pre id="result">([\s\S]*?)<\/pre>/)[1]);
  assert.equal(result.error, undefined);
  assert.deepEqual(result.keyboard, {
    label: "Guest C",
    fieldBefore: "0.200",
    focusKept: true,
    movedTrack: "c",
    frames: 24000,
  });
  assert.equal(result.errorVisible, true);
  assert.equal(result.seekSent, true);
  assert.equal(result.boundedOriginalSeek, true);
  assert.equal(result.playbackErrorVisible, true);
});
