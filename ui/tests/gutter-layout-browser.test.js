// Real-browser contract for the permanent track-control gutter (owner, 2026-11-19):
// the timeline canvases start at the gutter's right edge and the painter measures
// the canvas, so time 0 begins where the wave area begins.
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

test("the wave area starts at the gutter's right edge", async () => {
  assert.ok(chrome, "no Chrome found: install Chrome/Chromium or set CHROME to its path");
  const url = `http://127.0.0.1:${port}/tests/browser/gutter-layout.html`;
  const { stdout: dom } = await run(
    chrome,
    [
      "--headless",
      "--no-sandbox",
      "--disable-gpu",
      "--window-size=940,400",
      "--virtual-time-budget=4000",
      "--dump-dom",
      url,
    ],
    { encoding: "utf8", timeout: 30000 },
  );
  const text = dom.match(/<pre id="result">([\s\S]*?)<\/pre>/)[1];
  const result = JSON.parse(text.replaceAll("&quot;", '"').replaceAll("&amp;", "&"));
  assert.equal(result.error, undefined);
  assert.equal(result.gutter, 80, "the gutter width is not wired into the theme");
  assert.equal(result.canvasLeft, 80, "the timeline canvas starts at the stack's left edge");
  assert.equal(result.canvasWidth, result.stackWidth - 80, "the canvas runs under the gutter");
  assert.equal(
    result.sizeWidth,
    result.canvasWidth,
    "the painter measures the stack, not the canvas",
  );
});
