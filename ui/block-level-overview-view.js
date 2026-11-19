// The approved compact overview (owner, 2026-11-19). Bars are proposed gain
// changes, not quality scores; the detailed list remains available on demand.
import { blockText } from "./block-level-model.js";
import {
  eligibleBlockIds,
  overviewScale,
  overviewSpeakers,
  speakerSummary,
} from "./block-level-overview.js";

const el = (tag, className = "", text) => {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
export function createBlockOverview({
  host,
  measured,
  ticked,
  t,
  fmt,
  clock,
  range = null,
  onChange,
  onListen,
  onJump,
}) {
  const speakers = overviewSpeakers(measured);
  const scale = overviewScale(measured);
  const skipped = new Set();
  const bars = new Map();
  const boxes = new Map();
  const groupBoxes = [];
  let selected = null;
  const summaries = new Map();
  const panels = new Map();
  const tabButtons = new Map();
  let activeSpeaker = speakers[0];
  const tabs = el("div", "block-speaker-tabs");
  tabs.setAttribute("role", "group");
  tabs.setAttribute("aria-label", t("ui.block_level.speakers"));
  host.append(tabs);
  let eligible = eligibleBlockIds(measured);
  const describe = (row) => blockText(row, measured.rate, t, fmt, clock);
  const controls = el("div", "block-overview-controls");
  const scopeLabel = el("label", "form-field", t("ui.block_level.scope"));
  const scope = el("select", "form-select");
  const all = el("option", "", t("ui.block_level.whole"));
  all.value = "all";
  const marked = el(
    "option",
    "",
    range
      ? t("ui.block_level.marked", {
          start: clock(range.start / measured.rate),
          end: clock(range.end / measured.rate),
        })
      : t("ui.block_level.no_range"),
  );
  marked.value = "range";
  marked.disabled = !range;
  scope.append(all, marked);
  scopeLabel.append(scope);
  const thresholdLabel = el("label", "form-field", t("ui.block_level.minimum"));
  const threshold = el("input", "form-num");
  threshold.type = "number";
  threshold.min = String(measured.threshold_db);
  threshold.max = "60";
  threshold.step = "0.5";
  threshold.value = String(measured.threshold_db);
  thresholdLabel.append(threshold);
  controls.append(scopeLabel, thresholdLabel);
  const filterHelp = el("details", "block-overview-filter-help");
  filterHelp.append(
    el("summary", "", t("ui.block_level.filter_explain")),
    el("p", "form-help", t("ui.block_level.filter_hint")),
  );
  const filters = el("details", "block-overview-list block-overview-filters");
  filters.append(el("summary", "", t("ui.block_level.filters")), controls, filterHelp);
  const legend = el("p", "block-overview-legend");
  legend.append(
    el("span", "block-overview-lift", t("ui.block_level.lift")),
    el("span", "block-overview-cut", t("ui.block_level.cut")),
  );
  const help = el("p", "form-help", t("ui.block_level.graph_help"));
  legend.append(el("span", "", `±${fmt(scale.gain)} dB`));

  const plots = el("div", "block-overview-plots");
  const detail = el("div", "block-overview-detail");
  detail.setAttribute("aria-live", "polite");
  detail.textContent = t("ui.block_level.pick");
  host.append(plots, legend, help, detail, filters);
  const details = el("details", "block-overview-list");
  details.append(el("summary", "", t("ui.block_level.details")));
  const list = el("div", "form-grid");
  details.append(list);
  host.append(details);
  function sync() {
    for (const [id, bar] of bars) {
      bar.dataset.included = String(ticked.has(id));
      bar.dataset.selected = String(selected?.id === id);
      bar.setAttribute("aria-pressed", String(selected?.id === id));
      bar.disabled = !eligible.has(id);
    }
    for (const [id, box] of boxes) {
      box.checked = ticked.has(id);
      box.disabled = !eligible.has(id);
    }
    for (const [box, rows] of groupBoxes) {
      const active = rows.filter((row) => eligible.has(row.id));
      const count = active.filter((row) => ticked.has(row.id)).length;
      box.checked = active.length > 0 && count === active.length;
      box.indeterminate = count > 0 && count < active.length;
      box.disabled = active.length === 0;
    }
    for (const [speaker, nodes] of summaries) {
      const view = speakerSummary(speaker, ticked, measured);
      const span = (key, values) =>
        values
          ? t(`ui.block_level.${key}`, { low: signed(values[0]), high: signed(values[1]) })
          : t("ui.block_level.no_span");
      nodes.before.textContent = span("before_span", view.before);
      nodes.after.textContent = span("after_span", view.after);
      nodes.count.textContent = t("ui.block_level.change_count", { count: view.blocks });
      nodes.extremes.textContent = t("ui.block_level.gain_extremes", {
        lift: fmt(view.lift),
        cut: fmt(view.cut),
      });
      nodes.warning.hidden = view.limited === 0;
      nodes.warning.textContent = t("ui.block_level.limit_warning", {
        count: view.limited,
        boost: fmt(measured.max_boost_db),
        cut: fmt(measured.max_cut_db),
      });
      nodes.left.textContent = t("ui.block_level.left_count", { count: view.leftOut });
    }
    onChange();
  }
  const signed = (value) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${fmt(Math.abs(value))}`;
  function activate(speaker) {
    activeSpeaker = speaker;
    for (const [owner, panel] of panels) panel.hidden = owner !== speaker;
    for (const [owner, button] of tabButtons)
      button.setAttribute("aria-pressed", String(owner === speaker));
    selected = null;
    detail.textContent = t("ui.block_level.pick");
    sync();
  }
  function include(row, yes) {
    if (yes && eligible.has(row.id)) {
      ticked.add(row.id);
      skipped.delete(row.id);
    } else {
      ticked.delete(row.id);
      skipped.add(row.id);
    }
  }
  function pick(speaker, row) {
    if (activeSpeaker !== speaker) activate(speaker);
    selected = row;
    detail.replaceChildren(
      el(
        "strong",
        "",
        `${speaker.name} · ${clock(row.start / measured.rate)}–${clock(row.end / measured.rate)}`,
      ),
    );
    detail.append(
      el(
        "p",
        "",
        t(row.gain_db > 0 ? "ui.block_level.lift_amount" : "ui.block_level.cut_amount", {
          gain: fmt(Math.abs(row.gain_db)),
        }),
      ),
    );
    detail.append(el("p", "form-help", describe(row)));
    const label = el("label", "check-row");
    const box = el("input");
    box.type = "checkbox";
    box.checked = ticked.has(row.id);
    box.disabled = !eligible.has(row.id);
    box.addEventListener("change", () => {
      include(row, box.checked);
      sync();
    });
    label.append(box, el("span", "", t("ui.block_level.include")));
    detail.append(label);
    const actions = el("div", "form-actions");
    for (const [key, action] of [
      ["listen", onListen],
      ["jump", onJump],
    ]) {
      if (!action) continue;
      const button = el("button", "button", t(`ui.block_level.${key}`));
      button.type = "button";
      button.addEventListener("click", () => action({ ...row, track_ids: speaker.track_ids }));
      actions.append(button);
    }
    detail.append(actions, el("p", "form-help", t("ui.block_level.listen_hint")));
    sync();
  }
  for (const speaker of speakers) {
    const section = el("section", "block-overview-speaker");
    panels.set(speaker, section);
    section.hidden = speaker !== activeSpeaker;
    const tab = el("button", "button block-speaker-tab", speaker.name);
    tab.type = "button";
    tab.title = speaker.name;
    tab.setAttribute("aria-pressed", String(speaker === activeSpeaker));
    tab.addEventListener("click", () => activate(speaker));
    tabButtons.set(speaker, tab);
    tabs.append(tab);
    const summary = el("div", "block-speaker-summary");
    const before = el("p", "block-speaker-before");
    const after = el("p", "block-speaker-after");
    const count = el("p", "block-speaker-count");
    const extremes = el("p", "block-speaker-extremes");
    const warning = el("p", "block-speaker-warning");
    const left = el("p", "block-speaker-left");
    left.title = t("ui.block_level.left_hint");
    const explanation = el("details", "block-overview-filter-help");
    explanation.append(
      el("summary", "", t("ui.block_level.estimate_more")),
      el("p", "form-help", t("ui.block_level.estimate_hint")),
    );
    summary.append(
      el("p", "block-speaker-zero", t("ui.block_level.own_zero")),
      before,
      after,
      explanation,
      count,
      extremes,
      warning,
      left,
    );
    summaries.set(speaker, { before, after, count, extremes, warning, left });
    section.append(summary);
    const header = el("div", "block-overview-speaker-head");
    const speakerName = el("strong", "", t("ui.block_level.gain_strip"));
    speakerName.title = speaker.name;
    header.append(speakerName);
    const label = el("label", "check-row");
    const box = el("input");
    box.type = "checkbox";
    label.append(
      box,
      el("span", "", t("ui.block_level.all_blocks", { count: speaker.rows.length })),
    );
    groupBoxes.push([box, speaker.rows]);
    box.addEventListener("change", () => {
      for (const row of speaker.rows) if (eligible.has(row.id)) include(row, box.checked);
      sync();
      if (selected) {
        const owner = speakers.find((s) => s.rows.includes(selected));
        pick(owner, selected);
      }
    });
    header.append(label);
    section.append(header);
    const strip = el("div", "block-overview-strip");
    strip.setAttribute("role", "group");
    strip.setAttribute("aria-label", speaker.name);
    for (const row of speaker.rows) {
      const bar = el("button", `block-overview-bar ${row.gain_db > 0 ? "is-lift" : "is-cut"}`);
      bar.type = "button";
      bar.title = `${describe(row)}. ${t("ui.block_level.graph_help")}`;
      bar.setAttribute("aria-label", describe(row));
      bar.style.left = `${(100 * row.start) / scale.end}%`;
      bar.style.width = `${(100 * (row.end - row.start)) / scale.end}%`;
      bar.style.height = `${Math.max(8, (46 * Math.abs(row.gain_db)) / scale.gain)}%`;
      bar.addEventListener("click", () => {
        pick(speaker, row);
        detail.scrollIntoView({ block: "nearest" });
      });
      bars.set(row.id, bar);
      strip.append(bar);
    }
    section.append(strip);
    const axis = el("div", "block-overview-axis");
    axis.append(
      el("span", "", clock(0)),
      el("span", "", clock(scale.end / measured.rate / 2)),
      el("span", "", clock(scale.end / measured.rate)),
    );
    section.append(axis);
    plots.append(section);
    const field = el("fieldset", "form-fieldset");
    field.append(el("legend", "form-label", speaker.name));
    const choices = el("div", "form-choices");
    for (const row of speaker.rows) {
      const choice = el("label", "form-choice block-level-choice");
      const box = el("input");
      box.type = "checkbox";
      box.addEventListener("change", () => {
        include(row, box.checked);
        sync();
        if (selected?.id === row.id) pick(speaker, row);
      });
      boxes.set(row.id, box);
      choice.append(box, el("span", "block-level-line", describe(row)));
      choices.append(choice);
    }
    field.append(choices);
    list.append(field);
  }
  function filter() {
    const value = threshold.valueAsNumber;
    const valid = Number.isFinite(value) && value >= measured.threshold_db && value <= 60;
    threshold.setAttribute("aria-invalid", String(!valid));
    eligible = valid
      ? eligibleBlockIds(measured, {
          threshold: value,
          range: scope.value === "range" ? range : null,
        })
      : new Set();
    ticked.clear();
    for (const id of eligible) if (!skipped.has(id)) ticked.add(id);
    selected = null;
    detail.textContent = t("ui.block_level.pick");
    sync();
  }
  scope.addEventListener("change", filter);
  threshold.addEventListener("input", filter);
  sync();
}
