// File > New project… / Open project… in a plain browser: the checks the dialog makes before
// it asks the server (src/kuulas/new_project.py applies the same rules and has the last word).
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  folderName,
  isAbsolutePath,
  newProjectRequest,
  openProjectRequest,
} from "../project-name.js";

describe("folderName", () => {
  test("adds the .kuulas suffix once", () => {
    assert.deepEqual(folderName("My show"), { ok: true, folder: "My show.kuulas" });
    assert.deepEqual(folderName("  Episode 12 "), { ok: true, folder: "Episode 12.kuulas" });
    assert.deepEqual(folderName("Show.kuulas"), { ok: true, folder: "Show.kuulas" });
    assert.deepEqual(folderName("Show.KUULAS"), { ok: true, folder: "Show.kuulas" });
    assert.deepEqual(folderName("Äänet ja öljy"), { ok: true, folder: "Äänet ja öljy.kuulas" });
    assert.deepEqual(folderName("v1.2"), { ok: true, folder: "v1.2.kuulas" });
  });
  test("refuses what cannot be a folder name", () => {
    const bad = ["", "   ", ".kuulas", "a/b", "a\\b", "a\0b", ".", "..", ".hidden"];
    for (const name of [...bad, "x".repeat(101)]) {
      assert.deepEqual(folderName(name), { ok: false, key: "ui.project.bad_name" }, name);
    }
    assert.equal(folderName("x".repeat(100)).ok, true);
    assert.equal(folderName(undefined).ok, false);
  });
});

describe("isAbsolutePath", () => {
  test("knows Unix, drive and UNC paths, and refuses ~ and .. paths", () => {
    assert.equal(isAbsolutePath("/Users/me/Podcasts"), true);
    assert.equal(isAbsolutePath("C:\\Users\\me"), true);
    assert.equal(isAbsolutePath("\\\\server\\share"), true);
    assert.equal(isAbsolutePath("~/Podcasts"), false);
    assert.equal(isAbsolutePath("Podcasts"), false);
    assert.equal(isAbsolutePath("/a/../b"), false);
    assert.equal(isAbsolutePath(""), false);
  });
});

describe("the dialog requests", () => {
  test("new project: the server gets the folder and the name as typed, trimmed", () => {
    assert.deepEqual(newProjectRequest({ parent: " /Users/me ", name: " Show " }), {
      ok: true,
      body: { parent: "/Users/me", name: "Show" },
    });
  });
  test("new project: a bad name points at the name field, a bad folder at the folder", () => {
    assert.deepEqual(newProjectRequest({ parent: "/Users/me", name: "a/b" }), {
      ok: false,
      field: "name",
      key: "ui.project.bad_name",
    });
    assert.deepEqual(newProjectRequest({ parent: "me", name: "Show" }), {
      ok: false,
      field: "parent",
      key: "ui.project.need_folder",
    });
  });
  test("open project: an absolute path", () => {
    assert.deepEqual(openProjectRequest(" /Users/me/Show.kuulas "), {
      ok: true,
      body: { path: "/Users/me/Show.kuulas" },
    });
    assert.deepEqual(openProjectRequest("Show.kuulas"), {
      ok: false,
      field: "path",
      key: "ui.project.need_folder",
    });
  });
});
