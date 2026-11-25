// A server answer that is not JSON used to reach the user as the browser's own words
// ("The string did not match the expected pattern." in Safari): now it names the request.
import assert from "node:assert/strict";
import { afterEach, describe, test } from "node:test";
import { ApiError, getClipboard } from "../api.js";

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

const answer =
  (status, body, statusText = "") =>
  () =>
    Promise.resolve(new Response(body, { status, statusText }));

describe("a server answer that is not JSON", () => {
  test("a good answer is parsed", async () => {
    globalThis.fetch = answer(200, JSON.stringify({ entries: [] }));
    assert.deepEqual(await getClipboard(), { entries: [] });
  });

  test("an OK answer with a broken body is an ApiError that names the request and the status", async () => {
    globalThis.fetch = answer(200, "<html>not json");
    await assert.rejects(getClipboard(), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 200);
      assert.equal(error.path, "/api/clipboard");
      assert.equal(error.code, "bad_json");
      assert.match(error.message, /\/api\/clipboard/);
      return true;
    });
  });

  test("an empty OK answer counts the same", async () => {
    globalThis.fetch = answer(200, "");
    await assert.rejects(getClipboard(), (error) => error.code === "bad_json");
  });

  test("an error answer that is not JSON keeps the status text", async () => {
    globalThis.fetch = answer(500, "Internal Server Error", "Internal Server Error");
    await assert.rejects(getClipboard(), (error) => {
      assert.equal(error.status, 500);
      assert.equal(error.message, "Internal Server Error");
      return true;
    });
  });
});
