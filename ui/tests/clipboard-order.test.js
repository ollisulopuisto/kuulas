import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { reorderTarget } from "../clipboard-order.js";

const ids = ["a", "b", "c", "d"];
const at = (draggedId, rowId, half) =>
  reorderTarget({ draggedId, rowId, offsetY: half === "upper" ? 5 : 35, rowHeight: 40, ids });

describe("reorderTarget: where a dragged entry lands in the Clipboard list", () => {
  test("the upper half of a row puts it before that row", () => {
    assert.deepEqual(at("d", "b", "upper"), { before: "b" });
  });

  test("the lower half puts it before the next row, or last after the last row", () => {
    assert.deepEqual(at("d", "a", "lower"), { before: "b" });
    assert.deepEqual(at("a", "d", "lower"), { before: null });
  });

  test("dropping where it already is changes nothing", () => {
    assert.equal(at("b", "b", "upper"), null);
    assert.equal(at("b", "b", "lower"), null);
    assert.equal(at("b", "a", "lower"), null); // before b: it is already there
    assert.equal(at("b", "c", "upper"), null);
    assert.equal(at("d", "d", "lower"), null); // last already
  });

  test("an entry that is not in this list (another shelf) is not reordered", () => {
    assert.equal(
      reorderTarget({ draggedId: "zzz", rowId: "a", offsetY: 5, rowHeight: 40, ids }),
      null,
    );
  });

  test("an unknown row is no target", () => {
    assert.equal(
      reorderTarget({ draggedId: "a", rowId: "zzz", offsetY: 5, rowHeight: 40, ids }),
      null,
    );
  });
});
