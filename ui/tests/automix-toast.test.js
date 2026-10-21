// The automix toast renderer (ui/automix-toast.js) on a tiny fake document.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createAutomixToast } from "../automix-toast.js";
import { automixToast } from "../automix-toast-model.js";

class Node {
  constructor() {
    this.textContent = "";
    this.hidden = false;
    this.title = "";
    this.dataset = {};
    this.attributes = {};
    this.children = [];
    const props = {};
    this.style = {
      props,
      setProperty: (k, v) => {
        props[k] = v;
      },
    };
  }
  setAttribute(k, v) {
    this.attributes[k] = v;
  }
  removeAttribute(k) {
    delete this.attributes[k];
  }
  append(child) {
    child.parent = this;
    this.children.push(child);
  }
  get lastElementChild() {
    return this.children.at(-1);
  }
  remove() {
    this.parent.children.splice(this.parent.children.indexOf(this), 1);
  }
}

function fakeDocument() {
  const nodes = new Map();
  return {
    nodes,
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, new Node());
      return nodes.get(id);
    },
    createElement: () => new Node(),
  };
}

const t = (key, values = {}) =>
  Object.keys(values).length ? `${key}${JSON.stringify(values)}` : key;
const job = (detail, extra = {}) => ({
  state: "running",
  progress: 0.49,
  message: "3/4 track 1/4 Olli: plugin (3/9) ...",
  eta: ["minutes", 12],
  detail,
  ...extra,
});
const tracks = {
  phase: 3,
  phases: 4,
  phase_name: "tracks",
  track: { index: 1, total: 4, name: "Olli" },
  stage: { name: "plugin", n: 3, of: 9, state: "working", off: [] },
};

describe("createAutomixToast", () => {
  test("fills the parts, the bar and nine pips; the notice stops its own live region", () => {
    const doc = fakeDocument();
    const toast = createAutomixToast(doc);
    toast.show(automixToast(job(tracks), t));
    const node = (id) => doc.nodes.get(id);
    assert.equal(node("notice").dataset.layout, "rich");
    assert.equal(node("notice").attributes["aria-live"], "off");
    assert.equal(node("notice-rich").hidden, false);
    assert.equal(node("nr-percent").textContent, "49 %");
    assert.equal(node("nr-bar").attributes["aria-valuenow"], "49");
    assert.equal(node("nr-fill").style.props["--nr-fraction"], "0.49");
    assert.equal(node("nr-name").textContent, "Olli");
    assert.equal(node("nr-name").title, "Olli");
    assert.equal(node("nr-note").hidden, true);
    assert.equal(node("nr-pips").children.length, 9);
    assert.equal(node("nr-pips").children[2].dataset.state, "working");
  });

  test("announces a phase once, not a stage change", () => {
    const doc = fakeDocument();
    const toast = createAutomixToast(doc);
    toast.show(automixToast(job(tracks), t));
    const live = doc.nodes.get("notice-live");
    const first = live.textContent;
    assert.ok(first.includes("phase.tracks"));
    live.textContent = "";
    toast.show(automixToast(job({ ...tracks, stage: { ...tracks.stage, n: 4 } }), t));
    assert.equal(live.textContent, "", "same phase: silent");
    toast.show(
      automixToast(
        job({ phase: 4, phases: 4, phase_name: "mastering", track: null, stage: null }),
        t,
      ),
    );
    assert.ok(live.textContent.includes("phase.mastering"));
    assert.equal(doc.nodes.get("nr-pips").children.length, 0);
  });

  test("indeterminate drops aria-valuenow; reset gives the plain notice back", () => {
    const doc = fakeDocument();
    const toast = createAutomixToast(doc);
    toast.show(automixToast(job(tracks, { indeterminate: true }), t));
    const bar = doc.nodes.get("nr-bar");
    assert.equal(bar.attributes["aria-valuenow"], undefined);
    assert.ok("indeterminate" in bar.dataset);
    toast.reset();
    assert.equal(doc.nodes.get("notice").dataset.layout, "plain");
    assert.equal(doc.nodes.get("notice").attributes["aria-live"], "polite");
    assert.equal(doc.nodes.get("notice-rich").hidden, true);
  });
});
