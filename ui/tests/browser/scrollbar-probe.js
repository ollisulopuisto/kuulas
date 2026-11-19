import { scrollThumb } from "/lane-sizing.js";

document.documentElement.dataset.theme =
  new URLSearchParams(location.search).get("theme") ?? "dark";
const c = document.getElementById("wave"),
  ctx = c.getContext("2d");
ctx.fillStyle = "#667fa4";
ctx.fillRect(0, 0, 800, 400);
for (let y = 0; y < 400; y += 8) {
  ctx.fillStyle = "#17202d";
  ctx.fillRect(0, y, 800, 3);
}
const bar = document.getElementById("lanes-scroll"),
  thumb = bar.firstElementChild;
const view = 400 - parseFloat(getComputedStyle(bar).top);
const geometry = scrollThumb({
  contentHeight: 900,
  viewHeight: view,
  scrollY: 0,
});
Object.assign(thumb.style, {
  top: geometry.top + "px",
  height: geometry.height + "px",
});
const heads = document.getElementById("track-headers");
heads.scrollTop = 100;
const r = thumb.getBoundingClientRect();
document.getElementById("result").textContent = JSON.stringify({
  scrollY: heads.scrollTop,
  thumb: { x: r.x, y: r.y, width: r.width, height: r.height },
  rail: {
    x: bar.getBoundingClientRect().x,
    width: bar.getBoundingClientRect().width,
    zIndex: Number(getComputedStyle(bar).zIndex),
    background: getComputedStyle(bar).backgroundColor,
  },
  nativeScrollbar: getComputedStyle(heads).scrollbarWidth,
});
