import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  clipLengthText,
  createInspector,
  openSections,
  selectedClip,
  syncGroupOf,
} from "../inspector.js";
import { createTrackClips, trackClipRows } from "../inspector-clips.js";
import { addBusForTrack, hasDuckControl } from "../inspector-track.js";

class FakeNode {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attrs = {};
    this.classList = {
      toggle() {},
      add() {},
      remove() {},
      contains() {
        return false;
      },
    };
    this.listeners = {};
    this.className = "";
    this.textContent = "";
    this.value = "";
    this.title = "";
    this.disabled = false;
    this.type = "";
    this.placeholder = "";
    this.style = { setProperty() {} };
    this.checked = false;
    this.hidden = false;
    this.focused = false;
    this.selected = false;
  }
  get options() {
    return this.children.filter((c) => c.tagName === "option");
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
  getAttribute(name) {
    return this.attrs[name];
  }
  addEventListener(type, fn) {
    this.listeners[type] = [...(this.listeners[type] ?? []), fn];
  }
  focus() {
    this.focused = true;
    globalThis.document.activeElement = this;
  }
  select() {
    this.selected = true;
  }
  closest() {
    return null;
  }
  querySelector(sel) {
    if (sel === "summary") return this.children.find((c) => c.tagName === "summary") ?? null;
    return null;
  }
  querySelectorAll() {
    return [];
  }
  all() {
    return this.children.flatMap((child) =>
      child instanceof FakeNode ? [child, ...child.all()] : [],
    );
  }
}

globalThis.document = {
  createElement: (tag) => new FakeNode(tag),
  documentElement: { lang: "en" },
  activeElement: null,
};

// The server sends sync-group members as { mediaId: origin } (SyncGroup.to_dict).
const project = {
  media: [{ id: "m1", name: "a.wav" }],
  tracks: [{ id: "t1", clips: [{ id: "c1", media: "m1" }] }],
  sync_groups: [{ id: "g1", main: "m1", members: { m1: 0, m2: 5 } }],
};

describe("inspector lookups", () => {
  test("the duck switch exists only for music tracks", () => {
    assert.equal(hasDuckControl({ kind: "music" }), true);
    assert.equal(hasDuckControl({ kind: "speech" }), false);
    assert.equal(hasDuckControl(null), false);
  });
  test("the sync group is found from the members object", () => {
    assert.equal(syncGroupOf(project, "m2").id, "g1");
    assert.equal(syncGroupOf(project, "zz"), null);
    assert.equal(syncGroupOf({ ...project, sync_groups: undefined }, "m1"), null);
  });

  test("only a single selection is inspected", () => {
    const base = { project, selection: new Set(["c1"]) };
    assert.equal(selectedClip(base).media.name, "a.wav");
    assert.equal(selectedClip(base).track.id, "t1", "the track gives the header colour");
    assert.equal(selectedClip({ ...base, selection: new Set(["c1", "x"]) }), null);
    assert.equal(selectedClip({ ...base, selection: new Set(["gone"]) }), null);
  });
});

describe("clip length readout", () => {
  test("a clip's length is h:mm:ss.mmm like every timecode", () => {
    assert.equal(clipLengthText({ length: 48_000 * 125.5 }, 48_000), "2:05.500");
    assert.equal(clipLengthText({ length: 48_000 * 3725.25 }, 48_000), "1:02:05.250");
    assert.equal(clipLengthText({ length: 0 }, 48_000), "0:00.000");
  });
});

describe("inspector sections (density rework, 2026-10-18)", () => {
  test("Track, Bus, Level and Sync start open, the rest closed", () => {
    assert.deepEqual(openSections(null), {
      track: true,
      clips: true,
      bus: true,
      level: true,
      fades: false,
      sync: true,
      source: false,
      details: false,
    });
  });

  test("what the user opened or closed is remembered; junk is ignored", () => {
    assert.deepEqual(openSections('{"fades":true,"level":false,"track":false}'), {
      track: false,
      clips: true,
      bus: true,
      level: false,
      fades: true,
      sync: true,
      source: false,
      details: false,
    });
    assert.deepEqual(openSections("not json"), openSections(null));
    assert.deepEqual(openSections('{"level":"yes","bogus":true}'), openSections(null));
  });
});

describe("New bus from a track (header pop-up and inspector)", () => {
  const run = (answer) => {
    const sent = [];
    const created = [];
    addBusForTrack({ change: (edit) => sent.push(edit) }, "t1", (id) => created.push(id));
    answer?.(sent[0]);
    return { sent, created };
  };

  test("creates the bus for the track and reports the new bus once the server answers", () => {
    const { sent, created } = run((edit) =>
      edit.done({ project: { buses: [{ id: "b1" }, { id: "b2" }] } }),
    );
    assert.equal(sent[0].op, "add_bus");
    assert.deepEqual(sent[0].args, { track_ids: ["t1"] });
    assert.deepEqual(created, ["b2"]);
  });

  test("an answer without a bus calls nothing back", () => {
    const { created } = run((edit) => {
      edit.done({ project: { buses: [] } });
      edit.done(undefined);
    });
    assert.deepEqual(created, []);
  });
});

describe("clip name in inspector", () => {
  const testProject = {
    rate: 48000,
    media: [{ id: "m1", name: "olli.wav", sha256: "abc" }],
    tracks: [
      {
        id: "t1",
        name: "Olli",
        clips: [
          {
            id: "c1",
            media: "m1",
            name: "Take 1",
            length: 48000,
            gain_db: 0,
            pan: 0,
            fade_in: 0,
            fade_out: 0,
          },
        ],
      },
    ],
    buses: [],
    sync_groups: [],
  };

  test("shows clip name input and focuses/selects it with focusName (F2)", () => {
    const root = new FakeNode("section");
    const sent = [];
    const editor = {
      change: (edit) => sent.push(edit),
    };
    const inspector = createInspector({ root, editor });
    const state = { project: testProject, selection: new Set(["c1"]), head: "1" };
    inspector.update(state);

    const nameInput = root.all().find((n) => n.className.includes("inspector-clip-name"));
    assert.ok(nameInput, "Clip name input exists in inspector");
    assert.equal(nameInput.value, "Take 1");

    inspector.focusName();
    assert.equal(nameInput.focused, true);
    assert.equal(nameInput.selected, true);

    // Editing to empty resets name to auto (sends name: "")
    nameInput.value = "   ";
    nameInput.listeners.blur[0]();
    assert.equal(sent.length, 1);
    assert.equal(sent[0].op, "set_clip");
    assert.equal(sent[0].args.clip_id, "c1");
    assert.equal(sent[0].args.name, "");
  });
});

describe("track clip properties list", () => {
  const project = {
    rate: 48000,
    media: [{ id: "m", name: "Audio.wav" }],
    tracks: [
      {
        id: "t",
        clips: [
          { id: "b", media: "m", start: 48000, length: 24000, muted: true },
          { id: "a", media: "m", start: 0, length: 48000, name: "Intro" },
        ],
      },
      { id: "other", clips: [{ id: "x", start: 0, length: 2 }] },
    ],
  };
  test("timeline order includes repeated source uses and muted clips, excludes other tracks", () => {
    assert.deepEqual(
      trackClipRows(project, "t").map((x) => [x.id, x.name, x.muted]),
      [
        ["a", "Intro", false],
        ["b", "Audio.wav", true],
      ],
    );
    assert.deepEqual(trackClipRows(project, "gone"), []);
  });
  test("click selects/jumps through existing action and edits/deletions refresh the list", () => {
    const details = new FakeNode("details");
    const calls = [];
    const view = createTrackClips({ details, trackId: "t", jump: (...args) => calls.push(args) });
    view.update({ project, selection: new Set(["a"]) });
    const buttons = details.all().filter((n) => n.tagName === "button");
    assert.equal(buttons.length, 2);
    assert.equal(buttons[0].attrs["aria-pressed"], "true");
    buttons[1].listeners.click[0]();
    assert.deepEqual(calls, [["b", "t", 48000]]);
    view.update({
      project: { ...project, tracks: [{ id: "t", clips: [] }] },
      selection: new Set(),
    });
    assert.equal(details.all().filter((n) => n.tagName === "button").length, 0);
  });
});
