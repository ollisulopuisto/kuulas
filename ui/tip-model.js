// Tooltip state machine and placement (WP48). Pure logic, no DOM.

export const DELAY_MS = 600;

export const INITIAL_TIP = {
  phase: "idle",
  target: null,
  since: 0,
  suppressed: null,
};

/**
 * Reducer for tooltip state.
 *
 * @param {{ phase: "idle" | "pending" | "shown", target: string | null, since: number, suppressed: string | null }} state
 * @param {{ type: "enter" | "leave" | "press" | "tick", target?: string, now: number }} event
 * @returns {{ phase: "idle" | "pending" | "shown", target: string | null, since: number, suppressed: string | null }}
 */
export function tipReduce(state, event) {
  switch (event.type) {
    case "enter": {
      const { target, now } = event;
      if (target === state.suppressed) {
        return { ...state };
      }
      if (state.phase === "shown" && target !== state.target) {
        return {
          phase: "shown",
          target,
          since: now,
          suppressed: state.suppressed,
        };
      }
      if (target !== state.target) {
        return {
          phase: "pending",
          target,
          since: now,
          suppressed: state.suppressed,
        };
      }
      return { ...state };
    }

    case "tick": {
      if (state.phase === "pending" && event.now - state.since >= DELAY_MS) {
        return { ...state, phase: "shown" };
      }
      return { ...state };
    }

    case "leave": {
      const suppressed = event.target === state.suppressed ? null : state.suppressed;
      if (event.target === state.target) {
        return {
          phase: "idle",
          target: null,
          since: event.now,
          suppressed,
        };
      }
      return { ...state, suppressed };
    }

    case "press": {
      if (event.target === state.target) {
        return {
          phase: "idle",
          target: null,
          since: event.now,
          suppressed: event.target,
        };
      }
      return { ...state };
    }

    default:
      return { ...state };
  }
}

/**
 * Returns formatted tooltip text combining hint with keyboard shortcuts.
 *
 * @param {string} hint
 * @param {string[]} [keys]
 * @returns {string}
 */
export function tipText(hint, keys) {
  if (typeof hint !== "string") return "";
  const trimmed = hint.trim();
  if (!trimmed) return "";
  if (!keys || !Array.isArray(keys) || keys.length === 0) {
    return trimmed;
  }
  return `${trimmed} (${keys.join(", ")})`;
}

/**
 * Places tooltip below or above anchor, clamped to viewport.
 *
 * @param {{ x: number, y: number, width: number, height: number }} anchor
 * @param {{ width: number, height: number }} size
 * @param {{ width: number, height: number }} viewport
 * @param {number} [gap=6]
 * @returns {{ x: number, y: number, side: "below" | "above" }}
 */
export function placeTip(anchor, size, viewport, gap = 6) {
  const belowY = anchor.y + anchor.height + gap;
  const aboveY = anchor.y - size.height - gap;
  const fitsBelow = belowY + size.height <= viewport.height - gap;

  const centerX = anchor.x + (anchor.width - size.width) / 2;
  const minX = gap;
  const maxX = Math.max(gap, viewport.width - size.width - gap);
  const clampedX = Math.min(maxX, Math.max(minX, centerX));

  return {
    x: clampedX,
    y: fitsBelow ? belowY : aboveY,
    side: fitsBelow ? "below" : "above",
  };
}
