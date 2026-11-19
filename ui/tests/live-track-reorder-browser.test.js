// Real-browser regression for the timeline scroll indicator and waveform stacking.
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

async function measure(query) {
  assert.ok(chrome, "no Chrome found: install Chrome/Chromium or set CHROME to its path");
  const url = `http://127.0.0.1:${port}/tests/browser/live-reorder.html?${query}`;
  const { stdout: dom } = await run(
    chrome,
    [
      "--headless",
      "--no-sandbox",
      "--disable-gpu",
      "--window-size=800,700",
      "--virtual-time-budget=4000",
      "--dump-dom",
      url,
    ],
    { encoding: "utf8", timeout: 30000 },
  );
  const text = dom.match(/<pre id="result">([\s\S]*?)<\/pre>/)[1];
  return JSON.parse(text.replaceAll("&quot;", '"').replaceAll("&amp;", "&"));
}

test("track order changes before release and the dragged controls survive repeated crossings", async () => {
  const result = await measure("");
  assert.equal(result.error, undefined);
  assert.deepEqual(result.afterFirstMove, ["b", "a", "c"]);
  assert.deepEqual(result.afterSecondMove, ["b", "c", "a"]);
  assert.deepEqual(result.afterBackMove, ["a", "b", "c"]);
  assert.equal(result.sameHandle, true);
  assert.equal(result.detachedRows, 0, "moving a captured handle releases native pointer capture");
  assert.equal(result.stoppedOnCancel, true);
  assert.equal(result.separateDragsHaveDifferentKeys, true);
  assert.equal(result.connectedThroughout, true);
  assert.equal(result.uniqueDragKeys, 1);
  assert.equal(result.callsBeforeUp, 3);
  assert.equal(result.callsAfterUp, 3, "release must not add a duplicate edit");
});
