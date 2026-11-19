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
document.getElementById("result").textContent = JSON.stringify(result);
