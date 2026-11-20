import { createBlockLevelPanel } from "../../block-level-panel.js";
import { initI18n, t } from "../../i18n.js";
import { installIcons } from "../../icons.js";

await initI18n({ language: "fi" });
installIcons();
const measured = {
  key: "fixture",
  rate: 48000,
  threshold_db: 3,
  max_cut_db: 18,
  max_boost_db: 6,
  speakers: [],
};
for (let s = 0; s < 3; s++) {
  const blocks = [];
  for (let i = 0; i < 8; i++)
    blocks.push({
      id: `${s}:${i}`,
      start: (i * 120 + s * 5) * 48000,
      end: (i * 120 + 30 + s * 5) * 48000,
      gain_db: i % 3 === 0 ? 0 : i % 2 === 0 ? 4 : -8,
      level_db: -24,
      deviation_db: i % 3 === 0 ? 0 : i % 2 === 0 ? -4 : 8,
    });
  measured.speakers.push({
    name: ["Olli", "2026-11-19-t03-04-25pm-guest232006--panu", "Kolmas puhuja"][s],
    track_ids: [`t${s}`],
    blocks,
    loud: [{ start: 3 * 48000, end: 4 * 48000, excess_db: 8 }],
  });
}
if (new URLSearchParams(location.search).has("visual")) {
  measured.speakers[0].blocks[2].gain_db = 6;
  measured.speakers[0].blocks[2].deviation_db = -10;
}
// ?nochange=a: the first speaker has no changes, one other has exactly one.
// ?nochange=b: nothing changes anywhere (owner sketch, 2026-11-20).
const nochange = new URLSearchParams(location.search).get("nochange");
if (nochange === "a") {
  for (const block of measured.speakers[0].blocks) {
    block.gain_db = 0;
    block.deviation_db = 1;
  }
  for (const [i, block] of measured.speakers[1].blocks.entries())
    if (i !== 1) {
      block.gain_db = 0;
      block.deviation_db = 0;
    }
  for (const block of measured.speakers[2].blocks) {
    block.gain_db = 0;
    block.deviation_db = -2;
  }
} else if (nochange === "b") {
  for (const speaker of measured.speakers)
    for (const block of speaker.blocks) {
      block.gain_db = 0;
      block.deviation_db = 1;
    }
}
let applied = null;
const listened = [],
  jumped = [];
const root = document.querySelector("section");
const panel = createBlockLevelPanel({
  root,
  t,
  fmt: (v) => v.toFixed(1).replace(".", ","),
  clock: (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`,
  api: {
    blockLevelMeasure: async () => ({ jobs: ["j"] }),
    getJobs: async () => ({ jobs: [{ id: "j", state: "completed", result: measured }] }),
    cancelJob: async () => {},
  },
  getRange: () => ({ start: 120 * 48000, end: 400 * 48000 }),
  onApply: (args) => {
    applied = args;
  },
  onListen: (r) => listened.push(r.id),
  onJump: (r) => jumped.push(r.id),
});
panel.open();
await new Promise((resolve) => setTimeout(resolve, 20));
const result = {};
const tabs = [...root.querySelectorAll(".block-speaker-tab")];
result.speakerTabs = tabs.length;
const referenceToggle = document.createElement("button");
referenceToggle.className = "button";
referenceToggle.setAttribute("aria-pressed", "true");
root.append(referenceToggle);
const selectedTab = tabs.find((tab) => tab.getAttribute("aria-pressed") === "true");
result.sharedToggleColors =
  selectedTab &&
  ["backgroundColor", "borderTopColor", "color"].every(
    (property) =>
      getComputedStyle(selectedTab)[property] === getComputedStyle(referenceToggle)[property],
  );
referenceToggle.remove();
result.oneSpeaker = [...root.querySelectorAll(".block-overview-speaker")].filter(
  (n) => !n.hidden,
).length;
result.ownZero = root.textContent.includes("oma vertailutaso = 0");
result.estimate = root.querySelector(".block-speaker-after")?.textContent;
result.countedApply = root.querySelector(".primary").textContent;
if (tabs[1]) {
  tabs[1].click();
  result.switchedSpeaker = root.querySelector(".block-speaker-tab[aria-pressed=true]")?.textContent;
  result.hiddenPrevious = root.querySelector(".block-overview-speaker").hidden;
  tabs[0].click();
}
result.bars = root.querySelectorAll(".block-overview-bar").length;
result.closedList = !root.querySelector(".block-overview-list").open;
result.legend = root.querySelector(".block-overview-legend").textContent;
result.help = root.textContent.includes("eivät laatua");
if (nochange) {
  const active = root.querySelector(".block-overview-speaker:not([hidden])");
  const card = active.querySelector(".block-speaker-nochange");
  result.cardVisible = !card.hidden;
  result.cardTitle = card.querySelector(".block-speaker-nochange-title").textContent;
  result.cardSpan = card.querySelector(".block-speaker-nochange-span").textContent;
  result.beforeHidden = active.querySelector(".block-speaker-before").hidden;
  result.afterHidden = active.querySelector(".block-speaker-after").hidden;
  result.countHidden = active.querySelector(".block-speaker-count").hidden;
  result.leftHidden = active.querySelector(".block-speaker-left").hidden;
  result.graphHidden = active.querySelector(".block-overview-strip").hidden;
  result.legendHidden = root.querySelector(".block-overview-legend").hidden;
  result.footer = root.querySelector(".block-level-total").textContent;
  const applyButton = root.querySelector(".actionbar [data-icon=check]");
  const againButton = root.querySelector(".actionbar [data-icon=reset]");
  result.applyText = applyButton.textContent;
  result.applyDisabled = applyButton.disabled;
  result.applyPrimary = applyButton.classList.contains("primary");
  result.againPrimary = againButton.classList.contains("primary");
  result.primaryLast = [...root.querySelectorAll(".actionbar .button")]
    .at(-1)
    .classList.contains("primary");
  const otherLink = active.querySelector(".block-speaker-other");
  result.otherLink = otherLink?.textContent ?? null;
  if (otherLink) {
    otherLink.click();
    const target = root.querySelector(".block-speaker-tab[aria-pressed=true]");
    result.linkActivated = target?.textContent;
    const targetSection = root.querySelector(".block-overview-speaker:not([hidden])");
    result.linkTargetCardHidden = targetSection.querySelector(".block-speaker-nochange").hidden;
    result.linkTargetCount = targetSection.querySelector(".block-speaker-count").textContent;
  }
  if (new URLSearchParams(location.search).has("shot")) {
    document.getElementById("result").hidden = true;
    root.querySelector(".block-speaker-tab").click();
  }
} else {
  const bar = root.querySelector(".block-overview-bar");
  bar.click();
  result.detail = root.querySelector(".block-overview-detail").textContent;
  root.querySelector(".block-overview-detail .form-actions button").click();
  root.querySelectorAll(".block-overview-detail .form-actions button")[1].click();
  result.listened = listened;
  result.jumped = jumped;
  const include = root.querySelector(".block-overview-detail input");
  include.click();
  result.excluded = bar.dataset.included === "false";
  result.afterExclusion = root.querySelector(".block-speaker-after").textContent;
  result.footerAfterExclusion = root.querySelector(".primary").textContent;
  result.leftAfterExclusion = root.querySelector(".block-speaker-left").textContent;
  const number = root.querySelector("input[type=number]");
  number.value = "6";
  number.dispatchEvent(new Event("input"));
  result.liftDisabled = [...root.querySelectorAll(".is-lift")].every((n) => n.disabled);
  number.value = "3";
  number.dispatchEvent(new Event("input"));
  result.manualExclusionKept = bar.dataset.included === "false";
  const select = root.querySelector("select");
  select.value = "range";
  select.dispatchEvent(new Event("change"));
  result.enabledInRange = [...root.querySelectorAll(".block-overview-bar")].filter(
    (n) => !n.disabled,
  ).length;
  if (new URLSearchParams(location.search).has("visual")) {
    document.getElementById("result").hidden = true;
    panel.close();
    panel.open();
    await new Promise((resolve) => setTimeout(resolve, 20));
    root.querySelector(":scope > .form-grid").scrollTop = 0;
    if (new URLSearchParams(location.search).has("detail"))
      root.querySelector(".block-overview-bar").click();
  } else if (new URLSearchParams(location.search).has("filtered")) {
    root.querySelector(".primary").click();
    result.applied = applied;
  } else {
    panel.projectChanged();
    number.value = "6";
    number.dispatchEvent(new Event("input"));
    result.staleApplyDisabled = root.querySelector(".primary").disabled;
    panel.close();
    panel.open();
    await new Promise((resolve) => setTimeout(resolve, 20));
    root.querySelector(".primary").click();
    result.applied = applied;
    result.closedAfterApply = !panel.isOpen();
  }
}
document.getElementById("result").textContent = JSON.stringify(result);
