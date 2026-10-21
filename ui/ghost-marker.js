/**
 * Implicit In/Out markers remembering the last cut as a hidden "ghost" marker (T69).
 */

/**
 * Remember the splice point of a cut.
 * @param {number} frame
 * @returns {{ frame: number }}
 */
export function rememberCut(frame) {
  return { frame };
}

/**
 * Clear the remembered ghost cut point.
 * @returns {null}
 */
export function clearGhost() {
  return null;
}

/**
 * Resolve an in/out mark placement, optionally using the ghost cut point
 * to infer the opposite mark.
 *
 * @param {{ frame: number } | null | undefined} ghost
 * @param {{ in?: number | null, out?: number | null, guessed?: { in?: boolean, out?: boolean } }} marks
 * @param {"in" | "out"} kind
 * @param {number} frame
 * @returns {{ in: number | null, out: number | null, guessed: { in: boolean, out: boolean } }}
 */
export function resolveMark(ghost, marks, kind, frame) {
  const currentIn = marks?.in ?? null;
  const currentOut = marks?.out ?? null;
  let guessedIn = marks?.guessed?.in ?? false;
  let guessedOut = marks?.guessed?.out ?? false;

  let newIn = currentIn;
  let newOut = currentOut;

  const ghostFrame = ghost && typeof ghost.frame === "number" ? ghost.frame : null;

  if (kind === "out") {
    newOut = frame;
    guessedOut = false;
    if (currentIn === null && ghostFrame !== null && ghostFrame < frame) {
      newIn = ghostFrame;
      guessedIn = true;
    }
  } else if (kind === "in") {
    newIn = frame;
    guessedIn = false;
    if (currentOut === null && ghostFrame !== null && ghostFrame > frame) {
      newOut = ghostFrame;
      guessedOut = true;
    }
  }

  return {
    in: newIn,
    out: newOut,
    guessed: {
      in: guessedIn,
      out: guessedOut,
    },
  };
}
