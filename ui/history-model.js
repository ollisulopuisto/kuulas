// The History panel's logic, pure: grouping steps by session marker, relative times in
// Helsinki time, paging, selection and the undo notice. history-panel.js only draws.
// Steps come from GET /api/history?limit=&before= (newest first), each with
// { id, label (as stored), name / name_base / name_detail (readable, made by the server),
//   run (key shared by repeated steps on one object), created (UTC), is_marker, marker
//   ("opened"|"closed"), is_head, side ("head"|"past"|"rolled_back"|"redo"|"branch"),
//   rolled_back_by, restore_target, checkpoint }.

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
  // The readable name (what the row shows), the stored label and the version's name.
  const named = steps.map((node) => ({
    node,
    label: [node.name, node.label, node.checkpoint?.name].filter(Boolean).join(" "),
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

// -- the list as drawn: restores, groups and runs -----------------------------------------
//
// Three kinds of step are not part of the current state, each with its own icon and word
// (never colour alone): undone (Redo walks them), rolled back (a Restore skipped them) and
// left behind (an edit after an undo). A run of one kind is one group row: undone opens by
// default (one key away), the others are closed. Consecutive steps that change one setting
// of one object (the server's `run` key) show as one row, for display only.

/** A step's place relative to the current state, as the group kinds name it. */
const DIM = { redo: "undone", rolled_back: "rolled_back", branch: "left_behind" };
const OPEN_BY_DEFAULT = { undone: true, rolled_back: false, left_behind: false, run: false };

const dimOf = (node) => DIM[node.side] ?? null;
const isGroupId = (id) => typeof id === "string" && /^[gr]:/.test(id);

/** The words each kind carries: on the row (title, aria-description) and as a status. */
const dimText = (dim, t) => (dim ? t(`ui.history.dim.${dim}`) : "");
const standsText = (node, t) => t(`ui.history.stands.${dimOf(node) ?? "current"}`);

/** Steps a restore in the current state points at (its target is the restore point). */
function restorePoints(nodes) {
  const points = new Set();
  for (const node of nodes) {
    if (node.restore_target && (node.side === "head" || node.side === "past")) {
      points.add(node.restore_target);
    }
  }
  return points;
}

/** The step a restore row restored, for "Go to restore point"; null for other rows. */
export function restorePointOf(nodes, id) {
  return nodes.find((node) => node.id === id)?.restore_target ?? null;
}

export const canGoToRestorePoint = (state) =>
  state?.panel === "history" && Boolean(state.historyRestoreTarget);

/** A run of steps as one row: "Track settings: Olli ×4 · gain −3.0 dB → gain −9.0 dB". */
function runLabel(members) {
  const newest = members[0];
  const oldest = members[members.length - 1];
  const base = newest.name_base || newest.name || newest.label;
  const to = newest.name_detail || "";
  const from = oldest.name_detail || "";
  const detail = from && to && from !== to ? `${from} → ${to}` : to;
  return `${base} ×${members.length}${detail ? ` · ${detail}` : ""}`;
}

/**
 * Split a list of steps into runs: consecutive steps with one `run` key. The head, a
 * restore point, a saved version and markers never join one, so they stay rows of their own.
 */
function runsOf(nodes, points) {
  const out = [];
  const anchor = (node) =>
    node.is_marker || !node.run || node.side === "head" || points.has(node.id) || node.checkpoint;
  for (const node of nodes) {
    const last = out[out.length - 1];
    if (!anchor(node) && last && !anchor(last[0]) && last[0].run === node.run) last.push(node);
    else out.push([node]);
  }
  return out;
}

/**
 * The rows the History panel draws, newest first. `expanded`: the user's open/closed
 * choice by group id ("g:<kind>:<newest step id>") or run id ("r:<newest step id>"),
 * over the defaults. `savedOnly` or a text `query`: a flat list where every row says
 * where it stands instead (a filter shows hits, not structure).
 *
 * Rows: markers as groupRows makes them; { kind: "group", id, group, count, expanded,
 * text, time, by } for a group; steps with label (the readable name), dim and dimText
 * (null/"" in the current state), parent (the group or run they are inside), restoreTarget,
 * restorePoint, run ({ key, count, expanded } on a run's first row), members (the ids a
 * group or run holds, for "Go to restore point") and stands (filters).
 */
export function historyRows(nodes, now, t, { expanded = {}, savedOnly = false, query = "" } = {}) {
  const flat = groupRows(nodes, now, t);
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const points = restorePoints(nodes);
  const filtered = savedOnly || (typeof query === "string" && query.trim() !== "");
  const stepRow = (row, extra = {}) => {
    const node = byId.get(row.id);
    const dim = dimOf(node);
    return {
      ...row,
      label: node.name || node.label,
      stored: node.label,
      dim,
      dimText: dimText(dim, t),
      parent: null,
      restoreTarget: node.side === "head" || node.side === "past" ? node.restore_target : null,
      restorePoint: points.has(node.id),
      run: null,
      stands: filtered ? standsText(node, t) : "",
      ...extra,
    };
  };
  const rowOf = new Map(flat.map((row) => [row.id, row]));
  if (filtered) return flat.map((row) => (row.kind === "step" ? stepRow(row) : row));

  const open = (id, kind) => expanded[id] ?? OPEN_BY_DEFAULT[kind] ?? true;
  /** Rows for a stretch of steps of one kind: runs collapsed unless opened. */
  const emit = (members, parent) => {
    const out = [];
    for (const run of runsOf(members, points)) {
      const first = run[0];
      if (first.is_marker) {
        out.push({ ...rowOf.get(first.id), parent });
        continue;
      }
      if (run.length === 1) {
        out.push(stepRow(rowOf.get(first.id), { parent }));
        continue;
      }
      const key = `r:${first.id}`;
      const isOpen = open(key, "run");
      const head = { key, count: run.length, expanded: isOpen };
      const members = run.slice(1).map((node) => node.id);
      if (!isOpen) {
        out.push(
          stepRow(rowOf.get(first.id), { parent, run: head, members, label: runLabel(run) }),
        );
        continue;
      }
      out.push(stepRow(rowOf.get(first.id), { parent, run: head, members }));
      for (const node of run.slice(1)) out.push(stepRow(rowOf.get(node.id), { parent: key }));
    }
    return out;
  };

  // Stretches of one kind: consecutive nodes with the same dim (and, rolled back, the same
  // restore). Markers inside a stretch belong to it.
  const stretches = [];
  for (const node of nodes) {
    const dim = dimOf(node);
    const key = dim ? `${dim}:${dim === "rolled_back" ? node.rolled_back_by : ""}` : null;
    const last = stretches[stretches.length - 1];
    if (last && last.key === key) last.nodes.push(node);
    else stretches.push({ key, dim, nodes: [node] });
  }
  const rows = [];
  for (const { dim, nodes: members } of stretches) {
    const steps = members.filter((node) => !node.is_marker);
    if (!dim || steps.length === 0) {
      rows.push(...emit(members, null));
      continue;
    }
    const id = `g:${dim}:${members[0].id}`;
    const isOpen = open(id, dim);
    const newest = rowOf.get(steps[0].id).time;
    const oldest = rowOf.get(steps[steps.length - 1].id).time;
    rows.push({
      kind: "group",
      id,
      group: dim,
      count: steps.length,
      expanded: isOpen,
      text: t(`ui.history.group.${dim}`, { count: steps.length }),
      dimText: dimText(dim, t),
      time: newest === oldest ? newest : `${oldest}–${newest}`,
      by: dim === "rolled_back" ? (steps[0].rolled_back_by ?? null) : null,
      members: members.map((node) => node.id),
    });
    if (isOpen) rows.push(...emit(members, id));
  }
  return rows;
}

/** The ids of every group and run in the list, open; or {} (the defaults) when all are. */
export function expandAllMap(nodes, now, t, expanded = {}) {
  const all = {};
  let closed = false;
  // Open everything, then read what exists (runs inside closed groups appear once open).
  for (let pass = 0; pass < 3; pass++) {
    for (const row of historyRows(nodes, now, t, { expanded: { ...expanded, ...all } })) {
      const id = row.kind === "group" ? row.id : row.run?.key;
      if (!id) continue;
      if (!(row.kind === "group" ? row.expanded : row.run.expanded) && !all[id]) closed = true;
      all[id] = true;
    }
  }
  return closed ? all : {};
}

/** The next drawn row in `direction` (1 older, -1 newer), markers skipped; stays at the ends. */
export function moveRow(rows, selected, direction) {
  const picks = rows.filter((row) => row.kind !== "marker");
  if (picks.length === 0) return null;
  const at = picks.findIndex((row) => row.id === selected);
  if (at < 0) return picks[0].id;
  return picks[Math.min(picks.length - 1, Math.max(0, at + direction))].id;
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
  !isGroupId(state.historySelected) &&
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
