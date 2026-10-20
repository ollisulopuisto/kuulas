// The plug-in name matcher: the same table as tests/test_plugins.py.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  editDistance,
  highlightRuns,
  labelFor,
  looksLikePath,
  matchPlugins,
  pathLabel,
  resolveTyped,
} from "../plugin-match.js";

const entries = (...specs) =>
  specs.map(([name, format]) => ({ name, format, path: `/p/${format}/${name}` }));
const DX = entries(
  ["Accentize dxRevive", "VST3"],
  ["Accentize dxRevive", "AU"],
  ["Accentize dxRevive", "VST2"],
  ["Waves NS1", "VST3"],
  ["FabFilter Pro-Q 3", "AU"],
  ["Reverb", "VST3"],
);

describe("matching", () => {
  for (const query of [
    "dxrev",
    "accentize dx",
    "dxrevi",
    "DXREVIVE",
    "accentize-dxrevive",
    "dx revive",
    "dxrevie",
    "acc dxr",
    "dxrvive",
  ]) {
    test(`"${query}" finds dxRevive as VST3`, () => {
      const top = matchPlugins(query, DX)[0];
      assert.equal(top.name, "Accentize dxRevive");
      assert.equal(top.format, "VST3");
    });
  }

  test("rank: exact, prefix, word-prefix, subsequence", () => {
    const items = entries(
      ["xreverb", "VST3"],
      ["Reverb", "VST3"],
      ["Big Reverb", "VST3"],
      ["Reverb Plus", "VST3"],
    );
    const got = matchPlugins("reverb", items);
    assert.deepEqual(
      got.map((m) => [m.name, m.tier]),
      [
        ["Reverb", "exact"],
        ["Reverb Plus", "prefix"],
        ["Big Reverb", "word"],
        ["xreverb", "subsequence"],
      ],
    );
  });

  test("one entry per name, best format", () => {
    const got = matchPlugins("dxrevive", DX).filter((m) => m.name.startsWith("Accentize"));
    assert.deepEqual(
      got.map((m) => m.format),
      ["VST3"],
    );
    assert.equal(matchPlugins("foo", entries(["Foo", "VST2"], ["Foo", "AU"]))[0].format, "AU");
  });

  test("a typo needs a name of five letters and a query of four", () => {
    assert.deepEqual(matchPlugins("wvae", entries(["Wave", "VST3"])), []);
    assert.equal(matchPlugins("wvaes", entries(["Waves", "VST3"]))[0].tier, "typo");
    assert.equal(matchPlugins("wv", entries(["Waves", "VST3"]))[0].tier, "subsequence");
    assert.deepEqual(matchPlugins("abx", entries(["abc", "VST3"])), []);
  });

  test("limit, highlight, nothing", () => {
    const many = entries(...Array.from({ length: 30 }, (_, i) => [`Comp ${i}`, "VST3"]));
    assert.equal(matchPlugins("comp", many, 5).length, 5);
    const top = matchPlugins("dxrev", DX)[0];
    assert.equal(
      top.indices
        .map((i) => top.name[i])
        .join("")
        .toLowerCase(),
      "dxrev",
    );
    assert.deepEqual(matchPlugins("zzzzqqq", DX), []);
    assert.deepEqual(matchPlugins("", DX), []);
  });

  test("edit distance counts a swap as one", () => {
    assert.equal(editDistance("wvaes", "waves"), 1);
    assert.equal(editDistance("abc", "xyz"), 3);
  });
});

describe("what typed text stands for", () => {
  test("a path is taken as typed", () => {
    assert.deepEqual(resolveTyped("/x/My.vst3", DX), { kind: "path", path: "/x/My.vst3" });
  });
  test("a name becomes the best match", () => {
    const got = resolveTyped("dxrev", DX);
    assert.equal(got.kind, "match");
    assert.equal(got.plugin.format, "VST3");
  });
  test("a name nothing matches is unmatched", () => {
    assert.deepEqual(resolveTyped("zzzzqqq", DX), { kind: "none" });
  });
  test("without a scan the text is plain", () => {
    assert.deepEqual(resolveTyped("dxRevive", []), { kind: "plain", text: "dxRevive" });
  });
  test("empty text stands for nothing", () => {
    assert.deepEqual(resolveTyped("  ", DX), { kind: "empty" });
  });
});

describe("helpers", () => {
  test("paths are told from names", () => {
    assert.equal(looksLikePath("/Library/x.vst3"), true);
    assert.equal(looksLikePath("~/x"), true);
    assert.equal(looksLikePath("dxRevive"), false);
  });
  test("labels", () => {
    assert.equal(pathLabel("/a/b/Accentize dxRevive.vst3"), "Accentize dxRevive");
    assert.equal(labelFor("/p/VST3/Reverb", DX), "Reverb");
    assert.equal(labelFor("/q/Mine.component", DX), "Mine");
  });
  test("highlight runs", () => {
    assert.deepEqual(highlightRuns("abcd", [1, 2]), [
      { text: "a", hit: false },
      { text: "bc", hit: true },
      { text: "d", hit: false },
    ]);
  });
});
