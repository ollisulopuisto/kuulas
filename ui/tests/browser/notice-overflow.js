// The automix result notice (owner, 2026-11-19: the buttons sat outside the
// panel): a long export path must wrap and the action buttons stay inside.
const notice = document.getElementById("notice");
document.getElementById("notice-text").textContent =
  "Miksattu automixerilla: /Users/dst/Dropbox/podcastit/vikasietotila/pikis/pikis" +
  " 2026-11-19/pikis 2026-11-19 automixer 2026-11-19 18-23-58.wav — Musiikki 4: gain_db" +
  " -18.4 is the track fader and is not applied (as in a session) · [automixer] 56 places" +
  " to listen to → /Users/dst/Dropbox/podcastit/vikasietotila/pikis/pikis" +
  " 2026-11-19/pikis 2026-11-19 automixer 2026-11-19 18-23-58.partial flags.txt ·" +
  " [automixer] beds: loudest -28.3 LUFS, speech -23.9 → beds +0.4 dB (loudest moment" +
  " -4.0 dB from the speech) · [automixer] mastered: -16.5 LUFS, lift +9.3 dB, limiting" +
  " 1.7 LU → /Users/dst/Dropbox/podcastit/vikasietotila/pikis/pikis" +
  " 2026-11-19/pikis 2026-11-19 automixer 2026-11-19 18-23-58.partial.wav";
const out = {};
const panel = notice.getBoundingClientRect();
for (const id of ["notice-action", "notice-action2", "notice-close"]) {
  out[id] = Math.round(document.getElementById(id).getBoundingClientRect().right - panel.right);
}
out.panelRight = Math.round(panel.right);
out.stageWidth = Math.round(document.querySelector(".stage").getBoundingClientRect().width);
document.getElementById("result").textContent = JSON.stringify(out);
