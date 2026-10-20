// The Clipboard tab drawn into a tiny stand-in for the DOM (there is no browser here): the
// three views, the Share star, the foreign rows' two buttons and the project list. What it
// cannot say is how it looks; it can say what is drawn and what a click reports.
import assert from "node:assert/strict";
import { beforeEach, describe, test } from "node:test";

class FakeNode {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attrs = {};
    this.listeners = {};
    this.className = "";
    this.textContent = "";
    this.value = "";
    this.title = "";
    this.disabled = false;
    this.type = "";
    this.placeholder = "";
    this.id = "";
    this.style = {};
  }

  append(...nodes) {
    this.children.push(...nodes);
  }

  replaceChildren(...nodes) {
    this.children = nodes;
  }

  setAttribute(name, value) {
    this.attrs[name] = value;
  }

  addEventListener(type, fn) {
    this.listeners[type] = [...(this.listeners[type] ?? []), fn];
  }

  click() {
    if (this.disabled) return;
    for (const fn of this.listeners.click ?? []) fn({});
  }

  all() {
    return this.children.flatMap((child) =>
      child instanceof FakeNode ? [child, ...child.all()] : [],
    );
  }

  querySelectorAll(selector) {
    if (selector === "[data-id]") return this.all().filter((node) => node.dataset.id !== undefined);
    throw new Error(`unsupported selector ${selector}`);
  }

  querySelector(selector) {
    const cls = selector.replace(/^\./, "");
    return this.all().find((node) => node.className.split(" ").includes(cls)) ?? null;
  }

  contains(node) {
    return node === this || this.all().includes(node);
  }

  focus() {}
}

globalThis.document = {
  activeElement: null,
  createElement: (tag) => new FakeNode(tag),
};

const { createClipboardPanel } = await import("../clipboard-panel.js");

const S = 48000;
const entry = (id, extra = {}) => ({
  id,
  name: `name ${id}`,
  length: 12 * S,
  clips: 2,
  slots: 1,
  missing_here: 0,
  created_utc: 1000,
  tracks: ["Anna"],
  source_name: "Pilot",
  shared: false,
  ...extra,
});

let calls;
let panel;
let root;
let picker;

beforeEach(() => {
  calls = [];
  root = new FakeNode("section");
  picker = true;
  const record =
    (name) =>
    (...args) =>
      calls.push([name, ...args]);
  panel = createClipboardPanel({
    root,
    actions: {
      select: record("select"),
      preview: record("preview"),
      stopPreview: record("stopPreview"),
      filter: record("filter"),
      rename: record("rename"),
      remove: record("remove"),
      pasteAgain: record("pasteAgain"),
      share: record("share"),
      view: record("view"),
      choose: record("choose"),
      keep: record("keep"),
      clearOld: record("clearOld"),
      toggleProject: record("toggleProject"),
      openProject: record("openProject"),
      openPath: record("openPath"),
      hasPicker: () => picker,
      adopt: record("adopt"),
      pasteHere: record("pasteHere"),
      now: () => 1000 + 300,
      canPasteAgain: () => true,
    },
  });
});

const state = (extra = {}) => ({
  project: { rate: S },
  clipboard: [entry("a"), entry("b", { shared: true })],
  clipboardShared: [],
  ...extra,
});
const byAction = (action) => root.all().filter((node) => node.dataset.action === action);

describe("the segmented control", () => {
  test("three views, the current one pressed, a click reports the view", () => {
    panel.update(state());
    const views = byAction("view");
    assert.deepEqual(
      views.map((node) => node.textContent),
      ["ui.clipboard.view.project", "ui.clipboard.view.shared", "ui.clipboard.view.others"],
    );
    assert.deepEqual(
      views.map((node) => node.attrs["aria-pressed"]),
      ["true", "false", "false"],
    );
    views[2].click();
    assert.deepEqual(calls, [["view", "others"]]);
  });
});

describe("the preview on a chip", () => {
  const playing = (id) => state({ clipboardPlaying: { id, seq: 1 } });

  test("idle: every chip shows Play, no progress meter", () => {
    panel.update(state());
    const buttons = byAction("preview");
    assert.deepEqual(
      buttons.map((node) => [
        node.textContent,
        node.attrs["data-icon"],
        node.attrs["aria-pressed"],
      ]),
      [
        ["ui.clipboard.preview", "play", "false"],
        ["ui.clipboard.preview", "play", "false"],
      ],
    );
    assert.equal(byAction("preview-progress").length, 0);
    buttons[0].click();
    assert.deepEqual(calls, [["preview", "a"]]);
  });

  test("only the playing chip shows Stop, and a click on it stops the preview", () => {
    panel.update(playing("b"));
    const [a, b] = byAction("preview");
    assert.equal(a.textContent, "ui.clipboard.preview");
    assert.equal(b.textContent, "ui.clipboard.preview_stop");
    assert.equal(b.attrs["data-icon"], "stop");
    assert.equal(b.attrs["aria-pressed"], "true");
    assert.equal(b.attrs["aria-label"], "ui.clipboard.preview_stop");
    b.click();
    a.click();
    assert.deepEqual(calls, [
      ["stopPreview", "b"],
      ["preview", "a"],
    ]);
  });

  test("the playing chip's bottom edge is a progress meter that follows the preview", () => {
    panel.update(playing("a"));
    const [meter] = byAction("preview-progress");
    assert.equal(meter.attrs.role, "progressbar");
    assert.equal(meter.attrs["aria-valuemin"], "0");
    assert.equal(meter.attrs["aria-valuemax"], "100");
    assert.equal(meter.dataset.id, "a");
    panel.progress(0.25);
    assert.equal(meter.attrs["aria-valuenow"], "25");
    assert.equal(meter.children[0].style.transform, "scaleX(0.25)");
    panel.progress(2);
    assert.equal(meter.attrs["aria-valuenow"], "100");
    // stopped: the meter goes with the redraw
    panel.update(state());
    assert.equal(byAction("preview-progress").length, 0);
    panel.progress(0.5); // nothing to fill: no error
  });

  test("the chip's buttons are square blocks with an icon over the label", () => {
    panel.update(state());
    for (const action of ["share", "preview", "paste", "rename", "delete"]) {
      for (const node of byAction(action)) {
        assert.match(node.className, /\bbutton block\b/, action);
        if (action !== "share") assert.ok(node.attrs["data-icon"], action);
      }
    }
    panel.update(state({ clipboardView: "shared", clipboardShared: [entry("s1")] }));
    for (const action of ["paste-here", "copy-here", "unshare"]) {
      const [node] = byAction(action);
      assert.match(node.className, /\bbutton block\b/, action);
      assert.ok(node.attrs["data-icon"], action);
    }
  });
});

describe("this project", () => {
  test("a Share star per entry (aria-pressed), no Pin, the metadata line", () => {
    panel.update(state());
    const stars = byAction("share");
    assert.equal(stars.length, 2);
    assert.deepEqual(
      stars.map((node) => node.attrs["aria-pressed"]),
      ["false", "true"],
    );
    assert.ok(stars.every((node) => node.title.length > 0));
    stars[0].click();
    stars[1].click();
    assert.deepEqual(calls, [
      ["share", "a", true],
      ["share", "b", false],
    ]);
    assert.equal(byAction("pin").length, 0);
    const meta = root.all().filter((node) => node.className === "clip-meta");
    assert.ok(meta.some((node) => node.textContent.startsWith("Pilot · Anna · 0:12 · ")));
  });

  test("Clear old entries reports the count and the click", () => {
    panel.update(state({ clipboardKeep: 25 }));
    const [field] = byAction("keep");
    assert.equal(field.value, "25");
    byAction("clear-old")[0].click();
    assert.deepEqual(calls, [["clearOld"]]);
  });
});

describe("shared", () => {
  test("each entry can be pasted here, copied here, or stopped being shared", () => {
    const shared = [entry("s1", { shared: true, source_name: "Elsewhere" })];
    panel.update(state({ clipboardView: "shared", clipboardShared: shared }));
    assert.equal(byAction("preview").length, 0); // plays only after it is copied here
    byAction("paste-here")[0].click();
    byAction("copy-here")[0].click();
    byAction("unshare")[0].click();
    assert.deepEqual(calls, [
      ["pasteHere", shared[0], ""],
      ["adopt", shared[0], ""],
      ["share", "s1", false],
    ]);
  });

  test("an empty shared store says how to fill it", () => {
    panel.update(state({ clipboardView: "shared" }));
    assert.ok(root.all().some((node) => node.textContent === "ui.clipboard.shared_empty"));
  });
});

describe("other projects", () => {
  const projects = [
    { name: "One", path: "/p/One.kuulas", last_opened: "2026-10-18T19:00:00Z", entries: 2 },
    { name: "Two", path: "/p/Two.kuulas", last_opened: "", entries: 0 },
  ];

  test("the recent projects list; a click asks to open one", () => {
    panel.update(state({ clipboardView: "others", clipboardProjects: projects }));
    const heads = byAction("project");
    assert.equal(heads.length, 2);
    assert.match(heads[0].children[0].textContent, /^One · /);
    heads[0].click();
    assert.deepEqual(calls, [["toggleProject", "/p/One.kuulas"]]);
  });

  test("an open project lists its entries read-only, adopting from that project", () => {
    const entries = [entry("f1")];
    panel.update(
      state({
        clipboardView: "others",
        clipboardProjects: projects,
        clipboardExpanded: ["/p/One.kuulas"],
        clipboardForeign: { "/p/One.kuulas": { status: "ok", entries } },
      }),
    );
    byAction("paste-here")[0].click();
    byAction("copy-here")[0].click();
    assert.deepEqual(calls, [
      ["pasteHere", entries[0], "/p/One.kuulas"],
      ["adopt", entries[0], "/p/One.kuulas"],
    ]);
    assert.equal(byAction("preview").length, 0);
    assert.equal(byAction("unshare").length, 0); // not the shared list
  });

  test("a project still loading, unreadable or empty says so", () => {
    const base = { clipboardView: "others", clipboardProjects: projects };
    for (const [foreign, hint] of [
      [{ status: "loading", entries: [] }, "ui.clipboard.project_loading"],
      [{ status: "error", entries: [] }, "ui.clipboard.project_unreadable"],
      [{ status: "ok", entries: [] }, "ui.clipboard.project_empty"],
    ]) {
      panel.update(
        state({
          ...base,
          clipboardExpanded: ["/p/One.kuulas"],
          clipboardForeign: { "/p/One.kuulas": foreign },
        }),
      );
      assert.ok(
        root.all().some((node) => node.textContent === hint),
        hint,
      );
    }
  });

  test("the desktop has an Open a project button; a browser has a path field", () => {
    panel.update(state({ clipboardView: "others", clipboardProjects: projects }));
    byAction("open-project")[0].click();
    assert.deepEqual(calls, [["openProject"]]);
    assert.equal(byAction("project-path").length, 0);

    picker = false;
    calls.length = 0;
    panel.update(state({ clipboardView: "others", clipboardProjects: projects, probe: 1 }));
    assert.equal(byAction("open-project").length, 0);
    const [field] = byAction("project-path");
    field.value = "/p/Typed.kuulas";
    byAction("project-go")[0].click();
    assert.deepEqual(calls, [["openPath", "/p/Typed.kuulas"]]);
  });

  test("no recent projects says how to look into one", () => {
    panel.update(state({ clipboardView: "others", clipboardProjects: [] }));
    assert.ok(root.all().some((node) => node.textContent === "ui.clipboard.others_empty"));
  });
});
