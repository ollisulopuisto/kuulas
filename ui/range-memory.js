// The range a cut used up (owner, 2026-10-18): X clears the in and out marks from the screen, but
// Undo brings them back, because the next thing is usually to nudge one of them. The marks are
// not part of the project history, so they are remembered here against the history head:
// `before` is the head the cut started from, `after` the head it made. Pure; app.js applies it.

/** Remember the marks a cut is about to use up, against the head it starts from. */
export function rememberRange(beforeHead, marks) {
  return {
    before: beforeHead,
    after: null,
    marks: {
      inPoint: marks.inPoint ?? null,
      outPoint: marks.outPoint ?? null,
      rangeTracks: new Set(marks.rangeTracks ?? []),
    },
  };
}

const hasMarks = (current) =>
  (current?.inPoint ?? null) !== null || (current?.outPoint ?? null) !== null;

/**
 * The head changed to `head`; `current` holds the marks now on screen.
 * -> { memory, patch }: the memory to keep and the state patch to apply (or null).
 */
export function stepRangeMemory(memory, head, current) {
  if (!memory) return { memory: null, patch: null };
  if (head === memory.before) {
    // Undo back to where the cut began: the marks return, unless new ones were set meanwhile.
    if (hasMarks(current)) return { memory, patch: null };
    return {
      memory,
      patch: {
        inPoint: memory.marks.inPoint,
        outPoint: memory.marks.outPoint,
        rangeTracks: new Set(memory.marks.rangeTracks),
      },
    };
  }
  if (memory.after === null) return { memory: { ...memory, after: head }, patch: null };
  if (head === memory.after) {
    // Redo: the range is used up again.
    if (!hasMarks(current)) return { memory, patch: null };
    return {
      memory,
      patch: { inPoint: null, outPoint: null, rangeTracks: new Set(), selection: new Set() },
    };
  }
  return { memory: null, patch: null };
}
