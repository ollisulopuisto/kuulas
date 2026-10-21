// The History panel's logic, pure: grouping steps by session marker, relative times in
// Helsinki time, paging, selection and the undo notice. history-panel.js only draws.
// Steps come from GET /api/history?limit=&before= (newest first), each with
// { id, label, created (UTC), is_marker, marker ("opened"|"closed"), is_head,
//   side ("head"|"past"|"redo"|"branch") }.

import { filterSteps } from "./history-filter.js";

const ZONE = "Europe/Helsinki";
const MINUTE = 60_000;
const NEAR_BOTTOM = 160; // px from the end of the list at which the next page is fetched

/** Date.parse, reading a time with no zone (SQLite's "2026-10-18 05:00:00") as UTC. */
function utcMs(created) {
  if (typeof created === "number") return created;
  const text = String(created);
  return Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(text) ? text : `${text.replace(" ", "T")}Z`);
}

const parts = (ms, options) =>
  Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", { timeZone: ZONE, hourCycle: "h23", ...options })
      .formatToParts(new Date(ms))
      .map((p) => [p.type, p.value]),
  );

const dayNumber = (ms) => {
  const p = parts(ms, { year: "numeric", month: "2-digit", day: "2-digit" });
  return Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day)) / 86_400_000;
};

/** Calendar days between a UTC time and `now`, counted in Helsinki: 0 today, 1 yesterday. */
export function dayDistance(created, now) {
  return dayNumber(now) - dayNumber(utcMs(created));
}

const clock = (ms) => {
  const p = parts(ms, { hour: "2-digit", minute: "2-digit" });
  return `${p.hour}.${p.minute}`;
};
const shortDate = (ms) => {
  const p = parts(ms, { day: "numeric", month: "numeric" });
  return `${p.day}.${p.month}.`;
};

/** "today 19.30", "yesterday 22.14", "10.10. 10.05": a moment with its day named. */
export function whenText(created, now, t) {
  const ms = utcMs(created);
  const days = dayDistance(ms, now);
  if (days <= 0) return t("ui.history.when.today", { time: clock(ms) });
  if (days === 1) return t("ui.history.when.yesterday", { time: clock(ms) });
  return t("ui.history.when.date", { date: shortDate(ms), time: clock(ms) });
}

/** A step's time: "just now", "20 min ago", "13.42", "yesterday 22.14", "10.10. 10.05". */
export function relativeTime(created, now, t) {
  const ms = utcMs(created);
  const age = now - ms;
  if (age < 45_000) return t("ui.history.just_now");
  if (age < 60 * MINUTE) return t("ui.history.ago_minutes", { count: Math.round(age / MINUTE) });
  if (dayDistance(ms, now) <= 0) return clock(ms);
  return whenText(ms, now, t);
}

/**
 * The step that is the current state: the head, or, when the head is a session marker
 * (opening a project writes one on top), the newest real step under it, whose state is
 * the same. null when there is none in the list.
 */
export function currentStep(nodes, head) {
  const at = nodes.findIndex((node) => node.id === head);
  if (at < 0) return null;
  return nodes.slice(at).find((node) => !node.is_marker)?.id ?? null;
}

const KINDS = new Set(["manual", "sent", "received", "export", "backup"]);

/** A step's saved version as the row shows it: { name, kind, kindLabel }, or null. */
function savedOf(checkpoint, t) {
  if (!checkpoint) return null;
  const known = KINDS.has(checkpoint.kind) ? checkpoint.kind : "manual";
  return {
    name: checkpoint.name,
    kind: checkpoint.kind,
    kindLabel: t(`ui.history.kind.${known}`),
  };
}

/**
 * The nodes to show under the panel's two filters, which combine: the text matches the
 * step's label or its version's name; "saved only" keeps steps that carry a checkpoint
 * (the server already pages only those; this keeps the list right while it catches up).
 * Session markers belong to the whole list, so they go while a filter is on.
 */
export function visibleNodes(nodes, { query = "", savedOnly = false } = {}) {
  const text = typeof query === "string" && query.trim() !== "";
  if (!text && !savedOnly) return nodes;
  let steps = nodes.filter((node) => !node.is_marker);
  if (savedOnly) steps = steps.filter((node) => node.checkpoint);
  if (!text) return steps;
  const named = steps.map((node) => ({
    node,
    label: node.checkpoint ? `${node.label} ${node.checkpoint.name}` : node.label,
  }));
  const kept = new Set(filterSteps(named, query).map((item) => item.node));
  return steps.filter((node) => kept.has(node));
}

/** The message key for an empty list: nothing yet, no saved versions yet, or nothing matches. */
export function emptyKey({ savedOnly = false, query = "" } = {}) {
  if (typeof query === "string" && query.trim() !== "") return "ui.history.empty_match";
  return savedOnly ? "ui.history.empty_saved" : "ui.history.empty";
}

/**
 * The rows to draw, in the order given (newest first). A marker step becomes a thin
 * divider ("Opened today 19.30"); a step is dimmed on the redo side and in an abandoned
 * branch, and a branch step is indented.
 */
export function groupRows(nodes, now, t) {
  const current = currentStep(nodes, nodes.find((node) => node.is_head)?.id);
  return nodes.map((node) => {
    if (node.is_marker) {
      const kind = node.marker === "closed" ? "closed" : "opened";
      return {
        kind: "marker",
        id: node.id,
        text: t(`ui.history.marker.${kind}`, { when: whenText(node.created, now, t) }),
      };
    }
    return {
      kind: "step",
      id: node.id,
      saved: savedOf(node.checkpoint, t),
      label: node.label,
      time: relativeTime(node.created, now, t),
      created: node.created,
      head: node.id === current,
      dimmed: node.side === "redo" || node.side === "branch",
      redo: node.side === "redo",
      indent: node.side === "branch",
    };
  });
}

/** The steps Redo would walk, newest first. */
export const redoSteps = (nodes) => nodes.filter((node) => node.side === "redo");

/**
 * Add a page to the list. A step in both is taken from the page (its place relative to
 * the head may have changed). Newest first, each step once; ids sort by time (UUIDv7),
 * which is the order the server pages in.
 */
export function mergePage(current, page) {
  const byId = new Map(current.map((node) => [node.id, node]));
  for (const node of page) byId.set(node.id, node);
  return [...byId.values()].sort((a, b) => (a.id < b.id ? 1 : a.id > b.id ? -1 : 0));
}

/** Whether the list should fetch its next (older) page: near the bottom, or too short to scroll. */
export function needsMore({ scrollTop, clientHeight, scrollHeight, more, loading }) {
  if (!more || loading) return false;
  return scrollTop + clientHeight >= scrollHeight - NEAR_BOTTOM;
}

const isStep = (node) => !node.is_marker;

/** Which step is picked after the list loaded: the pick if still there, else the current step, else the newest. */
export function selectionAfterLoad(selected, nodes, head) {
  const steps = nodes.filter(isStep);
  if (selected && steps.some((node) => node.id === selected)) return selected;
  const current = currentStep(nodes, head);
  if (current) return current;
  return steps[0]?.id ?? null;
}

/** The next step in `direction` (1 older, -1 newer) skipping markers; stays at the ends. */
export function moveSelection(nodes, selected, direction) {
  const steps = nodes.filter(isStep);
  if (steps.length === 0) return null;
  const at = steps.findIndex((node) => node.id === selected);
  if (at < 0) return steps[0].id;
  return steps[Math.min(steps.length - 1, Math.max(0, at + direction))].id;
}

/** Restore applies to the History panel's pick, unless the pick already is the current state. */
export const canRestore = (state) =>
  state?.panel === "history" &&
  Boolean(state.historySelected) &&
  state.historySelected !== (state.historyCurrent ?? state.head);

/**
 * The toast after an Undo or Redo (the `moved` of the route's answer): only when it
 * passed a session marker, so a step from an earlier sitting is not a surprise.
 */
export function undoNotice(moved, now, t) {
  if (!moved?.crossed_marker || !moved.step) return null;
  const ms = utcMs(moved.step.created);
  const days = dayDistance(ms, now);
  const part = days <= 0 ? "today" : days === 1 ? "yesterday" : "date";
  const verb = moved.direction === "redo" ? "redid" : "undid";
  return t(`ui.history.${verb}.${part}`, { date: shortDate(ms), label: moved.step.label });
}
